# Subharmonic Synthesizer 0.1.1 (experimental)

QML-only Mod for the original PRIME 4 (JC11), paired with the matching native
output DSP core. This source is not approved for deck installation. Installing
the Mod on stock EngineX cannot add a native audio processor or flash firmware.

Enable it explicitly in Mod Hub, then use Settings → Mixer → Subharmonic
Synthesizer. Main, Booth, Phones and Zone have separate profiles. Defaults are
off, 25% strength and 25–56 Hz output filtering. Advanced controls expose input
band strengths, threshold, attack, release and the lower generated-frequency
cutoff. This is additive octave synthesis; the cutoffs are filter transitions,
not absolute bounds on every harmonic. Adaptive loudness and DSP protection
are not included. Version 0.1.1 provides larger slider touch areas and readable
switch labels on the dark panel. Apply keeps its position while edits are
unsaved.

The boot-bound three-second backend lease follows the Mod loader's validated
enabled/quarantine state. A stopped backend, missing Mod, disable or quarantine
returns processing to bypass with a 40 ms transition. Persisted settings alone
cannot turn DSP on after a reboot. No startup script, helper binary, firmware
patch or system service is installed by this Mod.

Use the shared off-device builder documented in the Output Equalizer README.
Public Mod Hub publication awaits the actual vendor QRC/rootfs restart/fallback
gate, physical routing checks and native PRIME 4 real-time validation.
