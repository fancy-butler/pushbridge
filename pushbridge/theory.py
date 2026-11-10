# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fancy Butler
"""Scales, note names and chord naming.  The scale list is shared with Noodle,
so the two apps speak the same language (klezmer names included)."""
from __future__ import annotations

from typing import NamedTuple, Optional


class Scale(NamedTuple):
    name: str
    group: str
    steps: tuple
    aka: str = ""


SCALES: list[Scale] = [
    Scale('Major (Ionian)', 'Everyday', (0, 2, 4, 5, 7, 9, 11,), 'Bilawal (thaat)'),
    Scale('Natural minor (Aeolian)', 'Everyday', (0, 2, 3, 5, 7, 8, 10,), 'Asavari (thaat) · ≈ Magen Avot'),
    Scale('Harmonic minor', 'Everyday', (0, 2, 3, 5, 7, 8, 11,), '≈ Nahawand (maqam)'),
    Scale('Melodic minor', 'Everyday', (0, 2, 3, 5, 7, 9, 11,), 'Jazz minor'),
    Scale('Major pentatonic', 'Everyday', (0, 2, 4, 7, 9,), 'Chinese gong mode'),
    Scale('Minor pentatonic', 'Everyday', (0, 3, 5, 7, 10,), ''),
    Scale('Blues', 'Everyday', (0, 3, 5, 6, 7, 10,), ''),
    Scale('Major blues', 'Everyday', (0, 2, 3, 4, 7, 9,), ''),
    Scale('Dorian', 'Modes', (0, 2, 3, 5, 7, 9, 10,), 'Kafi (thaat)'),
    Scale('Phrygian', 'Modes', (0, 1, 3, 5, 7, 8, 10,), 'Bhairavi (thaat) · ≈ Kurd (maqam)'),
    Scale('Lydian', 'Modes', (0, 2, 4, 6, 7, 9, 11,), 'Kalyan / Yaman (thaat)'),
    Scale('Mixolydian', 'Modes', (0, 2, 4, 5, 7, 9, 10,), 'Khamaj (thaat) · ≈ Adonai Malach'),
    Scale('Locrian', 'Modes', (0, 1, 3, 5, 6, 8, 10,), ''),
    Scale('Irish/Scottish: Major (Ionian)', 'Irish / Scottish', (0, 2, 4, 5, 7, 9, 11,), ''),
    Scale('Irish/Scottish: Mixolydian', 'Irish / Scottish', (0, 2, 4, 5, 7, 9, 10,), ''),
    Scale('Irish/Scottish: Dorian', 'Irish / Scottish', (0, 2, 3, 5, 7, 9, 10,), ''),
    Scale('Irish/Scottish: Aeolian', 'Irish / Scottish', (0, 2, 3, 5, 7, 8, 10,), ''),
    Scale('Irish/Scottish: Pentatonic', 'Irish / Scottish', (0, 2, 4, 7, 9,), ''),
    Scale('Freygish (Ahava Rabboh)', 'Klezmer', (0, 1, 4, 5, 7, 8, 10,), 'Phrygian dominant · ≈ Hijaz · Spanish Gypsy'),
    Scale('Mi Sheberach (Ukrainian Dorian)', 'Klezmer', (0, 2, 3, 6, 7, 9, 10,), 'Dorian ♯4 · Romanian minor · Altered Dorian'),
    Scale('Klezmer harmonic minor', 'Klezmer', (0, 2, 3, 5, 7, 8, 11,), 'Harmonic minor'),
    Scale('Adonai Malach (≈ Mixolydian)', 'Klezmer', (0, 2, 4, 5, 7, 9, 10,), 'Mixolydian'),
    Scale('Magen Avot (≈ natural minor)', 'Klezmer', (0, 2, 3, 5, 7, 8, 10,), 'Aeolian / natural minor'),
    Scale('Bebop dominant', 'Jazz', (0, 2, 4, 5, 7, 9, 10, 11,), ''),
    Scale('Bebop major', 'Jazz', (0, 2, 4, 5, 7, 8, 9, 11,), ''),
    Scale('Bebop minor (Dorian)', 'Jazz', (0, 2, 3, 4, 5, 7, 9, 10,), ''),
    Scale('Lydian dominant', 'Jazz', (0, 2, 4, 6, 7, 9, 10,), 'Overtone scale · Acoustic scale'),
    Scale('Altered (Super Locrian)', 'Jazz', (0, 1, 3, 4, 6, 8, 10,), 'Diminished whole-tone'),
    Scale('Lydian augmented', 'Jazz', (0, 2, 4, 6, 8, 9, 11,), ''),
    Scale('Dorian ♭2 (Phrygian ♮6)', 'Jazz', (0, 1, 3, 5, 7, 9, 10,), ''),
    Scale('Mixolydian ♭6', 'Jazz', (0, 2, 4, 5, 7, 8, 10,), 'Aeolian dominant · Hindu'),
    Scale('Locrian ♮2 (half-diminished)', 'Jazz', (0, 2, 3, 5, 6, 8, 10,), 'Aeolian ♭5'),
    Scale('Diminished (half-whole)', 'Jazz', (0, 1, 3, 4, 6, 7, 9, 10,), 'Octatonic · dominant diminished'),
    Scale('Diminished (whole-half)', 'Jazz', (0, 2, 3, 5, 6, 8, 9, 11,), 'Octatonic'),
    Scale('Harmonic major', 'Jazz', (0, 2, 4, 5, 7, 8, 11,), ''),
    Scale('Phrygian dominant', 'Harmonic-minor modes', (0, 1, 4, 5, 7, 8, 10,), 'Freygish · Ahava Rabboh · ≈ Hijaz · Spanish Gypsy'),
    Scale('Locrian ♮6', 'Harmonic-minor modes', (0, 1, 3, 5, 6, 9, 10,), ''),
    Scale('Dorian ♯4', 'Harmonic-minor modes', (0, 2, 3, 6, 7, 9, 10,), 'Mi Sheberach · Ukrainian Dorian · Romanian minor'),
    Scale('Ionian ♯5', 'Harmonic-minor modes', (0, 2, 4, 5, 8, 9, 11,), ''),
    Scale('Lydian ♯2', 'Harmonic-minor modes', (0, 3, 4, 6, 7, 9, 11,), ''),
    Scale('Ultralocrian', 'Harmonic-minor modes', (0, 1, 3, 4, 6, 8, 9,), ''),
    Scale('Double harmonic (Byzantine)', 'Middle East / Balkans / Spain', (0, 1, 4, 5, 7, 8, 11,), 'Double harmonic major · ≈ Hijaz Kar · Bhairav · Arabic'),
    Scale('Hungarian minor (Gypsy minor)', 'Middle East / Balkans / Spain', (0, 2, 3, 6, 7, 8, 11,), 'Hungarian double minor · Double harmonic minor'),
    Scale('Hungarian major', 'Middle East / Balkans / Spain', (0, 3, 4, 6, 7, 9, 10,), ''),
    Scale('Neapolitan minor', 'Middle East / Balkans / Spain', (0, 1, 3, 5, 7, 8, 11,), ''),
    Scale('Neapolitan major', 'Middle East / Balkans / Spain', (0, 1, 3, 5, 7, 9, 11,), ''),
    Scale('Persian', 'Middle East / Balkans / Spain', (0, 1, 4, 5, 6, 8, 11,), ''),
    Scale('Spanish 8-tone (flamenco)', 'Middle East / Balkans / Spain', (0, 1, 3, 4, 5, 6, 8, 10,), 'Spanish Phrygian'),
    Scale('Hirajoshi', 'East Asia', (0, 2, 3, 7, 8,), ''),
    Scale('In (Miyako-bushi)', 'East Asia', (0, 1, 5, 7, 8,), ''),
    Scale('Insen', 'East Asia', (0, 1, 5, 7, 10,), ''),
    Scale('Iwato', 'East Asia', (0, 1, 5, 6, 10,), ''),
    Scale('Kumoi', 'East Asia', (0, 2, 3, 7, 9,), ''),
    Scale('Yo', 'East Asia', (0, 2, 5, 7, 9,), ''),
    Scale('Ryukyu (Okinawa)', 'East Asia', (0, 4, 5, 7, 11,), ''),
    Scale('Pelog (approx.)', 'East Asia', (0, 1, 3, 7, 8,), ''),
    Scale('Bhairav', 'India (thaat, approx.)', (0, 1, 4, 5, 7, 8, 11,), 'Double harmonic'),
    Scale('Todi', 'India (thaat, approx.)', (0, 1, 3, 6, 7, 8, 11,), ''),
    Scale('Purvi', 'India (thaat, approx.)', (0, 1, 4, 6, 7, 8, 11,), ''),
    Scale('Marwa', 'India (thaat, approx.)', (0, 1, 4, 6, 7, 9, 11,), ''),
    Scale('Whole tone', 'Symmetric & strange', (0, 2, 4, 6, 8, 10,), ''),
    Scale('Augmented', 'Symmetric & strange', (0, 3, 4, 7, 8, 11,), ''),
    Scale('Tritone', 'Symmetric & strange', (0, 1, 4, 6, 7, 10,), ''),
    Scale('Prometheus', 'Symmetric & strange', (0, 2, 4, 6, 9, 10,), ''),
    Scale('Enigmatic', 'Symmetric & strange', (0, 1, 4, 6, 8, 10, 11,), ''),
    Scale('Messiaen mode 3', 'Symmetric & strange', (0, 2, 3, 4, 6, 7, 8, 10, 11,), ''),
    Scale('Chromatic', 'Symmetric & strange', (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11,), ''),
]

SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
# keys conventionally written with flats
FLAT_ROOTS = {1, 3, 5, 8, 10}


def scale_index(name: str) -> int:
    for i, s in enumerate(SCALES):
        if s.name == name:
            return i
    return 0


def find_scales(text: str) -> list[int]:
    """Indices of scales whose name, group or aka contains `text` (case-insensitive)."""
    t = text.lower().strip()
    return [i for i, s in enumerate(SCALES) if t in s.name.lower() or t in s.aka.lower() or t in s.group.lower()]


_LETTERS = "CDEFGAB"
_LETTER_PC = [0, 2, 4, 5, 7, 9, 11]
_speller: dict = {}


def spelling(root: int, scale: Optional[Scale] = None) -> list[str]:
    """Names for all 12 pitch classes in a key.  Seven-note scales get one letter
    per degree (D Freygish = D E♭ F♯ G A B♭ C); everything else falls back to
    sharps or flats by key."""
    key = (root % 12, scale)
    if key in _speller:
        return _speller[key]
    names = list(FLAT if root % 12 in FLAT_ROOTS else SHARP)
    if scale is not None and len(scale.steps) == 7:
        rname = names[root % 12]
        li = _LETTERS.index(rname[0])
        ok = {}
        for d, step in enumerate(scale.steps):
            letter = (li + d) % 7
            pc = (root + step) % 12
            acc = (pc - _LETTER_PC[letter] + 6) % 12 - 6
            if abs(acc) > 1:
                ok = None
                break
            ok[pc] = _LETTERS[letter] + ("#" if acc == 1 else "b" if acc == -1 else "")
        if ok:
            for pc, n in ok.items():
                names[pc] = n
    _speller[key] = names
    return names


def pc_name(pc: int, root: int = 0, scale: Optional[Scale] = None) -> str:
    return spelling(root, scale)[pc % 12]


def note_name(note: int, middle_c: int = 3, root: int = 0, scale: Optional[Scale] = None) -> str:
    """MIDI note -> name with octave.  middle_c=3 is Ableton/Yamaha (60 = C3),
    middle_c=4 is scientific/Roland (60 = C4).  Octave follows the letter, so
    B#/Cb land in the right octave."""
    name = pc_name(note, root, scale)
    octave = note // 12 - (5 - middle_c)
    if name.startswith("B#"):
        octave -= 1
    elif name.startswith("Cb"):
        octave += 1
    return f"{name}{octave}"


def in_scale(note: int, root: int, scale: Scale) -> bool:
    return (note - root) % 12 in scale.steps


_CHORDS = [
    ((0, 4, 7), ""), ((0, 3, 7), "m"), ((0, 3, 6), "dim"), ((0, 4, 8), "aug"),
    ((0, 2, 7), "sus2"), ((0, 5, 7), "sus4"),
    ((0, 4, 7, 10), "7"), ((0, 4, 10), "7"), ((0, 4, 7, 11), "maj7"), ((0, 4, 11), "maj7"),
    ((0, 3, 7, 10), "m7"), ((0, 3, 10), "m7"), ((0, 3, 7, 11), "m(maj7)"), ((0, 3, 6, 10), "m7b5"),
    ((0, 3, 6, 9), "dim7"), ((0, 4, 7, 9), "6"), ((0, 3, 7, 9), "m6"), ((0, 2, 4, 7), "add9"),
    ((0, 2, 3, 7), "m(add9)"), ((0, 2, 4, 7, 10), "9"), ((0, 2, 4, 10), "9"), ((0, 2, 4, 7, 11), "maj9"),
    ((0, 2, 3, 7, 10), "m9"), ((0, 1, 4, 7, 10), "7b9"), ((0, 4, 5, 7, 10), "7sus4"), ((0, 5, 7, 10), "7sus4"),
    ((0, 7), "5"),
]
_INTERVALS = ["Octave", "Minor 2nd", "Major 2nd", "Minor 3rd", "Major 3rd", "Perfect 4th", "Tritone",
              "Perfect 5th", "Minor 6th", "Major 6th", "Minor 7th", "Major 7th"]


def name_chord(notes, middle_c: int = 3, key_root: int = 0, scale: Optional[Scale] = None) -> Optional[str]:
    """Name what's being held: a note, an interval or a chord (with slash bass)."""
    keys = sorted(set(notes))
    if not keys:
        return None
    pcs = sorted({k % 12 for k in keys})
    bass = keys[0] % 12
    nm = lambda pc: pc_name(pc, key_root, scale)
    if len(pcs) == 1:
        return note_name(keys[0], middle_c, key_root, scale) if len(keys) == 1 else f"{nm(pcs[0])} octaves"
    if len(keys) == 2:
        return _INTERVALS[(keys[1] - keys[0]) % 12]
    for root in [bass] + [p for p in pcs if p != bass]:
        iv = tuple(sorted((p - root) % 12 for p in pcs))
        for tpl, suffix in _CHORDS:
            if iv == tpl:
                return nm(root) + suffix + ("" if root == bass else "/" + nm(bass))
    return " ".join(nm(p) for p in pcs)
