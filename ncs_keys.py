#!/usr/bin/env python3
"""Security-key, CRC and payload-coding functions of the 9CJ3A ECM (SH7058), transcribed from
the ROM, with a self-test that runs the ROM's own routines in sh2_mini.py and compares.

    python3 ncs_keys.py            # self-test + print test vectors

Transcribed routines (addresses in dumps/dh1_9CJ3A_pass1.bin):
  app   0x31B4A  expected key for SID 27 in the application (sessions FA/DA path):
                 key = enc1(seed, s27k), s27k = 0x968148AD (halves at 0x31C80 / 0x31C8C)
                 mess1 = 0x31C16, swap = 0x31C34, mess2 = 0x31C3E
  boot  0x1490   CRC-16: reflected poly 0x8408, init 0xFFFF, no final xor (residue 0xF0B8)
  boot  0x1EAC   seed  = crc(R<<16|T) << 16 | crc(T<<16|R), R = random word, T = timer word
  boot  0x1F00   key   = crc(f1(sH), f2(sL), W) << 16 | crc(R, f1(sL), f2(W))
                 f1 = 0x2A38: 170*x mod 30323, f2 = 0x2A7A: 171*x mod 30269 (Wichmann-Hill)
                 W  = first programmed key-slot word (0x6280/0x6300/0x6380); 0xFFFF if none,
                      and then SID 27 82 accepts ANY key (0x1DA8-0x1DB2).
  boot  0x42B0   payload decode of each u32 = dec1(u32, scode), scode = u32 @0x5FE0 (0x737133EF)
"""
import random
import struct
import sys
from pathlib import Path

ROM = Path(__file__).resolve().parent / "dumps" / "dh1_9CJ3A_pass1.bin"
S27K = 0x968148AD
SCODE = 0x737133EF          # u32 at 0x5FE0 = nissutils keyset s36k2 for this s27k


def mess1(a, b, x):
    v2 = (x + b) & 0xFFFF
    v3 = v2 << 2
    return (((v3 >> 16) + v2 + v3 - 1) ^ a) & 0xFFFF


def mess2(a, b, x):
    v0 = (x + b) & 0xFFFF
    v1 = v0 << 1
    v2 = ((v1 >> 16) + v0 + v1 - 1) & 0xFFFF
    v3 = v2 << 4
    v4 = v3 + (v3 >> 16)
    return (a ^ v4 ^ v2) & 0xFFFF


def enc1(data, code):
    dH, dL = data >> 16, data & 0xFFFF
    kL = mess1(dH, dL, code >> 16)
    kH = mess2(dL, kL, code & 0xFFFF)
    return (kH << 16) | kL


def dec1(data, code):
    dH, dL = data >> 16, data & 0xFFFF
    kL = mess2(dH, dL, code & 0xFFFF)
    kH = mess1(dL, kL, code >> 16)
    return (kH << 16) | kL


def crc16(data):
    crc = 0xFFFF
    for byte in data:
        for _ in range(8):
            if (crc ^ byte) & 1:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc >>= 1
            byte >>= 1
    return crc


def _wh(x, q, a, r, mod):
    # Schrage form exactly as the ROM: x is exts.w, C-style truncating division
    x = x - 0x10000 if x & 0x8000 else x
    k = int(x / q)
    v = a * (x - k * q) - r * k
    v = ((v + 0x8000) & 0xFFFF) - 0x8000         # exts.w
    if v < 0:
        v += mod
    return v & 0xFFFFFFFF


def f1(x):
    return _wh(x, 178, 170, 63, 30323)


def f2(x):
    return _wh(x, 177, 171, 2, 30269)


def boot_seed(R, T):
    hi = crc16(struct.pack(">I", ((R << 16) + T) & 0xFFFFFFFF))
    lo = crc16(struct.pack(">I", ((T << 16) + R) & 0xFFFFFFFF))
    return (hi << 16) | lo


def boot_key(R, seed, W):
    a = struct.pack(">HHH", f1(seed >> 16) & 0xFFFF, f2(seed & 0xFFFF) & 0xFFFF, W & 0xFFFF)
    b = struct.pack(">HHH", R & 0xFFFF, f1(seed & 0xFFFF) & 0xFFFF, f2(W) & 0xFFFF)
    return (crc16(a) << 16) | crc16(b)


def frame_crc(frame):
    """RomRaider/NcsCoDec: append ~crc low byte first; residue over the whole frame = 0xF0B8."""
    c = (~crc16(frame)) & 0xFFFF
    return frame + bytes([c & 0xFF, c >> 8])


# ------------------------------------------------------------------ self-test vs ROM code
def selftest(n=200):
    from sh2_mini import SH2
    rom = ROM.read_bytes()
    assert struct.unpack_from(">I", rom, 0x5FE0)[0] == SCODE
    rng = random.Random(9)
    bad = 0

    def cpu():
        return SH2(rom)

    vectors = []
    for i in range(n):
        seed = rng.getrandbits(32)
        # app 0x31B4A: seed at 0xFFFF5A6C, expected key -> 0xFFFF8448
        c = cpu(); c.wl(0xFFFF5A6C, seed); c.call(0x31B4A)
        k_rom = c.rl(0xFFFF8448)
        k_py = enc1(seed, S27K)
        bad += k_rom != k_py
        if i < 3:
            vectors.append(("app key 0x31B4A", f"seed {seed:08X}", f"key {k_rom:08X}"))

        # boot CRC 0x1490 over n bytes
        buf = bytes(rng.getrandbits(8) for _ in range(rng.randint(1, 140)))
        c = cpu()
        for j, x in enumerate(buf):
            c.wb(0xFFFF6000 + j, x)
        crc_rom = c.call(0x1490, (0xFFFF6000, len(buf))) & 0xFFFF
        bad += crc_rom != crc16(buf)

        # boot seed 0x1EAC: R in r4, T = low word of u32 @0xFFFFF430
        R, T = rng.getrandbits(16), rng.getrandbits(16)
        c = cpu(); c.wl(0xFFFFF430, T)
        s_rom = c.call(0x1EAC, (R,))
        bad += s_rom != boot_seed(R, T)

        # boot key 0x1F00(r4=R, r5=seed, r6=W)
        W = 0xFFFF if i % 2 else rng.getrandbits(16)
        c = cpu()
        k2_rom = c.call(0x1F00, (R, s_rom, W))
        k2_py = boot_key(R, s_rom, W)
        bad += k2_rom != k2_py
        if i < 2:
            vectors.append(("boot seed 0x1EAC", f"R {R:04X} T {T:04X}", f"seed {s_rom:08X}"))
            vectors.append(("boot key 0x1F00", f"R {R:04X} seed {s_rom:08X} W {W:04X}", f"key {k2_rom:08X}"))

        # boot decode 0x42B0(r4=src, r5=dst, r6=len, r7=scode)
        plain = [rng.getrandbits(32) for _ in range(4)]
        enc = b"".join(struct.pack(">I", enc1(p, SCODE)) for p in plain)
        c = cpu()
        for j, x in enumerate(enc):
            c.wb(0xFFFF6100 + j, x)
        c.call(0x42B0, (0xFFFF6100, 0xFFFF6200, len(enc), SCODE))
        out = bytes(c.rb(0xFFFF6200 + j) for j in range(len(enc)))
        bad += out != b"".join(struct.pack(">I", p) for p in plain)
        if i == 0:
            vectors.append(("boot decode 0x42B0", f"enc1({plain[0]:08X}, scode) = {enc1(plain[0], SCODE):08X}",
                            f"ROM decodes to {struct.unpack_from('>I', out)[0]:08X}"))
    return bad, vectors


if __name__ == "__main__":
    bad, vec = selftest()
    for name, inp, out in vec:
        print(f"{name:20} {inp:40} -> {out}")
    fr = frame_crc(bytes.fromhex("3482008200 80".replace(" ", "")) + bytes(128))
    print(f"frame residue check: crc16(frame+~crc) = {crc16(fr):04X} (boot expects F0B8)")
    print("ROM routines vs Python:", "all match" if bad == 0 else f"{bad} MISMATCHES")
    sys.exit(1 if bad else 0)
