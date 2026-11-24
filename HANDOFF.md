# Handoff — 2015 Nissan Frontier ECU firmware pull (bench)

Written 2026-11-23 for whoever continues this project. Everything here came from the
session on 2026-11-20 to 2026-11-23. Paths were checked to exist on that date.

> **Status update, 2026-11-23 evening (Claude), read this first.** Sections 7 and parts of 8 are
> superseded:
> - The K-line module's labels ARE controller-side ("RX" = its output, "TX" = its input), proven
>   with a meter (1k on LIN pulled "RX" to 0.08 V). Rewired, the loop-back passes and the 25 ms
>   fast-init pulse is intact on the wire (the converter held lows of 30 ms without releasing).
>   The current hookup is in `bench_wiring_teensy41_frontier_ecm.md` §7.1.
> - **The ECM does NOT answer on K-line, but it DOES answer diagnostics on CAN** 0x7E0/0x7E8,
>   provided the frames are padded to 8 bytes. The "settled: K-line only" item below was wrong
>   (short-DLC frames and/or listen-only opens). Identity read results are in
>   `vq40_ecu_reference.md`: software 9CJ3A on 23710-9CF0A hardware; the VIN in the ECM decodes
>   to MY2014.
> - **DONE: full 1 MB ROM dumped over CAN, two identical passes** (`ncs_dump.py`, `dumps/`; details
>   in `vq40_ecu_reference.md`). No security access was needed for reading.

---

## 1. Goal and rig

- **Goal:** pull the firmware from a 2015 Nissan Frontier 4.0 VQ40DE ECM (Hitachi) on a bench.
- **Host:** Debian Linux. **Controller:** Teensy 4.1.
- **Bench supply:** 13.5 V, 2 A limit. The ECM drew 0.171 A at power-on.
- **CAN:** transceiver on Teensy pins 22 and 23, wired to ECM pins 113 and 114. A second CAN
  transceiver sits on a breadboard and is not connected to the ECM.
- **Ammeter:** an ACS712 module inline with the ECM's 12 V feed, output on Teensy pin 15.
- **K-line interface:** an eletechsup LINTTL3 TTL-to-LIN module (SIT1021T transceiver).

## 2. Links provided by the user

| Resource | Link |
|---|---|
| fenugrec/nisprog, Nissan ECU reflash tool | https://github.com/fenugrec/nisprog |
| RomRaider/RomRaider | https://github.com/RomRaider/RomRaider |
| jakka351/OpenJ2534 | https://github.com/jakka351/OpenJ2534 |
| User's GitHub: 8hp-teensy-flasher, 8hp-tcu-open, NissanDBCFilez | https://github.com/alldogsoffroad |
| K-line module, Amazon listing | https://www.amazon.com/Converter-Analyzer-TJA1020-Communication-Monitoring/dp/B0F31584W1 |
| K-line module, manufacturer page | https://eletechsup.com/products/linttl3-lin-2-1-sae-j2602-transceiver-lin-bus-module-master-slave-protocol-controller-20kbd-uart-ttl232-rs485-k-line-can-data-analyzer |
| 2015 Frontier FSM, EC section (ECU connector diagram on page 533) | https://www.nicoclub.com/service-manual?fsm=Frontier%2F2015%2FEC.pdf |
| Nissan ECU reverse-engineering wiki | https://nissanecu.miraheze.org/wiki/Main_Page |
| fenugrec/nissutils | https://github.com/fenugrec/nissutils |
| OE parts catalogs | www.amayama.com, www.nissanpartsdeal.com |

## 3. Photos provided by the user

Kept outside the repository; the three used here are in `photos/`.

| File | Shows |
|---|---|
| `IMG_2745.jpg` | ECM board, solder side, three connectors |
| `IMG_2744.jpg` | ECM board, component side (chips are conformal coated) |
| `IMG_2747.jpg` | ECM housing label: 343668 / DH1 / NEC009-007; Hitachi BEM3B2-300A1 3X29 A |
| `IMG_2753.jpg` | ECM connector end, all three connectors |
| `IMG_2754.jpg` | Close-up of the 32-way connector |
| `IMG_2758.jpg` | VF Tuner WiFlash board with the STM32 and CP2102N |
| `IMG_2757.jpg` | VF Tuner WiFlash board with the ESP32-PICO-D4 |
| `IMG_2765.jpg` | K-line module, solder side, terminal labels |
| `IMG_2764.jpg` | K-line module, component side |

## 4. Facts provided by the user

- The ECM is from a 2015 Frontier and was removed from its housing for the photos.
- The chips are lacquered, so their part numbers could not be read.
- The user owns a VF Tuner WiFlash (USB to OBD2) and opened it for inspection.
- From the user's work with VFTuner: early D40 ECUs have 1.5 MB ROMs, middle years 2.0 MB,
  later years 2.5 MB. The user considers the VFTuner owner untrustworthy.
- The firmware that was on the Teensy at the start is committed, so it could be replaced.

## 5. Measurements reported by the user

| Measurement | Value |
|---|---|
| ECM current draw at power-on | 0.171 A |
| Resistance across the ECM CAN pins | 120 Ω |
| ECM pin 104 to ground, unloaded | 13.2 V, later 13.3 V |
| ECM pin 104 with 1k to ground, module wire attached | 13.29 V |
| ECM pin 104 with 1k to ground, wire off the ECM | 0.5 V |
| Module TX to ground, module alone, SLP unconnected | 1.48 V |
| Module SLP to ground, unconnected | 0.96 V |
| Module LIN to ground, unloaded | 13.19 V, later 13.3 V |
| Module LIN with 1k to ground | 0.379 V |
| Module SLP to ground with 3.3 V applied | 3.29 V |
| Module TX with 3.3 V on SLP, open | 4.95 V |
| Module TX with 10k to ground | 2.47 V |
| Module TX with 15k to ground | 3.06 V |
| Module RX to ground, driven by the Teensy | 3.30 V |
| Teensy pin 7 to ground | 3.06 V |
| Module LIN while the Teensy pulsed the module input (20 ms and 24 ms lows) | 12.14 V both times |

Two of these should not be relied on:

- **13.29 V at pin 104 with 1k to ground.** It conflicts with the later 0.5 V reading; the
  resistor was probably not in circuit.
- **12.14 V on module LIN during pulsing.** Unexplained. A fully driven line would read
  about 6 to 7 V.

## 6. Files in this workspace

This repository's folder.

| File | Contents |
|---|---|
| `bench_wiring_teensy41_frontier_ecm.md` | ECM pin map from the FSM, power wiring, K-line schematics (sections 7.1 and 7.2) |
| `vq40_ecu_reference.md` | VQ40 ECM part numbers by year, and the K-line versus CAN findings |
| `firmware/d40_kline/d40_kline.ino` | Teensy firmware: the user's dual SLCAN sketch plus a K-line bridge on a third USB serial port |
| `firmware/build/d40_kline.ino.hex` | The build that was on the Teensy at handoff |
| `nis_kline.py` | Read-only K-line client, ported from nisprog |
| `test_nis_kline.py` | Bench-free tests for the client (all passed at handoff) |
| `ncs_probe.py` | The earlier CAN probe, kept for reference |

## 7. State at handoff

**Settled**

- This ECM does its diagnostics on K-line, on ECM pin 104. CAN pins 113 and 114 carry only
  the vehicle bus: the ECM answered none of the standard diagnostic CAN requests, and the
  FSM (LAN section, page 6) lists the ECM's data link as K-line.
- The nisprog read protocol is known in full (section 8).
- The ECM side is fine: pin 104 is a weak pull-up to battery.
- The Teensy drives its pins correctly and reads them correctly.

**Open**

- The loop-back through the K-line module does not pass. The Teensy drives the module's RX
  low and the module's TX never goes low.
- Whether the module's RX and TX labels are named from the controller's side is not settled.
  One test argued against it, but that test relied on the Teensy's weak internal pull-up and
  is not conclusive.
- The Teensy serial port's receive path has never been proven on real hardware.

**Proposed next step, not yet done**

1. Power off.
2. Move the module's TX wire to Teensy pin 8 and its RX wire to Teensy pin 7.
3. Move the 15k so it is a pull-up from pin 7 to Teensy 3.3 V.
4. Power on and measure pin 7 to ground. About 3.3 V is expected. About 4 V means the board
   has its own 5 V pull-up; then put the 15k from pin 7 to ground instead.
5. Run `python3 nis_kline.py --port /dev/ttyACM2 selftest`. "K-line loop-back OK" means the
   labels are controller-side. Still nothing means the labels are as listed; swap back.

To prove the serial port can receive, put a jumper from Teensy pin 8 to pin 7 and run the
same command.

## 8. Technical notes a successor needs

### ECM connections (2015 FSM, EC section, page 533)

Terminals 97 to 128 are on the 32-way connector, which is the right-hand one when looking
into the ECM's own connector face. The FSM draws it harness-side, so left and right are
mirrored on the ECM itself. FSM harness-side view:

```
        C1   C2   C3   C4   C5   C6   C7   C8
  R1 |  128  124  120  116  112  108  104  100
  R2 |  127  123  119  115  111  107  103   99
  R3 |  126  122  118  114  110  106  102   98
  R4 |  125  121  117  113  109  105  101   97
```

| Function | Terminal |
|---|---|
| K-line (data link) | 104 |
| CAN-H, CAN-L | 114, 113 |
| VBR, IGNSW (both to +12 V on the bench) | 121, 109 |
| Grounds | 123, 124, 127, 128 (one wire is enough) |
| BATT (on the 48-way connector) | 26 |

To download other FSM sections from nicoclub, replace `fsm=` with `fsm_download=` in the
URL. The `fsm=` form returns an index page.

### K-line protocol (from the nisprog and freediag source)

- 10,400 baud, 8 data bits, no parity, 1 stop bit.
- Fast init: bus idle 300 ms, K low 25 ms, K high 25 ms, then send `81 10 FC 81 0E`.
  The ECM answers `C1`, then two key bytes.
- Frame: a format byte, the data, then a checksum. The checksum is the 8-bit sum of every
  byte before it. The format byte is `0x80 + length` with addresses, or just the length for
  the short header.
- ECU ID: send `1A 81`; the answer is `5A 31` plus five characters.
- Memory read without a kernel: send `AC 81` followed by up to twelve `83 <4-byte address>`
  entries, expect `EC 81`; then send `21 81 04 01` and receive one byte per address in
  `61 81 ...`. This reads about one byte per 7.5 bytes on the wire, so a full ROM takes
  several hours.
- nisprog has no kernel for this chip family, so that slow read is the only path it offers.

### Teensy toolchain

- Build: `~/bin/arduino-cli compile --fqbn "teensy:avr:teensy41:usb=serial3" --output-dir "<workspace>/firmware/build" "<workspace>/firmware/d40_kline"`
- Enter programming mode without the button: open `/dev/ttyACM2` with pyserial and set
  `baudrate = 134`. Wait about 4 s.
- Flash: `teensy_loader_cli --mcu=imxrt1062 -w <workspace>/firmware/build/d40_kline.ino.hex`.
  The first attempt often fails with "error writing to Teensy"; run it again.
- USB ports: `/dev/ttyACM0` is CAN1, `/dev/ttyACM1` is CAN2, `/dev/ttyACM2` is the K-line
  bridge.
- K-line pins: Teensy pin 8 transmits to the module's RX, pin 7 receives from module TX.

### Things that caused mistakes in this session

- On this Teensy, a pin only feeds the serial port while the pin is assigned to the serial
  port, and `digitalRead()` only works while the pin is a plain GPIO. A test that drives a
  pin as GPIO and expects the serial port to see it proves nothing.
- The serial port's single-wire loop-back mode does not echo on this core.
- A sleeping SIT1021 leaves its data output floating, so a voltage on the module's TX does
  not show whether the module is awake. SLP must be 2 to 7 V.
- The module pulls its TX up to 5 V through 10k. The Teensy is not 5 V tolerant: use 15k
  from TX to ground, which gives 3.0 V.
- The SIT1021 releases the K-line after 27 ms of continuous low, so a static meter reading
  of a driven line is misleading. Fast init's 25 ms low fits; slow init does not.
- Do not declare new hardware faulty without a test that separates the possible causes.

### K-line bridge commands

`python3 nis_kline.py --port /dev/ttyACM2 <command>`

| Command | Does |
|---|---|
| `status` | Idle line level |
| `selftest` | Send a pattern, expect it echoed through the module |
| `gpiotest` | Drive the transmit pin low, read both pins |
| `info` | Fast init, key bytes, ECU ID |
| `read <addr> <len>` | Read bytes and hexdump them |
| `dump <file> <start> <len>` | Dump a range to a file; resumes if interrupted |
| `stop` | Send stopCommunication |
| `latch`, `latch --read`, `latch --selftest` | Count low pulses on the line by hand tests |
| `toggle [sec] [low_ms]` | Pulse the transmit pin for a meter reading |

`test_nis_kline.py` runs without hardware.

### How the user likes to work

- Bench actions are the user's. The agent runs the tests and reads the results.
- Stage a hand test, then wait for the user to say "go" or "done" before starting.
- Keep to the step asked for. The user stopped a long chain of diagnostics as drifting.
- When asked for something concrete, give exactly that.
