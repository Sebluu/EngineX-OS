# Experimental PRIME 4 output DSP and Mods

Source for original PRIME 4 / JC11 only, on the EngineX 5.3.0 base at upstream
472a414df386ee05fc77eff03cb5146dc15cedcb. No flashable image or approved
installation is provided. PRIME 4+, G2, other boards and unknown output layouts
are excluded. Adaptive loudness and DSP protection remain out of scope.

| Branch | Compiled EQ | Compiled SUB | Purpose |
| --- | --- | --- | --- |
| feature/dsp-core | Off | Off | Inert integration foundation |
| feature/output-eq | On | Off | Output Equalizer topic |
| feature/subharmonic-synth | Off | On | Octave synthesizer topic |
| feature/button-led-behavior | No DSP changes | No DSP changes | QML-only steady PLAY/DJ-FX Mod, experimental |
| test/all-features | On | On | Offline integration checks, including LED Mod and fixture checks |

## Mod Hub split

The native callback adapter cannot be installed through the current Mod API.
Stock EngineX has no public out-of-process audio-insert interface; a Go helper
cannot insert audio into Engine's hardware callback. The matching core still
needs a separately validated EngineX build.

tools/mods/build_output_dsp_mods.py builds two independent, reproducible,
QML-only Mod archives with standard mod.json / qmlFiles: Output Equalizer and
Subharmonic Synthesizer. They contain no firmware, executable, lifecycle script,
dependency installer or service. They stay out of the official registry until
release validation is complete; installing one on stock EngineX cannot add DSP.
Settings → Mixer launches the enabled Mod's panel lazily. A panel failure is
confined to the optional Loader instead of importing Controls into the startup
UI. No speculative Touch FX shortcut is generated.

A third, independent QML-only prime4-steady-leds Mod controls PLAY and DJ-FX indicators without the DSP core or a firmware edit. Its builder verifies original module hashes and a uniquely JC11 assignment context. See docs/prime4-steady-button-leds.md for validation and restart limits.

All processing defaults off. EQ offers eight bands (90 Hz low shelf;
180/350/750/1500/3000/8000 Hz bells; 19 kHz high shelf), advanced frequency/Q and
an optional 24 dB/oct highpass. Main, Booth, Phones and Zone have independent
profiles; the spare ten-channel output pair is untouched. The graph previews
the filter response at 48 kHz. SUB is additive, filtered octave synthesis with
strength and maximum frequency in its basic panel and detector parameters in
Advanced. The existing digital peak limiter follows active processing;
this does not introduce or claim a speaker-protection system.

## Restart and failure behavior

The backend validates the actual installed Mod, its enabled state, removable
source identity and quarantine status before renewing a three-second lease.
The lease uses Linux boot ID and monotonic boot time; a previous boot's lease,
a stopped backend, removed Mod or quarantine cannot keep renewing processing.
The callback reads bounded lock-free atomic snapshots; lease and file checks
happen on the ordinary control worker. Loss of authorization returns the
affected feature to bypass through a 40 ms crossfade. Settings persist
independently, using atomic replacement and file/directory sync.

Missing, truncated, extra-token, non-finite or out-of-range configs bypass.
FIFO, symlink and oversized configs are rejected without a blocking file read.
An unchanged config is reevaluated when the activation mask changes. Flat EQ
does not engage processing or its limiter. Unsupported sample rates and
mismatched hardware layouts bypass.

## Offline validation and remaining release gates

The integration workflow uses disposable build runners, never a deck or the
maintainer's laptop. It checks all feature flag combinations, 32–192 kHz signal
behavior, stereo isolation, exact inactive bypass, malformed file handling,
boot-bound lease expiry, concurrent publication with sanitizers, reproducible
Mod archives, loader lifecycle/quarantine, backend race checks, Qt 5 component
loading, existing mocked boot/fallback and rootfs-overlay regression suites,
ARM64 native callback guard/budget and ARMv7 cross-link/emulated functionality.
Emulation does not establish the PRIME 4's real-time deadline.

Still mandatory before any deck installation:

- Native armhf callback/budget tests on the project's supported build host,
  including the PRIME 4's actual CPU margin.
- Build against the exact official QRC and rootfs; verify Settings placement,
  controller/mixer assignments and native Engine startup.
- Isolated rootfs release gates on populated /data, repeated restarts,
  interrupted install/upgrade, quarantine, stock fallback and uninstall.
  Unit fixtures do not certify these scenarios.
- Physical routing, split cue, Cue/Master, Zone, Computer Mode, external inputs,
  repeated changes and audio continuity.

The normal recovery guard and stock fallback remain responsible for recovery.
No Factory Reset, --erase-data, updater or device reboot is part of these tests.
Passing CI cannot guarantee that an installed experimental build cannot brick
or fail to boot. Do not distribute these source branches as installable
firmware or publish the Mods as compatible with stock EngineX.
