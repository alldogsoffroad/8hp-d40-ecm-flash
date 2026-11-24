# 8-forward-gear ECM patch: spec (D-N5)

ECM 23710-9CF0A (DH1), software **9CJ3A**, SH7058, 1 MB. Stock image `dumps/dh1_9CJ3A_pass1.bin`
(SHA-256 `7972aa88…61e1ad`). Builder: `build_8gear_patch.py` → `dumps/dh1_9CJ3A_8gear.bin`
(SHA-256 `0c2c2691c9dee6b393ad4a5a8429b69646405aad43d7b78dfda1942ae816cce6`, with the 8HP70 calibration below), edit list
`dumps/8gear_edits.txt`. Written 2026-11-23. **This image is flashed on the bench ECM and verified by read-back** (`ecm_reflash_sequence.md` §13).

Tags: [V] = read in the disassembly (`sh-elf-objdump -b binary -m sh2e -EB`) or the dump;
[I] = inference. RAM cells: 0xFFFF1090 = engaged gear − 1, 0xFFFF1091 = target gear − 1 (from
0x174 B3), 0xFFFF108E/108F = copies of them, 0xFFFF1505 = engaged gear number (= 1090 + 1 on this
AT calibration, cal 0x869A bit 7 = 0, code 0x755AE–0x755BC) [V].

## Design rules

1. **Gear 8 must get through** wherever the code rejects it (nibble limits, classification
   chains, the abort in 0xF0ED8).
2. **Every 5-entry gear table gets an 8-entry table** in free space and its clamp is raised to 7,
   so each gear has its own cell. (The first version filled 6th–8th with the stock 5th-gear value;
   the 8HP70 calibration, section P, replaced that with nearest-ratio values and ratio-derived
   recomputation.)
3. **Where Nissan's code already handles gears 6/7 explicitly**, the structure is left alone (the
   8-entry tables, the 8×8 maps, the gear list 0xFF80); gear 8 follows the same path as 7. Their
   values are recalibrated in section P, and the top-gear test 0x7BABC is changed by P7.
4. **Calibration:** the ECM's own 8-entry ratio tables get the true 8HP ratios (D-N5), and the
   1..5 gear window becomes 1..8.

Free space used: **0x19900–0x19947** (72 bytes) of the erased 0x1988C–0x1FFFF [V: all FF, no
literal or table points into it]. The patch changes bytes in both 0x8200–0x1FFFF and
0x20000–0xFFFFF, so it needs the **full application range** (0x8200–0xFFFFF), not the
calibration-only range.

## Edits (56 edits, 262 bytes including checksums; the P edits are the 8HP70 calibration)

### S – 0x174 decoder (handler 0xE297C area)
| Id | Address | Stock behaviour [V] | Change |
|---|---|---|---|
| S1 | 0xE26E8 `E6 08` | target nibble: `mov #8,r6; …; cmp/ge r6,r2; bt 0xE2706` → nibble ≥ 8 writes **0** (1st) to 0xFFFF1091 | `mov #9,r6`: nibble 8 → 0xFFFF1091 = 7 |
| S2 | 0xE2826 `E2 08` | engaged nibble: `mov #8,r2; and #15,r0; cmp/ge r2,r0; bt 0xE283C` → ≥ 8 writes 0 to 0xFFFF1090 | `mov #9,r2` |
| S3 | 0xE271A–0xE2721 | target nibble → 0xFFFF283F: chain `cmp/eq #1..#7 → 0`, 9 → 4, 0/10 → 3, 11/15 → 0; **8 is not listed: the cell keeps its old value** | `add #-1,r0; tst #0xF8,r0; bt 0xE274E; add #1,r0` replaces the `==1`/`==2` tests: 1..8 → 0. The remaining `==3..7` tests never match; 9/10/11/15 unchanged |
| S4 | 0xE2760–0xE2767 | target nibble → 0xFFFF2620: 1..7 → 8, 0/10 → 4, 9 → 2, 11/15 → 8; 8 not listed | same range test, `bt 0xE27D8`: 1..8 → 8 |

Disassembly after S3 (patched image): `e271a add #-1,r0 / e271c tst #248,r0 / e271e bt 0xe274e /
e2720 add #1,r0 / e2722 cmp/eq #3,r0 …`. Nibble 0 is caught earlier (`e2716 tst r0,r0; bt`), so
the range test only sees 1..15. The second gear writer 0xE1B48 (3-bit fields) is the handler of
ID **0x251** (dispatch `e0e54 mov.w 0x4A20; cmp/eq; bt 0xe0f22`), which is not in the ECM's
receive table at 0x97B8 [V], so it never runs; not patched.

### R – the four users of the 5-entry ratio table 0x1247E
0x1247E holds 5 words (3.842/2.353/1.529/1.000/0.839 ×1024) and is followed directly by the
8-entry 0x12488, so raising a clamp alone would read the wrong table. Each user is repointed to
0x12488 (which K2 fills with 8HP ratios) and its clamp raised to 7.
| Id | Literal pool | Clamps (`mov #4` → `#7`) | Stock code [V] |
|---|---|---|---|
| R1 | 0x44EBC | 0x44E1A (r10), 0x44E26 (r6) | `cmp/gt r10,r12; bf.s; mov #4,r6; mov.l →1247E; mov.w @(r0,r13)` index 0xFFFF108E; result × speed → 0xFFFF157C+4 |
| R2 | 0x4E6B8 | 0x4E4AE (r4), 0x4E4B6 (r6) | `cmp/hi r4,r0; …; mulu.w ratio,@(86,gbr); >>10` → 0xFFFF157A |
| R3 | 0x9B838 | 0x9B78A (r2), 0x9B792 (r6) | only when engaged = target (0xFFFF1090 = 1091); → 0xFFFF1EC6 |
| R4 | 0xF18C0 | 0xF16F2 (r2), 0xF16F8 (r6) | index = min(108E, 108F); ratio × 0xFFFF10E4 + cal 0x8F5A |
Register check: the clamp registers are overwritten before any later read (r10 at 0x44F28, r4 at
0x4E4B8, r2 at 0x9B79C and 0xF172E) [V]. Each pool word has exactly one loader [V].

### B – byte tables 0xF700 / 0xF705 / 0xF70A / 0xF70F (function 0x67A5C, enabled by cal 0x8AA6 bit 3 = 1)
Stock [V]: `mov.l →108E; mov #4,r5; mov.b @r2,r6; cmp/hi r5,r6; bf; mov #4,r6` then
`mov.b @(r0,r11)` from two of the four 5-byte tables (gbr flag bit 5 picks the pair). Stock data:
F700 = 00 00 00 00 64, F705 = 00 00 00 00 64, F70A = 00 00 00 00 3C, F70F = 00 00 00 00 3C
(only 5th gear non-zero).
Change: four 8-byte tables at **0x19900 / 0x19908 / 0x19910 / 0x19918** (= stock + 5th value
for 6–8), literals 0x67CB4 / 0x67CA4 / 0x67CB0 / 0x67CA0 repointed, clamps 0x67A7C and 0x67A84
`#4` → `#7`.

### T – torque-intervention scaling (0x177 B4, function 0x68E62; B4 lives in 0xFFFF3910)
Stock [V]: upshift path `mov.l →108E; @(1,r7) = target; clamp to 1..4 (0x68F14/0x68F1A); add #-1`
→ index 0..3 into **0x10409** (first step, 4 × 0x99 = 60 %) and **0xF9C1** (4 × 0x57); the
third path indexes **0xF9BC** with the target clamped to 1..4 (0x68F8E/0x68F96; bytes F9BD–F9C0
= 00, and 0xF9C1 starts right after, so a raised clamp would overrun into the next table).
Change: T1 7-entry copies at **0x19920** (99 ×7) and **0x19928** (57 ×7), literals 0x69054 /
0x69058, clamps `#4` → `#7` (upshifts into 2nd…8th get their own cell); T2 8-entry copy at
**0x19930** (00 ×8), literal 0x69060, clamps `#4` → `#7`.
Not changed: the downshift path uses the 4×4 map 0xB3B4 (`03 01 01 01 03 01 01 01 03 02 01 01
03 01 00 01`) with engaged clamped to 1..4 and target to 0..3, and its result is multiplied by B4
(`mulu.w` with @0xFFFF3910 at 0x68FE4) [V]. So **every downshift from 6th, 7th or 8th uses the
stock 5→4 cell** (the emulation gives identical outputs for 8→7 and 5→4) [E].
**Is the path used? Yes.** 8hp-tcu-open sends the cut on up- and downshifts (`nissan_out.c`,
`nissan_tx.c`; review 2026-11-24). The stock Nissan TCM also requests downshift cuts: the truck
logs (`2026-09-1*_torque_*.txt`) show a power-on **4→3 downshift** (code 9, pedal ~31 %, ~280 Nm)
with **B4 = 0x1A (~10 %) for ~100 ms** [O]. That is 1 of only 4 downshift events logged; the two
5→4 at ≤ 32 % pedal had none. (The earlier note "B4 non-zero only during upshifts" was based on
logs aimed at upshifts and is wrong.)
**Effect of the 4×4 clamp, executing the patched ROM** (B4 0x1A) [E]: class from 0xB3B4 = 3 for
2→1, and **1 for every other downshift, 3→2 … 8→7 including skips (8→6, 6→4)**, with identical
outputs. So every 8HP downshift except into 1st uses the same cell as the stock 4→3, the case the
stock TCM was seen cutting in. **Conclusion: no patch and no TCU restriction needed**; keep
downshift cut amounts near the stock size (~10 %) until a drive test shows otherwise.

### G – gear paths that drop gear 8 / gears 6–8
| Id | Address | Stock [V] | Change |
|---|---|---|---|
| G1 | 0xF0FD4–0xF0FE3 (16 bytes) | 0xF0ED8 (enabled, cal 0x8A95 bit 0 = 1): index = max(108E,108F); `cmp/eq #0..#6` read word 0x912C[i] (2618 3E33 5FB8 925A AE70 AE70 AE70); **index 7 → `mov #0,r6; mov #1,r14` = abort** | Rewritten: `mov.l @0xF11C8,r1; cmp/eq #6; bf; mov.w @(12,r1)` for 7th (stock entry), `mov.w @(10,r1)` for 8th (own cell 0x9136); 0xF0FDC/0xF0FDE unchanged (landing point of cases 1–5). Verified by executing the ROM: stock aborts index 7, patched gives 1F0C 2E91 457E 57CB 71E5 925A AE70 AE70 [E]; 8th is held at AE70 by decision B (see the torque-floor section) |
| G2 | 0x529C2 `8B 05` | 0x52998: class of target gear → 0xFFFF2282: 1st → 2, 2nd → 2, 3rd → 2/3, 4th/5th → 4/5; **6th+ falls through and the cell keeps a stale value** (or 1 with flag) | `bf 0x529D0` → `nop`: 6th–8th classed like 4th/5th |

### K – calibration
| Id | Address | Stock | Patched |
|---|---|---|---|
| K1 | 0x86B8 | 05: window `0x86B9 (1) ≤ 0xFFFF1505 ≤ 0x86B8 (5)` at 0x7575E and 0x75784 [V] | **08** (all forward gears, the cal's intent [I]) |
| K2 | 0x12488 and 0x141A6 | 3.842 2.353 1.529 1.000 0.839 0.839 0.839 0.839 | **4.714 3.143 2.106 1.667 1.285 1.000 0.839 0.667** (×1024: 12DB 0C92 086D 06AB 0524 0400 035B 02AB) |
| K3 | literals 0x7BA0C, 0x7BC70 | code reads ratio[5] directly (0x12492 = 0.839, the stock top-gear ratio) | → 0x12494 (ratio[6] = 8HP 7th = 0.839): value read unchanged |

## Checksums (all four reproduced from the stock image byte for byte)
| Name | Stored at | Definition | Evidence |
|---|---|---|---|
| ROM16_A | word 0x20000 | 16-bit word sum 0x20002–0xFFFFF | boot code 0x2AC2–0x2B46 compares it; start pointer 0x20002 set at 0x12EA [V] |
| ROM16_B | word 0x8200 | 16-bit word sum 0x8202–0x1FFFF | same routine, pointer 0x8202 [V] |
| ALT | u32 0x20404 / 0x20408 | sum32 / xor32 of 0x2040C–0x221A7 | nissutils `validate_altcks` [V on stock] |
| ALT2 | u32 0x96E0 / 0x96D8 | sum32 / xor32 of 0x8204–0xFFFFF except the u32 at 0x20000 and the two result words | nissutils `checksum_alt2` [V on stock] |
Fix order ALT → ROM16_A → ALT2 → ROM16_B (each later range contains the earlier result).
`--selftest` re-runs the fixer on the stock dump and gets the identical image. Patched values:
ALT unchanged, ALT2 D60A873B / CBB97407, A BA83, B 57EC. Not a gate: 0xEDB50 computes a 32-bit
value over 0x8200–0xFFFFF into RAM (the OBD **CVN**, [I]); it will differ from stock. The boot
block's RIPEMD-160 (0x798) hashes a RAM download buffer (0xFFFF8500), not a stored ROM digest.

## Reviewed, deliberately not changed
All 75 loaders of 0xFFFF108E–1095/1505 were scanned for gear constants [V]. Unchanged because
the code already copes with 6–8 or the result is the stock 5th-gear behaviour:
8-entry clamp-7 users (0x3F298, 0x67E6E, 0x75FFC, 0x7AA42, 0x7F034/7F044, 0x7F0D2, 0x7F4FA,
0x7FF24, 0x8034C); 8×8 maps 0xB314 / 0xE48C (only upshifts from 1st–3rd non-zero); 0x11772,
0x112C2/0x112D2 (structure; values recomputed in P1); 4×4 maps on axis 0xF7B0 (structure; own
gear axis in P5); gear list 0xFF80 = 2,2,3,4,5,6,7,8 (0x4FBD0 finds 8 correctly); 0x6898E (only
targets 2nd–4th); the top-gear test 0x7BABC was first left as Nissan's own handling of 6th+ and
is now changed by P7; legality table 0x167A4 (check
calibrated off, cal 0x13C7A bit 4 = 0); substitute handlers 0xE4AFE/0xE4BCA (loss of 0x174).

## Predictions for the bench (RAM reads over 0x23 are allowed)
Stock ECM today, TCU sending target nibble 8: **0xFFFF1091 = 00** (reads as 1st), 0xFFFF283F and
0xFFFF2620 unchanged from the previous frame. Patched ECM: 0x174 B3 = 0x88 → **1090 = 1091 = 07,
1505 = 08, 283F = 00, 2620 = 08**; B3 = 0x76 (target 7th = high nibble, engaged 6th = low nibble) → 1091 = 06, 1090 = 05, 1505 = 06.
Gear-cut cells on an upshift into 8th read the new tables (0x19920: 0x99 first step).

## Open
- The per-gear calibration (section P) is a ratio-matched starting point, not a drive
  calibration; the tables' meanings are decoded below, but the values still need drive validation.
- The downshift cut path (0xB3B4) is 4×4, but every 8HP downshift except into 1st uses the stock 4→3 cell; it needs a running-engine test (section T).
- The reflash path is decoded and proven: `ecm_reflash_sequence.md` §2–§13.

## P - 8HP70 per-gear calibration (user, 2026-11-23: "match all per-gear values to the 8hp70")
**Method.** Each 8HP gear takes the stock value of the RE5R05A gear with the nearest ratio (log
distance): 8HP 1st–8th → RE5 **1, 1, 2, 3, 3, 4, 5, 5** (`NEAREST` in the builder).
Exception: tables whose stock data satisfy value × ratio = constant are speed-per-gear quantities
and are **recomputed from the true 8HP ratio**. They are interpolated in 1/ratio through the five
stock points, which is exact at the two ratios the gearboxes share, 1.000 and 0.839. This
replaces the earlier "6th–8th = stock 5th" fill for the B and T tables.
| Id | Table | Stock (RE5 1st–5th) | 8HP 1st–8th |
|---|---|---|---|
| P1 | 0x112C2 and 0x112D2 (value × ratio ≈ 7 550), in place | 07AF 0C6C 135A 1D6A 2344 | 064C 0959 0DEE 11B7 16F7 **1D6A 2344** 2CA3 |
| P2 | 0x912C (× ratio = 37 467) → new 0x19938 for 1st–6th via literal 0xF0FD0 | 2618 3E33 5FB8 925A AE70 | 1F0C 2E91 457E 57CB 71E5 925A, 7th = stock AE70 (exact); 8th has its own cell 0x9136, **kept at AE70** (decision B: it caps a torque floor; the true value DB6C would raise that floor about 25 %) |
| P3 | 0x11772, in place | 7FFF 7FFF 00C8 7FFF 7FFF | 7FFF 7FFF 7FFF 00C8 00C8 7FFF 7FFF 7FFF (the stock 3rd-gear limit 0x00C8 now applies in 4th/5th) |
| P4 | 8×8 shift matrices 0xB314 / 0xE48C [engaged][target] (axes from 0x7EF16/0x7EF28), in place | values only on upshifts from 1st–3rd | shift i→j = RE5 shift NEAREST[i]→NEAREST[j]; when both map to the same RE5 gear, the adjacent RE5 shift in the same direction |
| P5 | gear axis of the 4×4 maps 0xB374/B384/B394 (0x7F2AC, target gear): literal 0x7F37C → own axis 0x19944 | 0,1,2,3 | **1,2,3,5**: 1st/2nd → RE5 1st row, 3rd → 2nd, 4th → 3rd, 5th → interpolated 3rd/4th, 6th–8th → 4th+ row. 0xF7B0 itself is unchanged (0x7F9C2 uses it with input 0xFFFF261D, not a gear) |
| P6 | 0xFF8F (index from the 0xFF80 gear-list search), in place | 5 5 5 4 3 | 5 5 5 5 5 4 3 3 |
| P7 | top-gear test 0x7BABC/0x7BACC/0x7BAD2 | engaged & target ≥ 5th | ≥ **7th** (= RE5 5th, 0.839), 7th and 8th unconditional |
| B1 | 0xF700/05/0A/0F copies (0x19900…) | 0 0 0 0 X | 0 0 0 0 0 0 X X |
| T1/T2 | upshift scaling 0x19920/0x19928, 0x19930 | uniform (0x99 / 0x57 / 00) | unchanged values |
Not converted (raw gear-number logic, not table values): G2 class 0x52998 (6th+ like 4th/5th);
the downshift 4×4 0xB3B4 (inactive while the TCU sends no cut on downshifts); the
"engaged ≥ target + 2" skip-shift test in 0x7F2AC. The meaning of most tables is still [I]; the
calibration reproduces the RE5 behaviour per ratio, it is not a drive-validated 8HP calibration.

## What the per-gear tables do (decoded 2026-11-23; [V] code read, [I] meaning inferred)
| Table | Function (code) | What it does | Active? | 8HP status / recommendation |
|---|---|---|---|---|
| **0x11772** | 0x7F4FA–0x7F530 | **Torque ramp-down limit per target gear.** Each pass, a floor in 0xFFFF3A72 drops by T[target]; output torque 0xFFFF3A70 = max(request, floor). A flag (0xFFFF4714 bit 0) resets it. 0x7FFF = no limit [V]. Tip-out / driveline-shunt damping [I] | yes (no gate found) | Stock damps only RE5 3rd (0xC8 per pass); nearest ratio puts it in 8HP 4th and 5th. Cells are already independent: tune per gear on the truck; nothing to restructure |
| **0x912C** | 0xF0ED8–0xF10D4, enabled by cal 0x8A95 bit 0 = 1 | **Inverse gear ratio** (speed per engine rev; table × ratio = 37 467). The working value 0xFFFF3384 rises toward T[max(engaged, target)] by 0x148 per pass and never steps down (step-down @0x913C = 0; the reset / measured-ratio path 0xF1016 is switched off by cal 0x8AAF bit 7 = 0 and 0x869A bit 7 = 0), so it latches at the highest gear reached since power-up, as in stock. The disabled mode computes it from a measured ratio (cal 0x93CA × 2048 / 0xFFFF2732), which confirms the meaning. Output 0xFFFF3384 × 0xFFFF392E → 0xFFFF45C8 (a speed estimate from engine speed [I]) | yes | 8th has its own cell (G1); its value is capped at 7th's AE70 by decision B, because the latched maximum scales a minimum-torque floor (see below) |
| **0x112C2 / 0x112D2** | 0x7FF24–0x80010 | **Engine-torque ceiling per engaged gear = constant ÷ ratio, i.e. a constant wheel-torque cap.** The offset 0xFFFF2942 is added, the result is applied as a minimum against requested torque, and during a shift it is rescaled by ratio[engaged] / ratio[target] (0x12488). 0x112D2 is used when 0xFFFF3A5A > cal 0x94DC (0) [V] | yes | P1 recomputes them from the 8HP ratios, keeping the same wheel-torque cap: correct by construction. Cells independent. No change |
| **0xB374 / 0xB384 / 0xB394** (4×4) | 0x7F2AC–0x7F30A | **Shift-phase time per target gear** [I] (byte × 10 → 0xFFFF(7F35C)+2) against a speed-like input (axis 0xF7B8 = 50…125). Variants: normal (B394), downshifts of 2+ gears (B374), above a threshold (B384) [V] | yes | Only 4 gear rows: the P5 axis puts 8HP 5th between two rows and 6th–8th share the last row. Split (8-row maps + wrapper) only if shift quality needs it; low priority until drive data |
| **0xB314 / 0xE48C** (8×8) | 0x7F02C–0x7F0C8 | **Upshift torque offset and its duration** [I]. E48C is a signed value (−0x8000 bias: +300 / +500) written to 0xFFFF4904 during an upshift; B314 is the duration (30 / 20 ticks), applied only while a load-type value stays under cal 0x9454+16/18 [V] | yes | Every engaged × target pair has its own cell. The P4 remap is a starting point; tune per shift on the truck |
| **0xFF8F** | 0x4FBD0 (via the 0xFF80 gear list) | Per-gear byte into 0xFFFF1968; purpose not decoded [I] | – | P6 nearest-ratio remap; leave |
| **0xF700 / 05 / 0A / 0F** | 0x67A5C | – | **no: calibrated off** (cal 0x8AA6 bit 3 = 0 → the routine exits at 0x67A76) [V] | Irrelevant in this calibration |
| upshift cut tables (0x19920 / 0x19928) | 0x68E62 | B4 scaling per target gear (uniform 0x99 / 0x57) [V/E] | yes | Already independent; values identical to stock for all gears |

**Conclusion.** The one known-wrong value, **0x912C in 8th**, is now fixed (own cell). The
others are either correct by construction (the ratio-derived torque cap and inverse ratio), already
independent and waiting for drive tuning (0x11772, the shift matrices), coarse but plausible (the
4×4 shift-time maps), or inactive (0xF700). The 4×4 maps' 8-row split can wait for drive data.

### What 0x912C finally feeds: a torque floor (decoded 2026-11-23)
- **0xFFFF392E** (0xF2504–0xF25A2) [V; meaning I]: a signed, torque-like value from the table
  0x12588 (biased +0x8000: 323, 395, 515, 683, 899, 1162, 1474, 1834) over the axis 0x12598
  (200…1600). The input is the elapsed time since an event (gbr+108 − gbr+116, ×5/16). So it ramps
  up with time, then is capped and offset.
- **0xFFFF45C8 = 0xFFFF392E × 0xFFFF3384 / 2¹⁵** (0xF105A–0xF10D4), i.e. that ramp times the
  latched inverse ratio.
- **Consumers: torque floors** [V]:
  - 0x7AE70 returns max(torque request, 0xFFFF45C8) and sets gbr+165 bit 4 when the floor wins;
  - 0x7A704 writes max(0xFFFF3C34, 0xFFFF45C8) → 0xFFFF3C36 and sets gbr+182 bit 6;
  - 0xF110C sets gbr+232 bits 4–5 when a value exceeds it.
  All are enabled by cal 0x8A95 bit 0 = 1 and gated at run time by 0xFFFF460C bit 5.
- **Consequence for the 8HP.** 0xFFFF3384 latches at the highest gear's value reached since
  power-up, so only the largest 0x912C entry matters to the floor:
  - stock latches at AE70 (5th, 0.839);
  - with 8th split out it latches at DB6C (0.667), **a floor about 25 % higher in engine-torque
    terms** once 8th has been used.
  Entries for 1st–7th affect the floor only before the first upshift past them.
- **Decision for the user:**
  - (A) keep DB6C, the 8HP's top-gear equivalent of stock's "top gear" factor;
  - (B) cap 8th at AE70 (= 7th, 0.839, a ratio both gearboxes share), giving exactly the stock
    floor magnitude.
  **Recommendation: (B). Chosen by the user 2026-11-23 and applied (0x9136 left at stock AE70; image SHA-256 0c2c2691…).** A torque floor forces a minimum engine torque. Its stock magnitude was
  validated in the truck, and raising it by 25 % has no benefit we can name. (B) restores the
  earlier behaviour (8th = 7th) for this one table while keeping the clean G1 code (0x9136 = AE70).
