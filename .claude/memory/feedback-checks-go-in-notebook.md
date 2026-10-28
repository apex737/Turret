---
name: feedback-checks-go-in-notebook
description: "Any check on real recordings (even a quick \"verify this claim\") goes into an ipynb first; never report numbers/conclusions from ad-hoc scripts in chat"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 470d7d64-0cf0-4834-97c1-a647e6464cf6
  modified: 2026-10-28T02:20:54.387Z
---

When I need to verify something with real device recordings — even a quick check to back a claim in chat — I build it as a notebook (`Tools/notebooks/`) that walks recording → one window's intermediate values → judgment with figures, and report only "결론 후보 + 노트북 경로 + 볼 절". I do not run ad-hoc scripts and then write tables, "확인됨", and decision options in chat.

**Why:** 2026-10-28 I verified two pre-recording concerns for the T measurement (mono playback, B0 floor) with throwaway scripts and put numbers, "verified" and options in chat. The user lost the thread entirely ("어딘가에서부터 놓친 것 같다") and said: "이런 실험을 혼자서 결론짓지 말고, 그냥 ipynb 시각화를 해달라고 한거야." The notebook also exposed that one of my chat claims (B0 floor caused by sharp 48.8/60 Hz lines) didn't match the figure.

**How to apply:** Applies GUIDE §10 to *verification* too, not just planned experiments. Before giving the user any real-data number, ask "is this from a notebook cell?" If not, make the notebook first. Also state in the notebook when a comparison isn't single-variable. Related: [[user-junior-wants-to-learn]], [[feedback-show-intermediate-calc]].
