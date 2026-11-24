# PRIME 4 steady button LEDs (investigation)

Requested behavior, separate from DSP:
- FX unit on: steady lit; FX unit off: original inactive state. No BPM/beat-phase modulation of the LED.
- PLAY: steady lit only during normal play; paused, stopped, empty and end-of-track: off.
- Do not change transport, FX DSP, BPM synchronization, CUE, jog, layer selection or other LEDs.
- Scope: original PRIME 4 / JC11 only. Test both physical FX units and both physical decks on every layer.

EngineX already interposes ALSA sequencer LED output in engine_ui_hook.c. The existing code documents velocity 0 = off, 1 = dim, >=2 = on. A NoteOn velocity alone cannot distinguish a beat-phase off event from a genuine FX disable, so globally rewriting MIDI velocity is not correct. The native source of the LED animation must be identified first.

The vendor JC11_Controller_Assignments.qml and JC11_Mixer_Assignments.qml are embedded in Engine, not tracked in this repository. The upstream report docs/re-report/ISSUE-140-PRIME4-BOOT-20261111.md identifies them but does not include their contents. Do not invent note numbers or property names, or modify the vendor binary. The read-only scanner on this branch inventories candidate assignments with context and hashes.

## Obtain evidence (build host, not the live deck)

Use the official matching Engine OS 5.3.0 image, the existing extraction helper and an ARM toolchain:
```sh
arm-linux-gnueabihf-gcc -O2 -shared -fPIC -o /tmp/qrc_dump.so tools/ui-mod/qrc_dump.c -ldl
python3 -I tools/ui-mod/extract_qrc.py --image /path/to/PRIME4-5.3.0-Update.img --preload /tmp/qrc_dump.so --out /tmp/jc11-qrc
python3 tools/ui-mod/inspect_button_leds.py /tmp/jc11-qrc > /tmp/jc11-led-report.txt
```
Share only the relevant excerpts or report for private development; do not commit vendor QRC resources. Confirm whether LED state is a QML binding or a native MCU behavior. If QML, patch only the verified bindings through build_packs.py, with exact unique anchors and a JC11 guard. If native, instrument only the relevant route after establishing the true enable/play state. No runtime LED changes in this investigation commit.

## Acceptance
- Paused/empty/ended PLAY is dark for >10 seconds, including after changing layers. Normal playing is lit.
- FX remains lit throughout multiple BPM changes when active; goes back to native off state immediately on disable.
- Cue preview, mixer FX assignment, MIDI/computer mode, stock LEDs and audio are unaffected.
- Compare actual hardware LED traffic and visible controls on a JC11, not just simulated UI.
