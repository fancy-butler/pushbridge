# Changelog

## 0.2.2 (2026-11-10)
- **Fix: the 64 pads didn't send anything.** Push Bridge now greets the Push the way Live does (welcome, Live mode, pad calibration, pad sensitivity, pad timing, aftertouch) using Live's own default values; says goodbye on quit
- Pad response (Live's six firmware velocity curves) and pad sensitivity (Live's threshold) on the Pads & strip page

## 0.2.1 (2026-11-10)
- Drums mode plays on its own channel, default 10 (General MIDI drums): FluidSynth and other GM synths play a kit with no setup
- Hand off now lets go of the Push completely on Linux too, so Bitwig + DrivenByMoss (or anything that opens the raw device) can take it; renamed "Hand to Live" to "Hand off"

## 0.2.0 (2026-11-10)
- **Windows 10/11.** New WinMM backend (ctypes, no compiled extensions), installer and portable zip built by CI
- Talks to your software through a loopback pair: Windows 11 MIDI Settings loopback, the default app loopback, or loopMIDI on Windows 10; picked automatically or by hand
- Windows hand-off: lets go of the Push entirely while Ableton Live runs, takes it back after
- Windows health checks with setup steps; start at login via the Run key; settings in %APPDATA%\PushBridge
- Windowed builds log to pushbridge.log next to the settings

## 0.1.0 (2026-11-10)
First version.
- Notes mode: in-key / chromatic, 4ths / 3rds / sequential, 67 scales shared with Noodle, proper note spelling
- Scales page on the Push itself (Live-style root buttons, any knob = scale)
- Drums mode (four 4×4 blocks from C1)
- Pressure (poly / channel), touch strip (pitch bend / mod), velocity curves, Accent, Note Repeat
- 8 named knobs + Master as CCs with LCD names and values; relative mode
- MIDI clock: Play, Tempo/Swing knobs, Tap Tempo
- Unused buttons pass through as CCs with LED feedback; notes from apps light the pads
- User button: raw pass-through; automatic and manual hand-off to Ableton Live
- On-screen live Push (also a virtual controller), health check, tray, headless service
