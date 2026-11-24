# Attribution

This project stands on other people's published work. Below is what was used, where, and under
which license. Third-party code was read as reference; no third-party source files are copied
into this repository. Where an algorithm or protocol was re-implemented here, the file says so,
and every re-implementation was checked against the ECM's own ROM code (see
`ecm_reflash_sequence.md`).

## Software projects

| Project | Author / license | Used for | Where in this repo |
|---|---|---|---|
| [RomRaider](https://github.com/RomRaider/RomRaider): `src/main/java/com/romraider/io/j2534/api/TestJ2534NCS.java`, `src/main/java/com/romraider/maps/checksum/NcsCoDec.java` | RomRaider.com, GPL-2.0-or-later | The Nissan NCS CAN read and programming sequence (10 FB / 23 reads; 10 85, 27, 31 81/82, 34 82/83), the payload encoding and the frame CRC-16 framing | `ncs_dump.py`, `ncs_flash.py`, `ncs_keys.py` (`frame_crc`); protocol notes in `ecm_reflash_sequence.md` |
| [nissutils](https://github.com/fenugrec/nissutils): `cli_utils/nislib.c`, `nisrom.c`, `romdb/keysets.csv` | fenugrec, GPLv3 (per source headers) | `enc1`/`dec1` (`mess1`/`mess2`) payload and key algorithms, the "alt" and "alt2" ROM checksums, the keyset database row for this ROM (s27k 968148AD / s36k1 7E5195C7 / s36k2 737133EF), and the `nisrom` identification of this ROM (SH7058, keyset, checksum locations, EEPROM routine) | `ncs_keys.py`, `build_8gear_patch.py` (checksum fixer), `vq40_ecu_reference.md` |
| [nisprog](https://github.com/fenugrec/nisprog) | fenugrec, GPL-3.0 | The Nissan K-line (KWP2000) client the K-line tool is ported from | `nis_kline.py`, `test_nis_kline.py` |
| [freediag](https://github.com/fenugrec/freediag) | fenugrec and contributors, GPL-3.0 | ISO 14230 framing and fast-init details for the K-line port | `nis_kline.py` |
| [python-can](https://github.com/hardbyte/python-can) | LGPL-3.0 | CAN access through the Teensy's SLCAN interface (a runtime dependency, not included) | all CAN scripts |
| [GNU Binutils](https://www.gnu.org/software/binutils/) (`sh-elf-objdump`) | GPL-3.0 | Disassembly of the SH7058 ROM for all static analysis | evidence in `8gear_patch_spec.md`, `ecm_reflash_sequence.md` |
| [rusefi](https://github.com/rusefi/rusefi) wiki | rusefi project | First draft of the VQ40DE ECM pinout (later confirmed against the FSM) | `bench_wiring_teensy41_frontier_ecm.md` |

Licensing note: this repository is GPL-3.0. Code here that re-implements algorithms from
nissutils (GPLv3), nisprog / freediag (GPL-3.0) and RomRaider (GPL-2.0-or-later) is compatible
with that license.

## Related projects by the same author

| Project | Relation |
|---|---|
| [8hp-tcu-open](https://github.com/alldogsoffroad/8hp-tcu-open) | The transmission-controller firmware this ECM patch pairs with (see README). Its documents supplied the 8HP70 gear ratios (`docs/reference/8hp70-landrover-l320-overview.md`), decision D-N5, and the ECM–transmission CAN decode (`docs/reference/nissan-ecm-tcm-interface.md`, `nissan_tx.c` frame layouts used by `gear_check.py` / `torque_check.py`) |
| [NissanDBCFilez](https://github.com/alldogsoffroad/NissanDBCFilez) | Nissan CAN database; frame layouts cross-checked against the truck logs |

## Documents and references

| Source | Used for |
|---|---|
| Nissan **2015 Frontier Factory Service Manual**, EC section (ECM harness connector terminal layout, p. EC-533) and LAN section (via the [NICOclub](https://www.nicoclub.com/service-manual) service-manual archive) | ECM connector pin map, CAN / K-line terminals, bench wiring |
| [Nissan ECU reverse-engineering wiki](https://nissanecu.miraheze.org/wiki/Main_Page) | Background on Nissan ECU families, NCS diagnostics and reflash concepts |
| [amayama.com](https://www.amayama.com) Nissan EPC and [nissanpartsdeal.com](https://www.nissanpartsdeal.com) catalogs | ECM part numbers and model-year applicability in `vq40_ecu_reference.md` |
| Renesas SH-2 / SH-2E instruction set (as implemented by binutils) | Instruction semantics for `sh2_mini.py` |

## Original work in this repository

The ROM analysis of software 9CJ3A (gear handling, torque-cut path, checksums, the CAN boot
loader's services, key check, erase/write/verify and reset logic), the 8-gear patch and its
8HP70 calibration, the flash tool, the SH-2 interpreter and all bench measurements were done for
this project, as recorded in `8gear_patch_spec.md` and `ecm_reflash_sequence.md`.
No Nissan ROM images are distributed here.
