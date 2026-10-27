---
name: user-background-level
description: "User's measured background level for the Turret project (quiz graded 2026-10-21) and how to explain things to them"
metadata:
  node_type: memory
  type: user
  originSessionId: 8104f310-a827-406a-8497-56de247878ed
  modified: 2026-10-21T07:38:43.633Z
---

Quiz graded 2026-10-21 (the quiz file was deleted 2026-10-22; the record survives in git history of branch restructure-docs, commit fdf6311): only 3 of 30 concepts passed — DMA ping-pong timing, UART throughput budget, shortcut learning. Most gaps are undergraduate DSP basics (aliasing fold location, Fourier shift property, zero-padding vs resolution, FIR linear phase/decimation) and basic ML evaluation (leakage, thresholds, AUC), not graduate topics. Confident misconceptions seen: Nyquist violation "disappears" rather than folds; HSI clock thought to be software; data leakage confused with lack of diversity; cross-spectrum written as the X1/X2 relation; earlier also "RMS×4 = 8× energy" and "preproc_run compensates the 1/4 sample count".

**How to apply:** treat this as background only; current gaps are whatever is listed in `learning/concepts.html`. Explain from first principles with the project's own numbers when asked, but do not write teaching materials — see [[knowledge-checkpoint-protocol]].
