# Output Equalizer 0.1.1 (experimental)

QML-only Mod for the original PRIME 4 (JC11). Requires a separately validated
EngineX build containing the matching output DSP core. Stock EngineX has no
native extension API for this processor. Installing this Mod on stock firmware
does not add DSP or change firmware. This source is not approved for deck installation.

After explicit Mod Hub activation, open Settings → Mixer → Output Equalizer.
Eight bands and an optional highpass have separate Main, Booth, Phones and Zone
profiles. All processing defaults off. Advanced controls expose frequency and Q.
The graph previews the digital filter response at 48 kHz. Version 0.1.1 keeps
switch labels readable against the dark panel background and keeps Apply in
the same position while edits are unsaved.

The loader owns activation, upgrades, removal and quarantine. The core requires
a renewable three-second lease tied to the current Linux boot identity.
Missing, invalid, disabled, removed or quarantined Mods cannot renew it; a dead
backend returns processing to bypass after lease expiry and a 40 ms crossfade.
Settings persist independently of Mod installation. No scripts, helper binaries,
services, firmware writes or dependency installations are included.

Build archives off-device with `python3 tools/mods/build_output_dsp_mods.py --out /tmp/output-dsp-mods`.
They are deliberately excluded from the public Mod registry pending the official
rootfs/QRC restart, fallback, routing and ARM real-time release gates.
