# Experimental PRIME 4 output DSP

Native source only. JC11, ten-channel layout, Main/Booth/Phones/Zone. Both features disabled on the core branch. No adaptive loudness or PIN. All settings default off. No hardware or full firmware validation yet; do not flash for live use.

The audio callback consumes bounded atomic snapshots prepared on the existing worker. A 40 ms parallel-filter transition avoids parameter jumps; a stereo-linked existing limiter follows active processing. Octave synthesis uses band-limited zero-crossing division and envelope tracking, not proprietary dbx code. Run the standalone test documented in its source; add ARM real-time checks before release.

## Review / local validation

The integration branch is not a release candidate. A flat EQ must bypass the new DSP and must not cause the limiter to engage. SUB detection now gates by each selected source band and the poll worker skips unchanged config files. The live UI has not been built against the original QRC tree. The graph remains an approximate response, not a measured curve. Verify actual sample rate, output routing, and native UI placement; inspect ARM real-time budget and test with music before deployment. Existing release scripts require official images, extra ARM tooling, filesystem modules, and the project's build-host setup. Do not install prebuilt upstream release assets from this fork expecting these changes.

```sh
cc -std=c11 -O2 -Wall -Wextra -Werror tools/ui-mod/test_output_dsp.c -lm -o /tmp/test_od
/tmp/test_od
```
