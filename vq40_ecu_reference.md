# VQ40DE ECM Reference — NA-Market D40 Frontier / Xterra / Pathfinder (R51)

Compiled Nov 2026 from nissanpartsdeal.com per-year catalog pages, amayama.com Nissan EPC
(nissan-general catalog, Frontier D40 frame 08.2011+), and part-fitment listings.
Part families and exact numbers below; **suffix letters** (A/B/C/D/E) denote production
variants — transmission (MT/AT), emissions (Fed/Cali), 2WD/4WD, and in-service supersessions.

> Scope: **VQ40DE 4.0L V6 only.** Excluded: Frontier 2.5L QR25DE numbers and Pathfinder
> 5.6L VQ56DE V8 numbers (both exist in the same catalog sections).

---

## Generation 1 — K-line era (2005 – mid-2011 production)
**Hitachi, Renesas SH7058 (1 MB ROM, some early SH7055 512 KB), ISO 14230 K-line diagnostics,
ROM/ECU IDs in the EA2xx family (e.g. EA21A). Fully supported by nisprog/npkern and the
RomRaider K-line Nissan definitions.**

| Part family | Known part numbers | Applicability (best available data) |
|---|---|---|
| **EA0xx** | 23710-EA010 | 2005–2006 Frontier 4.0 |
| **EA6xx** | 23710-EA610, EA620 (–A/–B/–C) | 2005–2006 Pathfinder 4.0 |
| **ZP0x** | 23710-ZP03A | 2005–2007 Frontier |
| **ZP4x** | 23710-ZP40A, ZP41A | 2005 Pathfinder |
| **ZP5x** | 23710-ZP50A–E; ZP51A–E; ZP52A/C; ZP53A–E; ZP54A–E; ZP56A/C | 2006–2008 Frontier / Pathfinder |
| **ZS0x / ZS4x** | 23710-ZS02A/C; ZS04A/C (2008 Frontier); ZS40A/B; ZS44A/B | 2008 Frontier |
| **ZL0x–ZL4x** | ZL00A–C; ZL04–ZL07; ZL28–ZL30; ZL32; ZL40; (ZL08–ZL13, ZL39 on Pathfinder 09) | 2008–2010 Frontier/Xterra/Pathfinder (ZL00A confirmed Xterra to 08/2009) |
| **ZS6x** | ZS60A–D; ZS61A–D | 2009 Pathfinder |
| **ZL7x / ZL9x** | ZL76A–ZL79B; ZL91A–ZL99A | 2009–2012 Pathfinder (appear on 2009, 2010, and 2012 catalog pages — Pathfinder ran these latest of the three models). ⚠️ Pathfinder V8 (VQ56) numbers may be mixed in this range; confirm per-VIN |
| **ZZ7x–ZZ9x** | ZZ70A–E (2009 Frontier); ZZ76; ZZ79; ZZ82; ZZ88; ZZ89A (2009–2011 Frontier, discontinued); ZZ94C | 2009–2011 all three models |

Hitachi hardware numbers seen on these units: **MEC35-621** (05 Frontier/Xterra),
**MEC35-652 / MEC35-751-A1** (05 Pathfinder/Xterra), **MEC150-370** (2012 Xterra/Frontier,
late K-line units).

---

## Transition — CAN era begins **08.2011 production (MY2012)**
Per the amayama EPC (Frontier D40, VQ40DE, 4WD PRO-4X 5AT, section 22611):
**23710-9CD5A — period 08.2011 – 12.2012.** So the CAN-only SH725xx ECU ("DH1"-family era)
starts with MY2012 trucks, not MY2013. Corresponding transition numbers:
- 2011–2012 Xterra catalog: **9BA0A/B, 9BD0A–D, 9BE0A–D, 9BE2A–D, 9CD1A–D, 9CD2A–D**
- 2012 Pathfinder catalog: **9BD8/9BD9, 9BE8/9BE9, 9CE0A/B** (alongside K-line ZL76–ZL79)
- 2012–2014 Frontier: **9BF0–9BF8** families (9BF5A = service replacement covering 2012–2014)

---

## Generation 2 — CAN-only era (12.2012 – 2019)
**Hitachi, Renesas SH725xx family (SH-2A), ISO 15765 CAN-only diagnostics @ 500 kbps on
0x7E0/0x7E8. ROM sizes seen by the community: 1.25 MB / 1.5 MB / 2 MB (dschultz's RomRaider
CAN tool accepts all three); VFTuner claims late-year units reach 2.5 MB. ECU label family
"DH1" (e.g. 343668 / DH1 / BEM3B2-300A1 on the 2013–2015 unit on our bench).**

| Part number(s) | Applicability |
|---|---|
| **9CFx: 9CF0A–C, 9CF2A–C, 9CF4A–C, 9CF5A** | EPC period **12.2012 – 10.2013** → MY2013–2014 **Frontier and 2013–2014 Xterra** (2013 Frontier page and 2014 Xterra page list the identical 9CFx families). 9CF5A = the BEM3B2-300A1 era (2013–2015 Frontier 4.0 listings) |
| **23710-ZP37A** | **2015–2018 Frontier 4.0 V6 confirmed** (S/SV/SL/PRO-4X, per nissanpartsdeal catalog). Hitachi hardware on this era: **MEC80-450 B1** |
| **23710-9BD4A** | 2012 Frontier 4.0 PCM (transition family) |
| 2019 Frontier / 2015 Xterra exact numbers | ⚠️ **Not publicly catalogued** — see delisting note below |

### ⚠️ MY2015+ ECM delisting from public EPC
From MY2015 onward, the ECM (23710-…) **disappears from public parts catalogs**: the
nissanpartsdeal "engine control module" sections for 2015/2019 Frontier and 2015 Xterra
contain only **23703-… parts** ("ENGINE CONTROL MODULE BLANK" = the mounting bracket), and
amayama's export EPC likewise shows no ECM rows after the 10.2013 period. The ECM became a
**VIN-programmed dealer-order item** (NATS programming via Consult-III+/NERS). Practical
consequences:
- Beware search results citing "23703-9BF0A for 2014–2019 Frontier" as an ECM — **23703 is the
  bracket series, not the computer**. Search engines conflate them.
- For MY2015–2019 numbers, the remaining sources are: Nissan TechInfo (reprogramming data per
  ECU number), seller listings (Solo/FS1/Clifford pre-programmed units), and the ZP37A-era
  service numbers on unit stickers.

---

## Cross-model sharing
The user-confirmed premise holds: the same ECM families appear across **Frontier (2005–2019),
Xterra (2005–2015), and Pathfinder R51 (2005–2012)** — they share the F-Alpha platform, VQ40DE,
and Hitachi ECM line. Exact numbers differ by model year, 2WD/4WD, MT/AT, and Fed/Cali; the
families above (EA/ZP/ZS/ZL/ZZ → 9B/9CD → 9CF/ZP37) are shared across the three nameplates.

## Protocol summary (ties into the firmware-pull project)
| Generation | Diagnostics | MCU / ROM | Tooling status |
|---|---|---|---|
| 2005–mid-2011 | ISO 14230 K-line | SH7055/7058, 512 KB/1 MB | nisprog + npkern, RomRaider defs — mature |
| 08.2011–~2015 (MY2012–15, 9CD5A/9CF5A incl. DH1) | **K-line (pin 104/DDL2) — CONFIRMED by FSM + bench** despite SH725xx silicon and CAN vehicle bus on 113/114 | SH725xx, size TBV | nisprog-family K-line path |
| ~2016–2019 (ZP37A era) | CAN (per VFTuner "SH7 1.5MB CAN") | SH725xx, up to 2.5 MB claimed | RomRaider TestJ2534NCS protocol (extracted) as reference |

### Bench-established facts (Nov 21 2026 session, BEM3B2-300A1/DH1)
- ECM CAN pins 113/114 = vehicle data network only: broadcasts 0x160/0x180/0x182/0x1F9 @ ~97 Hz
  and 0x551/0x580/0x6E2 @ ~10 Hz at 500 kbps. ECM ACKs external frames (TEC=0).
- **No diagnostic response on CAN** to: 11-bit 0x7E0–0x7E7 (3E 00 / 10 C0), 0x7DF 01 00,
  0x754/0x75D; 29-bit 0x18DB33F1 01 00, 0x18DA10F1 (3E 00 / 10 C0 / 10 03), 0x18DA20F1,
  0x18DA11F1. FSM LAN-6 explains: ECM is NOT a "Diag on CAN" unit (the TCM is); ECM
  diagnostics ride DDL2/K-line on ECM terminal 104 ("Data link connector", V wire,
  idle ~5 V–battery, CONSULT/GST). **A firmware dump via CAN is therefore impossible on
  this unit; the read must go through K-line pin 104.**

### CORRECTION 2026-11-23 (later): the ECM DOES answer diagnostics on CAN
Sent from the Teensy SLCAN port (ACM0, 500 kbit/s, opened normally with `O`, not listen-only):
- `7DF 02 01 00` → `7E8 06 41 00 BF 9F A8 93` (OBD mode 01 PID 00, positive)
- `7E0 02 01 00` → same reply (physical addressing works)
- `7E0 02 3E 00` → `7E8 03 7F 3E 80` (tester present refused, NRC 0x80)
- `7E0 02 10 C0` → `7E8 02 50 C0` (Nissan/NCS diagnostic session accepted)
So the Nov 21 "no diagnostic response on CAN" result was a tooling error (the exact cause is
not established; candidates: listen-only open / P1 mode, or the ACM0/ACM1 confusion recorded
that day), not a property of the ECM. The K-line on pin 104 is fully verified electrically but
the ECM never answers on it; **CAN 0x7E0/0x7E8 is the diagnostic path** (`ncs_probe.py`).
Independent research agrees: SH7253x Nissan ECMs are CAN-diag units (PCMflash lists them under
"Nissan/Infiniti CAN-bus"; npkern/nisprog K-line support stops at SH7058).

### Identity read over CAN (2026-11-23, `ncs_probe.py` frames padded to DLC 8)
Unpadded (short-DLC) requests are ignored by this ECM; zero-padded 8-byte frames are answered.
This, plus listen-only opens, is the likely cause of the Nov 21 "silent on CAN" result.
| Request | Reply (ASCII) |
|---|---|
| `10 C0` | `50 C0` (NCS session) |
| `21 10` ECU ID | `19CJ3A00000` |
| `21 81` VIN | `1N6AD0EV4EN……` (VIN redacted; MY2014 Frontier) |
| `21 F0` | `9CF0A` … `3X61BH9N8` (original part number 23710-9CF0A) |
| `21 FE` | `9CJ3A` (current software, a later reflash not in the catalog table above) |
| `21 FF` | `FF…FF NNAC EOLPG 01 13 11 09 00 34 5C EF 0E` (meaning not decoded) |
| `22 F1 87`, `22 F1 90` | `7F 22 12` (UDS DIDs not supported) |
| `09 02/04/06` in session C0 | `7F 09 80` (OBD mode 09 not served in this session) |
| `10 81` | `50 81` (back to default session) |
| `27 81` seed, in session C0 | `7F 27 80` (refused: not served in this session; no key sent) |
| `10 FB` then `27 81` | `50 FB`, then `7F 27 80` again (no key sent); `10 81` → `50 81`, broadcasts normal |

RomRaider `TestJ2534NCS.java` (master, read 2026-11-23): the **read** path is `10 FB` → `21 10/81/80/F0/FE/FF`
→ `23 <addr32> <len 0x3F>` with **no SecurityAccess**; `27 81` / `27 82 11 22 33 44` appear only in the
programming path after `10 85`. All requests use ISO-TP frame padding (`ISO15765_FRAME_PAD`).

**First memory read, 2026-11-23:** `10 C0` → `10 FB` → `23 00 00 00 00 00 3F` → `63` + 63 bytes,
no SecurityAccess. (The 6-byte form `23 <addr32> <len>` is refused with `7F 23 12`; RomRaider's
frame is `23 <addr32> 00 <len>`.) Address 0 is the SH-2A vector table:
```
00000000  00 00 24 70 FF FF 7F FC 00 00 24 70 FF FF 7F FC   power-on PC 0x00002470, SP 0xFFFF7FFC,
00000010  00 00 24 70 00 00 24 70 00 00 24 70 00 00 24 70   manual-reset PC/SP the same,
00000020  00 00 24 70 00 00 24 70 00 00 24 70 00 00 24 70   exception vectors -> 0x2470
00000030  00 00 24 70 00 00 24 70 00 00 24 70 00 00 24
```
**The dump path is open: session FB + repeated 0x23 reads.**

**FULL DUMP, 2026-11-23 (`ncs_dump.py`):** the ECM reads `0x000000`–`0x0FFFFF` and refuses
`0x100000` with `7F 23 22` (a read straddling 0x100000 is refused the same way). **ROM = 1 MB.**
Two independent passes are byte-identical:
`dumps/dh1_9CJ3A_pass1.bin` = `dumps/dh1_9CJ3A_pass2.bin`,
SHA-256 `7972aa88ba98880fc0942f6496ed08327b1b7f3c9a3148b38676b382f161e1ad`.
~4.6 KB/s, 222 s per pass. Evidence the 1 MB is the whole ROM: aligned pointers in the image
target 0x000000–0x0FFFFF (~20,000) with no cluster above 1 MB; 0xF8000–0xFFFFF is erased (FF)
apart from a few bytes at the very end; `9CF0A` at 0x6EFF, `19CJ3A00000` ×2 at 0x8204 (just past
RomRaider's programming start 0x8200). VFTuner's "1.5 MB early D40" claim does not hold for
this unit.

**Size cross-check from the firmware itself (static, `sh-elf-objdump -b binary -m sh2a -EB`):**
- 0x0016AE–0x0016D4 (programming request range check): accepted target ranges are
  0x8200–0x1FFFF and **0x8200–0xFFFFF**.
- 0x002AC2–0x002B24 (background ROM checksum): 16-bit word sum in 0x30C0-byte slices; the slice
  end is clamped with `mov #16 / shll16` = **0x100000** and the pass completes when the pointer
  equals 0x100000 (a second sum runs up to 0x20000).
- 0x0EDB50–0x0EDB84 (second checksum): bytes are only added when 0x8200 ≤ addr ≤ **0xFFFFF**.
- No literal 0x0017FFFF / 0x001FFFFF exists; 0x00180000 / 0x00200000 never appear aligned.
So the firmware's own checksum and reprogramming logic treat 0x100000 as the end of flash: the
1 MB end is not just a limit in the 0x23 read handler. 0x0000–0x81FF is the boot block;
0x8200–0xFFFFF is the reflashable application + calibration.
Not in this dump: the MCU's separate data flash (EEPROM emulation: adaptations, NATS, DTCs),
which is not in the 0x000000–0x0FFFFF code-flash space.

**Data-flash probe, 2026-11-23** (session FB, `23 <addr> 00 10`): 0x80100000, 0x80104000,
0x80107FF0, 0x80108000, 0x8011FFF0 → all `7F 23 22`; RAM 0xFFFF0000 and 0xFFFF7FF0 → data
(readable); 0x000FFFF0 → FF (end of code flash). So the 0x23 handler serves code flash and RAM
but refuses the SH725x data-flash window. The firmware also has almost no literal pointers into
0x8010xxxx (one, 0x80128115), so whether the NV data (adaptations/NATS/DTCs) is in on-chip data
flash or in an external EEPROM is not established. RAM is in use at least 0xFFFF0000–0xFFFF7FFF
(reset SP 0xFFFF7FFC).

**nissutils `nisrom` on the dump (2026-11-23, fenugrec/nissutils master, built locally):**
`LOADER CPU "SH7058"`, CPUcode 28, LOADER 80 @0x4E3C, `FID "4ZVPFN2"` @0x15628, IVT2 @0x20004,
alt cks 0x2040C–0x221A4, alt2 cks from 0x8204, RIPEMD160 present, keyset `s27k 0x968148AD`,
`s36k1 0x7E5195C7`, **`&EEPROM_read()` 0x6B770, EEPROM PORT 0xFFFFF73A**, MD5
a5016d94809c667aff68e7289c1fd955.
- **The MCU is an SH7058 (1 MB flash), not SH725x** as assumed above; this is why the ROM is
  exactly 1 MB. The SH7058 has no data flash: the probe refusals at 0x8010xxxx are simply
  unmapped space.
- **The NV data is in an external serial EEPROM.** `EEPROM_read(word_addr r4, dest r5)` @0x6B770
  drives SCI registers at 0xFFFFF010 (status @+4, TDR @+3) with chip select on port 0xFFFFF73A,
  word-addressed (`shll` of the index), so 16-bit words; consistent with a 93C66-class
  Microwire part. Callers (17 sites, e.g. 0x41D3A, 0x53306, 0x6C352, 0xB8D5E) read single words
  on demand, often as value + complement pairs (e.g. words 117/79, 113/114); there is no
  whole-EEPROM mirror in RAM, so a RAM dump would not reproduce it.

**CAN diagnostics vs the EEPROM (static decode, verified at the key addresses, 2026-11-23):**
service table @0x183BC (24-byte entries: positive SID, session mask, handler), dispatcher
0xE5F78. `23` handler 0xE82EC, range check 0xE84BA: allowed 0x000000–0x0FFFFF,
0xFFFE0000–0xFFFE0FFF, 0xFFFF0000–0xFFFFFFFF; else NRC 22; params = addr32 + len16 (1..0x3F).
`27` only in sessions 85/FA/DA. **No CAN service reads the external EEPROM**; the only words
available over CAN are those the firmware keeps in RAM: see `dumps/eeprom_words_from_ram.txt`
(words 00–04 and their complements 78–7C, all complement checks pass; 76, 6C). A full EEPROM
read needs a code upload (npkern is K-line only, no CAN port exists) or a SOIC-8 clip on the chip.
(0xFFFF0000+ includes SH7058 I/O registers at the top: don't sweep it blindly with 0x23.)

**The ECM's CAN message table (ROM 0x97B8–0x9837, found 2026-11-23):** pairs of
{config word, HCAN2 ID word = ID<<5}; config high byte 03 = transmit (A3 for 0x580), 01 = receive,
low byte = DLC; 0500 0000 = unused slot. Cross-check: the TX set equals the frames seen on the
bench bus (0x160 DLC 7, 0x180, 0x182, 0x1F9, 0x551, 0x580, 0x6E2).
| Direction | ID (DLC) |
|---|---|
| ECM transmits | 0x1F9 (8), 0x551 (8), 0x182 (8), 0x180 (8), 0x160 (7), 0x6E2 (8), 0x512 (4), 0x580 (8) |
| ECM receives | 0x245 (8), **0x176 (7)**, 0x560 (3), **0x177 (8)**, **0x174 (8)**, 0x342 (4), 0x280 (8), 0x625 (6), 0x358 (8), 0x35D (8), 0x215 (7), 0x354 (8), 0x1A5 (5) |
0x174/0x176/0x177 are the transmission-controller frames the ECM listens for (0x177 = the known
torque-reduction request); the ECM is an automatic-transmission calibration. 0x421 is not in
the ECM's list.

The image holds the donor truck's VIN and immobilizer data; the ECM is a junkyard
unit that is not reusable, so the user does not treat the dump as sensitive (2026-11-23).

## Sources
- nissanpartsdeal.com per-year catalog pages (2005–2012 Frontier, 2011 Xterra, 2005/2006/2009 Pathfinder captured locally before rate-block)
- amayama.com Nissan EPC — Frontier D40 08.2011+ frame, section 22611 (period-coded)
- Part fitment listings (nissanpartsdeal part pages via search index; modulemechanics; eBay)
- Community sources for MCU/ROM: nisprog docs, RomRaider forum (dschultz CAN thread), VFTuner announcements

## Open gaps
1. Exact 2013–2019 Frontier numbers beyond 9CF5A/ZP37A (2014–2015, 2019 variants; 2WD/MT splits)
2. Xterra 2013–2015 and Pathfinder 2010–2012 exact numbers
3. Per-number engine/transmission tagging (which suffix letter = which config)
4. Definitive ROM size per part number (resolves electronically once the bench read works)
