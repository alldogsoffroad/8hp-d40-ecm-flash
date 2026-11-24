#!/usr/bin/env python3
"""
ncs_probe.py — bench probe for 2013-2015 Nissan Frontier VQ40 ECM (Hitachi, DH1 family)

Read-only diagnostics over CAN via a Teensy 4.1 running Lawicel SLCAN firmware
(the 8hp-teensy-flasher dual-serial build: CAN1 = first ACM port, CAN2 = second).

Protocol from RomRaider TestJ2534NCS (GPL-2) as documented in the project notes:
  0x7E0/0x7E8 @ 500 kbps, ISO-TP; sessions 10 C0 / 10 FB; identity via 21 xx;
  SecurityAccess 27 81 seed -> 27 82 <key>; memory read via 23 <addr32> <len>.

SAFETY: only read-oriented services are implemented (3E/10/21/22/27/23).
        No erase (0x31), no write (0x34). Nothing here can flash the ECU.

Usage:
  python3 ncs_probe.py                     # passive probe (no key sent)
  python3 ncs_probe.py --key               # + dummy-key test (11 22 33 44)
  python3 ncs_probe.py --ids               # + 21 F0/FE/FF part-number queries
  python3 ncs_probe.py --key --read 0 64   # + test read of 64 bytes @ 0x00000000
Options:
  --port /dev/ttyACM0   SLCAN serial port (try ACM1 if ACM0 is the wrong CAN channel)
  --listen              just listen for ambient traffic, send nothing
"""
import argparse
import sys
import time

import can

REQ_ID = 0x7E0
RESP_ID = 0x7E8

DUMMY_KEY = bytes.fromhex("11223344")

NRC = {
    0x10: "general reject", 0x11: "service not supported", 0x12: "sub-function not supported",
    0x13: "incorrect length", 0x22: "conditions not correct", 0x24: "request sequence error",
    0x31: "request out of range", 0x33: "security access denied", 0x35: "invalid key",
    0x36: "exceeded number of attempts", 0x37: "required time delay not expired",
    0x7F: "sub-function not supported in active session",
}


class IsoTp:
    """Minimal ISO-TP: TX single-frame only (all our requests are <=7 bytes).
    RX: single + first/consecutive frames, sends flow control."""

    def __init__(self, bus, timeout=0.4):
        self.bus = bus
        self.timeout = timeout

    def _send_raw(self, data):
        # always DLC 8, zero padded: the DH1 ECM ignores short frames (bench 2026-11-23:
        # unpadded requests all timed out, the same requests padded to 8 bytes were answered)
        data = bytes(data) + bytes(8 - len(data))
        self.bus.send(can.Message(arbitration_id=REQ_ID, data=data, is_extended_id=False))

    def request(self, payload, gap=0.05):
        """Send a request (<=7 bytes), return full response payload or None."""
        assert len(payload) <= 7
        self._send_raw(bytes([len(payload)]) + bytes(payload))
        return self._receive()

    def _receive(self):
        buf, remaining, start = bytearray(), 0, time.monotonic()
        got_first = False
        while time.monotonic() - start < self.timeout:
            msg = self.bus.recv(timeout=max(0.01, self.timeout - (time.monotonic() - start)))
            if msg is None:
                break
            if msg.arbitration_id != RESP_ID or not msg.data:
                continue
            d, pci = msg.data, msg.data[0] >> 4
            if pci == 0:  # single frame
                return bytes(d[1:1 + (msg.data[0] & 0x0F)])
            if pci == 1:  # first frame
                total = ((msg.data[0] & 0x0F) << 8) | d[1]
                buf = bytearray(d[2:]); remaining = total - len(buf); got_first = True
                self._send_raw([0x30, 0x00, 0x00])  # flow control: clear to send
                start = time.monotonic()
                continue
            if pci == 2 and got_first:  # consecutive
                buf += d[1:1 + min(remaining, 7)]
                remaining -= min(remaining, 7)
                if remaining <= 0:
                    return bytes(buf)
        return None


def hx(b):
    return " ".join(f"{x:02X}" for x in b) if b else "(no response)"


def describe(resp, sid):
    """Pretty-print a response; returns short verdict string."""
    if resp is None:
        return "TIMEOUT"
    if resp and resp[0] == 0x7F:
        nrc = NRC.get(resp[2], "?") if len(resp) > 2 else "?"
        return f"NEGATIVE (7F {resp[1]:02X} {resp[2]:02X} = {nrc})"
    if resp and resp[0] == sid + 0x40:
        return "OK"
    return f"UNEXPECTED {hx(resp)}"


def step(tag, tp, payload, show=True):
    resp = tp.request(payload)
    print(f"  [{tag:<14}] TX {hx(bytes(payload)):<16} RX {hx(resp)}")
    return resp


def main():
    ap = argparse.ArgumentParser(description="read-only NCS bench probe")
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--bitrate", type=int, default=500000)
    ap.add_argument("--key", action="store_true", help="test dummy SecurityAccess key")
    ap.add_argument("--ids", action="store_true", help="query 21 F0/FE/FF part numbers")
    ap.add_argument("--read", nargs=2, type=lambda v: int(v, 0), metavar=("ADDR", "LEN"),
                    help="test 0x23 read (ADDR and LEN, hex ok) after session")
    ap.add_argument("--listen", action="store_true", help="passive listen only")
    args = ap.parse_args()

    print(f"opening SLCAN on {args.port} @ {args.bitrate} bps ...")
    try:
        bus = can.Bus(interface="slcan", channel=args.port, bitrate=args.bitrate)
    except Exception as e:
        sys.exit(f"could not open {args.port}: {e}\n(try --port /dev/ttyACM1 for the other CAN channel)")

    if args.listen:
        print("listening 3 s for ambient traffic (expect silence on a bench)...")
        end = time.monotonic() + 3
        n = 0
        while time.monotonic() < end:
            m = bus.recv(timeout=0.2)
            if m:
                n += 1
                print(f"  ID={m.arbitration_id:03X}  {hx(m.data)}")
        print(f"{n} frames seen" + ("  <- unexpected! check pins/termination" if n else "  (quiet, good)"))
        return

    tp = IsoTp(bus)
    print("\n== 1. link check (NCS init first — Nissan CAN ECUs ignore pre-init requests) ==")
    r = step("NCS init 10 C0", tp, [0x10, 0xC0])
    r2 = step("TesterPresent", tp, [0x3E, 0x00])
    if r is None and r2 is None:
        print("\nno response to init or TesterPresent.")
        print("checks: PSU on (VBR+IGNSW+ground)? current draw? 120R across CANH/L?")
        print("        correct ACM port (try --port /dev/ttyACM1)? wiring per FSM map?")
        return

    print("\n== 2. session + identity ==")
    r = step("ECU ID 21 10", tp, [0x21, 0x10])
    if r and len(r) > 1 and r[0] == 0x61:
        try:
            print(f"     ECU ID string: {bytes(r[1:]).decode('ascii', 'replace').strip()}")
        except Exception:
            pass
    step("VIN 21 81", tp, [0x21, 0x81])
    if args.ids:
        step("part# 21 F0", tp, [0x21, 0xF0])
        step("part# 21 FE", tp, [0x21, 0xFE])
        step("part# 21 FF", tp, [0x21, 0xFF])
    r = step("UDS 22 F1 87", tp, [0x22, 0xF1, 0x87])

    print("\n== 3. security access ==")
    r = step("seed 27 81", tp, [0x27, 0x81])
    seed = None
    if r and r[0] == 0x67:
        seed = r[2:] if len(r) > 2 else r[1:]
        print(f"     seed ({len(seed)} bytes): {hx(seed)}")
    elif r is not None:
        print(f"     seed request refused: {describe(r, 0x27)}")

    unlocked = False
    if args.key:
        if seed:
            r = step("key 27 82", tp, [0x27, 0x82] + list(DUMMY_KEY))
            if r and r[0] == 0x67:
                print("     *** SECURITY ACCESS GRANTED with dummy key 11 22 33 44 ***")
                unlocked = True
            else:
                print(f"     dummy key rejected: {describe(r, 0x27)}")
        else:
            print("     no seed available; skipping key test")

    print("\n== 4. read test ==")
    step("session 10 FB", tp, [0x10, 0xFB])
    if args.read:
        addr, ln = args.read
        # RomRaider TestJ2534NCS: 23 <addr32> 00 <len> (7 bytes); the 6-byte form gets 7F 23 12
        frame = [(addr >> 24) & 0xFF, (addr >> 16) & 0xFF, (addr >> 8) & 0xFF, addr & 0xFF, 0x00, ln]
        r = step(f"read 23 @{addr:08X}", tp, [0x23] + frame)
        if r and r[0] == 0x63:
            print("     read OK — dump path viable; first bytes above")
        else:
            print(f"     read result: {describe(r, 0x23)} (locked? retry with --key after unlock)")
    elif unlocked:
        print("  (use --read 0 64 to try a read now that security is open)")
    print("\ndone.")


if __name__ == "__main__":
    main()
