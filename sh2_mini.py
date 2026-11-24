"""Minimal big-endian SH-2 interpreter, just enough to execute small leaf routines of the
9CJ3A ROM (key, CRC and decode routines) so their outputs can be used as test vectors.

Only the opcodes those routines use are implemented; anything else raises. Not a
general emulator: no exceptions, interrupts, FPU or peripherals.
"""
import struct

M32 = 0xFFFFFFFF
SENTINEL = 0xDEAD0000


def s32(x):
    x &= M32
    return x - (1 << 32) if x & 0x80000000 else x


def sx8(x):
    x &= 0xFF
    return x - 0x100 if x & 0x80 else x


def sx16(x):
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


class SH2:
    def __init__(self, rom):
        self.rom = rom
        self.ram = {}
        self.r = [0] * 16
        self.t = 0
        self.q = self.m = 0
        self.pr = self.macl = self.mach = self.gbr = self.vbr = 0
        self.sr_rest = 0xF0

    # ---- memory
    def rb(self, a):
        a &= M32
        if a < len(self.rom):
            return self.rom[a]
        return self.ram.get(a, 0)

    def wb(self, a, v):
        a &= M32
        if a < len(self.rom):
            raise RuntimeError(f"write to ROM {a:#x}")
        self.ram[a] = v & 0xFF

    def rw(self, a):
        return (self.rb(a) << 8) | self.rb(a + 1)

    def rl(self, a):
        return (self.rw(a) << 16) | self.rw(a + 2)

    def ww(self, a, v):
        self.wb(a, v >> 8)
        self.wb(a + 1, v)

    def wl(self, a, v):
        self.ww(a, (v >> 16) & 0xFFFF)
        self.ww(a + 2, v & 0xFFFF)

    # ---- run
    def call(self, addr, args=(), sp=0xFFFF7F00, max_steps=2_000_000):
        for i, v in enumerate(args):
            self.r[4 + i] = v & M32
        self.r[15] = sp
        self.pr = SENTINEL
        pc = addr
        steps = 0
        while pc != SENTINEL:
            pc = self.step(pc)
            steps += 1
            if steps > max_steps:
                raise RuntimeError("step limit")
        return self.r[0]

    def step(self, pc, in_delay=False):
        op = self.rw(pc)
        n = (op >> 8) & 15
        m = (op >> 4) & 15
        r = self.r
        nxt = pc + 2
        hi = op >> 12
        lo4 = op & 15
        lo8 = op & 0xFF

        def delay(target):
            self.step(pc + 2, True)
            return target

        if hi == 0x6:
            if lo4 == 0x3: r[n] = r[m]
            elif lo4 == 0x0: r[n] = sx8(self.rb(r[m])) & M32
            elif lo4 == 0x1: r[n] = sx16(self.rw(r[m])) & M32
            elif lo4 == 0x2: r[n] = self.rl(r[m])
            elif lo4 == 0x4: r[n] = sx8(self.rb(r[m])) & M32; r[m] = (r[m] + 1) & M32 if n != m else r[n]
            elif lo4 == 0x6: v = self.rl(r[m]); r[m] = (r[m] + 4) & M32; r[n] = v
            elif lo4 == 0x9: r[n] = (((r[m] & 0xFFFF) << 16) | (r[m] >> 16)) & M32  # swap.w
            elif lo4 == 0xB: r[n] = (-r[m]) & M32
            elif lo4 == 0xC: r[n] = r[m] & 0xFF
            elif lo4 == 0xD: r[n] = r[m] & 0xFFFF
            elif lo4 == 0xE: r[n] = sx8(r[m]) & M32
            elif lo4 == 0xF: r[n] = sx16(r[m]) & M32
            else: raise NotImplementedError(f"{op:04x} @{pc:#x}")
        elif hi == 0x2:
            if lo4 == 0x0: self.wb(r[n], r[m])
            elif lo4 == 0x1: self.ww(r[n], r[m] & 0xFFFF)
            elif lo4 == 0x2: self.wl(r[n], r[m])
            elif lo4 == 0x6: r[n] = (r[n] - 4) & M32; self.wl(r[n], r[m])
            elif lo4 == 0x7:
                self.q = (r[n] >> 31) & 1; self.m = (r[m] >> 31) & 1; self.t = int(self.q != self.m)
            elif lo4 == 0x8: self.t = int((r[n] & r[m]) == 0)
            elif lo4 == 0x9: r[n] &= r[m]
            elif lo4 == 0xA: r[n] ^= r[m]
            elif lo4 == 0xB: r[n] |= r[m]
            elif lo4 == 0xD: r[n] = ((r[m] & 0xFFFF) << 16 | (r[n] >> 16)) & M32
            elif lo4 == 0xE: self.macl = ((r[n] & 0xFFFF) * (r[m] & 0xFFFF)) & M32
            elif lo4 == 0xF: self.macl = (sx16(r[n]) * sx16(r[m])) & M32
            else: raise NotImplementedError(f"{op:04x} @{pc:#x}")
        elif hi == 0x3:
            a, b = r[n], r[m]
            if lo4 == 0x0: self.t = int(a == b)
            elif lo4 == 0x2: self.t = int(a >= b)
            elif lo4 == 0x3: self.t = int(s32(a) >= s32(b))
            elif lo4 == 0x4: self._div1(n, m)
            elif lo4 == 0x6: self.t = int(a > b)
            elif lo4 == 0x7: self.t = int(s32(a) > s32(b))
            elif lo4 == 0x8: r[n] = (a - b) & M32
            elif lo4 == 0xC: r[n] = (a + b) & M32
            else: raise NotImplementedError(f"{op:04x} @{pc:#x}")
        elif hi == 0x4:
            if lo8 == 0x00: self.t = r[n] >> 31; r[n] = (r[n] << 1) & M32
            elif lo8 == 0x01: self.t = r[n] & 1; r[n] >>= 1
            elif lo8 == 0x08: r[n] = (r[n] << 2) & M32
            elif lo8 == 0x09: r[n] >>= 2
            elif lo8 == 0x18: r[n] = (r[n] << 8) & M32
            elif lo8 == 0x19: r[n] >>= 8
            elif lo8 == 0x28: r[n] = (r[n] << 16) & M32
            elif lo8 == 0x29: r[n] >>= 16
            elif lo8 == 0x11: self.t = int(s32(r[n]) >= 0)
            elif lo8 == 0x15: self.t = int(s32(r[n]) > 0)
            elif lo8 == 0x24: c = r[n] >> 31; r[n] = ((r[n] << 1) | self.t) & M32; self.t = c
            elif lo8 == 0x10: r[n] = (r[n] - 1) & M32; self.t = int(r[n] == 0)
            elif lo8 == 0x22: r[n] = (r[n] - 4) & M32; self.wl(r[n], self.pr)
            elif lo8 == 0x12: r[n] = (r[n] - 4) & M32; self.wl(r[n], self.macl)
            elif lo8 == 0x13: r[n] = (r[n] - 4) & M32; self.wl(r[n], self.gbr)
            elif lo8 == 0x26: self.pr = self.rl(r[n]); r[n] = (r[n] + 4) & M32
            elif lo8 == 0x16: self.macl = self.rl(r[n]); r[n] = (r[n] + 4) & M32
            elif lo8 == 0x17: self.gbr = self.rl(r[n]); r[n] = (r[n] + 4) & M32
            elif lo8 == 0x1E: self.gbr = r[n]
            elif lo8 == 0x1A: self.macl = r[n]
            elif lo8 == 0x0A: self.mach = r[n]
            elif lo8 == 0x0B: tgt = r[n]; self.pr = pc + 4; return delay(tgt)
            elif lo8 == 0x2B: return delay(r[n])
            else: raise NotImplementedError(f"{op:04x} @{pc:#x}")
        elif hi == 0x0:
            if op == 0x000B: return delay(self.pr)
            if op == 0x0009: pass
            elif op == 0x0019: self.q = self.m = self.t = 0
            elif lo4 == 0xA and m == 1: r[n] = self.macl
            elif lo4 == 0xC: r[n] = sx8(self.rb(r[0] + r[m])) & M32
            elif lo4 == 0xD: r[n] = sx16(self.rw(r[0] + r[m])) & M32
            elif lo4 == 0x4: self.wb(r[0] + r[n], r[m])
            elif lo4 == 0x5: self.ww(r[0] + r[n], r[m] & 0xFFFF)
            elif lo4 == 0x7: self.macl = (r[n] * r[m]) & M32
            elif lo8 == 0x12: r[n] = self.gbr
            else: raise NotImplementedError(f"{op:04x} @{pc:#x}")
        elif hi == 0x7: r[n] = (r[n] + sx8(op)) & M32
        elif hi == 0xE: r[n] = sx8(op) & M32
        elif hi == 0x9: r[n] = sx16(self.rw(pc + 4 + lo8 * 2)) & M32
        elif hi == 0xD: r[n] = self.rl(((pc + 4) & ~3) + lo8 * 4)
        elif hi == 0x5: r[n] = self.rl(r[m] + lo4 * 4)
        elif hi == 0x1: self.wl(r[n] + lo4 * 4, r[m])
        elif hi == 0x8:
            sub = n
            if sub == 0x0: self.wb(r[m] + lo4, r[0])
            elif sub == 0x1: self.ww(r[m] + lo4 * 2, r[0] & 0xFFFF)
            elif sub == 0x4: r[0] = sx8(self.rb(r[m] + lo4)) & M32
            elif sub == 0x5: r[0] = sx16(self.rw(r[m] + lo4 * 2)) & M32
            elif sub == 0x8: self.t = int(r[0] == (sx8(op) & M32))
            elif sub in (0x9, 0xB, 0xD, 0xF):
                tgt = pc + 4 + sx8(op) * 2
                take = (self.t == 1) if sub in (0x9, 0xD) else (self.t == 0)
                if sub in (0xD, 0xF):
                    self.step(pc + 2, True)
                    return tgt if take else pc + 4
                return tgt if take else nxt
            else: raise NotImplementedError(f"{op:04x} @{pc:#x}")
        elif hi == 0xA:
            d = op & 0xFFF
            d = d - 0x1000 if d & 0x800 else d
            return delay(pc + 4 + d * 2)
        elif hi == 0xB:
            d = op & 0xFFF
            d = d - 0x1000 if d & 0x800 else d
            self.pr = pc + 4
            return delay(pc + 4 + d * 2)
        elif hi == 0xC:
            sub = n
            if sub == 0x8: self.t = int((r[0] & lo8) == 0)
            elif sub == 0x9: r[0] &= lo8
            elif sub == 0xB: r[0] |= lo8
            elif sub == 0xA: r[0] ^= lo8
            elif sub == 0x4: r[0] = sx8(self.rb(self.gbr + lo8)) & M32
            elif sub == 0x0: self.wb(self.gbr + lo8, r[0])
            else: raise NotImplementedError(f"{op:04x} @{pc:#x}")
        else:
            raise NotImplementedError(f"{op:04x} @{pc:#x}")
        return nxt

    def _div1(self, n, m):
        r = self.r
        old_q = self.q
        self.q = (r[n] >> 31) & 1
        tmp2 = r[m]
        r[n] = ((r[n] << 1) | self.t) & M32
        if old_q == 0:
            if self.m == 0:
                tmp0 = r[n]; r[n] = (r[n] - tmp2) & M32; tmp1 = int(r[n] > tmp0)
                self.q = tmp1 if self.q == 0 else int(tmp1 == 0)
            else:
                tmp0 = r[n]; r[n] = (r[n] + tmp2) & M32; tmp1 = int(r[n] < tmp0)
                self.q = int(tmp1 == 0) if self.q == 0 else tmp1
        else:
            if self.m == 0:
                tmp0 = r[n]; r[n] = (r[n] + tmp2) & M32; tmp1 = int(r[n] < tmp0)
                self.q = tmp1 if self.q == 0 else int(tmp1 == 0)
            else:
                tmp0 = r[n]; r[n] = (r[n] - tmp2) & M32; tmp1 = int(r[n] > tmp0)
                self.q = int(tmp1 == 0) if self.q == 0 else tmp1
        self.t = int(self.q == self.m)
