# SPDX-License-Identifier: GPL-3.0-or-later
import copy

from pushbridge import theory as T
from pushbridge.engine import settings as S
from pushbridge.engine.engine import Engine, ROOT_UPPER
from pushbridge.hw import alsa
from pushbridge.hw import protocol as P
from pushbridge.hw.device import PushDevice


class FakeSeq:
    client = 99

    def __init__(self):
        self.sent = []

    def to_push(self, m):
        self.sent.append(bytes(m))


def make():
    seq = FakeSeq()
    dev = PushDevice(seq)
    dev.connected = True
    out = []
    eng = Engine(copy.deepcopy(S.DEFAULTS), dev, out.append)
    return eng, dev, seq, out


# ---------------------------------------------------------------- protocol
def test_lcd_line_uses_24_to_27():
    for line in range(4):
        m = P.lcd_line(line, "hello")
        assert len(m) == 77
        assert m[:8] == bytes((240, 71, 127, 21, 24 + line, 0, 69, 0))
        assert m[8:13] == b"hello" and m[-1] == 247


def test_lcd_glyphs_and_cells():
    b = P.lcd_bytes("B♭ █")
    assert b[:4] == [66, P.GLYPH_FLAT, 32, P.GLYPH_BLOCK]
    c = P.cells("A", "B")
    assert len(c) == 68 and c[0] == "A" and c[9] == "B"


def test_rgb_sysex_nibbles():
    m = P.rgb_led(5, 132, 255, 0)
    assert list(m) == [240, 71, 127, 21, 4, 0, 8, 5, 0, 8, 4, 15, 15, 0, 0, 247]


def test_parse():
    assert P.parse(bytes((0x90, 36, 100))).kind == "pad"
    assert P.parse(bytes((0x90, 36, 0))).kind == "pad_off"
    e = P.parse(bytes((0xB0, 71, 127)))
    assert e.kind == "encoder" and e.value == -1
    assert P.parse(bytes((0xB0, 85, 127))).kind == "button"
    assert P.parse(bytes((0x90, 0, 127))).kind == "enc_touch"
    assert P.parse(bytes((0xE0, 0, 64))).value == 8192
    assert P.parse(bytes((0xA0, 40, 50))).kind == "pressure"


def test_palette_roundtrip_is_sane():
    assert P.palette_index(0, 0, 0) == 0
    assert P.palette_index(255, 255, 255) == 3
    assert P.palette_index(255, 0, 0) == 5          # red [bright]
    assert P.palette_index(0, 0, 255) in (41, 45)  # ocean/blue


# ---------------------------------------------------------------- alsa structs
def test_seq_event_roundtrip():
    for m in [bytes((0x93, 60, 100)), bytes((0x80, 60, 0)), bytes((0xA1, 61, 33)),
              bytes((0xB2, 74, 99)), bytes((0xE0, 0, 64)), bytes((0xE5, 127, 127)), bytes((0xD3, 77)),
              bytes((0xF8,)), bytes((0xFA,))]:
        ev, _ = alsa.encode(m)
        assert alsa.decode(ev) == m, m


def test_sysex_event_roundtrip():
    m = P.lcd_line(0, "sysex")
    ev, keep = alsa.encode(m)
    assert ev.type == alsa.EV_SYSEX and alsa.decode(ev) == m


def test_push_detection():
    assert alsa.is_push1("Ableton Push")
    assert not alsa.is_push1("Ableton Push 2")
    assert not alsa.is_push1("Push Bridge")


# ---------------------------------------------------------------- engine
def test_in_key_4ths_layout_c_major():
    eng, *_ = make()
    assert eng.pad_to_note(0) == 36                 # C1 bottom-left
    assert [eng.pad_to_note(i) for i in range(8)] == [36, 38, 40, 41, 43, 45, 47, 48]
    assert eng.pad_to_note(8) == 41                 # next row up = 3 degrees = F


def test_chromatic_layout():
    eng, *_ = make()
    eng.s["in_key"] = False
    assert eng.pad_to_note(1) == 37 and eng.pad_to_note(8) == 41


def test_freygish_root_d():
    eng, *_ = make()
    eng.s["scale"] = "Freygish (Ahava Rabboh)"
    eng.s["root"] = 2
    assert [eng.pad_to_note(i) for i in range(8)] == [38, 39, 42, 43, 45, 46, 48, 50]


def test_press_release_sends_notes_and_lights():
    eng, dev, seq, out = make()
    eng.handle(P.Event("pad", 36, 100))
    assert out[-1] == bytes((0x90, 36, 100))
    assert dev.pad_rgb[0] == tuple(eng.s["colors"]["pressed"])
    eng.handle(P.Event("pad_off", 36, 0))
    assert out[-1] == bytes((0x80, 36, 0))
    assert dev.pad_rgb[0] == tuple(eng.s["colors"]["root"])


def test_duplicate_pitch_pads_refcount():
    eng, dev, seq, out = make()
    # in 4ths in-key, pad 3 (F) and pad 8 (F) are the same pitch
    assert eng.pad_to_note(3) == eng.pad_to_note(8)
    eng.pad_press(3, 90)
    eng.pad_press(8, 90)
    eng.pad_release(3)
    assert not any(m[0] & 0xF0 == 0x80 for m in out)   # still held on pad 8
    eng.pad_release(8)
    assert out[-1][0] & 0xF0 == 0x80


def test_accent_and_curves():
    eng, *_ = make()
    assert eng.velocity(64) == 64
    eng.s["velocity_curve"] = "soft"
    assert eng.velocity(64) > 64
    eng.accent = True
    assert eng.velocity(10) == 127


def test_encoder_absolute_cc():
    eng, dev, seq, out = make()
    eng.handle(P.Event("encoder", 71, 5))
    assert out[-1] == bytes((0xB0, 74, 5))          # encoder 1 = CC74 by default
    eng.handle(P.Event("encoder", 71, -10))
    assert out[-1] == bytes((0xB0, 74, 0))


def test_scales_overlay_root_buttons():
    eng, dev, seq, out = make()
    eng.handle(P.Event("button", P.BUTTONS["Scales"], 127))
    assert eng.overlay == "scales"
    eng.handle(P.Event("button", P.UPPER_ROW[1], 127))    # G
    assert eng.s["root"] == ROOT_UPPER[1] == 7
    assert "knob:" in dev.lcd[0]
    eng.handle(P.Event("encoder", 72, 2))
    assert eng.s["scale"] == T.SCALES[1].name


def test_unused_buttons_pass_through_as_cc_and_take_led_feedback():
    eng, dev, seq, out = make()
    eng.handle(P.Event("button", P.BUTTONS["Mute"], 127))
    assert out[-1] == bytes((0xBF, 60, 127))
    eng.handle_app(bytes((0xBF, 60, 4)))
    assert dev.button[60] == 4


def test_feedback_notes_light_pads():
    eng, dev, seq, out = make()
    eng.handle_app(bytes((0x90, 36, 100)))
    assert dev.pad_rgb[0] == tuple(eng.s["colors"]["feedback"])


def test_drums_quadrants():
    eng, *_ = make()
    eng.s["mode"] = "drums"
    assert eng.pad_to_note(0) == 36 and eng.pad_to_note(3) == 39 and eng.pad_to_note(8) == 40
    assert eng.pad_to_note(4) == 52 and eng.pad_to_note(32) == 68 and eng.pad_to_note(63) == 99


def test_passthrough_mode():
    eng, dev, seq, out = make()
    eng.handle(P.Event("button", P.BUTTONS["User"], 127))
    assert eng.passthrough
    eng.handle(P.Event("pad", 40, 77))
    assert out[-1] == bytes((0x90, 40, 77))
    seq.sent.clear()
    eng.handle_app(bytes((0x90, 40, 5)))
    assert seq.sent == [bytes((0x90, 40, 5))]
    assert dev.pad_rgb[4] == P.palette_rgb(5)


def test_chord_names():
    assert T.name_chord([60, 64, 67]) == "C"
    assert T.name_chord([62, 65, 69, 72]) == "Dm7"
    assert T.name_chord([60, 67]) == "Perfect 5th"


def test_lcd_flush_only_sends_changes():
    eng, dev, seq, out = make()
    eng.refresh()
    seq.sent.clear()
    dev.flush_lcd()
    first = [m for m in seq.sent if m[4] in (24, 25, 26, 27)]
    assert len(first) == 4
    seq.sent.clear()
    dev.flush_lcd()
    assert seq.sent == []


def test_spelling():
    sc = T.SCALES[T.scale_index("Freygish (Ahava Rabboh)")]
    assert [T.pc_name(2 + st, 2, sc) for st in sc.steps] == ["D", "Eb", "F#", "G", "A", "Bb", "C"]
    maj = T.SCALES[0]
    assert [T.pc_name(6 + st, 6, maj) for st in maj.steps] == ["F#", "G#", "A#", "B", "C#", "D#", "E#"]
    assert T.note_name(65, 3, 6, maj) == "E#3"
    assert T.name_chord([55, 58, 62], 3, 2, sc) == "Gm"
    assert "Bb" in T.note_name(58, 3, 2, sc)


PROC = '''Client   0 : "System" [Kernel]
  Port   0 : "Timer" (Rwe-)
Client  24 : "Ableton Push" [Kernel Legacy]
  Port   0 : "Ableton Push Live Port" (RWeX)
    Connecting To: 128:0
    Connected From: 128:0, 130:0
  Port   1 : "Ableton Push User Port" (RWeX)
Client 128 : "Push Bridge" [User Legacy]
  Port   1 : "Push 1" (RWeX)
    Connecting To: 129:0
Client 129 : "Bitwig Studio" [User Legacy]
  Port   0 : "in" (-We-)
Client 130 : "WINE midi driver" [User Legacy]
  Port   0 : "out" (RWeX)
'''


def test_proc_parse():
    from pushbridge.health import parse_seq_clients
    c = parse_seq_clients(PROC)
    assert c[24]["ports"][0]["from"] == [(128, 0), (130, 0)]
    assert c[128]["ports"][1]["to"] == [(129, 0)]


def test_scan_and_auto_handoff(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from pushbridge import core as core_mod
    from pushbridge.hw.alsa import PortInfo

    class Seq2(FakeSeq):
        client, public = 128, 1
        on_push = on_app = on_change = None

        def ports(self):
            return [PortInfo(24, 0, "Ableton Push", "Ableton Push Live Port", 0x63),
                    PortInfo(24, 1, "Ableton Push", "Ableton Push User Port", 0x63)]

        def connect_push(self, ports):
            self.connected = ports

        def to_apps(self, m):
            pass

    c = core_mod.Core(demo=True)
    seq = Seq2()
    c.seq = seq
    c.device.seq = seq
    assert c.device.scan()
    assert seq.sent[0] == P.mode_live()
    assert any(m[4] == 0x18 for m in seq.sent if m[0] == 0xF0 and len(m) > 5)   # LCD written
    monkeypatch.setattr(core_mod.alsa, "connections_text", lambda: PROC)
    c._auto_handoff()
    assert c.engine.standby and c.device.muted
    seq.sent.clear()
    c.engine.handle(P.Event("pad", 36, 100))
    assert seq.sent == []
    monkeypatch.setattr(core_mod.alsa, "connections_text", lambda: PROC.replace(", 130:0", ""))
    c._auto_handoff()
    assert not c.engine.standby and seq.sent        # took it back and repainted
