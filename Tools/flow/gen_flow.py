#!/usr/bin/env python3
"""Steps/*.md + problem.md → flow.html

원본은 md다. flow.html은 직접 고치지 않고 이 스크립트로만 만든다.
규칙을 어기면 HTML을 만들지 않고 실패한다:
  - 모든 Step은 최종 목표(G*)를 하나 이상 goal_ref로 가리켜야 한다
  - goal_ref는 problem.md에 있는 ID여야 한다
  - exit(정량 통과 기준)가 비어 있으면 안 된다
  - depends_on / on_fail은 존재하는 Step이어야 하고, 순환이 없어야 한다

사용: python Tools/flow/gen_flow.py [프로젝트 루트]   (기본: 현재 폴더)
필요: pip install pyyaml markdown
"""
import json
import re
import sys
from pathlib import Path

# Windows 콘솔(cp949)에서도 한글·기호 출력이 깨지거나 멈추지 않게 한다
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    import markdown
    import yaml
except ImportError as e:
    sys.exit(f"[오류] {e.name}가 없다. Tools/.venv의 파이썬으로 실행하거나 pip install pyyaml markdown")

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
TEMPLATE = Path(__file__).with_name("flow_template.html")
FM = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.S)
REQUIRED = ["id", "title", "depends_on", "goal_ref", "exit", "status"]


def split(path):
    m = FM.match(path.read_text(encoding="utf-8"))
    if not m:
        sys.exit(f"[오류] {path}: frontmatter(--- ... ---)가 없다")
    return yaml.safe_load(m.group(1)) or {}, m.group(2).strip()


def render(text):
    return markdown.markdown(text, extensions=["tables", "sane_lists"])


def main():
    errors, warns = [], []

    pmeta, pbody = split(ROOT / "problem.md")
    refs = {}
    for group in ("goals", "priorities", "invariants"):
        for k, v in (pmeta.get(group) or {}).items():
            refs[k] = {"group": group, "text": v}

    steps = {}
    for f in sorted((ROOT / "Steps").glob("*.md")):
        meta, body = split(f)
        miss = [k for k in REQUIRED if k not in meta]
        if miss:
            errors.append(f"{f.name}: 필수 항목 없음 {miss}")
            continue
        if meta["id"] != f.stem:
            errors.append(f"{f.name}: id({meta['id']})가 파일 이름과 다르다")
        meta["depends_on"] = meta["depends_on"] or []
        meta["goal_ref"] = meta["goal_ref"] or []
        meta["on_fail"] = meta.get("on_fail")
        meta["body"] = render(body)
        meta["file"] = f"Steps/{f.name}"
        steps[meta["id"]] = meta

    for s in steps.values():
        sid = s["id"]
        if not str(s["exit"]).strip():
            errors.append(f"{sid}: exit(정량 통과 기준)가 비어 있다")
        if not any(r.startswith("G") for r in s["goal_ref"]):
            errors.append(f"{sid}: 최종 목표(G*)와 연결되지 않았다 — goal_ref={s['goal_ref']}")
        for r in s["goal_ref"]:
            if r not in refs:
                errors.append(f"{sid}: goal_ref '{r}'가 problem.md에 없다")
        for d in s["depends_on"]:
            if d not in steps:
                errors.append(f"{sid}: depends_on '{d}'가 없다")
        if s["on_fail"] and s["on_fail"] not in steps:
            errors.append(f"{sid}: on_fail '{s['on_fail']}'가 없다")

    # 깊이 = 가장 긴 선행 경로 길이. 순환이면 오류.
    level, visiting = {}, set()

    def depth(sid):
        if sid in level:
            return level[sid]
        if sid in visiting:
            errors.append(f"{sid}: depends_on 순환")
            return 0
        visiting.add(sid)
        deps = [d for d in steps[sid]["depends_on"] if d in steps]
        level[sid] = 1 + max((depth(d) for d in deps), default=-1)
        visiting.discard(sid)
        return level[sid]

    for sid in steps:
        depth(sid)
        steps[sid]["level"] = level[sid]

    # 최종 목표(G)와 불변조건(I)은 어떤 Step에서든 검증되어야 한다
    for k in (k for k in refs if k[0] in "GI"):
        if not any(k in s["goal_ref"] for s in steps.values()):
            warns.append(f"{k}: 이것을 검증하는 Step이 없다 — {refs[k]['text']}")

    if errors:
        print("\n".join("[오류] " + e for e in errors))
        sys.exit(1)
    for w in warns:
        print("[경고] " + w)

    data = {
        "project": pmeta.get("project", ROOT.name),
        "refs": refs,
        "problem_body": render(pbody),
        "steps": sorted(steps.values(), key=lambda s: (s["level"], s["id"])),
    }
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("__TITLE__", data["project"]).replace("__DATA__", payload)
    out = ROOT / "flow.html"
    out.write_text(html, encoding="utf-8")
    print(f"[완료] {out} — Step {len(steps)}개")


if __name__ == "__main__":
    main()
