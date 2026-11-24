#!/usr/bin/env python3
"""Bench step A (ecm_reflash_sequence.md section 6.A): reads only.

Sends exactly: 10 C0, 10 FB, and five 23 reads of RAM. No other service (not even 10 81
at the end: the session simply times out / the ECM is powered off).
"""
import os
import sys

import can

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ncs_probe as n  # noqa: E402

REQS = [
    ("session C0", [0x10, 0xC0]),
    ("session FB", [0x10, 0xFB]),
    ("0xFFFF4606 x1", [0x23, 0xFF, 0xFF, 0x46, 0x06, 0x00, 0x01]),
    ("0xFFFF23E7 x1", [0x23, 0xFF, 0xFF, 0x23, 0xE7, 0x00, 0x01]),
    ("0xFFFF117B x1", [0x23, 0xFF, 0xFF, 0x11, 0x7B, 0x00, 0x01]),
    ("0xFFFF2386 x2", [0x23, 0xFF, 0xFF, 0x23, 0x86, 0x00, 0x02]),
    ("0xFFFF6904 x4", [0x23, 0xFF, 0xFF, 0x69, 0x04, 0x00, 0x04]),
]


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM0"
    bus = can.Bus(interface="slcan", channel=port, bitrate=500000)
    tp = n.IsoTp(bus, timeout=1.0)
    try:
        for name, req in REQS:
            r = tp.request(req)
            print(f"{name:14} -> {n.hx(req)}  <-  {n.hx(r)}")
            if req[0] == 0x10 and (not r or r[0] != 0x50):
                print("session refused; stopping")
                return
    finally:
        bus.shutdown()


if __name__ == "__main__":
    main()
