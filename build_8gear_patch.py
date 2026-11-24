#!/usr/bin/env python3
"""Build the 8-forward-gear patch (decision D-N5) for the Frontier/Xterra ECM
23710-9CF0A, software 9CJ3A (SH7058, 1 MB), and recompute its checksums.

Desk-side only: this script never talks to the ECM.

    python3 build_8gear_patch.py --selftest          # checksum fixer vs the stock dump
    python3 build_8gear_patch.py                     # build dumps/dh1_9CJ3A_8gear.bin
    python3 build_8gear_patch.py --list              # print every edit

Every edit asserts the stock bytes first, so the script refuses any other
software version. See 8gear_patch_spec.md for the evidence behind each site.
"""
import argparse
import math
import hashlib
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STOCK = HERE / "dumps" / "dh1_9CJ3A_pass1.bin"
OUT = HERE / "dumps" / "dh1_9CJ3A_8gear.bin"
STOCK_SHA256 = "7972aa88ba98880fc0942f6496ed08327b1b7f3c9a3148b38676b382f161e1ad"
ROM_SIZE = 0x100000

# ---------------------------------------------------------------- checksums
# Four checksums, all reproduced from the stock image (see --selftest):
#  ROM16_A  word @0x20000 = 16-bit word sum of 0x20002..0xFFFFF   (boot code 0x2AC2)
#  ROM16_B  word @0x8200  = 16-bit word sum of 0x8202..0x1FFFF    (boot code 0x2AC2)
#  ALT      u32 @0x20404 = sum32, u32 @0x20408 = xor32 of block 0x2040C..0x221A7
#           (nissutils nisrom "alt cks", block 0x2040C-0x221A4 rounded up to u32)
#  ALT2     u32 @0x96E0 = sum32, u32 @0x96D8 = xor32 of all u32 in 0x8204..0xFFFFF
#           except the u32 @0x20000 and the two result words themselves
#           (nissutils checksum_alt2 from ECUREC 0x8204, skip = IVT2-4)
# Dependencies: ALT block -> inside ROM16_A; ALT words -> inside ALT2 and ROM16_A;
# ALT2 words -> inside ROM16_B. So fix in the order ALT, ROM16_A, ALT2, ROM16_B.
ALT_START, ALT_END, ALT_S, ALT_X = 0x2040C, 0x221A4, 0x20404, 0x20408
ALT2_START, ALT2_SKIP, ALT2_S, ALT2_X = 0x8204, 0x20000, 0x96E0, 0x96D8
A_WORD, A_START, A_END = 0x20000, 0x20002, 0x100000
B_WORD, B_START, B_END = 0x8200, 0x8202, 0x20000


def u32(b, a):
    return struct.unpack_from(">I", b, a)[0]


def sum16(b, start, end):
    return sum(struct.unpack_from(">%dH" % ((end - start) // 2), b, start)) & 0xFFFF


def sum_xor32(b, start, end, skip=()):
    s = x = 0
    for a in range(start, end, 4):
        if a in skip:
            continue
        w = u32(b, a)
        s = (s + w) & 0xFFFFFFFF
        x ^= w
    return s, x


def alt_block_end():
    # nisrom validate_altcks(): size = (((end + 1) - start) & ~3) + 4
    return ALT_START + ((((ALT_END + 1) - ALT_START) & ~3) + 4)


def compute_checksums(b):
    """Return the four checksum values as they should be stored for image b,
    computed in dependency order on a working copy."""
    w = bytearray(b)
    s, x = sum_xor32(w, ALT_START, alt_block_end())
    struct.pack_into(">II", w, ALT_S, s, x)
    struct.pack_into(">H", w, A_WORD, sum16(w, A_START, A_END))
    s2, x2 = sum_xor32(w, ALT2_START, ROM_SIZE, skip=(ALT2_SKIP, ALT2_S, ALT2_X))
    struct.pack_into(">I", w, ALT2_S, s2)
    struct.pack_into(">I", w, ALT2_X, x2)
    struct.pack_into(">H", w, B_WORD, sum16(w, B_START, B_END))
    return w


def check_report(b, label):
    ok = True
    s, x = sum_xor32(b, ALT_START, alt_block_end())
    r = [("ALT sum  @0x20404", u32(b, ALT_S), s), ("ALT xor  @0x20408", u32(b, ALT_X), x)]
    s2, x2 = sum_xor32(b, ALT2_START, ROM_SIZE, skip=(ALT2_SKIP, ALT2_S, ALT2_X))
    r += [("ALT2 sum @0x96E0 ", u32(b, ALT2_S), s2), ("ALT2 xor @0x96D8 ", u32(b, ALT2_X), x2)]
    r += [("ROM16_A  @0x20000", struct.unpack_from(">H", b, A_WORD)[0], sum16(b, A_START, A_END)),
          ("ROM16_B  @0x8200 ", struct.unpack_from(">H", b, B_WORD)[0], sum16(b, B_START, B_END))]
    print(f"[{label}]")
    for name, stored, calc in r:
        good = stored == calc
        ok &= good
        print(f"  {name} stored {stored:08X} computed {calc:08X} {'OK' if good else 'MISMATCH'}")
    return ok


# ---------------------------------------------------------------- the patch
# 8HP ratios x1024 (docs/reference/8hp70-landrover-l320-overview.md in 8hp-tcu-open):
# 4.714 3.143 2.106 1.667 1.285 1.000 0.839 0.667. Stock 5th 0.839 = 0x035B, same scale.
RATIOS_8HP = [4.714, 3.143, 2.106, 1.667, 1.285, 1.000, 0.839, 0.667]
RATIO_WORDS = [round(r * 1024) for r in RATIOS_8HP]

FREE_BASE = 0x19900          # inside the erased area 0x1988C..0x1FFFF
NEW = {                      # new gear-indexed tables in free space
    "F700x8": FREE_BASE + 0x00,
    "F705x8": FREE_BASE + 0x08,
    "F70Ax8": FREE_BASE + 0x10,
    "F70Fx8": FREE_BASE + 0x18,
    "10409x7": FREE_BASE + 0x20,
    "F9C1x7": FREE_BASE + 0x28,
    "F9BCx8": FREE_BASE + 0x30,
    "912Cx6": FREE_BASE + 0x38,   # 6 words
    "F7B0ax": FREE_BASE + 0x44,   # 4-byte gear axis
}
FREE_USED_END = FREE_BASE + 0x48

# ---- 8HP70 calibration ("match all per-gear values to the 8HP70", user 2026-11-23)
# The stock calibration is for the RE5R05A. Each 8HP gear takes the stock value of the RE5 gear
# with the nearest ratio (log distance) unless the table is provably ratio-derived, in which case
# it is recomputed from the true 8HP ratio (value x ratio = constant in the stock data).
RATIOS_RE5 = [3.842, 2.353, 1.529, 1.000, 0.839]
NEAREST = [min(range(5), key=lambda k: abs(math.log(r / RATIOS_RE5[k]))) for r in RATIOS_8HP]
assert NEAREST == [0, 0, 1, 2, 2, 3, 4, 4]


def extend(stock, src, n_stock, n_new):
    """8 (or 7) entries from a stock 5- (or 4-) entry gear table by nearest ratio. For the
    4-entry upshift tables (index = target gear - 2) the stock entry for the RE5 upshift into
    the nearest-ratio gear is used (into 1st does not exist: the 1-2 entry)."""
    vals = list(stock[src:src + n_stock])
    if n_stock == 5:
        return bytes(vals[NEAREST[g]] for g in range(n_new))
    if n_stock == 4 and n_new == 7:      # upshift into 8HP gear g = 2..8
        return bytes(vals[max(NEAREST[g - 1], 1) - 1] for g in range(2, 9))
    raise ValueError


def inv_ratio_interp(stock_vals):
    """Ratio-derived per-gear words: piecewise-linear in 1/ratio through the five stock points
    (exact where the 8HP shares a ratio: 1.000 and 0.839), end segments extrapolated."""
    xs = [1 / r for r in RATIOS_RE5]
    out = []
    for r in RATIOS_8HP:
        x = 1 / r
        k = 0 if x <= xs[1] else (3 if x >= xs[3] else max(i for i in range(4) if xs[i] <= x))
        v = stock_vals[k] + (stock_vals[k + 1] - stock_vals[k]) * (x - xs[k]) / (xs[k + 1] - xs[k])
        out.append(max(0, min(0xFFFF, round(v))))
    return out


def remap_matrix(old):
    """8x8 shift matrix [engaged][target] (stock non-zero only on upshifts from 1st-3rd).
    8HP shift i->j takes the RE5 shift NEAREST[i]->NEAREST[j]; when both map to the same RE5
    gear, the adjacent RE5 shift in the same direction."""
    new = [[0] * 8 for _ in range(8)]
    for i in range(8):
        for j in range(8):
            a, b = NEAREST[i], NEAREST[j]
            if i < j and b <= a:
                b = a + 1
            elif i > j and b >= a:
                b = a - 1
            new[i][j] = old[a][b] if 0 <= b <= 4 else 0
    return new


def edits(stock):
    """List of (address, old bytes, new bytes, site id, description)."""
    E = []

    def e(addr, old, new, site, desc):
        E.append((addr, bytes(old), bytes(new), site, desc))

    def lit(addr, old, new, site, desc):
        e(addr, struct.pack(">I", old), struct.pack(">I", new), site, desc)

    # S1/S2 - 0x174 decoder (handler 0xE297C area): accept nibble 8.
    e(0xE26E8, b"\xE6\x08", b"\xE6\x09", "S1", "target-gear nibble limit: mov #8,r6 -> mov #9,r6")
    e(0xE2826, b"\xE2\x08", b"\xE2\x09", "S2", "engaged-gear nibble limit: mov #8,r2 -> mov #9,r2")
    # S3/S4 - classification chains: replace the '==1 / ==2' tests with a 1..8 range test.
    #   add #-1,r0 ; tst #0xF8,r0 ; bt <in-gear target> ; add #1,r0
    e(0xE271A, bytes.fromhex("88018917880289 15".replace(" ", "")),
      bytes.fromhex("70FFC8F8891670 01".replace(" ", "")), "S3",
      "chain -> 0xFFFF283F: nibbles 1..8 -> class 0 (was 1..7; 8 left the cell stale)")
    e(0xE2760, bytes.fromhex("88018939880289 37".replace(" ", "")),
      bytes.fromhex("70FFC8F8893870 01".replace(" ", "")), "S4",
      "chain -> 0xFFFF2620: nibbles 1..8 -> 8 (was 1..7; 8 left the cell stale)")

    # R1..R4 - the four users of the 5-entry ratio table 0x1247E -> 8-entry 0x12488, clamp 7.
    for site, pool, clamps in (
        ("R1", 0x44EBC, [(0x44E1A, 0xEA), (0x44E26, 0xE6)]),
        ("R2", 0x4E6B8, [(0x4E4AE, 0xE4), (0x4E4B6, 0xE6)]),
        ("R3", 0x9B838, [(0x9B78A, 0xE2), (0x9B792, 0xE6)]),
        ("R4", 0xF18C0, [(0xF16F2, 0xE2), (0xF16F8, 0xE6)]),
    ):
        lit(pool, 0x0001247E, 0x00012488, site, "ratio table literal 0x1247E -> 0x12488")
        for a, op in clamps:
            e(a, bytes([op, 0x04]), bytes([op, 0x07]), site, "gear clamp mov #4 -> mov #7")

    # B1 - four 5-byte tables at 0xF700/05/0A/0F (function 0x67A5C, index 0xFFFF108E).
    for name, src, pool in (("F70Fx8", 0xF70F, 0x67CA0), ("F705x8", 0xF705, 0x67CA4),
                            ("F70Ax8", 0xF70A, 0x67CB0), ("F700x8", 0xF700, 0x67CB4)):
        lit(pool, src, NEW[name], "B1", f"byte table 0x{src:X} (5) -> 0x{NEW[name]:X} (8)")
        e(NEW[name], b"\xFF" * 8, extend(stock, src, 5, 8), "B1", f"new table {name}")
    e(0x67A7C, b"\xE5\x04", b"\xE5\x07", "B1", "gear clamp mov #4,r5 -> #7")
    e(0x67A84, b"\xE6\x04", b"\xE6\x07", "B1", "gear clamp mov #4,r6 -> #7")

    # T1 - torque-cut scaling (0x177 B4, function 0x68E62): upshift tables by target gear.
    lit(0x69054, 0x10409, NEW["10409x7"], "T1", "upshift 1st-step table 0x10409 (4) -> 7")
    e(NEW["10409x7"], b"\xFF" * 8, extend(stock, 0x10409, 4, 7) + b"\xFF", "T1", "new table 10409x7")
    lit(0x69058, 0xF9C1, NEW["F9C1x7"], "T1", "upshift table 0xF9C1 (4) -> 7")
    e(NEW["F9C1x7"], b"\xFF" * 8, extend(stock, 0xF9C1, 4, 7) + b"\xFF", "T1", "new table F9C1x7")
    e(0x68F14, b"\xE4\x04", b"\xE4\x07", "T1", "target clamp mov #4,r4 -> #7")
    e(0x68F1A, b"\xE6\x04", b"\xE6\x07", "T1", "target clamp mov #4,r6 -> #7")
    lit(0x69060, 0xF9BC, NEW["F9BCx8"], "T2", "table 0xF9BC (5, index 1..4) -> 8 (index 1..7)")
    e(NEW["F9BCx8"], b"\xFF" * 8, extend(stock, 0xF9BC, 5, 8), "T2", "new table F9BCx8")
    e(0x68F8E, b"\xE4\x04", b"\xE4\x07", "T2", "target clamp mov #4,r4 -> #7")
    e(0x68F96, b"\xE2\x04", b"\xE2\x07", "T2", "target clamp mov #4,r2 -> #7")

    # G1 - 0xF0ED8 per-gear word table 0x912C: index 7 (8th) was aborted (mov #1,r14). The
    #      7th/8th lookup 0xF0FD4-0xF0FE3 is rewritten so 8th has its own cell:
    #        f0fd4 mov.l @(0xF11C8),r1   base 0x912C (moved ahead of the compare)
    #        f0fd6 cmp/eq #6,r0
    #        f0fd8 bf 0xf0fe0
    #        f0fda mov.w @(12,r1),r0     7th: entry 6 (stock)
    #        f0fdc bra 0xf0fe4           (unchanged: also the landing point of cases 1-5)
    #        f0fde mov r0,r6             (unchanged)
    #        f0fe0 mov.w @(10,r1),r0     8th: 0x9136, free since P2 moved gears 1-6 away
    #        f0fe2 mov r0,r6             falls into f0fe4 with r14 = 0
    e(0xF0FD4, bytes.fromhex("88068b03d17b8516a0026603e600ee01"),
      bytes.fromhex("d17c88068b028516a00266038515660 3".replace(" ", "")), "G1",
      "7th/8th lookup: 8th reads its own cell 0x9136 instead of aborting")
    # G2 - 0x52998 gear class -> 0xFFFF2282: target >= 6th fell through and held the
    #      stale value; now classed like 4th/5th: 'bf 0x529d0' after 'cmp/eq #4,r0' -> nop.
    e(0x529C2, b"\x8B\x05", b"\x00\x09", "G2", "bf 0x529d0 -> nop (6th..8th classed like 4th/5th)")

    # K1/K2 - calibration.
    e(0x86B8, b"\x05", b"\x08", "K1", "gear-number window max (0xFFFF1505 in 0x86B9..0x86B8) 5 -> 8")
    for tab in (0x12488, 0x141A6):
        e(tab, stock[tab:tab + 16], struct.pack(">8H", *RATIO_WORDS), "K2",
          f"8-entry ratio table 0x{tab:X} -> 8HP ratios")
    # K3 - function 0x7B900 / 0x7BA.. reads ratio[5] of 0x12488 directly (0x12492, stock
    #      0.839 = top gear). With K2 that cell becomes 1.000, so point it at ratio[6]
    #      (8HP 7th = 0.839): the value read stays byte-identical to stock.
    lit(0x7BA0C, 0x12492, 0x12494, "K3", "hard-coded ratio[5] -> ratio[6] (keeps 0.839)")
    lit(0x7BC70, 0x12492, 0x12494, "K3", "hard-coded ratio[5] -> ratio[6] (keeps 0.839)")

    # ---- P: 8HP70 per-gear calibration (nearest-ratio map NEAREST = RE5 1,1,2,3,3,4,5,5)
    def words(a, n):
        return list(struct.unpack_from(">%dH" % n, stock, a))

    # P1 ratio-derived (value x ratio = const in stock): 0x112C2 / 0x112D2 in place
    for tab in (0x112C2, 0x112D2):
        e(tab, stock[tab:tab + 16], struct.pack(">8H", *inv_ratio_interp(words(tab, 5))), "P1",
          f"per-gear 0x{tab:X} (= K/ratio) recomputed for 8HP ratios")
    # P2 0x912C (= 37 467/ratio): gears 1-6 from a new table via the F0FD0 literal; 7th keeps
    #    the stock entry 6 (0.839 -> 0xAE70, exact). 8th has its own cell 0x9136 (old entry 5, no
    #    longer read since the F0FD0 repoint; read by the G1 code for index 7), deliberately left
    #    at the stock 0xAE70 (user decision B, 2026-11-23): the value latches at the highest gear
    #    reached and scales a minimum-torque floor (0xFFFF45C8, used at 0x7AE70 / 0x7A704), so
    #    capping 8th at 0.839 keeps that floor at its stock magnitude. The true 8th value would be
    #    0xDB6C (37 467 / 0.667), giving a floor about 25 % higher.
    v912 = inv_ratio_interp(words(0x912C, 5))
    lit(0xF0FD0, 0x912C, NEW["912Cx6"], "P2", "0x912C gears 1-6 -> new table (K/ratio)")
    e(NEW["912Cx6"], b"\xFF" * 12, struct.pack(">6H", *v912[:6]), "P2", "new table 912Cx6")
    assert stock[0x9136:0x9138] == b"\xAE\x70"     # 8th cell = stock AE70 (cap, decision B)
    # P3 nearest-ratio, in place: per-gear limit 0x11772
    e(0x11772, stock[0x11772:0x11782],
      struct.pack(">8H", *[words(0x11772, 5)[NEAREST[g]] for g in range(8)]), "P3",
      "per-gear words 0x11772 by nearest ratio")
    # P4 8x8 shift matrices [engaged][target] 0xB314 (bytes) / 0xE48C (words)
    oldb = [list(stock[0xB314 + 8 * r:0xB314 + 8 * r + 8]) for r in range(8)]
    e(0xB314, stock[0xB314:0xB354], bytes(sum(remap_matrix(oldb), [])), "P4", "8x8 byte matrix 0xB314 remapped")
    oldw = [words(0xE48C + 16 * r, 8) for r in range(8)]
    e(0xE48C, stock[0xE48C:0xE50C], struct.pack(">64H", *sum(remap_matrix(oldw), [])), "P4",
      "8x8 word matrix 0xE48C remapped")
    # P5 target-gear axis of the 4x4 maps 0xB374/B384/B394 (function 0x7F2AC): own axis
    #    [1,2,3,5] so 8HP 1-2 -> RE5 1st row, 3 -> 2nd, 4 -> 3rd, 5 -> between 3rd/4th, 6-8 -> 4th+
    #    row. 0xF7B0 itself stays (also used by 0x7F9C2 with input 0xFFFF261D, not a gear).
    lit(0x7F37C, 0xF7B0, NEW["F7B0ax"], "P5", "gear axis 0xF7B0 -> own 8HP axis")
    e(NEW["F7B0ax"], b"\xFF" * 4, bytes([1, 2, 3, 5]), "P5", "new axis 1,2,3,5")
    # P6 per-gear byte list 0xFF8F, indexed by the 0xFF80 gear-list search (idx = gear-1, 1st->0)
    e(0xFF8F, stock[0xFF8F:0xFF97],
      bytes(stock[0xFF8F + NEAREST[g]] for g in range(8)), "P6", "per-gear bytes 0xFF8F by nearest ratio")
    # P7 top-gear test 0x7BABC (stock: engaged & target >= 5th): RE5 5th = 8HP 7th/8th
    e(0x7BABC, b"\xE4\x04", b"\xE4\x06", "P7", "top-gear threshold index 4 -> 6 (>= 7th)")
    e(0x7BACC, b"\x88\x04", b"\x88\x06", "P7", "cmp/eq #4 -> #6")
    e(0x7BAD2, b"\x89\x08", b"\x00\x09", "P7", "8th treated like 7th (both = RE5 5th): bt -> nop")
    return E


def apply(stock):
    img = bytearray(stock)
    E = edits(stock)
    for addr, old, new, site, desc in E:
        cur = bytes(img[addr:addr + len(old)])
        if cur != old:
            sys.exit(f"{site} @0x{addr:X}: expected {old.hex()} found {cur.hex()} - wrong software?")
        img[addr:addr + len(new)] = new
    # every byte outside the listed edits must still be stock
    touched = set()
    for addr, old, new, *_ in E:
        touched.update(range(addr, addr + len(new)))
    return img, E, touched


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stock", type=Path, default=STOCK)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--selftest", action="store_true", help="only check the fixer against the stock image")
    ap.add_argument("--list", action="store_true", help="print the edits and exit")
    a = ap.parse_args()

    stock = a.stock.read_bytes()
    if len(stock) != ROM_SIZE:
        sys.exit("stock image must be 1 MB")
    sha = hashlib.sha256(stock).hexdigest()
    if sha != STOCK_SHA256:
        sys.exit(f"stock SHA-256 {sha} != expected 9CJ3A dump")

    # 1) the fixer must reproduce the stock checksums byte for byte
    ok = check_report(stock, "stock as dumped")
    refixed = compute_checksums(stock)
    same = bytes(refixed) == stock
    print(f"  fixer re-run on stock reproduces the image byte for byte: {same}")
    if not (ok and same):
        sys.exit("checksum model does not reproduce the stock image - stop")
    if a.selftest:
        return

    if any(b != 0xFF for b in stock[0x1988C:0x20000]):
        sys.exit("free space 0x1988C..0x1FFFF is not erased")

    img, E, touched = apply(stock)
    if a.list:
        for addr, old, new, site, desc in E:
            print(f"{site:3} 0x{addr:05X}  {old.hex():>16} -> {new.hex():<16} {desc}")
        return
    img = compute_checksums(img)
    if not check_report(img, "patched"):
        sys.exit("patched image checksums inconsistent")

    ck = {ALT_S, ALT_S + 1, ALT_S + 2, ALT_S + 3, ALT_X, ALT_X + 1, ALT_X + 2, ALT_X + 3,
          ALT2_S, ALT2_S + 1, ALT2_S + 2, ALT2_S + 3, ALT2_X, ALT2_X + 1, ALT2_X + 2, ALT2_X + 3,
          A_WORD, A_WORD + 1, B_WORD, B_WORD + 1}
    diff = [i for i in range(ROM_SIZE) if img[i] != stock[i]]
    stray = [i for i in diff if i not in touched and i not in ck]
    if stray:
        sys.exit(f"unexpected changed bytes: {[hex(i) for i in stray[:10]]}")
    if any(i < 0x8200 for i in diff):
        sys.exit("patch touches the boot block (< 0x8200) - not reflashable")
    a.out.write_bytes(img)
    print(f"{len(E)} edits, {len(diff)} bytes differ from stock (incl. checksums); "
          f"free space used 0x{FREE_BASE:X}..0x{FREE_USED_END - 1:X}")
    print(f"wrote {a.out}  SHA-256 {hashlib.sha256(img).hexdigest()}")


if __name__ == "__main__":
    main()
