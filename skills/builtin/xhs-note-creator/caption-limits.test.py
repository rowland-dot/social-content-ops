"""Issue 64: the post check treats ~300 as a target, warns above 800, refuses above 1000; 5-10 hashtags.

Run: python skills/builtin/xhs-note-creator/caption-limits.test.py   (exit 0 = pass).
Drives scripts/validate_meta.py as a program on generated meta.json files and asserts exit code and message.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

here = Path(__file__).resolve().parent
script = here / "scripts" / "validate_meta.py"


def post(caption_len: int = 300, tags: int = 5) -> dict:
    return {
        "title": "测试标题",
        "platform": "小红书",
        "created_at": "2026-10-23T10:00:00+08:00",
        "caption": "字" * caption_len,
        "hashtags": [f"#话题{i}" for i in range(tags)],
        "claims": [],
        "creation_guide": {"path": "profiles/acme-test/creation-guide.md", "date": "2026-10-29"},
        "card_count": 3,
        "cards": [
            {"page": 1, "type": "cover", "title": "封面", "content": "封面"},
            {"page": 2, "type": "content", "title": "内容", "content": "内容"},
            {"page": 3, "type": "ending", "title": "结尾", "content": "结尾"},
        ],
    }


def run(meta: dict) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "meta.json"
        f.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run([sys.executable, str(script), str(f)], capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout


failures = []


def check(name: str, ok: bool, out: str = "") -> None:
    if not ok:
        failures.append(f"{name}: {out.strip()!r}")


for n in (301, 585, 800):
    code, out = run(post(n))
    check(f"{n} chars passes with no warning", code == 0 and "WARN" not in out, out)

for n in (801, 1000):
    code, out = run(post(n))
    check(f"{n} chars passes with a warning naming length and 300-800", code == 0 and "WARN" in out and str(n) in out and "300-800" in out, out)

code, out = run(post(1001))
check("1001 chars fails", code == 1 and "ERROR" in out and "1001" in out, out)

code, out = run(post(99))
check("99 chars fails", code == 1 and "ERROR" in out, out)

code, out = run(post(300, tags=10))
check("10 hashtags pass", code == 0, out)

for n in (4, 11):
    code, out = run(post(300, tags=n))
    check(f"{n} hashtags fail", code == 1 and "ERROR" in out, out)

# the written guidance says the same thing as the check
skill = (here / "SKILL.md").read_text(encoding="utf-8")
schema = (here / "references" / "meta-schema.md").read_text(encoding="utf-8")
doc = script.read_text(encoding="utf-8")
check("SKILL.md no longer caps caption at 300", "100-300 字" not in skill)
check("SKILL.md says over 300 is allowed when content needs it", "300" in skill and "可以超" in skill)
check("SKILL.md hashtags 5-10", "5-10 个" in skill and "5-8" not in skill)
check("meta-schema caption entry updated", "100-300 字" not in schema and "300" in schema)
check("script docstring updated", "100..300" not in doc and "5..8" not in doc)

if failures:
    print("FAILED:\n- " + "\n- ".join(failures))
    sys.exit(1)
print("ok")
