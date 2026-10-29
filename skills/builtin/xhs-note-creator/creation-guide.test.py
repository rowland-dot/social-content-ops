"""Issue 125: the note writer reads the account's creation guide first and meta.json records which one it read.

Run: python skills/builtin/xhs-note-creator/creation-guide.test.py   (exit 0 = pass).
Drives scripts/validate_meta.py on generated notes for a made-up account, and reads SKILL.md and the meta schema.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

here = Path(__file__).resolve().parent
sys.path.insert(0, str(here))
import reference_fixture as rf
script = here / "scripts" / "validate_meta.py"
GUIDE = {"path": "profiles/acme-test/creation-guide.md", "date": "2026-10-29"}


def post(guide) -> dict:
    meta = {
        "title": "测试标题", "platform": "小红书", "created_at": "2026-10-29T10:00:00+08:00",
        "caption": "字" * 150, "hashtags": [f"#话题{i}" for i in range(5)], "claims": [], rf.FIELD: rf.ANALYSIS_PATH,
        "card_count": 3,
        "cards": [{"page": 1, "type": "cover", "title": "封面", "content": "封面"},
                  {"page": 2, "type": "content", "title": "内容", "content": "内容"},
                  {"page": 3, "type": "ending", "title": "结尾", "content": "结尾"}],
    }
    if guide is not None:
        meta["creation_guide"] = guide
    return meta


def run(meta):
    with tempfile.TemporaryDirectory() as d:
        rf.write_analysis(Path(d))
        f = Path(d) / "meta.json"
        f.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run([sys.executable, str(script), str(f)], capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout


failures = []


def check(name, ok, out=""):
    if not ok:
        failures.append(f"{name}: {out.strip()!r}")


code, out = run(post(None))
check("a note with no creation_guide is refused", code == 1 and "creation_guide" in out, out)
code, out = run(post({"path": "", "date": "2026-10-29"}))
check("an empty guide path is refused", code == 1 and "creation_guide" in out, out)
code, out = run(post({"path": GUIDE["path"], "date": "yesterday"}))
check("a guide date that is not YYYY-MM-DD is refused", code == 1 and "creation_guide" in out, out)
code, out = run(post(GUIDE))
check("a note naming the guide it read is accepted", code == 0 and "ERROR" not in out, out)

skill = (here / "SKILL.md").read_text(encoding="utf-8")
for need in ("creation_guide.py check --brand", "整份读完", "没有创作指南", "profiles/_template/creation-guide.md", "creation_guide"):
    check(f"SKILL.md says: {need}", need in skill)
first = skill.find("creation_guide.py check --brand")
check("the guide is read before Step 0", 0 <= first < skill.find("### Step 0"), str(first))
schema = (here / "references" / "meta-schema.md").read_text(encoding="utf-8")
for need in ("creation_guide", "path", "date"):
    check(f"meta-schema.md says: {need}", need in schema)

for line in failures:
    print("FAIL", line)
print("PASS" if not failures else f"{len(failures)} failed")
sys.exit(1 if failures else 0)
