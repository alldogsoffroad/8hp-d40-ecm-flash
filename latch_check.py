#!/usr/bin/env python3
"""Does power-up clear the 0x912C working value 0xFFFF3384?  (reads only)

Run right after the user power-cycles the ECM:
 1. no TCM frames: 10 C0, 10 FB, read 0xFFFF3384      -> prediction 0000 if RAM is cleared
 2. TCM frames in 1st (B3 0x11), then 3rd (0x33), then back to 1st, reading as it goes:
    prediction: rises by 0x148 per pass to 1F0C, then to 457E, and stays at 457E in 1st.
"""
import os
import sys
import time

import can

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ncs_probe as n  # noqa: E402
from gear_check import LockedBus, TcmTx, read  # noqa: E402


def show(tp, label):
    v = read(tp, 0xFFFF3384, 2)
    print(f"{label:28} 0xFFFF3384 = {' '.join('%02X' % x for x in v) if v else '--'}")


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM0"
    raw = can.Bus(interface="slcan", channel=port, bitrate=500000)
    bus = LockedBus(raw)
    tp = n.IsoTp(bus, timeout=2.0)
    try:
        for sub in (0xC0, 0xFB):
            print(f"10 {sub:02X} -> {n.hx(tp.request([0x10, sub]))}")
        show(tp, "after power-up, no frames")
        tx = TcmTx(bus)
        tx.b3 = 0x11
        tx.start()
        for b3, label in ((0x11, "1st"), (0x33, "3rd"), (0x11, "back to 1st")):
            tx.b3 = b3
            for t in (0.3, 1.5):
                time.sleep(t)
                show(tp, f"{label}, +{t}s")
        tx.stop_ev.set()
        tx.join(timeout=1)
    finally:
        raw.shutdown()


if __name__ == "__main__":
    main()
