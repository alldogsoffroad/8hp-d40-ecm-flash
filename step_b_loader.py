#!/usr/bin/env python3
"""Bench step B (ecm_reflash_sequence.md section 6.B): enter the boot loader, read a seed.

Sends exactly: 10 85, 27 81 (application -> hand-off), 3E 00, 27 81 (loader seed).
NO 27 82, NO 31, NO 34. Between requests it only listens and counts the ECM's broadcast
frames (0x160/0x180/0x182/0x1F9/0x551/...). Stops at the first unexpected reply.
Afterwards the user power-cycles the ECM; `--listen` then checks that broadcasts resumed.
"""
import collections
import os
import sys
import time

import can

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ncs_probe as n  # noqa: E402

BROADCAST = {0x160, 0x180, 0x182, 0x1F9, 0x551, 0x580, 0x6E2}


def sample(bus, seconds):
    c = collections.Counter()
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        m = bus.recv(timeout=0.05)
        if m is not None and m.arbitration_id in BROADCAST:
            c[m.arbitration_id] += 1
    return {f"{k:03X}": v for k, v in sorted(c.items())}


def req(tp, payload, wait_pending=5.0):
    r = tp.request(payload)
    t0 = time.monotonic()
    while r and len(r) >= 3 and r[0] == 0x7F and r[2] == 0x78 and time.monotonic() - t0 < wait_pending:
        r = tp._receive()
    print(f"  -> {n.hx(payload):24} <- {n.hx(r)}")
    return r


def main():
    port = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "/dev/ttyACM0"
    bus = can.Bus(interface="slcan", channel=port, bitrate=500000)
    tp = n.IsoTp(bus, timeout=1.0)
    try:
        if "--listen" in sys.argv:
            print("broadcasts over 1 s:", sample(bus, 1.0))
            return
        print("broadcasts before (1 s):", sample(bus, 1.0))
        r = req(tp, [0x10, 0x85])
        if not r or r[0] != 0x50:
            print("10 85 not accepted: stop"); return
        print("broadcasts in session 85 (0.5 s):", sample(bus, 0.5))
        r = req(tp, [0x27, 0x81])
        if not r or r[0] != 0x67:
            print("application 27 81 not accepted: stop"); return
        for i in range(3):
            print(f"broadcasts after hand-off, window {i + 1} (0.5 s):", sample(bus, 0.5))
        r = req(tp, [0x3E, 0x00])
        r = req(tp, [0x27, 0x81])
        if r and r[0] == 0x67 and len(r) >= 6:
            print(f"loader seed: {n.hx(r[2:6])}")
        print("broadcasts at the end (1 s):", sample(bus, 1.0))
        print("done: no 27 82 / 31 / 34 sent. Power-cycle the ECM now.")
    finally:
        bus.shutdown()


if __name__ == "__main__":
    main()
