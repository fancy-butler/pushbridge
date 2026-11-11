# Push Bridge

Play the **original (2013) Ableton Push** with any MIDI software on Linux and Windows: Bitwig, Reaper, Ardour, Surge XT, Vital, Noodle, a hardware synth on a USB-MIDI cable, or anything else that takes MIDI.

The Push 1 is a class-compliant USB-MIDI device, so Linux sees it out of the box. On its own, though, it's a dumb grid. Scales, in-key layouts, the display and the colours all came from Ableton Live's script. Push Bridge does that job instead:

- **Notes mode** with Live-style **in-key** or **chromatic** layouts (4ths, 3rds or sequential), with root pads in blue and in-scale pads in white. When you press a note, every pad with that pitch lights up.
- **67 scales**, the same list as Noodle. Klezmer names sit beside the textbook ones (Freygish / Ahava Rabboh, Mi Sheberach, Adonai Malach, Magen Avot), along with Irish/Scottish modes, jazz, harmonic-minor modes, maqam and Balkan approximations, Japanese, Indian thaat and more. Notes are spelled properly for the key (D Freygish is D E♭ F♯ G A B♭ C).
- **Scales page on the Push itself.** Press **Scales**: the top button row picks C G D A E B and the row above the pads picks F B♭ E♭ A♭ D♭ G♭, as on Live. Any knob scrolls through scales. The last two top buttons switch the layout and In Key / Chromatic.
- **Drums mode** (press **Note**): four colour-coded 4×4 blocks starting at C1 (36), on **channel 10** (the General MIDI drum channel), so any GM synth plays a kit straight away. Octave buttons move by 16.
- **Live chord names** on the Push's LCD while you play (Gm, Cmaj7, D7/F♯ …).
- **Pressure**: polyphonic or channel aftertouch. The **touch strip** does pitch bend or mod wheel.
- **Accent** (full velocity), **velocity curves** (soft / hard / fixed).
- **Note Repeat** with the 1/4–1/32t buttons. Press harder to play the repeats louder.
- **8 knobs + Master** send CCs. Name them in the app and the LCD shows the names and values. Shift+turn gives fine control, and there's an optional relative mode for endless-encoder-aware software.
- **MIDI clock**: Play starts and stops it, the Tempo knob sets BPM (Swing knob = 0.1 BPM fine), Tap Tempo taps and blinks on the beat.
- **Every other button is yours.** It sends a CC you can MIDI-learn. Send the CC back and the button's light follows.
- **Notes coming back from your software light the pads** in orange, so a MIDI file playing in your DAW shows on the grid.
- **User button = plain MIDI controller.** The raw Push goes straight to your software and back, including LEDs and LCD sysex.
- **Hand off to Ableton Live.** When another app (for example Live under Wine) starts driving the Push directly, Push Bridge goes quiet and takes over again once that app lets go. There's also a manual switch.
- **Live on-screen Push** that mirrors every light and the display. It also works as a virtual Push you can play with the mouse.
- **Health check** for every link from the Push to your software, including which apps are listening and whether anything else is fighting over the Push.
- **Stays out of the way**: tray icon, start at login, headless systemd service.

Licensed GPL-3.0-or-later. © 2026 Fancy Butler. Not affiliated with Ableton or Akai.

![The live surface](docs/surface.png)

---

## Install

```fish
git clone https://github.com/fancy-butler/pushbridge
cd pushbridge
```

Plug the Push in **with its power supply** (USB bus power alone can't light it fully), then check that Linux sees it:

```fish
aconnect -l | grep -i push      # → client NN: 'Ableton Push' with two ports
```

### Arch / CachyOS

```fish
cd packaging/arch
makepkg -si
```

### Fedora

```fish
sudo dnf install python3-pyside6 alsa-lib pipx
pipx install --system-site-packages .
```

### Debian / Ubuntu (24.04+)

```bash
sudo apt install python3-pyside6.qtwidgets python3-pyside6.qtsvg pipx
pipx install --system-site-packages .
```

There are no compiled extensions and no udev rule to install. MIDI goes straight to `libasound` through ctypes, using the ALSA *sequencer*. That means Push Bridge never locks the Push away from other software.

Run `pushbridge`, or `pushbridge --demo` to try it without hardware.

### Windows 10 / 11

Download **PushBridge-…-windows-setup.exe** (or the portable zip) from [Releases](https://github.com/fancy-butler/pushbridge/releases) and run it. No drivers needed: the Push is class-compliant.

Windows has no virtual MIDI ports, so Push Bridge reaches your software through a **loopback pair** (a one-time, two-minute setup; Health walks you through it):

- **Windows 11**: open the **MIDI Settings** app (Windows MIDI Services Tools) › Loopback Endpoints › *Create New Loopback Endpoint Pair*. Name side A **Push Bridge App** and side B **Push Bridge**. In your DAW, pick **Push Bridge**. (The default app loopback pair also works; Push Bridge takes side A and you pick side B.)
- **Windows 10**: install [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html) and add two ports, **Push Bridge** and **Push Bridge Back**. In your DAW, use **Push Bridge** as the input and **Push Bridge Back** as the output (for lights).

You can also pick the ports by hand under Knobs & buttons.

## Use it

1. Start Push Bridge. The Push lights up and its display shows your scale.
2. In your software, pick **Push Bridge › Push 1** as the MIDI input (under PipeWire it may just say "Push Bridge").
3. Play.

| On the Push | Does |
|---|---|
| **Scales** | Key and scale page (top row C G D A E B, lower row F B♭ E♭ A♭ D♭ G♭, any knob = scale) |
| **Note** | Notes ↔ Drums |
| **Octave ↑↓**, **▲▼** | Octave (drums: ±16 pads) |
| **◀ ▶** | Root down/up a semitone (Shift: a 5th) |
| **Accent** | Every hit at 127 |
| **Repeat** + 1/4 … 1/32t | Note repeat at that rate |
| **Play**, **Tap Tempo**, Tempo/Swing knobs | MIDI clock |
| **User** | Plain MIDI controller (raw pass-through) |
| **Shift** + knob | Fine adjust |
| Everything else | A CC on channel 16 (configurable) for MIDI-learn, with light feedback |

## Ableton Live, Bitwig and other Push software

Push Bridge gets out of Live's way:

- **Windows**: while Ableton Live is running, Push Bridge lets go of the Push completely and takes it back when Live quits. With Windows 11's multi-client MIDI that's seamless. On Windows 10 only one app can open the Push at a time, so if Live started while Push Bridge was holding it, re-enable Push in Live's Link/Tempo/MIDI preferences (or press **Hand off** before starting Live).
- **Linux**: Live doesn't run natively. People run it under Wine with mixed results, and whether Live's Push 1 script works through Wine's MIDI is up to Wine. When Live (or any other app) starts sending to the Push directly, Push Bridge steps aside automatically.

The same goes for **Bitwig with the DrivenByMoss extension**, which has full Push 1 support (clip launching, sequencer, device pages, display). There's no need to quit Push Bridge for it.

Either way, **Hand off** on the Play page (or in the tray) lets go of the Push by hand, and **Take it back** reclaims it. The automatic behaviour can be switched off under Knobs & buttons › App.

## Headless

```fish
systemctl --user enable --now pushbridge.service
```

## Credits

Ableton never published the Push 1 protocol. Push Bridge builds on community work: [crosslandwa/push-wrapper](https://github.com/crosslandwa/push-wrapper), [Carlborg/hardpush](https://github.com/Carlborg/hardpush), the pushmod blog (RGB pad sysex) and Adam Murray's palette notes. Icons: Lucide (ISC).
