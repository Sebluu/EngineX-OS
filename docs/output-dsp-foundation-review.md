# Audio DSP foundation review and proposed Mod interface

Reviewed 2026-11-24. Original PRIME 4 / JC11, Engine OS 5.3.0 base.
Code baseline: `d0c03de6b254a81f36844541e1c646bfa4673005` on the fork's
`test/all-features`; LED packaging commit `62d972f` does not change audio.
This is a source review and a design proposal, not an installable core,
hardware acceptance, or a promise that dropouts can never occur.
The independently packaged LED Mod does not contain this DSP code.

## Decision

Keep a synchronous native PCM insert in Engine's existing render callback.
Reuse the upstream hook and its real-time guards. Do not divert the monitor
signal through a Go/Python daemon, browser, network stream or second sound
server. The first Mod interface should select and configure reviewed DSP nodes
compiled into the core. Arbitrary native plug-in loading is a later, separate
decision: one faulty in-process plug-in can stall or crash Engine.

The current code is a useful prototype, but not yet the general DSP Mod API
or the audio-quality evidence needed for a live controller release.
UI design remains deferred. Adaptive loudness and new speaker-protection
features remain outside this work.

## What the current code actually does

| Property | Evidence and limit |
| --- | --- |
| Audio format | `hook_master_output` receives Engine's planar `float` PCM and calls `od_process` in place. No codec, audio IPC, additional resampler or queued audio block is introduced by `output_dsp.h`. |
| Scope | Product check is JC11, and the insert requires exactly ten output channels. Four stereo pairs are processed; the fifth is left to Engine. Other layouts bypass this insert. |
| Output names | Upstream `tools/ui-mod/README.md` identifies the pairs as Main, Booth, Headphones and Zone, followed by a spare. This is supporting source evidence; physical split-CUE, Cue/Master, Zone, external-input and Computer Mode acceptance is still required. |
| Algorithms | Up to eight RBJ EQ biquads plus a two-biquad highpass per channel. SUB uses filtered mono detection, zero-crossing octave division, envelope tracking and a filtered additive signal. It is not a pitch-preserving full-band octave processor. |
| Controls | The ordinary worker polls settings every 80 ms and prepares coefficients. The audio path reads a bounded atomic mailbox once per pair/block, never spins on a writer, and processes the same block. |
| Changes | Two DSP states are mixed for 40 ms. This is a transition duration, not a 40 ms audio delay. Rapid changes wait for the current fade to finish and then take the latest publication. |
| Failure handling | Invalid configuration, unsupported sample rate and absent authorization produce bypass through the control worker. The backend's three-second authorization lease is tied to the Linux boot ID. |
| Existing output stage | Active output DSP also engages the existing master soft clipper/peak limiter for that pair. Its knee is about -1.5 dBFS. This is nonlinear processing even if the separate limiter preference is off. It has no lookahead buffer. |
| Mod integration | EQ and SUB are fixed IDs and compile-time feature flags with a custom settings API, not a registry of DSP nodes or a versioned general audio plug-in ABI. The QML Mods alone cannot add the native insert to published EngineX. |

Relevant implementation: `tools/ui-mod/output_dsp{,_control}.h`,
`engine_ui_hook.c`, `master_limiter.h`, and
`pkg/webui/output_dsp{,_runtime}.go`. The Go backend handles settings and
authorization; it never carries the PCM stream.

## Latency and signal quality

There are three different quantities to measure:

1. **Additional audio buffering:** the current insert adds zero queued frames.
   Each output sample is computed while Engine is rendering that same block.
   An impulse test checks immediate response after activation settles.
2. **Execution time:** the additional computation must fit inside the existing
   deadline, together with all vendor processing and other enabled effects.
   Faster computation does not require an extra audio block. Missing the
   deadline causes a dropout; a later bypass cannot repair the missed block.
3. **Filter response:** minimum-phase IIR filters have frequency-dependent
   phase/group delay. SUB also has detector settling and attack/release.
   These are not a constant delay applied to the entire dry signal. They still
   need measurement and listening tests.

The engineering goal is **zero extra buffered blocks**, with a small measured
CPU cost and adequate reserve on JC11. A 70 ms ceiling is not the target.
Total wired input/control-to-output latency must be compared with the same
device on its unmodified baseline. Browser UI latency and Bluetooth speaker
latency are different measurements and cannot establish this result.

The existing ARM64 CI run
[45469937451](https://github.com/Sebluu/EngineX-OS/actions/runs/45469937451)
reported four-pair EQ+SUB helper costs of 61,605 ns at 64 frames and
248,801 ns at 256 frames, at 96 kHz. The latter is about 0.249 ms against
a 2.667 ms block. These figures are **not PRIME 4 numbers**: the harness
takes each block's least time in three identical passes on a shared ARM64
runner, then reports the maximum of those least times. It excludes the vendor
DSP and is not a worst-case scheduler measurement. The mock-callback test
also passed, but cannot replace a native armhf/controller load test.

“No lossy compression” is achievable here: preserve Engine's native PCM
format and avoid encode/decode and unnecessary conversions. “Bit-perfect”
applies to bypass, not active EQ or synthesis, which intentionally change
samples and involve floating-point rounding. A float path by itself does not
prove a source-bit-depth or THD+N claim.

The existing SUB bound is a hard clamp of the added signal to +/-0.20, and
the following limiter can change peaks. Therefore the current prototype
cannot be described as completely transparent or free of nonlinear products.
Those choices need an explicit headroom and sound-quality decision, not just
a faster implementation. No new automatic gain or protection feature is
implicitly approved by this review.

## Findings to resolve before device audio testing

| Priority | Finding | Required resolution |
| --- | --- | --- |
| P0 | `core.ready` is written by the settings worker. It proves the core loaded and the product gate passed; it does not prove that the actual audio callback is running with the claimed format or physical routing. The initial rate also has a default before observation. | Publish capability only after observing the supported callback, product, layout, rate and processing owner; invalidate it on mismatch. Verify the JC11 rate rather than extrapolating from a different board. |
| P0 | Lease expiry is evaluated by that same worker. If the worker hangs after enabling DSP, the callback retains its last configuration indefinitely. The lease is not an independent audio-path watchdog. | Use the existing once-per-block monotonic timestamp for a bounded freshness check with atomically published deadlines. Share that clock read with existing users; no new file access or wait in the callback. Distinguish backend loss from worker loss in tests. |
| P0 | Audio state is global per pair. The mailbox has one publisher, and processing assumes one non-reentrant consumer. Those assumptions are not a general multi-instance ABI. | Bind a validated render owner/format epoch. Competing or stale owners must skip optional processing rather than race, reuse another stream's state or wait. Cover actual callback concurrency and lifecycle. |
| P1 | Every configuration change zeroes the new EQ and SUB history, even when one algorithm is unchanged. A 40 ms crossfade reduces discontinuities but does not prove unchanged-stage continuity or absence of modulation, phase cancellation or low-frequency transients. | Preserve compatible histories; define changes that need prepared state replacement. Compare unchanged-stage output against a continuous reference during automation and rapid toggles. Quantify residual transients. |
| P1 | The final limiter is selected by `od_process`'s active/fading return value. When bypass completes, its contribution disappears without its own handoff; state can also survive inactivity. | Specify and test the complete insert-to-limiter transition, including hot input and stale envelopes. Choose explicit gain/headroom behavior. Do not test only the isolated EQ header. |
| P1 | A render-rate mismatch currently returns dry immediately and cancels a pending fade while awaiting a new configuration. | Define a format-epoch reset and supported transition policy. Test rate/layout changes and invalid-rate recovery without applying coefficients for the wrong rate. |
| P1 | Current signal tests cover basic tones, finiteness, rates and isolation, but do not establish numerical/spectral quality at extreme valid settings. | Double-precision reference response, pole stability after float quantization, low-frequency/high-Q error, sweeps, impulses, THD+N/IMD, near-silence/denormals, overload and long-run stereo tests. Include the complete final output stage. |
| P1 | A passing build-host budget or QEMU run cannot establish JC11 scheduling margin, physical audio routing or end-to-end latency. | Native armhf measurements plus non-destructive real-device wired loopback and load tests; publish the conditions and results. |

These are source-review findings, not reported physical PRIME 4 failures.
The existing authorization, atomic configuration and startup fallback remain
useful. They do not guarantee that any arbitrary DSP code is crash-proof or
inaudible when it fails.

## Proposed first DSP Mod contract

This is a proposal; these manifest fields and functions are not implemented.

- A versioned **core capability** identifies product, core ABI, observed render
  rate, channel layout, supported nodes, parameter bounds and supported routes.
  A Mod requiring an unavailable capability stays disabled with a clear reason.
- A Mod selects a reviewed node such as `eq8` or `subharmonic-v1`, an allowed
  output route and validated parameters. Mods do not receive arbitrary PCM
  pointers, change ALSA settings, open capture devices or inject code.
- Use a bounded, prevalidated processing plan with a fixed node count and
  preallocated resident state. Choose maxima from measured JC11 budgets.
  Reject a plan that exceeds supported resources before activation.
- Prepare coefficients/state on the control worker. Publish complete immutable
  snapshots atomically. The render owner adopts at a block boundary without
  allocation, locks, I/O, logging, retry loops or waiting for a helper.
- Reuse the current Mod Hub validation, persistence, enable/disable and
  quarantine lifecycle. Connect authorization to each node; restore dry output
  smoothly when authorization or capability becomes invalid. Add restart and
  upgrade tests with profiles already installed.
- Keep route/channel order, dry-path timing and the native PCM format fixed.
  Do not add a sample-rate conversion or lookahead stage to this interface.
  Node-specific delay, phase and nonlinear behavior must be documented.
- Native third-party modules, if considered later, require their own trust,
  ABI, bounded-execution, memory-lifetime and offline validation policy.
  Checking an execution timer after a plug-in returns cannot stop one that
  never returns. Out-of-process isolation also needs buffers/deadlines and
  introduces a different latency/failure tradeoff.

## Existing upstream work and collaboration opportunities

Public GitHub issues, open PRs, audio/DSP branch searches and commit searches
were inspected on 2026-11-24. This is a scoped public search, not proof that
no private or unannounced work exists.

| Work | Observed status | How to build on it |
| --- | --- | --- |
| [#237: audit audio callbacks](https://github.com/Cd1s/EngineX-OS/issues/237) | Closed; maintainer states audit and timing coverage shipped in 5.3.0.5-r1. Branch `agent/5305-audio-audit` exists. | Reuse callback interposition guards, sanitizer coverage and budget harnesses rather than create an independent audio engine. |
| [#235: real-deck xrun measurements](https://github.com/Cd1s/EngineX-OS/issues/235) | Open, claimed by the maintainer, needs hardware, milestone 5.3.0.6. No comments at inspection. | Align the DSP acceptance report with its ALSA counters, CPU/load conditions and zero-xrun release criterion. |
| [#196: Mod/API discussion](https://github.com/Cd1s/EngineX-OS/issues/196) | Maintainer explicitly explains that Mods currently have no runtime audio DSP loader and that real-time effects are C11 core contributions. | Present the bounded-node capability proposal here or in a focused core PR when review findings are resolved. This review did not post a message. |
| [#221: Tap Delay Pads](https://github.com/Cd1s/EngineX-OS/issues/221) | Open. Maintainer review says the submitted helper stores presets and computes BPM divisions, without processing Engine's audio. | Potential consumer of a future control/node API; it is not an existing audio-insert foundation to reuse. |
| [#115: volunteer development/hardware testing](https://github.com/Cd1s/EngineX-OS/issues/115) | Closed discussion; JoshCollis offered PRIME 4 and SC6000 hardware. Current availability is unconfirmed. | A possible later hardware reviewer, not an active collaboration established by this work. |

No current public DSP plug-in-loader PR was found in these searches. The
soundest next upstream contribution is the narrowly scoped capability,
freshness and owner contract, using the established native hook. Contacting
maintainers or volunteers is a separate user-authorized action.

## Verification added by this review

`test_output_dsp_continuity.c` checks bit-exact inactive and flat-EQ bypass
(including negative zero and subnormals) at six rates; active EQ+SUB output
independent of audio block cuts, including activation; an immediate processed
impulse with no extra queued block; settled disable-to-bypass; and isolation
of the untouched output. The experimental workflow runs it normally, under
ASan/UBSan, and as ARMv7 code under QEMU alongside the existing suites.

These checks do not cover the P0/P1 findings above, certify an arbitrary Mod,
or establish actual controller latency/THD+N. Resolving those findings, then
measuring the complete pipeline, is the next implementation stage. The
experimental DSP core is not offered for installation on the user's device.
