#!/usr/bin/env python3
"""
nis_kline.py - read-only Nissan K-line client for the 2013-2015 Frontier VQ40 ECM (DH1 family).

Talks to the K-line bridge in firmware/d40_kline/d40_kline.ino (Teensy 4.1, third USB
serial port). The protocol layer ports fenugrec's nisprog / freediag ISO 14230 code:

  fast init           bus idle >= 300 ms, K low 25 ms, K high 25 ms, then immediately
  startCommunication  81 10 FC 81 <cks>                      -> C1 <KB1> <KB2>
  readECUID           1A 81                                    -> 5A 31 <5 characters>
  memory read         AC 81 83 <addr32> ... (max 12 addresses) -> EC 81
                      21 81 04 01                              -> 61 81 <one byte per address>
                      (nisprog's no-kernel "dumpmem" path: about 7.5 bus bytes per data byte,
                      so a full ROM takes hours, not minutes)

Frame: [format][target][source][data][checksum], checksum = 8-bit sum of every preceding
byte. format = 0x80 | length when addresses are present, or just the length for the short
header nisprog switches to once the ECU says it supports one. Length is 6 bits, so at most
63 data bytes per frame.

READ-ONLY: only services 81 (start/stop communication), 1A, AC and 21 are ever sent.

Usage (third Teensy serial port):
  python3 nis_kline.py --port /dev/ttyACM2 status
  python3 nis_kline.py --port /dev/ttyACM2 selftest             # converter loop-back, no ECM needed
  python3 nis_kline.py --port /dev/ttyACM2 info                 # init + ECU ID
  python3 nis_kline.py --port /dev/ttyACM2 read 0 64
  python3 nis_kline.py --port /dev/ttyACM2 dump ecu_rom.bin 0 0x180000
  python3 nis_kline.py --port /dev/ttyACM2 stop
"""
import argparse
import os
import signal
import sys
import time

import serial

TARGET = 0x10          # nisprog default destaddr
TESTER = 0xFC          # nisprog default testerid
BAUD = 10400
KB_FMTLEN, KB_LENBYTE, KB_SHORTHDR, KB_LONGHDR = 0x01, 0x02, 0x04, 0x08
SID_ECUID, SID_AC, SID_RDBLI = 0x1A, 0xAC, 0x21
SID_STARTCOMM, SID_STOPCOMM = 0x81, 0x82
RC_STARTCOMM, RC_STOPCOMM, RC_NEG = 0xC1, 0xC2, 0x7F
NRC_BUSY, NRC_PENDING = 0x21, 0x78
P2E_S = 5.5            # responsePending allowance (ISO 14230 P2E max is 5 s)
ADDRESSES_PER_REQUEST = 12   # 2 + 5 x 12 = 62 data bytes, the most a 6-bit length allows

NRC = {
    0x10: "general reject", 0x11: "service not supported", 0x12: "sub-function not supported",
    0x13: "wrong message length or format", 0x14: "response too long",
    0x21: "busy, repeat request", 0x22: "conditions not correct", 0x24: "request sequence error",
    0x31: "request out of range", 0x33: "security access denied", 0x35: "invalid key",
    0x36: "too many attempts", 0x37: "time delay not expired", 0x72: "programming failure",
    0x78: "response pending", 0x92: "voltage too high", 0x93: "voltage too low",
}


class KlineError(Exception):
    """Protocol-level failure."""


class NoResponse(KlineError):
    def __init__(self, code):
        self.code = code
        text = {
            1: "no response from the ECU",
            3: "no response, and the K-line read LOW before transmitting "
               "(the converter does not see the idle line as high)",
        }.get(code, f"bridge error {code}")
        super().__init__(text)


# ---- framing (pure functions; freediag diag_l2_iso14230.c flavour) ----

def build_frame(data, short, target=TARGET, tester=TESTER):
    if not 1 <= len(data) <= 63:
        raise ValueError("a frame carries 1..63 data bytes")
    body = bytes([len(data)]) + data if short else bytes([0x80 | len(data), target, tester]) + data
    return body + bytes([sum(body) & 0xFF])


def _frame_at(raw, i):
    """Frame starting at raw[i]: (payload, checksum_ok, total_length); "partial" when the
    header is valid but the frame is cut short; None when the byte cannot start a frame."""
    fmt = raw[i]
    if fmt == 0x00:
        return None                  # never a frame start here (would need a length byte format)
    kind, dl = fmt & 0xC0, fmt & 0x3F
    if dl == 0:
        if kind in (0x80, 0xC0):
            if i + 4 > len(raw):
                return None
            hdr, dl = 4, raw[i + 3]
        elif kind == 0x00:
            if i + 2 > len(raw):
                return None
            hdr, dl = 2, raw[i + 1]
        else:
            return None
    else:
        hdr = 3 if kind in (0x80, 0xC0) else 1 if kind == 0x00 else None
        if hdr is None:
            return None
    if dl == 0:
        return None
    total = hdr + dl + 1
    if i + total > len(raw):
        return "partial"
    frame = raw[i:i + total]
    return frame[hdr:hdr + dl], (sum(frame[:-1]) & 0xFF) == frame[-1], total


def decode_frames(raw):
    """Split wire bytes into (payload, checksum_ok) frames. Bytes that do not begin a
    frame are skipped (a stray break byte can precede a reply); a frame that arrives
    cut short is returned with the bytes received so far and checksum_ok False."""
    out, i = [], 0
    while i < len(raw):
        f = _frame_at(raw, i)
        if f == "partial":
            if i == 0:
                out.append((raw, False))
            break
        if f is None:
            i += 1
            continue
        if not f[1]:
            # misaligned? look a few bytes ahead for a clean start before giving up
            for j in range(i + 1, min(i + 9, len(raw))):
                g = _frame_at(raw, j)
                if isinstance(g, tuple) and g[1]:
                    f = None
                    i = j
                    break
            if f is None:
                continue
            end = i + f[2] if i + f[2] <= len(raw) else len(raw)
            out.append((raw[i:end], False))
            i = end
            continue
        out.append((f[0], True))
        i += f[2]
    return out


def describe(payload):
    if payload[:1] == b"\x7f" and len(payload) >= 3:
        return f"negative response {payload.hex(' ')} ({NRC.get(payload[2], 'unknown code')})"
    return payload.hex(" ")


# ---- bridge (the Teensy firmware) ----

class Bridge:
    def __init__(self, port):
        self.ser = serial.Serial(port, 115200, timeout=0.05, write_timeout=1.0)
        time.sleep(0.2)
        self.ser.reset_input_buffer()

    def close(self):
        self.ser.close()

    def raw(self, line, timeout=1.5):
        """One command; returns the reply up to CR (no error translation)."""
        self.ser.reset_input_buffer()
        self.ser.write((line + "\r").encode())
        end = time.monotonic() + timeout
        buf = bytearray()
        while True:
            buf += self.ser.read(256)
            if b"\r" in buf:
                return bytes(buf).split(b"\r", 1)[0]
            if time.monotonic() > end:
                raise KlineError(f"the bridge did not answer {line!r} (is the right port set?)")

    def cmd(self, line, timeout=1.5):
        r = self.raw(line, timeout)
        if r.startswith(b"E"):
            raise NoResponse(int(r[1:3]))
        return r


# ---- Nissan protocol ----

class NisKline:
    def __init__(self, bridge, verbose=False):
        self.b = bridge
        self.verbose = verbose
        self.use_short = False
        self.kb1 = self.kb2 = None
        self.exchanges = 0

    def xchg(self, frame, init=False):
        """Send one ready-built frame (None = listen only); raw reply bytes, b'' if none."""
        if frame is None:
            cmd, timeout = "R", 0.5
        else:
            # 300 ms idle + 50 ms wake-up for init; P3 + wire time + first-byte wait + gap otherwise
            budget = (350 if init else 5) + (len(frame) + 400) * 10.0 * 1000 / BAUD + 60 + 23 + 400
            cmd, timeout = ("I" if init else "T") + frame.hex().upper(), budget / 1000.0
        try:
            r = self.b.cmd(cmd, timeout)
        except NoResponse:
            self.exchanges += 1
            return b""
        self.exchanges += 1
        if r.startswith(b"E"):
            raise NoResponse(int(r[1:3]))
        if not r.startswith(b"R"):
            raise KlineError(f"unexpected bridge reply {r!r}")
        return bytes.fromhex(r[1:].decode("ascii"))

    def drain(self):
        try:
            self.b.raw("R", 0.5)
        except KlineError:
            pass

    def fast_init(self):
        self.use_short = False
        payload = self._one(build_frame(bytes([SID_STARTCOMM]), False), init=True)
        if payload[0] != RC_STARTCOMM:
            raise KlineError("startCommunication refused: " + describe(payload))
        self.kb1, self.kb2 = payload[1], payload[2]
        # as nisprog: once the ECU offers a short header, use it and nothing else
        self.use_short = bool(self.kb1 & KB_SHORTHDR)
        self.drain()
        return self.kb1, self.kb2

    def _one(self, frame, init=False):
        """Single request/response, with busy and pending handling."""
        for _ in range(4):
            raw = self.xchg(frame, init)
            deadline, good, busy = time.monotonic() + P2E_S, None, False
            while True:
                for payload, ok in decode_frames(raw):
                    if not ok:
                        raise KlineError("bad checksum in reply " + payload.hex(" "))
                    if payload[0] != RC_NEG:
                        good = payload
                    elif payload[2] == NRC_PENDING:
                        continue
                    elif payload[2] == NRC_BUSY:
                        busy = True
                    else:
                        raise KlineError("ECU refused: " + describe(payload))
                if good is not None or busy or time.monotonic() > deadline:
                    break
                raw = self.xchg(None)
            if busy:
                continue
            if good is None:
                raise NoResponse(1)
            return good
        raise KlineError("ECU kept answering busyRepeatRequest")

    def request(self, data):
        return self._one(build_frame(data, self.use_short))

    def ecuid(self):
        payload = self.request(bytes([SID_ECUID, 0x81]))
        if len(payload) < 7 or payload[0] != 0x5A:
            raise KlineError("unexpected readECUID reply " + payload.hex(" "))
        return payload[2:7].decode("ascii", "replace"), payload

    def stop(self):
        return self.request(bytes([SID_STOPCOMM]))[0] == RC_STOPCOMM

    def _read_group(self, addr, count):
        stage = bytes([SID_AC, 0x81]) + b"".join(
            b"\x83" + (addr + k).to_bytes(4, "big") for k in range(count))
        if self.request(stage) != b"\xec\x81":
            raise KlineError(f"unexpected reply to the address request at 0x{addr:08X}")
        data = self.request(bytes([SID_RDBLI, 0x81, 0x04, 0x01]))
        if len(data) != 2 + count or data[:2] != b"\x61\x81":
            raise KlineError(f"unexpected data reply at 0x{addr:08X}: {data.hex(' ')}")
        return data[2:]

    def read_mem(self, addr, length, progress=None):
        """nisprog's retry scoring: successes earn back what failures cost (25 a failure)."""
        out, score, failures = bytearray(), 100, 0
        while len(out) < length:
            count = min(ADDRESSES_PER_REQUEST, length - len(out))
            try:
                out += self._read_group(addr + len(out), count)
                score = min(100, score + 5)
            except KlineError as e:
                score -= 25
                failures += 1
                if score <= 0:
                    raise KlineError(f"too many read errors at 0x{addr + len(out):08X}: {e}") from e
                if self.verbose:
                    print(f"\n  retry at 0x{addr + len(out):08X} (score {score}): {e}")
                time.sleep(0.3)
                self.drain()
            if progress:
                progress(len(out), failures)
        return bytes(out)


def connect(port, verbose=False):
    k = NisKline(Bridge(port), verbose)
    kb1, kb2 = k.fast_init()
    return k, kb1, kb2


def hexdump(data, base=0, width=16):
    for o in range(0, len(data), width):
        row = data[o:o + width]
        print(f"{base + o:08X}  " + " ".join(f"{b:02X}" for b in row))


def int_arg(s):
    return int(s, 0)


def main():
    ap = argparse.ArgumentParser(description="read-only Nissan K-line client (D40 Frontier ECM)")
    ap.add_argument("--port", default="/dev/ttyACM2", help="Teensy third serial port")
    ap.add_argument("-v", "--verbose", action="store_true", help="log every bridge exchange")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="bridge status and K-line idle level")
    sub.add_parser("selftest", help="K-line loop-back test of the converter (no ECM needed)")
    p = sub.add_parser("monitor", help="watch the K-line receive pin for low pulses (for hand tests)")
    p.add_argument("seconds", type=int, nargs="?", default=30)
    p = sub.add_parser("gpiotest", help="plain-GPIO check of the K-line pins")
    p = sub.add_parser("latch", help="count pulses on the K-line receive pin (no timing needed)")
    p.add_argument("--read", action="store_true", help="report the count since arming")
    p.add_argument("--selftest", action="store_true", help="check the latch with a pulse made by the Teensy")
    p = sub.add_parser("toggle", help="pulse the transmit pin for a meter reading on the K-line")
    p.add_argument("seconds", type=int, nargs="?", default=180)
    p.add_argument("low_ms", type=int, nargs="?", default=20, help="length of each low pulse, 1..24 ms")
    sub.add_parser("info", help="fast init, key bytes, ECU ID")
    sub.add_parser("stop", help="send stopCommunication")
    p = sub.add_parser("read", help="read bytes and hexdump them")
    p.add_argument("addr", type=int_arg)
    p.add_argument("length", type=int_arg)
    p = sub.add_parser("dump", help="dump a range to a file (resumes if the file exists)")
    p.add_argument("file")
    p.add_argument("start", type=int_arg)
    p.add_argument("length", type=int_arg)
    args = ap.parse_args()

    if args.cmd == "status":
        b = Bridge(args.port)
        r = b.raw("S")
        scan = b.raw("N")
        b.close()
        level, open_ = r[1:2], r[2:3]
        print(f"K-line level at idle : {'HIGH' if level == b'1' else 'LOW'}")
        print(f"Bridge UART          : {'running' if open_ == b'1' else 'closed'}")
        if scan[:1] == b"N":
            bits = scan[1:14].decode("ascii", "replace")
            print("Pin  : " + " ".join(f"{p:2d}" for p in range(len(bits))))
            print("High : " + " ".join(f"{c:>2}" for c in bits))
        if level != b"1":
            print("WARNING: the converter reads the idle line as low. The ECU will not be heard "
                  "like this (check the K-line idle voltage and the pull-up).")
        return

    if args.cmd == "toggle":
        secs = max(1, min(580, args.seconds))
        low_ms = max(1, min(24, args.low_ms))
        b = Bridge(args.port)
        b.ser.write(f"g{low_ms}\r".encode())
        print(f"Transmit pin is toggling (low {low_ms} ms / high 20 ms) for {secs} s: "
              f"read the converter's LIN terminal with the meter now.", flush=True)

        def _stopped(signum, frame):            # make a kill end the toggling too
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, _stopped)
        signal.signal(signal.SIGINT, _stopped)
        try:
            time.sleep(secs)
        except KeyboardInterrupt:
            pass
        b.ser.write(b"\r")                      # any character ends the toggling
        b.ser.timeout = 3.0
        r = b.ser.read_until(b"\r")
        b.close()
        if r.startswith(b"g"):
            print("Toggling stopped.")
        else:
            sys.exit(f"unexpected reply after the toggle: {r!r}")
        return

    if args.cmd == "latch":
        b = Bridge(args.port)
        if args.selftest:
            armed = b.cmd("C")          # pin level when armed, e.g. b"C1"
            low = b.raw("w")            # the Teensy pulls its own receive pin low; b"w0" when read low
            count = b.raw("c")
            b.close()
            print(f"Pin level when armed            : {'HIGH' if armed[1:2] == b'1' else 'LOW'}")
            print(f"Pin read while the Teensy pulls it low : {'LOW' if low == b'w0' else 'HIGH'}")
            n = int(count[1:]) if count.startswith(b"c") and count[1:].isdigit() else -1
            print(f"Pulses counted                  : {n}")
            print("RESULT: the latch works" if low == b"w0" and n == 1
                  else "RESULT: the latch does NOT work - hand-test results would be meaningless")
            return
        if args.read:
            r = b.raw("c")
            b.close()
            if not r.startswith(b"c"):
                sys.exit(f"unexpected bridge reply {r!r}")
            n = int(r[1:])
            print(f"Pulses counted on the converter's output : {n}")
            if n:
                print("RESULT: the converter's output does follow its input - it answered.")
            else:
                print("RESULT: no pulse on the converter's output was seen.")
        else:
            r = b.cmd("C")
            b.close()
            if not r.startswith(b"C"):
                sys.exit(f"unexpected bridge reply {r!r}")
            print(f"Line level when armed : {'HIGH' if r[1:2] == b'1' else 'LOW'}")
            if r[1:2] != b"1":
                print("WARNING: the converter's output is low at idle, so a low pulse cannot be seen.")
            print("Latch armed: every low pulse on the converter's output is counted from now on.")
        return

    if args.cmd == "monitor":
        secs = args.seconds
        b = Bridge(args.port)
        try:
            r = b.raw(f"M{secs}", secs + 3.0)
        except serial.SerialException as e:
            b.close()
            sys.exit(f"the bridge disconnected during the watch (the Teensy rebooted - usually "
                     f"its 5 V was shorted to ground for an instant): {e}")
        b.close()
        if len(r) < 5 or r[:1] != b"M":
            sys.exit(f"unexpected bridge reply {r!r}")
        idle = r[1:2].decode()
        events, longest = int(r[2:-3]), int(r[-3:])
        print(f"Line level when the watch started : {'HIGH' if idle == '1' else 'LOW'}")
        print(f"Low pulses seen                   : {events}")
        print(f"Longest low pulse                 : {longest / 10:.1f} ms")
        if events:
            print("RESULT: the converter's output does follow its input - it answered.")
        else:
            print("RESULT: no low pulse on the converter's output at any time.")
        return

    if args.cmd == "gpiotest":
        b = Bridge(args.port)
        r = b.raw("Z", 3.0)
        b.close()
        if len(r) != 6 or r[:1] != b"Z":
            sys.exit(f"unexpected bridge reply {r!r}")
        idle, at1, at8, txback, after = r[1:6].decode("ascii")
        hilo = lambda c: "HIGH" if c == "1" else "LOW"
        print(f"Receive pin, bus idle            : {hilo(idle)}")
        print(f"Receive pin, 1 ms into TX low    : {hilo(at1)}")
        print(f"Receive pin, 8 ms into TX low    : {hilo(at8)}")
        print(f"Transmit pin read back while low : {hilo(txback)}")
        print(f"Receive pin, 1 ms after release  : {hilo(after)}")
        if (idle, at1, at8, txback, after) == ("1", "0", "0", "0", "1"):
            print("RESULT: the K-line path is healthy at the GPIO level")
        elif txback == "1":
            print("RESULT: the Teensy cannot pull its transmit pin (8) low - something holds it high")
        elif idle == "0":
            print("RESULT: the Teensy does not see the converter's output on its receive pin (7)")
        elif at8 == "1":
            print("RESULT: transmit pin goes low, but the converter's output stays high - the "
                  "module is not driving the bus (asleep, or the low does not reach its input)")
        else:
            print("RESULT: unexpected combination")
        return

    if args.cmd == "selftest":
        b = Bridge(args.port)
        r = b.raw("Q", 1.5)
        b.close()
        if r == b"K1":
            print("K-line loop-back OK: the converter echoed the test pattern")
        elif r.startswith(b"K0"):
            print("K-line loop-back FAILED; the converter returned:",
                  r[2:].decode("ascii", "replace") or "nothing")
            print("Nothing back means the converter is asleep or unpowered (SLP needs 2-7 V), "
                  "or the TX/RX wires are swapped.")
        else:
            sys.exit(f"unexpected bridge reply {r!r}")
        return

    try:
        k, kb1, kb2 = connect(args.port, args.verbose)
    except (KlineError, serial.SerialException) as e:
        sys.exit(f"init failed: {e}")

    try:
        if args.cmd == "info":
            print(f"startCommunication OK   KB1=0x{kb1:02X} KB2=0x{kb2:02X}")
            print(f"  length in format byte: {'yes' if kb1 & KB_FMTLEN else 'no'}   "
                  f"extra length byte: {'yes' if kb1 & KB_LENBYTE else 'no'}   "
                  f"short header: {'yes' if kb1 & KB_SHORTHDR else 'no'}   "
                  f"long header: {'yes' if kb1 & KB_LONGHDR else 'no'}")
            print(f"  using {'short (1-byte)' if k.use_short else 'address'} headers this session")
            ecuid, payload = k.ecuid()
            print(f"readECUID               {payload.hex(' ')}")
            print(f"ECU ID                  {ecuid}")
        elif args.cmd == "stop":
            print("stopCommunication", "OK" if k.stop() else "refused")
        elif args.cmd == "read":
            data = k.read_mem(args.addr, args.length)
            hexdump(data, args.addr)
            print(f"{len(data)} bytes, {k.exchanges} exchanges")
        elif args.cmd == "dump":
            path, start, length = args.file, args.start, args.length
            done = os.path.getsize(path) if os.path.exists(path) else 0
            if done > length:
                sys.exit(f"{path} is {done} bytes, longer than the requested {length}; refusing")
            if done == length:
                print(f"{path} already complete ({done} bytes)")
                return
            if done:
                print(f"resuming {path} at 0x{start + done:08X} ({done} of {length} bytes)")
            t0, first = time.monotonic(), done
            last = [""]
            chunk = 4096

            def tick(n, failures):
                now, got = time.monotonic(), done + n
                rate = (got - first) / max(now - t0, 1e-6)
                eta = (length - got) / rate if rate else 0
                line = (f"\r0x{start + got:08X}  {100 * got / length:5.1f}%  {rate:5.0f} B/s  "
                        f"ETA {eta / 60:5.1f} min  retries {failures}")
                if line != last[0]:
                    print(line, end="", flush=True)
                    last[0] = line

            with open(path, "ab" if done else "wb") as f:
                while done < length:
                    data = k.read_mem(start + done, min(chunk, length - done), tick)
                    f.write(data)
                    f.flush()
                    done += len(data)
                    tick(0, 0)
            secs = time.monotonic() - t0
            print(f"\ndone: {done} bytes in {secs / 60:.1f} min "
                  f"({(done - first) / max(secs, 1e-6):.0f} B/s), {k.exchanges} exchanges -> {path}")
    except NoResponse as e:
        sys.exit(f"\n{e}")
    except KlineError as e:
        sys.exit(f"\nerror: {e}")
    finally:
        k.b.close()


if __name__ == "__main__":
    main()
