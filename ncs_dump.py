#!/usr/bin/env python3
"""
ncs_dump.py - read-only flash dump of the 2013-2015 Frontier VQ40 ECM (Hitachi DH1) over CAN.

Protocol (RomRaider TestJ2534NCS read path, confirmed on the bench 2026-11-23):
  0x7E0 -> 0x7E8, 500 kbit/s, ISO-TP, every frame zero-padded to 8 bytes
  10 C0            -> 50 C0     Nissan diagnostic session
  10 FB            -> 50 FB     read session
  23 <addr32> 00 <len<=0x3F>    -> 63 <len bytes>
  10 81            -> 50 81     back to the default session at the end
No SecurityAccess is needed or sent. Only services 10, 23 are used: nothing here can
erase or write.

The output file always holds the image from <start> contiguously, so an interrupted dump
resumes from the file's current length. The dump ends at <start>+<length> or at the first
address the ECM refuses as out of range (7F 23 31), whichever comes first.

Usage:
  python3 ncs_dump.py dump  rom_pass1.bin                 # from 0 until the ECM refuses
  python3 ncs_dump.py dump  rom_pass1.bin --length 0x1000 # a short test
  python3 ncs_dump.py compare rom_pass1.bin rom_pass2.bin
"""
import argparse
import os
import sys
import time

import can

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ncs_probe as n  # noqa: E402  (IsoTp with 8-byte padding, hx)

CHUNK = 0x3F
NRC_OUT_OF_RANGE = 0x31


class Ecm:
    def __init__(self, port, bitrate):
        self.bus = can.Bus(interface="slcan", channel=port, bitrate=bitrate)
        self.tp = n.IsoTp(self.bus, timeout=1.0)

    def close(self):
        try:
            self.tp.request([0x10, 0x81])
        finally:
            self.bus.shutdown()

    def enter_read_session(self):
        for sub in (0xC0, 0xFB):
            r = self.tp.request([0x10, sub])
            if not r or r[0] != 0x50:
                raise RuntimeError(f"session 10 {sub:02X} refused: {n.hx(r)}")

    def read(self, addr, ln):
        """bytes on success, ('nrc', code) on a negative reply, None on silence/garbage."""
        req = [0x23, (addr >> 24) & 0xFF, (addr >> 16) & 0xFF, (addr >> 8) & 0xFF, addr & 0xFF,
               0x00, ln]
        r = self.tp.request(req)
        if r is None:
            return None
        if r[0] == 0x63 and len(r) == ln + 1:
            return bytes(r[1:])
        if r[0] == 0x7F and len(r) >= 3 and r[1] == 0x23:
            return ("nrc", r[2])
        return None


def dump(args):
    start, end = args.start, args.start + args.length
    have = os.path.getsize(args.file) if os.path.exists(args.file) else 0
    addr = start + have
    if addr >= end:
        print(f"{args.file} already holds {have} bytes; nothing to do")
        return
    print(f"dumping 0x{addr:06X}..0x{end:06X} into {args.file}"
          + (f" (resuming after {have} bytes)" if have else ""))
    ecm = Ecm(args.port, args.bitrate)
    t0, done0, last_report = time.monotonic(), addr, 0.0
    try:
        ecm.enter_read_session()
        with open(args.file, "ab") as f:
            while addr < end:
                # never straddle a 64 KB boundary: a read across 0x100000 is refused with
                # 7F 23 22 (bench 2026-11-23)
                ln = min(CHUNK, end - addr, 0x10000 - (addr & 0xFFFF))
                for attempt in range(6):
                    r = ecm.read(addr, ln)
                    if isinstance(r, bytes):
                        break
                    if isinstance(r, tuple):
                        if r[1] == NRC_OUT_OF_RANGE:
                            break
                        if r[1] == 0x22 and (addr & 0xFFFF) == 0 and attempt >= 2:
                            # the DH1 refuses its first address past the 1 MB flash with
                            # 7F 23 22 (bench 2026-11-23): treat a repeated 22 at a 64 KB
                            # boundary as the end of readable memory
                            r = ("nrc", NRC_OUT_OF_RANGE)
                            break
                        print(f"\n  0x{addr:06X}: negative reply 7F 23 {r[1]:02X}, retrying")
                    else:
                        print(f"\n  0x{addr:06X}: no reply, re-entering the read session")
                    time.sleep(0.2 * (attempt + 1))
                    try:
                        ecm.enter_read_session()
                    except RuntimeError as e:
                        print(f"  {e}")
                if isinstance(r, tuple) and r[1] == NRC_OUT_OF_RANGE:
                    print(f"\nECM refuses 0x{addr:06X} as out of range: end of readable memory")
                    break
                if not isinstance(r, bytes):
                    sys.exit(f"\ngave up at 0x{addr:06X} after 6 attempts; rerun to resume")
                f.write(r)
                addr += ln
                now = time.monotonic()
                if now - last_report > 2.0 or addr >= end:
                    last_report = now
                    rate = (addr - done0) / max(now - t0, 1e-6)
                    eta = (end - addr) / rate if rate else 0
                    f.flush()
                    print(f"\r  0x{addr:06X}  {(addr - start) / 1024:7.1f} KB  "
                          f"{rate / 1024:5.1f} KB/s  ETA {eta / 60:5.1f} min (if the ROM runs "
                          f"to 0x{end:06X})", end="", flush=True)
    finally:
        ecm.close()
    size = os.path.getsize(args.file)
    print(f"\ndone: {args.file} = {size} bytes (0x{size:X}) from 0x{start:06X}; "
          f"{time.monotonic() - t0:.0f} s")


def compare(args):
    a, b = open(args.a, "rb").read(), open(args.b, "rb").read()
    print(f"{args.a}: {len(a)} bytes, {args.b}: {len(b)} bytes")
    m = min(len(a), len(b))
    diffs = [i for i in range(m) if a[i] != b[i]]
    if not diffs and len(a) == len(b):
        print("IDENTICAL")
        return
    print(f"{len(diffs)} differing bytes in the common {m} bytes"
          + ("" if len(a) == len(b) else "; lengths differ"))
    for i in diffs[:20]:
        print(f"  0x{i:06X}: {a[i]:02X} vs {b[i]:02X}")
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="read-only CAN flash dump, DH1 ECM")
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--bitrate", type=int, default=500000)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("dump")
    p.add_argument("file")
    p.add_argument("--start", type=lambda v: int(v, 0), default=0)
    p.add_argument("--length", type=lambda v: int(v, 0), default=0x280000,
                   help="upper bound (default 2.5 MB); the ECM's out-of-range reply ends it sooner")
    p = sub.add_parser("compare")
    p.add_argument("a")
    p.add_argument("b")
    args = ap.parse_args()
    dump(args) if args.cmd == "dump" else compare(args)


if __name__ == "__main__":
    main()
