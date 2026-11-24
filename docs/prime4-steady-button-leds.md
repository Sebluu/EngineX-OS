# PRIME 4 steady button LEDs (experimental Mod)

The official PRIME 4 Engine OS 5.3.0 image was downloaded from the pinned
vendor URL and verified against SHA-256
8e49313be0ef338d5452631c5772ee5b1d72e076cae65bf69a6df8b5b210029f.
Its QRC was extracted under unprivileged QEMU, without a physical deck.

JC11_Controller_Assignments.qml identifies its root object as
"PRIME 4 Controller Assignment", uses Simple PLAY LEDs and explicitly enables
DJ-FX flashing. The QML-only builder in tools/mods/build_prime4_led_mod.py
verifies the original controller and module hashes and that this creation
context is uniquely JC11 within the supplied firmware before packaging.

The Mod overrides the shared PlayCue, DJFxActivate and SweepFxSelect QRC modules. Its small
LED-only conditions are scoped to that exact JC11 assignment context.
Paused, ended and empty PLAY LEDs turn off; active DJ-FX and Sweep-FX selection LEDs stay continuously
on. CUE, actions, transport, MIDI note/channel routing, layering, RGB PLAY LEDs
and audio remain unchanged. Unknown assignment contexts retain vendor logic.

The standard Mod Hub manifest has only qmlFiles. There is no helper, script,
firmware write, MIDI-velocity filter, service edit or MCU update. QML components
load with Engine: enable/disable/uninstall takes full effect after an explicit
Engine UI restart, performed when playback is stopped. The Mod never restarts
Engine automatically. The standard loader owns restoration and quarantine.

Tests use real pinned module sources, Qt 5 state fixtures, reproducible
archives, unknown-source refusal and the actual Go Mod loader in temporary
directories. Their simulated loader restart is not a physical power-on test.
Actual controller-QML startup, restart/fallback and visible hardware LED
traffic remain release gates. This source and the generated experimental
archive are not approved for deck installation.

The read-only inspect_button_leds.py evidence collector remains available for
new vendor versions. Never guess note numbers, remove native control actions,
or globally rewrite outgoing MIDI velocities.
