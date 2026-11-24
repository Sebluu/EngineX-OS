# Experimental PRIME 4 output DSP

Native source only. JC11, ten-channel layout, Main/Booth/Phones/Zone. Both features disabled on the core branch. No adaptive loudness or PIN. All settings default off. No hardware or full firmware validation yet; do not flash for live use.

The audio callback consumes bounded atomic snapshots prepared on the existing worker. A 40 ms parallel-filter transition avoids parameter jumps; a stereo-linked existing limiter follows active processing. Octave synthesis uses band-limited zero-crossing division and envelope tracking, not proprietary dbx code. Run the standalone test documented in its source; add ARM real-time checks before release.
