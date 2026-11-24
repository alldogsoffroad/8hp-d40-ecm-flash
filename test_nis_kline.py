#!/usr/bin/env python3
"""Bench-free checks for nis_kline.py: runs the protocol layer against a fake bridge that
behaves like the Teensy firmware wired to a cooperative ECU (plus injected faults).
Run:  python3 test_nis_kline.py
"""
import nis_kline as nk


def mem(a):
    return ((a * 2654435761) >> 7) & 0xFF


class FakeECU:
    """Implements the bridge command set on top of a small fake ECU."""

    def __init__(self, quirks=(), refuse_ac=False):
        self.quirks = list(quirks)
        self.refuse_ac = refuse_ac
        self.short = None          # None until fast init succeeded
        self.staged = []
        self.hold = None
        self.cmds = []

    raw = None                    # set below: raw() behaves like cmd()

    def out(self, payload):
        return nk.build_frame(payload, self.short).hex().upper().encode()

    def reply(self, data):
        sid = data[0]
        if sid == 0x1A:
            return b"\x5a\x31DH1AB"
        if sid == 0xAC:
            if self.refuse_ac:
                return b"\x7f" + bytes([sid, 0x11])
            assert data[1] == 0x81 and (len(data) - 2) % 5 == 0
            assert all(data[k] == 0x83 for k in range(2, len(data), 5))
            self.staged = [int.from_bytes(data[k + 1:k + 5], "big") for k in range(2, len(data), 5)]
            return b"\xec\x81"
        if sid == 0x21:
            assert data == b"\x21\x81\x04\x01", data.hex(" ")
            return b"\x61\x81" + bytes(mem(a) for a in self.staged)
        if sid == 0x82:
            return b"\xc2"
        return b"\x7f" + bytes([sid, 0x11])

    def cmd(self, line, timeout=1.5):
        self.cmds.append(line)
        if line[0] == "I":
            if bytes.fromhex(line[1:]) != bytes.fromhex("8110FC810E"):
                return b"E02\r"
            self.short = True
            return b"R" + nk.build_frame(b"\xc1\x6f\x8f", False, 0xFC, 0x10).hex().upper().encode() + b"\r"
        if line[0] == "R":
            hold, self.hold = self.hold, None
            return b"R" + (hold or b"") + b"\r"
        if line[0] != "T" or self.short is None:
            return b"E01\r"                      # not initialised: the ECU stays silent
        f = bytes.fromhex(line[1:])
        hdr = 3 if f[0] & 0x80 else 1
        assert (sum(f[:-1]) & 0xFF) == f[-1], "checksum"
        assert ((f[0] & 0x80) == 0) == self.short, "header style must follow KB1"
        assert (f[0] & 0x3F) == len(f) - hdr - 1, "length field"
        data = f[hdr:-1]
        if self.quirks:
            q = self.quirks.pop(0)
            if q == "drop":
                return b"E01\r"
            if q == "busy":
                return b"R" + self.out(b"\x7f" + bytes([data[0], 0x21])) + b"\r"
            if q == "pending":
                self.hold = self.out(self.reply(data))
                return b"R" + self.out(b"\x7f" + bytes([data[0], 0x78])) + b"\r"
        return b"R" + self.out(self.reply(data)) + b"\r"


FakeECU.raw = FakeECU.cmd


def session(quirks=(), **kw):
    k = nk.NisKline(FakeECU(quirks, **kw))
    assert k.fast_init() == (0x6F, 0x8F)
    assert k.use_short
    return k


def test_frames():
    assert nk.build_frame(b"\x1a\x81", True) == bytes.fromhex("021A819D")
    assert nk.build_frame(b"\x81", False) == bytes.fromhex("8110FC810E"), "startCommunication frame"
    assert nk.build_frame(b"\x1a\x81", False) == bytes.fromhex("8210FC1A8129")
    try:
        nk.build_frame(bytes(64), True)
        raise AssertionError("64 data bytes must be rejected")
    except ValueError:
        pass
    d = nk.decode_frames
    startcom = nk.build_frame(b"\xc1\x6f\x8f", False, 0xFC, 0x10)
    assert startcom == bytes.fromhex("83FC10C16F8F4E"), "hand-computed reference frame"
    assert d(startcom) == [(bytes.fromhex("C16F8F"), True)]
    assert d(b"\x00" + startcom) == [(bytes.fromhex("C16F8F"), True)], "junk byte before the reply"
    two = d(bytes.fromhex("021A819D") + bytes.fromhex("02EC816F"))
    assert [p for p, _ in two] == [bytes.fromhex("1A81"), bytes.fromhex("EC81")]
    bad = bytes.fromhex("83FC10C16F8F00")
    assert d(bad) == [(bad, False)], "bad checksum is reported with the whole frame"
    assert d(bytes.fromhex("83FC10C1")) == [(bytes.fromhex("83FC10C1"), False)], "truncated"
    junk = b"\x00\x00" + startcom + bytes.fromhex("02EC816F")
    assert d(junk) == [(bytes.fromhex("C16F8F"), True), (bytes.fromhex("EC81"), True)]
    assert d(b"") == []


def test_info():
    k = session()
    assert k.ecuid()[0] == "DH1AB"
    assert k.stop() is True
    assert [c[0] for c in k.b.cmds] == ["I", "R", "T", "T"], k.b.cmds   # init, drain, 1A, 82


def test_read():
    k = session()
    assert k.read_mem(0, 40) == bytes(mem(a) for a in range(40))
    assert len(k.b.staged) == 4, "last group of 40 holds 4 addresses"
    assert k.exchanges == 1 + 8
    k2 = session()
    assert k2.read_mem(0x1234, 12) == bytes(mem(a) for a in range(0x1234, 0x1240))


def test_faults():
    k = session(["drop", "busy", "pending", "drop"])
    assert k.read_mem(0x100, 36) == bytes(mem(a) for a in range(0x100, 0x124))


def test_refused():
    k = session(refuse_ac=True)
    try:
        k.read_mem(0, 12)
        raise AssertionError("a refused AC must fail")
    except nk.KlineError as e:
        assert "service not supported" in str(e), e


def test_silent():
    k = nk.NisKline(FakeECU())
    k.b.cmd = lambda line, timeout=1.5: b"E01\r"
    try:
        k.fast_init()
        raise AssertionError("silence must fail")
    except nk.NoResponse:
        pass


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all checks passed")
