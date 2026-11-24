#!/usr/bin/env python3
"""ncs_flash.py - reflash the DH1 ECM (23710-9CF0A, SH7058) through its own CAN boot loader.

Protocol as decoded from the 9CJ3A ROM and confirmed on the bench up to the key
(ecm_reflash_sequence.md, sections 2-5a):

  10 85                         -> 50 85         application: programming session
  27 81                         -> 67 81 <seed>  application hands off; the loader issues the seed
  27 82 11 22 33 44             -> 67 82         loader: any key (key slots erased, W = FFFF)
  31 81 82 F0 5A                -> 71 81 ..      erase blocks 8-15; F05A is the loader's magic
  31 81 01 (repeat)             -> .. 01 busy, then .. 02
  34 82 a2 a1 a0 80 <128 enc> <~crc lo hi>  x 7932   0x8200..0xFFF80, data = enc1(u32, scode)
  31 82 00, 31 82 01 (repeat)   -> .. 02         loader verifies ROM16_A / ROM16_B
  34 83 00 00 00 30 <48 bytes> <~crc>             finalise: record + start marker 0x8080
  10 81                                          reset into the new application

  python3 ncs_flash.py IMAGE                    # DRY RUN (default): build every frame, check the
                                                # image, run the whole sequence against a
                                                # simulated loader through the real ISO-TP code
  python3 ncs_flash.py IMAGE --live --port /dev/ttyACM0 --confirm <first 12 hex of SHA-256>

Live mode also asks for the word FLASH on the terminal. If anything fails AFTER the erase, the
ECM powers up in its loader (start marker 0x8080 erased): run the same command again, with the
stock image if the new one is in doubt (dumps/dh1_9CJ3A_pass1.bin). The same sequence works
from the loader [I: the loader's own 10 85 / 27 81 serve the same mode].
"""
import argparse
import hashlib
import os
import random
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ncs_keys import SCODE, crc16, dec1, enc1, frame_crc  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
STOCK = os.path.join(HERE, "dumps", "dh1_9CJ3A_pass1.bin")
REQ_ID, RESP_ID = 0x7E0, 0x7E8
APP_START, ROM_END, BLOCK = 0x8200, 0x100000, 0x80
DUMMY_KEY = bytes.fromhex("11223344")
MAGIC_TRAILER = bytes.fromhex("4E4855F9")       # u32 @0xFFF84, checked by the boot at reset
RECORD_SRC = 0x7000                               # latest programming record in the stock image


# ------------------------------------------------------------------ image + frames
def sum16(b, s, e):
    return sum(struct.unpack_from(">%dH" % ((e - s) // 2), b, s)) & 0xFFFF


def check_image(img, stock):
    problems = []
    if len(img) != ROM_END:
        problems.append(f"image is {len(img)} bytes, not 1 MB")
        return problems
    if img[:APP_START] != stock[:APP_START]:
        problems.append("boot area 0x0-0x81FF differs from the ECM's (the loader cannot write it)")
    if struct.unpack_from(">H", img, 0x20000)[0] != sum16(img, 0x20002, ROM_END):
        problems.append("ROM16_A (word @0x20000) wrong: the loader's verify would fail")
    if struct.unpack_from(">H", img, 0x8200)[0] != sum16(img, 0x8202, 0x20000):
        problems.append("ROM16_B (word @0x8200) wrong: the loader's verify would fail")
    if img[0xFFF84:0xFFF88] != MAGIC_TRAILER:
        problems.append("trailer magic @0xFFF84 missing: the boot would not start the application")
    if struct.unpack_from(">I", stock, 0x5FE0)[0] != SCODE:
        problems.append("scode @0x5FE0 in the ECM's boot block is not 0x737133EF")
    return problems


def block_frame(img, addr):
    data = img[addr:addr + BLOCK]
    enc = b"".join(struct.pack(">I", enc1(w, SCODE)) for w in struct.unpack(">32I", data))
    head = bytes([0x34, 0x82, (addr >> 16) & 0xFF, (addr >> 8) & 0xFF, addr & 0xFF, BLOCK])
    return frame_crc(head + enc)


def record_frame(record48):
    assert len(record48) == 0x30
    return frame_crc(bytes([0x34, 0x83, 0, 0, 0, 0x30]) + record48)


# ------------------------------------------------------------------ ISO-TP (both directions)
class IsoTp:
    """ISO 15765-2 over a python-can-like bus (send/recv). Frames always padded to 8 bytes."""

    def __init__(self, bus, timeout=1.0):
        self.bus = bus
        self.timeout = timeout

    def _send(self, data):
        import can
        data = bytes(data) + bytes(8 - len(data))
        self.bus.send(can.Message(arbitration_id=REQ_ID, data=data, is_extended_id=False))

    def _recv_resp(self, timeout):
        end = time.monotonic() + timeout
        while True:
            left = end - time.monotonic()
            if left <= 0:
                return None
            m = self.bus.recv(timeout=left)
            if m is not None and m.arbitration_id == RESP_ID and m.data:
                return bytes(m.data)

    def send(self, payload):
        payload = bytes(payload)
        if len(payload) <= 7:
            self._send(bytes([len(payload)]) + payload)
            return
        n = len(payload)
        self._send(bytes([0x10 | (n >> 8), n & 0xFF]) + payload[:6])
        pos, sn = 6, 1
        while pos < n:
            fc = self._recv_resp(self.timeout)
            if fc is None or fc[0] >> 4 != 3:
                raise IOError(f"no flow control (got {fc.hex() if fc else 'nothing'})")
            flag, bs, st = fc[0] & 0x0F, fc[1], fc[2]
            if flag == 1:            # wait
                continue
            if flag != 0:
                raise IOError(f"flow control overflow/abort {fc.hex()}")
            gap = st / 1000.0 if st <= 0x7F else (0.0001 * (st - 0xF0) if 0xF1 <= st <= 0xF9 else 0.127)
            sent = 0
            while pos < n and (bs == 0 or sent < bs):
                self._send(bytes([0x20 | (sn & 0x0F)]) + payload[pos:pos + 7])
                pos += 7
                sn += 1
                sent += 1
                if gap:
                    time.sleep(gap)

    def receive(self, timeout=None):
        timeout = self.timeout if timeout is None else timeout
        d = self._recv_resp(timeout)
        if d is None:
            return None
        pci = d[0] >> 4
        if pci == 0:
            return d[1:1 + (d[0] & 0x0F)]
        if pci != 1:
            return None
        n = ((d[0] & 0x0F) << 8) | d[1]
        buf = bytearray(d[2:8])
        self._send([0x30, 0x00, 0x00])
        while len(buf) < n:
            c = self._recv_resp(self.timeout)
            if c is None or c[0] >> 4 != 2:
                return None
            buf += c[1:8]
        return bytes(buf[:n])

    def request(self, payload, timeout=None, pending_limit=60.0):
        self.send(payload)
        r = self.receive(timeout)
        t0 = time.monotonic()
        while r and len(r) >= 3 and r[0] == 0x7F and r[2] == 0x78 and time.monotonic() - t0 < pending_limit:
            r = self.receive(5.0)
        return r


# ------------------------------------------------------------------ simulated loader (dry run)
class SimEcu:
    """The ECM as decoded (ecm_reflash_sequence.md section 2): application until 27 81, then the
    boot loader with its checks. Speaks ISO-TP on a fake bus so IsoTp above is exercised."""

    def __init__(self, stock, fc_bs=8, fc_st=0):
        self.flash = bytearray(stock)
        self.mode = "app"
        self.seed_given = self.unlocked = False
        self.magic = None
        self.erase_polls = self.verify_polls = 0
        self.next_addr = None
        self.verified = False
        self.status = 0
        self.fc_bs, self.fc_st = fc_bs, fc_st
        self.out = []                       # frames waiting for the tester
        self.rx = None                      # [total, buf, since_fc]
        self.log = []

    # bus side
    def tester_frame(self, d):
        pci = d[0] >> 4
        if pci == 0:
            self.handle(bytes(d[1:1 + (d[0] & 0x0F)]))
        elif pci == 1:
            n = ((d[0] & 0x0F) << 8) | d[1]
            self.rx = [n, bytearray(d[2:8]), 0]
            self.out.append(bytes([0x30, self.fc_bs, self.fc_st]) + bytes(5))
        elif pci == 2 and self.rx:
            self.rx[1] += d[1:8]
            self.rx[2] += 1
            if len(self.rx[1]) >= self.rx[0]:
                msg = bytes(self.rx[1][:self.rx[0]])
                self.rx = None
                self.handle(msg)
            elif self.fc_bs and self.rx[2] == self.fc_bs:
                self.rx[2] = 0
                self.out.append(bytes([0x30, self.fc_bs, self.fc_st]) + bytes(5))
        elif pci == 3:
            pass                             # tester flow control: responses here are short

    def reply(self, p):
        assert len(p) <= 7
        self.out.append(bytes([len(p)]) + p + bytes(7 - len(p)))

    # loader logic
    def handle(self, m):
        sid = m[0]
        if sid == 0x10:
            self.reply(bytes([0x50, m[1]]))
            if m[1] == 0x81 and self.mode == "boot":
                self.mode = "reset"
            return
        if sid == 0x27 and m[1] == 0x81:
            if self.mode == "app":
                self.mode = "boot"          # hand-off; the loader issues the seed (bench step B/C)
            if self.seed_given:
                return self.reply(b"\x7F\x27\x22")
            self.seed_given = True
            return self.reply(b"\x67\x81" + bytes(random.getrandbits(8) for _ in range(4)))
        if self.mode != "boot":
            return self.reply(bytes([0x7F, sid, 0x22]))
        if sid == 0x27 and m[1] == 0x82:
            if not self.seed_given:
                return self.reply(b"\x7F\x27\x22")
            self.unlocked = True            # W = FFFF: any key
            return self.reply(b"\x67\x82")
        if sid == 0x31:
            if not self.unlocked:
                return self.reply(b"\x7F\x31\x33")
            if m[1] == 0x81 and len(m) == 5 and m[2] in (0x81, 0x82):
                self.magic = m[3:5]
                for a in range(0x8000, ROM_END):  # blocks 8-15
                    self.flash[a] = 0xFF
                self.erase_polls = 2
                self.next_addr = APP_START
                return self.reply(b"\x71\x81\x01")
            if m[1] == 0x81 and m[2:3] == b"\x01":
                if self.erase_polls:
                    self.erase_polls -= 1
                    return self.reply(b"\x71\x81\x01")
                return self.reply(b"\x71\x81\x02")
            if m[1] == 0x82 and m[2:3] == b"\x00":
                self.verify_polls = 2
                return self.reply(b"\x71\x82\x01")
            if m[1] == 0x82 and m[2:3] == b"\x01":
                if self.verify_polls:
                    self.verify_polls -= 1
                    return self.reply(b"\x71\x82\x01")
                a = struct.unpack_from(">H", self.flash, 0x20000)[0] == sum16(self.flash, 0x20002, ROM_END)
                b = struct.unpack_from(">H", self.flash, 0x8200)[0] == sum16(self.flash, 0x8202, 0x20000)
                self.verified = a and b
                return self.reply(bytes([0x71, 0x82, 2 if self.verified else (8 if not a else 4)]))
            return self.reply(b"\x7F\x31\x12")
        if sid == 0x34:
            if not self.unlocked:
                return self.reply(b"\x7F\x34\x33")
            if crc16(m) != 0xF0B8:
                return self.reply(b"\x74\x0A")
            if self.magic != b"\xF0\x5A":
                return self.reply(b"\x74\x01")
            sub, addr, ln = m[1], (m[2] << 16) | (m[3] << 8) | m[4], m[5]
            data = m[6:-2]
            if sub == 0x82:
                if addr != self.next_addr or ln != BLOCK or not (APP_START <= addr <= ROM_END - BLOCK):
                    return self.reply(b"\x7F\x34\x12")
                plain = b"".join(struct.pack(">I", dec1(w, SCODE)) for w in struct.unpack(">32I", data))
                self.flash[addr:addr + BLOCK] = plain
                self.next_addr += BLOCK
                return self.reply(b"\x74\x02")
            if sub == 0x83:
                if addr or ln != 0x30 or not self.verified:
                    return self.reply(b"\x7F\x34\x22")
                self.flash[0x7100:0x7130] = data
                # the real loader writes 00 here (bench 2026-11-23: 0x8080-0x80FF read back 00;
                # 0x19DC fills its buffer with r1 = 0); the reset check ORs the byte with F0
                self.flash[0x8080:0x8100] = b"\x00" * 0x80
                return self.reply(b"\x74\x02")
            return self.reply(b"\x7F\x34\x12")
        return self.reply(bytes([0x7F, sid, 0x11]))

    def boots_application(self):
        b = self.flash[0x8000] & (self.flash[0x8080] | 0xF0)
        return not (b == 0xFF or b < 0xF0) and self.flash[0xFFF84:0xFFF88] == MAGIC_TRAILER


class FakeBus:
    def __init__(self, ecu):
        self.ecu = ecu

    def send(self, msg):
        assert msg.arbitration_id == REQ_ID and len(msg.data) == 8
        self.ecu.tester_frame(bytes(msg.data))

    def recv(self, timeout=None):
        import can
        if not self.ecu.out:
            return None
        return can.Message(arbitration_id=RESP_ID, data=self.ecu.out.pop(0), is_extended_id=False)

    def shutdown(self):
        pass


# ------------------------------------------------------------------ the sequence
class Abort(Exception):
    pass


def run(tp, img, record48, say, erased_flag):
    def expect(payload, ok, what, timeout=None):
        r = tp.request(payload, timeout)
        if not r or not ok(r):
            raise Abort(f"{what}: sent {bytes(payload[:8]).hex(' ')}..., got {r.hex(' ') if r else 'no reply'}")
        return r

    expect([0x10, 0x85], lambda r: r[0] == 0x50, "10 85")
    say("10 85 ok")
    r = expect([0x27, 0x81], lambda r: r[0] == 0x67, "27 81 (hand-off + seed)")
    say(f"27 81 ok, seed {r[2:].hex()}")
    expect(bytes([0x27, 0x82]) + DUMMY_KEY, lambda r: r[0] == 0x67, "27 82 (key)")
    say("27 82 ok: loader unlocked")

    expect([0x31, 0x81, 0x82, 0xF0, 0x5A], lambda r: r[0] == 0x71, "31 81 (erase start)", timeout=5.0)
    erased_flag[0] = True
    say("erase started: from here an abort leaves the ECM in its loader")
    t0 = time.monotonic()
    while True:
        r = expect([0x31, 0x81, 0x01], lambda r: r[0] == 0x71, "31 81 01 (erase poll)", timeout=5.0)
        if r[-1] != 0x01:
            break
        if time.monotonic() - t0 > 120:
            raise Abort("erase did not finish in 120 s")
        time.sleep(0.4)
    if r[-1] != 0x02:
        raise Abort(f"erase ended with status {r[-1]:02X}")
    say(f"erase done ({time.monotonic() - t0:.1f} s)")

    t0 = time.monotonic()
    addrs = range(APP_START, ROM_END, BLOCK)
    for i, addr in enumerate(addrs):
        expect(block_frame(img, addr), lambda r: r[0] == 0x74 and r[-1] == 0x02, f"34 82 @0x{addr:05X}", timeout=2.0)
        if i % 256 == 0 or addr == ROM_END - BLOCK:
            el = time.monotonic() - t0
            say(f"  0x{addr:05X}  {i + 1}/{len(addrs)}  {el:.0f} s")
    say("all blocks written")

    expect([0x31, 0x82, 0x00], lambda r: r[0] == 0x71, "31 82 00 (verify start)", timeout=5.0)
    t0 = time.monotonic()
    while True:
        r = expect([0x31, 0x82, 0x01], lambda r: r[0] == 0x71, "31 82 01 (verify poll)", timeout=5.0)
        if r[-1] != 0x01:
            break
        if time.monotonic() - t0 > 60:
            raise Abort("verify did not finish in 60 s")
        time.sleep(0.4)
    if r[-1] != 0x02:
        raise Abort(f"verify failed, status {r[-1]:02X} (4 = calibration sum, 8 = program sum)")
    say("verify ok (ROM16_A and ROM16_B)")

    expect(record_frame(record48), lambda r: r[0] == 0x74 and r[-1] == 0x02, "34 83 (finalise)", timeout=5.0)
    say("finalise ok: record written, start marker set")
    tp.request([0x10, 0x81], timeout=1.0)
    say("10 81 sent: the ECM resets into the new application")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("--stock", default=STOCK, help="the ECM's own dump (boot block, scode, record)")
    ap.add_argument("--record-hex", help="48-byte programming record (default: copy of the stock record @0x7000)")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--confirm", help="first 12 hex digits of the image SHA-256 (live mode)")
    a = ap.parse_args()

    img = open(a.image, "rb").read()
    stock = open(a.stock, "rb").read()
    sha = hashlib.sha256(img).hexdigest()
    print(f"image {a.image}  SHA-256 {sha}")
    problems = check_image(img, stock)
    if problems:
        for p in problems:
            print("  REFUSED:", p)
        sys.exit(1)
    print("  image checks ok: 1 MB, boot area = ECM's, ROM16_A/B correct, trailer magic present")
    record = bytes.fromhex(a.record_hex) if a.record_hex else stock[RECORD_SRC:RECORD_SRC + 0x30]
    if len(record) != 0x30:
        sys.exit("record must be 48 bytes")
    frames = [block_frame(img, ad) for ad in range(APP_START, ROM_END, BLOCK)]
    assert len(frames) == 7932 and all(len(f) == 136 and crc16(f) == 0xF0B8 for f in frames)
    print(f"  {len(frames)} block frames built (136 bytes each, CRC residue F0B8)")

    erased = [False]
    if not a.live:
        random.seed(1)
        ecu = SimEcu(stock, fc_bs=8, fc_st=0)
        tp = IsoTp(FakeBus(ecu), timeout=0.2)
        try:
            run(tp, img, record, lambda s: print("  [sim]", s), erased)
        except Abort as e:
            sys.exit(f"DRY RUN FAILED: {e}")
        same = bytes(ecu.flash[APP_START:]) == img[APP_START:]
        print(f"DRY RUN: simulated flash 0x8200-0xFFFFF == image: {same}; "
              f"boot area untouched: {bytes(ecu.flash[:0x7000]) == stock[:0x7000]}; "
              f"start marker set, application would start: {ecu.boots_application()}")
        sys.exit(0 if same and ecu.boots_application() else 1)

    if not a.confirm or not sha.startswith(a.confirm.lower()) or len(a.confirm) < 12:
        sys.exit("live mode needs --confirm with the first 12 hex digits of the image SHA-256")
    print("LIVE: this erases and rewrites 0x8200-0xFFFFF of the ECM. Supply must be stable.")
    if input("type FLASH to continue: ").strip() != "FLASH":
        sys.exit("not confirmed")
    import can
    bus = can.Bus(interface="slcan", channel=a.port, bitrate=500000)
    tp = IsoTp(bus, timeout=1.0)
    try:
        run(tp, img, record, print, erased)
        print("DONE. Power-cycle and check the broadcasts (step_b_loader.py --listen).")
    except (Abort, IOError) as e:
        print(f"ABORTED: {e}")
        if erased[0]:
            print("The erase had started: the ECM will power up in its loader. Re-run this command "
                  "(with the stock image dumps/dh1_9CJ3A_pass1.bin if in doubt).")
        else:
            print("Nothing was erased. Power-cycle the ECM to return to the application.")
        sys.exit(1)
    finally:
        bus.shutdown()


if __name__ == "__main__":
    main()
