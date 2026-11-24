#!/usr/bin/env python3
"""Bench check of the 8-gear patch: transmit the TCM frame set (as nissan_tx.c packs it) with
chosen gears and read the ECM's gear cells over 23 (session C0/FB, reads only).

TX (engine stopped, speeds 0): 0x174 / 0x176 / 0x177 every 10 ms, 0x560 every 100 ms
(12 pages: calibration ID "8HP001", CVN 0000, fault pages 00).
Reads per case: 0xFFFF1090 (2: engaged-1, target-1), 0xFFFF1505 (gear number),
0xFFFF283F (class), 0xFFFF2620 (class).
"""
import os
import sys
import threading
import time

import can

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ncs_probe as n  # noqa: E402

CAL_ID = b"8HP001"
PAGES = [0x15, 0x16, 0x17, 0x40, 0x41, 0x42, 0x43, 0x10, 0x11, 0x12, 0x13, 0x14]

# (B3, prediction for 1090, 1091, 1505, 283F, 2620)
CASES = [
    (0x22, (0x01, 0x01, 0x02, 0x00, 0x08)),   # control: 2nd / 2nd (stock behaviour too)
    (0x88, (0x07, 0x07, 0x08, 0x00, 0x08)),   # 8th / 8th: stock would give 00 00
    (0x76, (0x05, 0x06, 0x06, 0x00, 0x08)),   # target 7th, engaged 6th
    (0x87, (0x06, 0x07, 0x07, 0x00, 0x08)),   # target 8th, engaged 7th
]


class LockedBus:
    def __init__(self, bus):
        self.bus, self.lock = bus, threading.Lock()

    def send(self, msg):
        with self.lock:
            self.bus.send(msg)

    def recv(self, timeout=None):
        return self.bus.recv(timeout=timeout)


class TcmTx(threading.Thread):
    def __init__(self, bus):
        super().__init__(daemon=True)
        self.bus, self.b3, self.stop_ev = bus, 0x22, threading.Event()

    def frame(self, cid, data):
        self.bus.send(can.Message(arbitration_id=cid, data=bytes(data), is_extended_id=False))

    def run(self):
        ctr, k, page = 0, 0, 0
        nxt = time.monotonic()
        while not self.stop_ev.is_set():
            t, e = self.b3 >> 4, self.b3 & 0x0F
            self.frame(0x174, [0xFF, 0xE7, 0x1C, self.b3, ctr, 0, 0, 0])
            self.frame(0x176, [0, 0, 0, 0, 0, 0, ctr])
            self.frame(0x177, [0, 0, (e - 1) & 7 if e else 0, 1 if e == 1 else 0, 0, 15 << 3])
            if k % 10 == 0:
                p = PAGES[page % 12]
                d = CAL_ID[p - 0x10] if 0x10 <= p <= 0x15 else 0x00
                self.frame(0x560, [0x65, p, d, 0])
                page += 1
            ctr, k = (ctr + 1) & 0x0F, k + 1
            nxt += 0.010
            time.sleep(max(0.0, nxt - time.monotonic()))


def read(tp, addr, ln):
    for _ in range(3):
        r = tp.request([0x23, (addr >> 24) & 0xFF, (addr >> 16) & 0xFF, (addr >> 8) & 0xFF, addr & 0xFF, 0, ln])
        if r and r[0] == 0x63 and len(r) == ln + 1:
            return list(r[1:])
    return None


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM0"
    raw = can.Bus(interface="slcan", channel=port, bitrate=500000)
    bus = LockedBus(raw)
    tp = n.IsoTp(bus, timeout=2.0)   # replies are slower while the TX thread loads the link
    tx = TcmTx(bus)
    tx.start()
    ok_all = True
    try:
        time.sleep(1.0)
        for sub in (0xC0, 0xFB):
            r = tp.request([0x10, sub])
            print(f"10 {sub:02X} -> {n.hx(r)}")
        for b3, pred in CASES:
            tx.b3 = b3
            time.sleep(0.6)
            g = read(tp, 0xFFFF1090, 2)
            gn = read(tp, 0xFFFF1505, 1)
            c1 = read(tp, 0xFFFF283F, 1)
            c2 = read(tp, 0xFFFF2620, 1)
            got = None if None in (g, gn, c1, c2) else (g[0], g[1], gn[0], c1[0], c2[0])
            ok = got == pred
            ok_all &= ok
            fmt = lambda v: " ".join(f"{x:02X}" for x in v) if v else "no reply"
            print(f"B3={b3:02X}  1090/1091/1505/283F/2620 = {fmt(got)}   predicted {fmt(pred)}   "
                  f"{'OK' if ok else 'DIFFERS'}")
    finally:
        tx.stop_ev.set()
        tx.join(timeout=1)
        raw.shutdown()
    print("all as predicted" if ok_all else "differences found")


if __name__ == "__main__":
    main()
