# Experimental PRIME 4 output DSP and Mods

The [2026-11-24 foundation review](output-dsp-foundation-review.md) describes
the current latency model, source-review blockers and proposed bounded DSP Mod
interface. In particular, the control-worker lease is not an independent
watchdog when that worker itself stops running. No physical audio acceptance
is implied by the offline tests below.

Source for original PRIME 4 / JC11 only, on the EngineX 5.3.0 base at upstream
472a414df386ee05fc77eff03cb5146dc15cedcb. No flashable image or approved
installation is provided. PRIME 4+, G2, other boards and unknown output layouts
are excluded. Adaptive loudness and DSP protection remain out of scope.

| Branch | Compiled EQ | Compiled SUB | Purpose |
| --- | --- | --- | --- |
| feature/dsp-core | Off | Off | Inert integration foundation |
| feature/output-eq | On | Off | Output Equalizer topic |
| feature/subharmonic-synth | Off | On | Octave synthesizer topic |
| feature/button-led-behavior | No DSP changes | No DSP changes | QML-only steady PLAY/DJ-FX/Sweep-FX Mod, experimental |
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
Settings → Mixer → Output Equalizer (or Subharmonic Synthesizer) launches the
enabled Mod's panel lazily. A panel failure is confined to the optional Loader.
No new Controls import is added to the startup UI. Panels load from the SDK's
ui/mods-overlay/EngineXMods directory; ui/active is optional and is not assumed
to exist. The panels are proper modal popups. Real Qt pointer tests verify
closing them above Settings, then using Settings and the main view again.
No speculative Touch FX shortcut is generated.

A third, independent QML-only prime4-steady-leds Mod controls PLAY, DJ-FX and Sweep-FX indicators without the DSP core or a firmware edit. Its builder verifies original module hashes and a uniquely JC11 assignment context. See docs/prime4-steady-button-leds.md for validation and restart limits.

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

The official 5.3.0 PRIME 4 fixture (SHA-256
8e49313be0ef338d5452631c5772ee5b1d72e076cae65bf69a6df8b5b210029f)
has been downloaded and its real QRC extracted (2,623 files). All four matching
UI packs build successfully. The LED archive passes 28 Qt binding cases,
cross-file JC11 scope checks and the standard Go loader's disabled install,
enable, persisted enable, disable, quarantine and uninstall checks.

Confirmed source checks:

- [Integrated C/Go/ARM/component suite](https://github.com/Sebluu/EngineX-OS/actions/runs/45316957624).
- [DSP core topic](https://github.com/Sebluu/EngineX-OS/actions/runs/45316960704),
  [EQ topic](https://github.com/Sebluu/EngineX-OS/actions/runs/45316954354),
  [SUB topic](https://github.com/Sebluu/EngineX-OS/actions/runs/45316963646).
- [Official QRC, 28 LED states, creation context, loader and matching packs](https://github.com/Sebluu/EngineX-OS/actions/runs/45311893936).

An additional integration-only workflow,
prime4-installed-mods-gate.yml, prepares a temporary candidate from the pinned
published JC11 5.3.0.5-r1 baseline. It compiles this branch's suite/hook/UI packs,
seeds all three Mods through the real loader, and adds assertions to a private
copy of the unchanged upstream release gate. Its sandbox revision is r2
without changing the project version or creating a Release. Images, vendor
files, test signing keys and archives are never uploaded.

[The complete isolated JC11 gate passed: 186 PASS, 0 FAIL](https://github.com/Sebluu/EngineX-OS/actions/runs/45318348421),
using source 113046766358a4715d3e4b6e7a3ac3078ea38ead. It verifies the
published baseline's update path, native Engine/Qt code under QEMU, all three
enabled Mods and exact generated overlays, non-flat/enabled DSP profiles,
populated synthetic music library, an abrupt namespace SIGKILL, second Engine
startup on the same data, dirty-cache purge and UI-ready without fallback.
Both DSP panels instantiate inside Engine before and after that restart.
Unsigned releases, bad signatures, edited manifests, tampered images and
signatures for another revision are refused. Valid signed staging is checked
without an eMMC device. The host clock remains unchanged.

This is an isolated userspace startup test on the actual rootfs, not a physical
power-on, kernel boot, real eMMC update or ARMv7 real-time certificate. The gate
adds assertions to a private copy; no existing upstream assertion is removed.
Its panel checks await actual render readiness on both boots.

Still mandatory before any deck installation:

- Native armhf callback/budget tests on the project's supported build host,
  including the PRIME 4's actual CPU margin.
- Native execution of the required release gates on the supported build host;
  the completed QEMU gate supplies functional evidence only.
- Actual controller/mixer assignments, Settings placement and required
  OpenGL/hardware screenshots.
- Interruption during Mod install/upgrade itself, forced startup hang with
  stock handback, and quarantine/uninstall followed by restart on the exact
  rootfs. Existing mocked guard and loader tests are green; the completed
  power-cut test is a healthy Engine run killed after UI-ready.
- Physical routing, split cue, Cue/Master, Zone, Computer Mode, external inputs,
  repeated changes and audio continuity.

The normal recovery guard and stock fallback remain responsible for recovery.
No real device is connected. No Factory Reset, --erase-data, firmware flashing
or physical device reboot is authorized or performed by these tests. Updater
verification, where exercised, is confined to the isolated rootfs gate.
Passing CI cannot guarantee that an installed experimental build cannot brick
or fail to boot. Do not distribute these source branches as installable
firmware. The DSP Mods require the matching native core; the independent LED
Mod still awaits physical controller validation before publication.
