# 8hp-d40-ecm-flash

Custom engine-computer (ECM) flash to run the ZF 8HP70 transmission natively in a 2nd-gen
Nissan Frontier / Xterra (D40, VQ40DE).

## How this relates to 8hp-tcu-open

| Project | Runs on | Job |
|---|---|---|
| [**8hp-tcu-open**](https://github.com/alldogsoffroad/8hp-tcu-open) | the 8HP's transmission controller | Open firmware that drives the 8HP. Its Nissan build (`TCU_VEHICLE=NISSAN`) talks to the truck's ECM over CAN the way the original 5-speed transmission controller did (0x174 / 0x176 / 0x177 / 0x560). |
| **8hp-d40-ecm-flash** (this repo) | the truck's ECM | Patches the ECM so it understands what that transmission controller sends: **true gears 1–8** and the 8HP's torque-reduction requests. Includes a tool to flash the ECM over CAN. |

The two are halves of one swap. The stock ECM is calibrated for a 5-speed: it treats gear 8 as
1st and runs 5-speed values in 6th and 7th. Rather than make the transmission controller pretend
to be a 5-speed, the decision (D-N5 in 8hp-tcu-open) was to reflash the ECM to accept 8 forward
gears. Until an ECM is patched with this project, the Nissan build of 8hp-tcu-open must not be
installed in a truck.

## Status (November 2026)

All work so far is on a bench ECM (engine never running):
**23710-9CF0A "DH1", software 9CJ3A, Renesas SH7058, 1 MB flash.**

| Item | Status |
|---|---|
| ROM read over CAN (0x7E0/0x7E8, no security) | ✔ two identical dumps |
| 8-gear patch: gear decoding, gear tables, torque-cut tables | ✔ built, 56 edits ([spec](8gear_patch_spec.md)) |
| 8HP70 per-gear calibration | ✔ ratio-matched defaults ([section P](8gear_patch_spec.md)); **not validated by driving** |
| Checksums | ✔ all four reproduced byte for byte on the stock image |
| ECM's CAN boot loader (session, key, erase, write, verify) | ✔ decoded and confirmed on the bench ([write-up](ecm_reflash_sequence.md)) |
| Flash tool `ncs_flash.py` | ✔ stock image and 8-gear image both flashed; read-back identical |
| Gear 8 accepted from the transmission controller (0x174) | ✔ bench: gear cells read 8th |
| Torque-cut request path for upshifts into 6th–8th | ✔ ROM emulation + bench (engine stopped) |
| Torque cut applied with the engine running | ✘ needs the truck (or a crank-signal simulator) |
| Other ECM part / software numbers | ✘ only 9CJ3A is supported; the builder refuses other images |
| Drive testing | ✘ not started |

## What's here

| File | Purpose |
|---|---|
| `build_8gear_patch.py` | Builds the 8-gear image from your own 9CJ3A dump and fixes the checksums (`--selftest` checks the fixer against the stock image) |
| `ncs_flash.py` | Flashes an image through the ECM's own CAN boot loader. Dry run against a simulated loader by default; `--live` needs the image hash and a typed confirmation |
| `ncs_dump.py`, `ncs_probe.py` | Read-only ROM dump / identity reads over CAN |
| `ncs_keys.py`, `sh2_mini.py` | Security, CRC and payload coding transcribed from the ROM, checked by running the ROM's own routines in a small SH-2 interpreter |
| `gear_check.py`, `torque_check.py`, `step_*.py` | The bench checks behind the status table |
| `8gear_patch_spec.md` | Every patched address with disassembly evidence |
| `ecm_reflash_sequence.md` | The boot-loader protocol, recovery, and every bench result |
| `vq40_ecu_reference.md`, `ecm_tcm_can_interface.md`, `bench_wiring_teensy41_frontier_ecm.md` | ECM identity, the ECM-transmission CAN interface, bench wiring |

Hardware used: a Teensy 4.1 running an SLCAN firmware (`firmware/`) on the ECM's CAN pins
(113/114) at 500 kbit/s, and a 13.5 V bench supply.

**No ROM images are included.** You need your own dump of a 9CJ3A ECM (`ncs_dump.py`); the
builder checks its SHA-256.

## Using it (bench)

```
python3 ncs_dump.py dump dumps/dh1_9CJ3A_pass1.bin      # read your ECM
python3 build_8gear_patch.py --selftest                 # checksum model vs your dump
python3 build_8gear_patch.py                            # -> dumps/dh1_9CJ3A_8gear.bin
python3 ncs_flash.py dumps/dh1_9CJ3A_8gear.bin          # dry run
python3 ncs_flash.py dumps/dh1_9CJ3A_8gear.bin --live --port /dev/ttyACM0 --confirm <12 hex of SHA-256>
```

If a flash is interrupted after the erase, the ECM powers up in its boot loader; run the same
command again (with the stock dump if in doubt). Keep your stock dump.

## Warning

This modifies an engine computer. The calibration for gears 6–8 is a ratio-matched starting
point derived from the stock 5-speed calibration, not a validated tune. Use at your own risk, off
public roads, and check emissions rules where you live.

## License

GPL-3.0, see [LICENSE](LICENSE).
