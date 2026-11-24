# Bench Wiring — Teensy 4.1 → 2013–2015 Frontier VQ40 ECM (Hitachi, 9CF5A era)

**Purpose:** bench interface for the firmware-pull project. Sections 1–6 are the CAN and power
wiring; **section 7 is the K-line interface, which is where the ECM's diagnostics live**
(CAN is the vehicle bus only on this ECM).

> ⚠️ **Source caveat:** pin functions below were first transcribed from the **2017 Frontier
> VQ40DE pinout** (rusefi wiki); the terminal layout was then confirmed from the **2015 FSM**
> itself (EC-533, "ECM Harness Connector Terminal Layout") and the functions (113/114 CAN
> communication line, 104 data link connector) from the 2015 FSM terminal table. Verify with a
> multimeter before applying power (see pre-flight checks).

---

## 1. ECM connections that matter on the bench

| Function | ECM pin | Wire color | Notes |
|---|---|---|---|
| **CAN-H** | **E55-114** | BLU | Vehicle data bus — no diagnostics on this ECM |
| **CAN-L** | **E55-113** | PNK | Vehicle data bus |
| **K-line (data link)** | **E55-104** | V | **The diagnostic interface** — see section 7 |
| Battery (+BATT) | F73-26 | RED/BLK | Keep-alive; fuse 53 (20 A) in vehicle |
| Main power (VBR) | E55-121 | RED | ECM-relay output from IPDM — **tie to +12 V on bench** to power the main rail (no IPDM here) |
| Ignition sense (IGNSW) | E55-109 | WHT/RED | Hot in ON/START; tie to +12 V to emulate key-on |
| Power ground | F73-12, F73-16, E55-123, E55-124, E55-127, E55-128 | BRN/PPL/GRY/BLK/BRN | All one net on the PCB (verify ≈0 Ω pin-to-pin). **Bench: one is sufficient** (electronics-only draw); **two recommended** (e.g. 123+128) purely for contact redundancy on rigged terminals. All six only if the rig ever drives injectors/coils. |

Connector key (facelift D40 ECM, 3 connectors): **F73** = 48-way (terminals 1–48),
**F57** = 48-way (49–96), **E55** = 32-way (97–128). CAN and most bench power lives on
**E55** (32-way) + **F73-26**.

### Physical identification (confirmed from unit photo, Nov 2026)

Viewed from the connector face: **left = 48-way ("F73" or "F57"), center = 48-way (the
other), right = 32-way ("E55", terminals 97–128)** — the right-hand connector is noticeably
shorter with a sparser cavity field (2 rows × 16). White marks sit at the upper-left corner
of all three connector faces (purpose unconfirmed — possibly orientation/QC marks; check
whether hand-applied or molded). Board silkscreen: **GE323337-D** (Hitachi).

**Bench goldmine:** the right-hand 32-way alone carries CAN (113/114), VBR (121), IGNSW
(109), and grounds (123/124/127/128) — the first bench session may not need the 48-ways at
all. Practical power order: **VBR + IGNSW + grounds → probe CAN; add BATT (F73-26) only if
the ECM stays silent** (BATT is the keep-alive feed; ROM lives in the MCU, so memory
retention isn't needed for dumping).

### 32-way ("E55") terminal map — CONFIRMED from 2015 FSM EC-533 (fig JSBIA0505ZZ)

Source: 2015 Frontier FSM EC section, page EC-533, "ECM Harness Connector Terminal Layout"
(nicoclub `service-manual?fsm_download=Frontier/2015/EC.pdf`; local copy /tmp/fsm2015/EC.pdf,
page 533 rendered at 300 DPI). The drawing is marked **"H.S." (harness side)** — so when
looking directly into the **ECU's own connector face, the left-right order is MIRRORED**
relative to this map. Rows/columns and the arithmetic are unchanged; only left↔right flips.

```
FSM harness-side view of the 32-way (terminals 97–128), 4 rows × 8 columns:
         C1   C2   C3   C4   C5   C6   C7   C8
  R1 |  128  124  120  116  112  108  104  100
  R2 |  127  123  119  115  111  107  103   99
  R3 |  126  122  118  114  110  106  102   98
  R4 |  125  121  117  113  109  105  101   97
        (unpopulated per FSM table: 105, 110, 115, 118, 119, 120, 125)

Bench-critical pins on this connector:
  CAN-H 114 → R3·C4      CAN-L 113 → R4·C4    (vertically adjacent pair)
  VBR   121 → R4·C2      IGNSW 109 → R4·C5    K-line 104 → R1·C7
  Grounds: 128 → R1·C1, 127 → R2·C1, 124 → R1·C2, 123 → R2·C2
           (a 2×2 block at the high-number end; VBR 121 sits just below it)
```

Sister connectors (same drawing): 49–96 block is 4×12 (middle view); 1–48 block is 4×12
(right view, **BATT 26 → R3·C6** there). Numbering cascades 128 (top-left of the 97–128
view) down to 1 (bottom-right of the 1–48 view), descending by 1 down each column, by 4
across each row.

**Physical-to-drawing orientation:** on our unit the 32-way is the RIGHT-hand connector of
the three (confirmed by photo) and shows as the LEFT view in the FSM figure — reconcile
ends with the multimeter signatures below before trusting absolute left/right.

**Multimeter cross-checks (unpowered) — the map predicts:**
1. Four cavities in a 2×2-ish block (C1–C2 × R1–R2, high-number end) all ≈0 Ω to each
   other = grounds 127/128/123/124. This end of the connector is the C1 end.
2. The vertical pair at C4·R3/R4 (two cavities on the same column, adjacent rows, on the
   opposite side of the connector from the ground block) shows ≈120 Ω across = CAN 114/113.
3. VBR (C2·R4, immediately below the ground block) vs IGNSW (C5·R4): 100 mA power test
   discriminates (VBR draws, IGNSW barely).

### Electrical identification of CAN + grounds (no diagram needed — do this)

With the ECM **unpowered** and a multimeter on the 32-way, the pins identify themselves:

1. **Grounds:** E55-123/124/127/128 (plus F73-12/16 on the 48-ways) all tie to the PCB
   ground plane. Probe pairs of cavities on Ω: any group reading **≈0 Ω to each other** (and
   to the board's mounting-hole/metal-work plane) = the ground family. Expect them clustered
   (columns 7–8 region).
2. **CAN pair:** measure across candidate adjacent pairs (row-neighbors, then
   column-neighbors):
   - **≈120 Ω** between two cavities = CAN-H ↔ CAN-L with internal termination → those are
     113/114, done.
   - If no ~120 Ω pair: look for two adjacent cavities each showing **similar, symmetric
     resistance-to-ground** (typically low-kΩ via the CAN transceiver) while other signal
     pins read open or asymmetric → that pair is CAN H/L (unterminated). Confirm on the
     powered bench: CAN-H idles ~2.5–3.5 V, CAN-L ~1.5–2.5 V (FSM reference values).
3. **Anchor the orientation:** grounds at columns 7–8 end + CAN pair at column 5 fixes the
   numbering direction (97 starts at the opposite end). VBR (121) and grounds 123/124 then
   fall in column 7; IGNSW (109) in column 4 — sanity-check VBR vs IGNSW by their loads:
   VBR feeds the main rail (measurable diode/capacitive charging to ground via a DMM's
   continuity/Ω pulse), IGNSW reads high-impedance (pull-up input).
4. If ambiguity remains between 121 (VBR) and 109 (IGNSW): power the identified grounds +
   one candidate at a time through the current-limited PSU (13.5 V, 100 mA limit):
   **VBR produces real current draw** (main rail comes up); **IGNSW draws almost nothing**.
   Wrong-pin risk is low at 100 mA current limit, but if any candidate shows a short to
   ground in step 1–3, exclude it from power testing.

### Identifying the physical connectors (important — read first)

F73 / F57 / E55 are **harness-side designations from the FSM wiring diagrams** — they are
generally NOT stamped on the ECM itself, which is why the labeling on the unit won't match.
The ECM-side connectors are identified by **cavity count + molded cavity numbers**:

1. Count cavities: the connector with **32 cavities** is "E55" (terminals 97–128) — it holds
   nearly everything the bench needs: **CAN (113/114), VBR (121), IGNSW (109), grounds
   (123/124/127/128), K-line (104)**. The two 48-cavity connectors are F73 (1–48) and
   F57 (49–96).
2. Terminal numbering is **continuous across the three connectors** (1–128), matching the
   FSM's sequential scheme. The connector faces have small molded/tampographed numbers next
   to the cavities — read the number range to confirm which connector is which
   (1–48 vs 49–96 vs 97–128), then locate the specific cavity by its molded number.
3. CAN pins 113/114 are **adjacent cavities** near one end of the 32-way; grounds
   123/124/127/128 and VBR 121 cluster near the other end.
4. Cross-reference: this Hitachi ECM format is shared with the VQ37VHR 370Z/G37
   (48+48+32, continuous 1–128 numbering). Note the 370Z version carries a **second CAN
   pair at 54/55** ("ENG COMM LINE", YEL/LT GRN) on the middle 48-way. The Frontier FSM
   transcription lists only 113/114 (PNK/BLU) as "Data lines" — that is the diagnostic bus
   we want. If a second twisted pair exists on this unit, ignore it for the dump work.

(If cavity numbers aren't legible on the connector faces, photograph them straight-on and
map by count/orientation against the FSM "Terminal Arrangement of ECM" page — 2015 Frontier
FSM, EC section, via the nicoclub service-manual archive.)

## 2. Teensy 4.1 + SN65HVD230 module

Same transceiver arrangement as the 8hp-teensy-flasher bench rig (single channel needed here).

| SN65HVD230 pin | Connect to |
|---|---|
| VCC | Teensy **3.3 V** |
| GND | Teensy **GND** |
| TXD (CTX) | Teensy **pin 22** (FlexCAN1 TX) — or pin 0 if you prefer CAN2 |
| RXD (CRX) | Teensy **pin 23** (FlexCAN1 RX) — or pin 1 for CAN2 |
| CANH | ECM **E55-114** (CAN-H) |
| CANL | ECM **E55-113** (CAN-L) |
| (120 Ω) | Across CANH↔CANL at the module — see termination check below |

## 3. Wiring diagram

```
 BENCH PSU (+12 V, current-limited 3–5 A)                TEENSY 4.1 (USB → host PC)
 ┌───────────────┐                                     ┌──────────────────────────┐
 │  +12V ────────┼──────┬──────────────┬────────────┐  │                          │
 │               │      │              │            │  │  3.3V ──────┐            │
 │   – (GND) ─┬──┼──────┼───────┬──────┼──────┐     │  │  GND ──┬────┼────┐       │
 └────────────┼─┘      │       │      │      │     │  └────────┼────┼────┼───────┘
              │        │       │      │      │     │           │    │    │
              │        │       │      │      │     │        SN65HVD230 MODULE
              │        │       │      │      │     │        ┌─────────────┐
              │        │       │      │      └─────┼────────┤ GND         │
              │        │       │      └────────────┼────────┤ VCC (3.3 V) │
              │        │       └───────────────────┼───┐    │             │
              │        │                           │   │    │ TXD ◄── Teensy pin 22 (CTX1)
              │        │                           │   │    │ RXD ──► Teensy pin 23 (CRX1)
              │        │                           │   │    │             │
              │        │                           │   │    │  CANH ──┬───┘│
              │        │                           │   │    │  CANL ──┼──┐│
              │        │                           │   │    └──[120Ω]─┼──┼┘ (bench term — verify, §4)
              │        │                           │   │               │  │
              │        │                           │   └───────────────┼──┼── ECM E55-114 (CAN-H)
              │        │                           └───────────────────┼──┼── ECM E55-113 (CAN-L)
              │        │                                               │  │
              └────────┼───────────────────────────────────────────────┼──┴─ common ground bus
                       │                                               │
        ECM F73-26 (BATT +12V) ────────────────────────────────────────┤
        ECM E55-121 (VBR +12V) ────────────────────────────────────────┤  +12 V distribution
        ECM E55-109 (IGNSW +12V) ──────────────────────────────────────┘
        ECM F73-12 / F73-16 / E55-123/124/127/128 (GND) ── to PSU negative
```

CAN H/L: use a **twisted pair** (~1 twist per inch), keep total length under ~1 m on the bench.

## 4. Pre-flight checks (before first power-up)

1. **Continuity/appearance:** confirm connector numbering against the ECM's own connector
   markings (E55 = 32-way). No pins bent, nothing shorted adjacent.
2. **Termination resistance** — ECM unpowered, PSU off:
   - Measure Ω across **E55-113 ↔ E55-114** (CAN-L ↔ CAN-H):
     - **≈120 Ω** → ECM has internal termination. Add no resistor at the module (or a second
       120 Ω → ~60 Ω total, also fine).
     - **open / very high** → no internal termination. Install 120 Ω across CANH/CANL at the
       SN65HVD230 module (many breakouts have an unpopulated 120 Ω spot — check before
       soldering your own).
   - Either 60 Ω or 120 Ω total works at bench wire lengths.
3. **Shorts:** Ω between +12 V nets (F73-26, E55-121, E55-109) and ground pins — should be
   no short. Sanity Ω from BATT to GND (loads a few hundred Ω to kΩ, not 0).
4. **PSU setup:** 13.5–14.0 V, current limit 3–5 A (the ECM alone, no actuators, should sit
   well under ~2 A). Power rails wired with 18–22 AWG.
5. **Ground order:** Teensy GND ↔ PSU negative ↔ ECM grounds tied together **before** plugging
   USB. Never let the CAN transceiver float relative to the ECU.

## 5. Power-up sequence

1. PSU off → wire everything → pre-flight checks above.
2. Power ECM (BATT/VBR/IGNSW) → confirm current draw is sane and stable.
3. Plug Teensy USB → load FlexCAN_T4 sketch at **500 kbps**.
4. Send TesterPresent (`0x7E0`: `02 3E 00 …`, expect `0x7E8`: `06 7E 00 …`) — if it answers,
   the physical layer is done and the NCS session dance (`10 C0` → `21 10`) begins.

## 6. Notes & cautions

- SN65HVD230 at 3.3 V is fine on this 5 V-era CAN network — the bus is differential
  (ISO 11898); this matches the working 8HP70 rig.
- Do not hot-plug the CAN pair with the ECM powered.
- If the ECM ignores everything: re-check termination (§4.2), confirm 500 kbps, and remember
  some Nissan ECUs stay quiet until they see valid bus traffic — the probe script's wake
  pattern handles this.
- ~~K-line (E55-104) intentionally unused~~ — WRONG, see section 7: this ECM's diagnostics are
  on K-line, not CAN.

---

## 7. K-line interface (added 2026-11-23) — the path that matters for the dump

The CAN pins are the vehicle bus only (confirmed on the bench and by FSM LAN-6: the ECM is not
a "Diag on CAN" unit). All diagnostics go through **ECM pin 104 (K-line), E55 R1·C7**.

Hardware: eletechsup **LINTTL3** module (TJA1021 design, SIT1021T on the board; plain
UART-to-K-line level converter). Firmware: `firmware/d40_kline/d40_kline.ino` (your dual
SLCAN sketch plus a K-line bridge on a third USB serial port). Client: `nis_kline.py`.

### 7.1 Teensy → module (corrected 2026-11-23 from a meter-only test)

**The module's RX/TX labels are named from the controller's side:** the terminal marked
**RX is the converter's data output** (connect to the MCU's RX), the terminal marked **TX is
its data input** (connect to the MCU's TX). Both terminals are pulled up to the module's 5 V
by 10k, so each needs a 15k to ground before it reaches a Teensy pin.

Evidence (Teensy wires off both terminals, LIN off the ECM, 15k still on "TX"): VIN 13.45 V,
SLP 3.29 V, INH 12.49 V (awake), RX 5.0 V, TX 3.0 V, LIN 12.14 V. With 1k from LIN to ground
(line dominant): **RX 0.08 V**, TX 3.0 V unchanged. So "RX" follows the line and "TX" doesn't.
The earlier hookup (pin 8 → "RX", pin 7 ← "TX") sent into the output and listened on the
input, which explains every failed test before this one.

```
 TEENSY 4.1                                   LINTTL3 MODULE
                                           ┌──────────────────┐
 pin 8  (Serial2 TX) ────────────┬────────►│ TX   (data IN)   │  pulled up to 5 V by 10k
                               [15k]       │                  │
                                 │         │                  │
 pin 7  (Serial2 RX) ◄───────────┼──┬──────│ RX   (data OUT)  │  open-drain, pulled up to
                                 │ [15k]   │                  │  5 V by 10k
                                 │  │      │                  │
 GND ────────────────────────────┴──┴─┬────│ GND (logic side) │
                                      │    │                  │
 3.3 V ───────────────────────────────│───►│ SLP  (must be H) │
                                      │    │                  │
                                      │    │ INH  (output) ───│── nothing
 (not connected) ─────────────────────│────│ VIN              │  see 7.2 for power
                                      │    │                  │
                                      │    │ LIN  ────────────│──► to ECM pin 104 (7.2)
                                      │    │ GND (power side) │
                                      │    └──────────────────┘
 GND ─────────────────────────────────┴──────── common ground = PSU negative
```

| Teensy side | Module terminal | Notes |
|---|---|---|
| pin 8 (TX2) | TX | module data input; **15k from TX to ground** (keeps the node at 3.0 V whenever pin 8 is not driving) |
| pin 7 (RX2) | RX | module data output; **15k from RX to ground** (required: 5 V through 10k, 15k gives 3.0 V high, 0.08 V low) |
| 3.3 V | SLP | 2–7 V wakes the converter; floating = asleep |
| GND | GND (both) | common ground |
| — | INH | leave open (≈ VIN when awake) |
| — | VIN | +12 V (7.2) |
| — | LIN | to ECM pin 104 (7.2) |

Expected DC levels, module powered and awake, nothing being sent: SLP ≈ 3.3 V, INH ≈ VIN − 1 V,
module TX ≈ 3.0–3.3 V, module RX ≈ 3.0 V, LIN ≈ 12–13 V (0.4 V with 1k to ground, and then
module RX ≈ 0.1 V).

Firmware note: `Y` (label test) drives pin 7 as an output, which now fights the converter's
output; don't use it with this wiring.

Pins 7/8 are used instead of Serial1's pins 0/1 because 0/1 carry the second CAN transceiver.

### 7.2 Module → ECU

```
 LINTTL3 MODULE                          ECM (Hitachi, 32-way connector E55)
                                      ┌─────────────────────────────────┐
 LIN ─────────────────────────────────│ pin 104   K-line (data link)    │
                                      │                                 │
 VIN ◄── bench +12 V ─────────────────│ pin 121   VBR                   │
              (13.5 V)        ┌───────│ pin 109   IGNSW                 │
                              │ ┌─────│ pin 26    BATT (48-way F73)     │
                              │ │     │                                 │
 PSU negative ────────────────┼─┼─────│ pins 123, 124, 127, 128  (GND)  │
                              │ │     │ pins 12, 16 (F73)         (GND) │
                              │ │     │                                 │
                              │ │     │ pins 113 (CAN-L), 114 (CAN-H) │◄─┐ optional: CAN
                              │ │     └─────────────────────────────────┘  │ transceiver on
                              │ │                                            │ Teensy 22/23
                              │ └─ one ground wire is enough (two preferred)│
                              └─ CAN is not needed for the K-line read ─────┘
```

One wire carries the diagnostics: **module LIN → ECM pin 104**. Power and ground on the
ECM are the same as in sections 1–6.

Limits of the SIT1021/TJA1021 on a K-line (from the datasheets):
- Receiver is referenced to VIN: recessive only guaranteed above 0.6 × VIN (8.1 V at 13.5 V),
  dominant below 0.4 × VIN. ECM pin 104 idles at 13.3 V, so no pull-up is needed.
- Transmitter releases the line after 27 ms of continuous low: fast init (25 ms low) works,
  slow init (5-baud address) cannot be done.
- A static "jumper RX to GND" test misleads (the line returns high by itself after ~27 ms).

Status at 2026-11-23: rewired per 7.1 (LIN off the ECM, no load on LIN): `status` idle HIGH,
`gpiotest` healthy (Z10001), `selftest` exact echo 3/3. **The Teensy ↔ converter path works.**
Module RX measured 3.67 V at idle with the 15k: slightly above the Teensy's 3.3 V rail, so
the board's pull-up is stiffer than 10k (≈5.4k). A 10k instead of the 15k on RX gives ≈3.25 V.
With LIN on ECM pin 104 (ECM drawing ~200 mA): loop-back still exact, but **no reply at all**
(E01, no bytes of any kind) to fast init with `81 10 FC 81`, `81 10 F1 81`, `81 11 F1 81` or
`C1 33 F1 81`, first-byte wait 300 ms; 2 s of listening shows no ECM traffic.
Wake-pulse check (firmware `H`, added 2026-11-23): the converter holds the line low for the
whole requested time: 25 ms → line low from +4 µs to +25.015 ms, one edge; 30 ms also intact.
So this converter has no short dominant timeout and the fast-init pulse is correct on the wire;
the "slow init impossible" limit above is not confirmed either. Next discriminator: is the ECM
actually on the line (LIN with 1k to ground ≈ 0.9 V with the ECM attached vs 0.38 V alone).

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

Expected on the K-line once running: fast init → `C1 <KB1> <KB2>`; `1A 81` → `5A 31 <ECU ID>`;
memory reads via `AC 81 83 <addr>…` + `21 81 04 01` (one byte per address, ~4–6 h for a
1.5 MB ROM). Checks: `python3 test_nis_kline.py` (no hardware), then `nis_kline.py status`,
`info`, `read 0 64`, `dump …`.
