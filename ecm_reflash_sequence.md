# ECM reflash over CAN: decoded sequence, security, blocks, recovery, prediction

ECM 23710-9CF0A, software 9CJ3A, SH7058 (1 MB), diagnostics on CAN 0x7E0/0x7E8, ISO-TP, frames
padded to 8 bytes. Decoded 2026-11-23 from `dumps/dh1_9CJ3A_pass1.bin` (desk only); external
references read as text, never run: RomRaider `TestJ2534NCS.java` + `NcsCoDec.java`, nissutils
`nislib.c` / `romdb/keysets.csv`. **Nothing has been sent to the ECM beyond the earlier reads.**
[V] = read in this ROM's disassembly; [E] = confirmed by executing the ROM routine in
`sh2_mini.py` (see `ncs_keys.py`); [R] = reference code; [I] = inference.

## 1. Entering the loader (application side)
| Step | Request | What the application does |
|---|---|---|
| 1 | `10 85` | SID 10 handler 0xE6A90 accepts 81/C0/85/FA/FB/DA; 85 sets session mask 0x0004 (0xE6B58) [V] |
| 2 | `27 81` | in session 85, SID 27 → 0xE8EA0: **not a seed request**. It checks preconditions and on success sets 0xFFFF6907 bit 5 and answers positively (0xE5F5C); otherwise NRC 0x22 [V] |
| – | (automatic) | the SID 27 post-handler 0xE9B90 sees bit 5, masks interrupts, clears the watchdog, stops CAN, sets VBR = 0 and runs `trapa #62` → boot vector 62 = **0x2514** [V] |

Preconditions for the app's `27 81` (0xE8EBA–0xE8EFC) [V; meanings I]: 0xFFFF4606 bit 7 = 1;
0xFFFF23E7 bit 5 = 0; byte 0xFFFF117B ≥ cal 0x8C59 (0x83; likely battery voltage); 0xFFFF2386
= 0 (likely engine speed); 0xFFFF6907 bits 2 and 3 = 0; if 0xFFFF6907 bit 7 is set, also word
0xFFFF6904 > 1000. `27 82` in session 85 gets NRC 0x22 from the application.
(The app's key routine 0x31B4A, `key = enc1(seed, 0x968148AD)` [E], belongs to the FA/DA
sessions; it is not on the 0x85 programming path.)

Boot entry 0x2514 [V]: new stack, init (0x29E6), mode from byte 0xFFFFDCAA (HCAN1 receive data,
the `81` of the last request [I]): 0x81 → mode 4, 0xFA → 0x40, 0xDA → 0x200; then copies the
flash routines (ROM 0x48DC–0x4BF7 → RAM 0xFFFF0800) and runs the loader loop at 0x3A0. **The
application stops running, so its broadcasts (0x160/0x180/0x1F9 …) stop** [I from the code path].

## 2. The boot loader's CAN services (table 0x4C0C, same 24-byte layout as the app's) [V]
`10` (0x3CCA), `21` (0x21B4), `27` (0x2160), `31` (0x143A, post 0x13F4), `34` (0x1C1E),
`35` (0x1518), `3E` (0x3FB4). No 36/37: data travels in SID 34 frames.

**SID 27 (mode 4 path 0x1C6C)**
- `27 81` (0x1CBC): once per entry (0xFFFF83B0 bit 6 must be clear). If byte 0x8100 ≠ FF, a
  tick counter 0xFFFF83AE must exceed 1000 first (in the dump 0x8100 = FF, so no wait).
  Seed = `crc(R<<16|T) << 16 | crc(T<<16|R)`, with R a random word and T a timer word (0x1EAC) [E].
  Reply `67 81 s3 s2 s1 s0`.
- `27 82 k3 k2 k1 k0` (0x1D58): needs the boot's own `27 81` first (NRC 0x22 otherwise).
  Accepted if the key equals the expected key (0x1F00 [E]), **or if the key word
  W (0xFFFF8294) = 0xFFFF**. W is loaded at boot init (0x2838–0x286E) from the first programmed
  slot word of 0x6280 / 0x6300 / 0x6380; **all three are erased (FFFF) in this dump**, so any key
  is accepted [V]. This is why RomRaider can send `11 22 33 44`. Unlocking sets 0xFFFF83B0 bit 5.
- With W ≠ FFFF, a wrong key fills a buffer and sets a lockout flag (0x1DB4–0x1DD6) [V];
  the key is then `crc(f1(sH), f2(sL), W) << 16 | crc(R, f1(sL), f2(W))`, f1 = 170·x mod 30323,
  f2 = 171·x mod 30269 [E].

**SID 31 (mode 4 path 0x1240; gbr 0xFFFF83B0)**
- `31 81 {81|82} F0 5A`: start the erase. Needs the unlock (NRC 0x33 otherwise). The word F05A is
  stored at 0xFFFF8292 and checked (0x22D0); every later write also needs it (0x1792).
  {81|82} selects the target as in SID 34 [I: 81 = calibration, 82 = whole application].
- `31 81 01`: erase status poll, answered `71 81 01` while busy. During the erase the RAM copy
  of the CAN interrupt answers it directly (0x4940) [V].
- `31 82 00`: start the verify. It loads the sum pointers 0x20002 / 0x8202 (0x12EA); the loader
  loop then computes **ROM16_A (word @0x20000 = sum 0x20002–0xFFFFF) and ROM16_B (word @0x8200 =
  sum 0x8202–0x1FFFF)** (0x2AC2) [V]. `31 82 01` polls: 01 busy, **02 = both sums good**, else
  4/8. These are the two sums `build_8gear_patch.py` recomputes; the loader checks no other
  checksum.

**SID 34 (0x1C1E → frame check 0x15E0–0x1704, write 0x1792)**
`34 <sub> a2 a1 a0 <len> <data…> <crc lo> <crc hi>`, after the unlock (NRC 0x33) [V]:
| sub | address | len | meaning |
|---|---|---|---|
| 0x81 | 0x8200–0x1FFFF | 0x80 | calibration block |
| 0x82 | 0x8200–0xFFFFF | 0x80 | application block |
| 0x83 | 0 | 0x30 | finalise record (48 bytes) |
| 0x88 | 0 | 2 | key-word slot write [I] |
Blocks must be sequential (each address = previous + 0x80). Frame CRC: CRC-16 (reflected 0x8408,
init FFFF) over the whole request including SID and the appended `~crc` low byte first; the
residue must be **0xF0B8** (0x1604) [E]. Data: each u32 is `enc1(u32, scode)` on the wire, and
the loader decodes it with `dec1` (0x42B0 [E]) using **scode = u32 @0x5FE0 = 0x737133EF**. After
each block the loader writes 128 bytes through the RAM flash routine 0xFFFF0A0A and compares
them word for word with the buffer (0xA90); a mismatch sets an error bit [V].
`34 83` (0x1824) needs a passed verify (0xFFFF83B0 bit 1). It appends a 128-byte record (48
data bytes + FF) to the log at 0x7000–0x7FFF in steps of 0x100, erasing block 7 when the log is
full. **The dump already holds two records: 0x6F00 = factory 9CF0A, 0x7000 = the dealer reflash
to 9CJ3A** (the same bytes `21 FF` returns). The next record goes to 0x7100 [I]. Processing
the finalise also writes the **0xF0 marker at 0x8080** (0x9EA–0x9F6) [V/I].

**Erase blocks** (0x4B28) [V]: depending on the mode flags, block 7 only (the record log),
block 8 only, or **blocks 8–15 in a loop** (whole application). The work is done by Renesas'
on-chip program/erase routines, downloaded via the flash control registers at 0xFFFFE800
(FKEY 0xA5) in 0x499E. Blocks 0–6 (0x0000–0x6FFF, the loader itself) are never erased.
0x8000–0x81FF lies in block 8 and holds the loader's markers.

## 3. Reset decision (0x2470) and recovery [V]
At power-up the boot computes `b = byte@0x8000 AND (byte@0x8080 OR 0xF0)` (dump: FF and F0):
- b = FF or b < F0 → **stays in the CAN loader** (main loop 0x3A0);
- otherwise, if u32 @0xFFF84 = `4E 48 55 F9` ("NHU…", present in the dump and unchanged in the
  patched image) → application via IVT2 0x20004; if the magic is absent, byte 0xFFF80 bit 0
  decides.
So once block 8 is erased, 0x8080 reads FF until the finalise rewrites F0, and **an interrupted
or failed flash leaves an ECM that powers up in the CAN loader**, ready for a retry with the
stock image (`dumps/dh1_9CJ3A_pass1.bin`). The loader blocks 0–6 are outside every erase path.
The external EEPROM (adaptations, NATS, DTCs) is not touched. The OBD CVN (0xEDB50) will
change [I].

## 4. Working sequence for this ECM (differs from RomRaider in one step)
```
10 85                        -> 50 85                     (app)
27 81                        -> 67 81 s s s s             (app hands off; the seed comes from the loader, see §5a)
   [app broadcasts stop]
27 82 xx xx xx xx            -> 67 82                     (boot: any key, because W = FFFF; not yet sent on the bench)
31 81 82 F0 5A               -> 71 81 …                   (erase blocks 8-15)
31 81 01  (repeat)           -> 71 81 01 … until done
34 82 a2 a1 a0 80 <enc1 data ×128> <~crc LE>  × 7 932    (0x8200 … 0xFFF80)
31 82 00, then 31 82 01 (repeat) -> … 02                  (ROM16_A / ROM16_B good)
34 83 00 00 00 30 <48-byte record> <~crc LE>             (record at 0x7100, marker F0 @0x8080)
10 81                        -> reset into the new application
```
(Superseded by §5a: the earlier claim that RomRaider's single `27 81` is used up by the
hand-off and needs repeating was contradicted on the bench. The loader issues the seed for
that same request.)
For the record, RomRaider writes 48 × FF (`21 FF` would then show blanks). A copy of the
0x7000 record's layout with our own ID is the better choice; that is the user's call.

## 5. Prediction
**Today: a reflash of `dumps/dh1_9CJ3A_8gear.bin` with the sequence in §4 is predicted to
succeed.**
- Every acceptance check on the path is decoded [V].
- The key is not needed (W = FFFF) [V].
- The image passes the loader's only image checks: ROM16_A/B (fixer self-tested on stock), the
  trailer magic, and the address range 0x8200–0xFFFFF [V].
- The scode, CRC and dec1 coding are confirmed by running the ROM's own routines [E].

Residual risks, in order:
1. The application's `27 81` preconditions (four RAM conditions with meanings not decoded);
   checkable by reads first.
2. Loader timing and ISO-TP flow control (block size / STmin from the loader's ISO-TP layer at
   0x32EC are not decoded); a 136-byte frame needs flow control.
3. Supply dropouts during a ~5–10 min write [I].

Failure modes before the erase change nothing. After the erase they leave the loader running
(§3), so the recovery is to write the stock image again with the same sequence.
No flashing tool exists yet: `ncs_keys.py` has the coding (enc1, CRC, frame builder), and a
writer would still need the ISO-TP sender with flow control.

## 5a. CORRECTION after bench step B (2026-11-23)
Step B observed `27 81` → **`67 81 0C BE 99 8B`** (a 4-byte seed), the broadcasts stopping at
once, and then the loader answering a second `27 81` with **`7F 27 22`**. The application's
success path (0xE8EBA–0xE8F1E → 0xE5F5C) only records a status code and computes no seed [V].
So the 4-byte seed most likely came from the **loader**, which handles the pending `27 81` after
the hand-off. Its "seed already issued" bit (0xFFFF83B0 bit 6) then refuses a second `27 81`
with NRC 22 [I, consistent with 0x1CC8–0x1CE8]. **Consequence: RomRaider's order `10 85` →
`27 81` → `27 82` is the right one for this ECM; the "send `27 81` twice" step in §4 is
wrong.** The corrected sequence is `10 85`, `27 81` (seed from the loader), `27 82 <any 4
bytes>`, then as in §4. The loader's `3E 00` gets `7F 3E 12` (sub-function not supported); the
loader replies on 0x7E8.
After a power-cycle (listen only, nothing sent) the application broadcasts again at normal rates
(0x160/0x180/0x182/0x1F9 ≈ 97–98 per s, 0x551/0x580/0x6E2 10 per s), as predicted from the
unchanged markers (§3) [O]. Entering the loader and leaving it by power-cycle is harmless.
**Step C (same day, `step_c_key.py`; only `10 85`, `27 81`, `27 82 11 22 33 44` sent)** [O]:
`50 85`; `67 81 8C 69 0F B0` (a different seed from step B, as expected from the random R/T)
and the broadcasts stopped; **`27 82 11 22 33 44` → `67 82`: the loader accepts any key**, as
predicted from W = FFFF. This confirms §5a: the seed comes from the loader, and RomRaider's
single `27 81` order is right. No 31 or 34 was sent. After a power-cycle (listen only) the
application broadcasts again at normal rates (0x160/0x180/0x182/0x1F9 98 per s) [O]: unlocking
the loader without erasing changes nothing persistent.

## 6. Bench steps proposed (need the user's OK; the user powers the ECM)
**A. Reads only (session FB, `23` reads of RAM; no state change).** `10 C0`, `10 FB`, then
`23 FF FF 46 06 00 01`, `23 FF FF 23 E7 00 01`, `23 FF FF 11 7B 00 01`, `23 FF FF 23 86 00 02`,
`23 FF FF 69 04 00 04`. Prediction with the engine stopped on a 13.5 V supply: 4606 bit 7 = 1,
23E7 bit 5 = 0, 117B ≥ 0x83, 2386 = 0000, 6907 bits 2/3 = 0 (and bit 7 = 0, or 6904 > 03E8). If
any condition fails, the app's `27 81` would answer `7F 27 22` and step B stops there harmlessly.
**Result of A (bench, 2026-11-23, engine stopped, 13.5 V supply, `step_a_reads.py`; only these
seven requests sent, no `10 81`)** [O]:
| Request | Reply | Prediction | |
|---|---|---|---|
| `10 C0` / `10 FB` | `50 C0` / `50 FB` | positive | ✔ |
| 0xFFFF4606 | `80` | bit 7 = 1 | ✔ |
| 0xFFFF23E7 | `00` | bit 5 = 0 | ✔ |
| 0xFFFF117B | `A7` | ≥ 0x83 | ✔ (0xA7 = 167; if ×0.08 V/bit that is 13.4 V, consistent with the supply: supports the battery-voltage reading [I]) |
| 0xFFFF2386 | `00 00` | 0 | ✔ |
| 0xFFFF6904–6907 | `FF FF 00 00` | 6907 bits 2/3/7 = 0 | ✔ (bit 7 = 0, so the 6904 counter is not consulted) |
All preconditions for the application's `27 81` hold in this state, so step B's `27 81` is
predicted to be accepted (positive reply, then hand-off to the loader).

**B. Enter the loader, read the seed, power off (no key, no 31, no 34).** `10 85` → predict `50 85`;
`27 81` → predict a positive reply, then the app broadcasts stop within ~100 ms; `3E 00`
(tester present to the loader) → predict a reply from the loader; `27 81` → predict
`67 81` + 4 seed bytes. Then the user powers the ECM off and on. Prediction: the markers are
unchanged (0x8080 = F0, magic present), so the application starts again and its broadcasts
resume. Nothing in this path writes flash: writes happen only after `31 81 …` / `34 …`, and the
wrong-key path needs `27 82`, which step B does not send.

## 7. Flash tool `ncs_flash.py` (written 2026-11-23, not yet run live)
- **Dry run (default):** checks the image, then builds all 7 932 block frames (136 bytes each,
  CRC residue F0B8) plus the finalise frame. It then runs the whole §4/§5a sequence through the
  real ISO-TP code against `SimEcu`, a simulation of the decoded loader. `SimEcu` covers the
  hand-off, the any-key unlock, the F05A magic, the erase of blocks 8–15, CRC/address/sequence
  checks, dec1 decoding, the ROM16 verify, and the record + 0x8080 start marker; its flow
  control uses block size 8 to exercise multi-frame transmit.
  - Image checks: 1 MB, boot area identical to the ECM's dump, ROM16_A/B correct, trailer magic
    at 0xFFF84, scode at 0x5FE0.
  - Result: for both `dh1_9CJ3A_8gear.bin` and the stock dump, the simulated flash equals the
    image at 0x8200–0xFFFFF, blocks 0–6 are untouched, and the reset logic would start the
    application.
  - A one-byte-corrupted image is refused (ROM16_A). Live mode refuses without `--confirm`
    matching the image SHA-256 and without typing FLASH.
- **Live:**
  `python3 ncs_flash.py dumps/dh1_9CJ3A_8gear.bin --live --port /dev/ttyACM0 --confirm 906ae047ec40`
- **The record** written by `34 83` defaults to a copy of the stock 0x7000 record (9CJ3A
  identity), so `21 FF` keeps answering the same; `--record-hex` overrides it.
- **What the dry run cannot prove:** the simulation is built from my decode, so it tests the tool
  against the model, not against the ECM. Not verified on the real ECM:
  - the exact positive-reply bytes of `31` and `34` (the tool accepts 0x71 / 0x74 and judges the
    last byte, 01 busy / 02 done, as RomRaider does) [R];
  - the loader's flow-control values;
  - the erase and write times (the tool allows 120 s for the erase, 60 s for the verify and 2 s
    per block).
  Expected write time: about 3–8 min over the Teensy SLCAN link [I].
- **Prediction for a live flash of `dh1_9CJ3A_8gear.bin`:** success, with every step up to the
  key already observed on the bench.
  - If a reply format differs from RomRaider's, the tool stops at the first `31 81` or `34 82`
    reply.
  - If it stops at `31 81` before the erase starts, nothing is lost.
  - If it stops after the erase, the ECM powers up in its loader and the same command recovers
    it, with the stock image if needed. The bench showed the loader is reachable with
    `10 85` / `27 81` from the application; reaching it from the loader after a failed flash
    [I] is the one recovery path not yet exercised.

## 8. First live flash: the stock image (2026-11-23, user's request "flash the stock image first to test the tool") [O]
Prediction stated before the run: success; erase `… 01` then `02`, blocks `74 … 02`, verify `02`,
finalise `02`; afterwards the application broadcasts, and a read-back differs from the stock dump
only by a new 48-byte record at 0x7100–0x712F.
- `ncs_flash.py dumps/dh1_9CJ3A_pass1.bin --live` (log `dumps/flash_stock_log.txt`): `10 85`,
  `27 81` (seed 046a2d98), `27 82` ok; **erase 8.5 s; 7 932 blocks in 174 s; verify ok (02);
  finalise ok; exit 0.**
- After the `10 81` reset the application broadcast at normal rates
  (0x160/0x180/0x182/0x1F9 98–99 per s).
- Full read-back with `ncs_dump.py` (`dumps/after_stock_flash.bin`, 209 s) compared with the
  stock dump:
  - **0x8200–0xFFFFF identical**; the boot area is identical except the two items below;
  - **0x7100–0x712F** = a copy of the 0x7000 record, as predicted;
  - **0x8080–0x80FF = 00** (stock F0): **not predicted**. The marker routine 0x19DC fills its
    buffer with zero (r1 = 0), so the loader writes 00. I had misread the value as F0. The reset
    check `byte@0x8000 AND (byte@0x8080 OR F0)` gives F0 for both, so the application starts,
    as observed. The F0 in the original dump came from the earlier dealer reflash process [I].
    `SimEcu` now writes 00.
- **The tool and the protocol work end to end on this ECM.** The record log now holds three
  records (0x6F00 factory, 0x7000 dealer, 0x7100 this flash); 13 slots remain before the loader
  erases the log block.

## 9. 8-gear image flashed (2026-11-23, user: "match all per-gear values to the 8hp70 and then lets flash") [O]
- Image `dumps/dh1_9CJ3A_8gear.bin`, SHA-256 `820f9016a2c9bb1578676bed1e1b49e9248a69911310faad917a4efb44fcc1ee`
  (structural patch + 8HP70 calibration, `8gear_patch_spec.md` section P). Prediction: as for the
  stock flash.
- Live run (log `dumps/flash_8gear_log.txt`): `10 85`, `27 81` (seed 7ff57a59), `27 82` ok;
  erase 8.5 s; 7 932 blocks in 187 s; verify ok (02); finalise ok; exit 0.
- After the `10 81` reset the application broadcasts at normal rates.
- Read-back (`dumps/after_8gear_flash.bin`, 224 s): **0x8200–0xFFFFF identical to the 8-gear
  image**. Below 0x8200 the only change against the previous read-back is the new record at
  0x7200 (a copy of the 9CJ3A record); the 0x8080 marker is 00. All as predicted.
- **The bench ECM now runs the 8-gear software.** The stock image can be restored any time with
  `ncs_flash.py dumps/dh1_9CJ3A_pass1.bin --live …` (tested above). The record log holds four
  records (12 slots left).
- Not yet checked: the patch's own behaviour. Spec "Predictions for the bench": send 0x174 with
  B3 = 0x88 and read 0xFFFF1090/1091/1505/283F/2620 over `23`.

## 10. Gear-8 bench check on the patched ECM (2026-11-23, `gear_check.py`) [O]
TCM frame set as `nissan_tx.c` packs it: 0x174/0x176/0x177 every 10 ms, 0x560 every 100 ms
(ID "8HP001", fault pages 00), engine stopped, speeds 0. RAM read with `23` in session FB, so no
writes. Replies are slower while the link also carries the TX; the reads need a 2 s timeout.
| 0x174 B3 (target/engaged) | 1090 1091 1505 283F 2620 | Prediction | |
|---|---|---|---|
| 0x22 (2nd/2nd, control) | 01 01 02 00 08 | 01 01 02 00 08 | ✔ (first run predicted 02 02 03: my mislabel of 0x22 as 3rd, corrected) |
| **0x88 (8th/8th)** | **07 07 08 00 08** | 07 07 08 00 08 | ✔ (a stock ECM gives 00 00 = 1st) |
| 0x76 (7th/6th) | 05 06 06 00 08 | 05 06 06 00 08 | ✔ |
| 0x87 (8th/7th) | 06 07 07 00 08 | 06 07 07 00 08 | ✔ |
**The patched ECM decodes true gears 6–8 from 0x174, including nibble 8**: gear number 8 in
0xFFFF1505, and both classification cells treat 8 as a forward gear.
Not covered: torque-cut behaviour and the effect of the per-gear calibration with a running engine.

## 11. Torque-cut check on the patched ECM (2026-11-23)
**Desk, executing the patched ROM** (`sh2_mini.py`, function 0x68E62, B4 = 0x67 in 0xFFFF3910,
shift flags set) [E]:
- Every upshift 1→2 … 7→8 gives first step 0xFFFF1867 = **3D** (0x99 × 0x67 / 256),
  0xFFFF13EA = **0609** (0x67 × cal 0x8722 = 0x0F) and 0xFFFF13EC = **0E46** (0x57 × (0x67 − 0x3D)).
  Stock and patched agree, because the stock tables are uniform.
- **Poison test:** with entry 6 of the new 0x19920 table set to 0x40, only 7→8 changes (step 0x19,
  13EC 0x1A82). With entry 5 of 0x19928 set to 0x20, only 6→7 changes (13EC 0x540); 5→6 is
  unchanged. So the patched code indexes the new 7-entry tables by target gear.
  (`sh2_mini.py` gained `lds Rm,MACL/MACH` for the downshift path.)

**Bench, engine stopped** (`torque_check.py`, TCM frame set, cut in 0x177 B4 only while
target ≠ engaged, as `nissan_tx.c` sends it; `23` reads in session FB) [O]:
| Case | 289F | 274F | 3910 | 2401 | 23E5–23EA | 1867 | 13EA–13ED |
|---|---|---|---|---|---|---|---|
| steady 7th | 00 | 00 | 00 | 20 | 00 08 00 08 00 08 | 00 | 00 00 00 00 |
| upshift 7→8, cut 0x67 | **67** | **67** | **67** | 20 | 00 08 00 08 00 08 | 00 | 00 00 00 00 |
| steady 8th | 00 | 00 | 00 | 20 | 00 08 00 08 00 08 | 00 | 00 00 00 00 |
All as predicted:
- the B4 chain carries the cut on an upshift into 8th;
- the shift flag 0xFFFF2401 bit 6 stays clear and 23E5–23EA are unchanged, so the cut functions
  (gate 0x69A2E–0x69A6C) do not run with the engine stopped and the outputs stay 0.

**Not covered:** the cut with a running engine (shift flags, ramp, spark retard 0xFFFF234C). That
needs the truck, or a crank-signal simulator on the bench.

## 12. Re-flash with the 0x912C 8th-gear split (2026-11-23) [O]
- Image SHA-256 `84af61c712112692fe9f8202d8b84221c49c30a2df9d06089ba0783bfe9b8bb6` (57 edits; G1 rewritten,
  0x9136 = DB6C). Prediction: as for the earlier flashes.
- Live run (log `dumps/flash_8gear_v2_log.txt`): seed 601236be, any-key unlock, erase 8.5 s,
  7 932 blocks in 190 s, verify 02, finalise ok, exit 0. Afterwards the application broadcasts at
  normal rates.
- Read-back (`dumps/after_8gear_v2_flash.bin`, 225 s): **0x8200–0xFFFFF identical to the image**
  (0x9136 = DB6C, 0xF0FD4 = d17c88068b028516a002660385156603). The boot area changed only by the
  new record at 0x7300 (5 records in the log, 11 slots left). All as predicted.
- `gear_check.py` repeated on the new software: all four cases as predicted (B3 0x88 → 07 07 08 00 08).
- 0x912C working value 0xFFFF3384 with the frame set running (B3 0x66 / 0x77 / 0x88 / 0x77):
  **DB 6C** every time. DB6C is reachable only through the new 8th-gear lookup. The value stays
  there after dropping to lower gears. **Correction (same day):** I first wrote that a reset path
  loads @0x9134 (AE70); in this calibration it does not run. Every gate in 0xF0ED8 is a calibration
  bit (gbr 0xFFFF462C + offset wraps to cal addresses) [V]:
  - 0x8A95 = 0x49: bit 0 = 1 (on), bit 1 = 0 (not skipped);
  - 0x8A97 bit 7 = 0: the alternative path 0xF106A is off;
  - 0x8AAF bit 7 = 0 and 0x869A bit 7 = 0: the branch to the reset / measured-ratio path 0xF1016
    is never taken;
  - the step-down parameter @0x913C = 0.
  Nothing else writes 0xFFFF3384 (its only writers are 0xF1026 and 0xF1056). **So the value only
  rises and latches at the highest gear's value reached since power-up**, by design: stock latches
  at AE70 (5th). The output 0xFFFF45C8 = 0xFFFF3384 × 0xFFFF392E is a threshold, compared at
  0x7A73C and 0x7AEA4 and setting flags gbr+232 bits 4–5 at 0xF110C [V; meaning I]. With the 8HP
  it latches at 8th (DB6C), the top-gear equivalent of stock's AE70, so the threshold is the
  8HP's top-gear one. Open: what 0xFFFF392E and the threshold represent.
- **Power-up check** (`latch_check.py`, reads only, immediately after a user power-cycle; before it,
  the value had latched at DB6C) [O]:
  | Moment | 0xFFFF3384 |
  |---|---|
  | after power-up, no TCM frames | **1F 0C** (predicted 0000) |
  | frames 1st (0x11), +0.3 s / +1.5 s | 1F 0C / 1F 0C |
  | 3rd (0x33), +0.3 s / +1.5 s | **44 34** / 45 7E |
  | back to 1st, +0.3 s / +1.5 s | 45 7E / 45 7E |
  **Power-up clears the latch**: the earlier DB6C is gone. The first value differs from my
  prediction because, with no frames, the gear cells are 0 (1st), and the function had already
  climbed to 1st's value before the first read. The step 0x1F0C → 0x4434 within ≤0.3 s is about
  29 steps of 0x148, i.e. one step per ~10 ms pass. The value stays at 3rd's level after dropping to
  1st, confirming the upward-only latch.

## 13. Re-flash with 8th capped at the stock torque-floor factor (2026-11-23, decision B) [O]
- Image SHA-256 `0c2c2691c9dee6b393ad4a5a8429b69646405aad43d7b78dfda1942ae816cce6` (56 edits; 8th keeps
  its own 0x912C cell 0x9136, left at the stock AE70 so the torque floor 0xFFFF45C8 keeps its stock
  magnitude; see `8gear_patch_spec.md`, torque-floor section).
- Live run (log `dumps/flash_8gear_v3_log.txt`): erase 8.9 s, 7 932 blocks in 187 s, verify 02,
  finalise ok, exit 0; the application then broadcasts normally.
- Read-back (`dumps/after_8gear_v3_flash.bin`): **0x8200–0xFFFFF identical to the image**
  (0x9136 = AE70). The boot area changed only by the new record at 0x7400 (6 records, 10 slots left).
- `gear_check.py`: all four cases as predicted.
- With 8th-gear frames (B3 0x88), 0xFFFF3384 = **AE 70**, the stock top value instead of the earlier
  DB6C, as predicted. **The bench ECM now runs this image.**
