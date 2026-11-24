#!/usr/bin/env python3
"""Bench step C: does the boot loader accept any key (key-slot word W = FFFF)?

Sends exactly: 10 85, 27 81, 27 82 11 22 33 44. NO 31, NO 34.
Prediction: 50 85; 67 81 <4-byte seed from the loader>; 67 82 (any key accepted).
Afterwards the user power-cycles the ECM (step_b_loader.py --listen checks the broadcasts).
"""
import os
import sys

import can

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ncs_probe as n  # noqa: E402
from step_b_loader import req, sample  # noqa: E402


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM0"
    bus = can.Bus(interface="slcan", channel=port, bitrate=500000)
    tp = n.IsoTp(bus, timeout=1.0)
    try:
        print("broadcasts before (1 s):", sample(bus, 1.0))
        r = req(tp, [0x10, 0x85])
        if not r or r[0] != 0x50:
            print("10 85 not accepted: stop"); return
        r = req(tp, [0x27, 0x81])
        if not r or r[0] != 0x67:
            print("27 81 not accepted: stop"); return
        print("broadcasts after hand-off (0.5 s):", sample(bus, 0.5))
        r = req(tp, [0x27, 0x82, 0x11, 0x22, 0x33, 0x44])
        verdict = "ACCEPTED" if r and r[0] == 0x67 else "REFUSED"
        print(f"dummy key {verdict}")
        print("done: no 31 / 34 sent. Power-cycle the ECM now.")
    finally:
        bus.shutdown()


if __name__ == "__main__":
    main()
