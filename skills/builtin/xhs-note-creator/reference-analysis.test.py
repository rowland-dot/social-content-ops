"""Issue 68: the note writer saves the reference posts it is given, decomposes them into
reference/reference-analysis.json before any draft, and the post check refuses a post without it.

Run: python skills/builtin/xhs-note-creator/reference-analysis.test.py   (exit 0 = pass).
Drives scripts/validate_meta.py on generated note folders (stand-in saved records in read_note.py's
folder shape: caption.md + record.json) and reads SKILL.md and the schema docs. No live request.
"""
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

here = Path(__file__).resolve().parent
sys.path.insert(0, str(here))
import reference_fixture as rf

script = here / "scripts" / "validate_meta.py"


def post(with_field=True) -> dict:
    meta = {
        "title": "测试标题", "platform": "小红书", "created_at": "2026-10-29T10:00:00+08:00",
        "caption": "字" * 150, "hashtags": [f"#话题{i}" for i in range(5)], "claims": [],
        "creation_guide": {"path": "profiles/acme-test/creation-guide.md", "date": "2026-10-29"},
        "card_count": 3,
        "cards": [{"page": 1, "type": "cover", "title": "封面", "content": "封面"},
                  {"page": 2, "type": "content", "title": "内容", "content": "内容"},
                  {"page": 3, "type": "ending", "title": "结尾", "content": "结尾"}],
    }
    if with_field:
        meta[rf.FIELD] = rf.ANALYSIS_PATH
    return meta


def run(meta, analysis="default", raw=None, remove=(), caption_extra=""):
    with tempfile.TemporaryDirectory() as d:
        folder = Path(d)
        rf.write_analysis(folder, None if analysis == "default" else analysis)
        if raw is not None:
            (folder / rf.ANALYSIS_PATH).write_text(raw, encoding="utf-8")
        for rel in remove:
            target = folder / rel
            if target.is_dir():
                for c in target.iterdir():
                    c.unlink()
                target.rmdir()
            else:
                target.unlink()
        meta = copy.deepcopy(meta)
        meta["caption"] += caption_extra
        f = folder / "meta.json"
        f.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run([sys.executable, str(script), str(f)], capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout


failures = []


def check(name, ok, out=""):
    if not ok:
        failures.append(f"{name}: {out.strip()!r}")


def refused(name, *args, **kw):
    code, out = run(*args, **kw)
    ref_lines = [l for l in out.splitlines() if l.startswith("ERROR:") and "reference_analysis" in l]
    check(name, code == 1 and ref_lines, out)


def mutated(fn):
    a = rf.complete_analysis()
    fn(a)
    return a


code, out = run(post())
check("a post with a complete analysis record passes", code == 0 and "ERROR" not in out, out)
code, out = run(post(), mutated(lambda a: a["posts"][0].update(kind="topic_study")))
check("kind topic_study passes", code == 0, out)
code, out = run(post(), mutated(lambda a: a.update(voice={"none": "这个账号还没有团队改写，没有文风参考"})))
check("voice none with a statement passes", code == 0, out)

refused("missing reference_analysis field", post(with_field=False))
refused("analysis file missing", post(), remove=[rf.ANALYSIS_PATH])
refused("analysis file does not parse", post(), raw="{not json")
refused("no post listed", post(), mutated(lambda a: a.update(posts=[])))
for key in ("kind", "source", "record"):
    refused(f"a post without {key}", post(), mutated(lambda a, k=key: a["posts"][0].pop(k)))
refused("unknown kind", post(), mutated(lambda a: a["posts"][0].update(kind="invented")))
for key in ("hook", "order", "product_entry", "cta", "length"):
    refused(f"structure without {key}", post(), mutated(lambda a, k=key: a["posts"][0]["structure"].pop(k)))
for key in ("speaker", "situation", "audience"):
    refused(f"context without {key}", post(), mutated(lambda a, k=key: a["posts"][0]["context"].pop(k)))
refused("record path does not exist", post(), remove=["reference/saved-1"])
with tempfile.TemporaryDirectory() as outside:  # a record kept where read_note.py saves it, outside the note folder
    saved = Path(outside) / "xhs-reference-notes" / "abc"
    saved.mkdir(parents=True)
    (saved / "caption.md").write_text(rf.SAVED_TEXT, encoding="utf-8")
    code, out = run(post(), mutated(lambda a: a["posts"][0].update(record=str(saved))))
    check("a record saved outside the note folder passes", code == 0, out)
    refused("20 characters copied from a record saved outside the note folder",
            post(), mutated(lambda a: a["posts"][0].update(record=str(saved))), caption_extra=rf.SAVED_TEXT[:20])
refused("voice neither from nor none", post(), mutated(lambda a: a.update(voice={})))
refused("voice from is empty", post(), mutated(lambda a: a.update(voice={"from": []})))
refused("voice none is blank", post(), mutated(lambda a: a.update(voice={"none": "  "})))
refused("draft_plan empty", post(), mutated(lambda a: a.update(draft_plan="")))
refused("20 characters copied from a saved caption.md", post(), caption_extra=rf.SAVED_TEXT[:20])
refused("20 characters copied from a saved text file", post(), caption_extra=rf.REWRITE_TEXT[5:25])
code, out = run(post(), caption_extra=rf.SAVED_TEXT[:19])
check("19 shared characters are allowed", code == 0, out)

skill = (here / "SKILL.md").read_text(encoding="utf-8")
guide = skill.find("creation_guide.py check --brand")
step3 = skill.find("### Step 3")
start = skill.find("### 参考帖记录与拆解")
check("new step sits after the creation guide and before ### Step 3", 0 <= guide < start < step3, f"{guide} {start} {step3}")
section = skill[start:step3]
for need in ("read_note.py", "reference/reference-analysis.json", "draft_plan", "reference_analysis",
             "team_supplied", "team_rewrite", "topic_study", "创作指南", "停下", "不编结构", "没有"):
    check(f"step text says: {need}", need in section)
check("instructions never tell the writer to use viral-template",
      all("不" in l or "never" in l.lower() or "禁" in l for l in skill.splitlines() if "viral-template" in l))
for doc in ("meta-schema.md", "output-spec.md"):
    t = (here / "references" / doc).read_text(encoding="utf-8")
    check(f"{doc} names reference_analysis", "reference_analysis" in t or "reference-analysis.json" in t)

for line in failures:
    print("FAIL", line)
print("PASS" if not failures else f"{len(failures)} failed")
sys.exit(1 if failures else 0)
