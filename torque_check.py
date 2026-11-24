#!/usr/bin/env python3
"""Bench check of the 0x177 B4 torque-cut chain on the patched ECM (engine stopped).

Sends the TCM frame set (gear_check.TcmTx) with a cut in 0x177 B4 while an upshift is pending,
and reads the chain's RAM cells with 23 (session FB, reads only):
  0xFFFF289F  B4 as stored by the 0x177 handler (0xE2B4C)
  0xFFFF274F  its mirror (block copy 0x20E04)
  0xFFFF3910  the copy the cut function uses (0x68AC0)
  0xFFFF2401  shift flags (bit 6 = shift in progress, gates the cut functions at 0x69A60)
  0xFFFF23E5..23EA  shift flags read by the gate 0x69A34..0x69A5A
  0xFFFF1867  first cut step, 0xFFFF13EA / 13EC  scaled cut (outputs of 0x68E62)
"""
import os
import sys
import time

import can

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ncs_probe as n  # noqa: E402
from gear_check import LockedBus, TcmTx, read  # noqa: E402


class TcmTxCut(TcmTx):
    cut = 0

    def frame(self, cid, data):
        if cid == 0x177:
            t, e = self.b3 >> 4, self.b3 & 0x0F
            data = list(data)
            data[4] = self.cut if t != e else 0       # as nissan_tx.c: a cut only while shifting
        super().frame(cid, data)


CASES = [("steady 7th", 0x77, 0x00), ("upshift 7->8, cut 0x67", 0x87, 0x67), ("steady 8th", 0x88, 0x00)]
CELLS = [("289F", 0xFFFF289F, 1), ("274F", 0xFFFF274F, 1), ("3910", 0xFFFF3910, 1),
         ("2401", 0xFFFF2401, 1), ("23E5-EA", 0xFFFF23E5, 6), ("1867", 0xFFFF1867, 1),
         ("13EA-ED", 0xFFFF13EA, 4)]


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM0"
    raw = can.Bus(interface="slcan", channel=port, bitrate=500000)
    bus = LockedBus(raw)
    tp = n.IsoTp(bus, timeout=2.0)
    tx = TcmTxCut(bus)
    tx.b3 = 0x77
    tx.start()
    try:
        time.sleep(1.0)
        for sub in (0xC0, 0xFB):
            print(f"10 {sub:02X} -> {n.hx(tp.request([0x10, sub]))}")
        for name, b3, cut in CASES:
            tx.b3, tx.cut = b3, cut
            time.sleep(0.6)
            vals = []
            for label, addr, ln in CELLS:
                v = read(tp, addr, ln)
                vals.append(f"{label}={' '.join(f'{x:02X}' for x in v) if v else '--'}")
            print(f"{name:24} " + "  ".join(vals))
    finally:
        tx.stop_ev.set()
        tx.join(timeout=1)
        raw.shutdown()


if __name__ == "__main__":
    main()
