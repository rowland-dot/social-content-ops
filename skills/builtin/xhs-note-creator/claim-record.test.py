"""Issue 102: every note keeps a claim record (meta.json `claims`) and the text check enforces it.

Run: python skills/builtin/xhs-note-creator/claim-record.test.py   (exit 0 = pass).
Drives scripts/validate_meta.py as a program on generated notes and asserts exit code and ERROR lines.
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

CAPTION_CLAIM = "每天一包，冲水喝就行"
CARD_NEW_WORDING = "看看我每天怎么喝"
PACK_PHRASE = "Oat Protein Tripeptide 10000mg"


def post(claims, caption_extra: str = "", card_content: str = "内容") -> dict:
    meta = {
        "title": "测试标题",
        "platform": "小红书",
        "created_at": "2026-10-28T10:00:00+08:00",
        "caption": CAPTION_CLAIM + "。" + "字" * 150 + caption_extra,
        "hashtags": [f"#话题{i}" for i in range(5)],
        "card_count": 3,
        rf.FIELD: rf.ANALYSIS_PATH,
        "creation_guide": {"path": "profiles/acme-test/creation-guide.md", "date": "2026-10-29"},
        "cards": [
            {"page": 1, "type": "cover", "title": "封面", "content": "封面"},
            {"page": 2, "type": "content", "title": "内容", "content": card_content},
            {"page": 3, "type": "ending", "title": "结尾", "content": "结尾"},
        ],
    }
    if claims is not None:
        meta["claims"] = claims
    return meta


def run(meta: dict, local_files=(), draft=None) -> tuple[int, str]:
    """Write the note into a fresh folder (plus any local evidence files and the long draft) and run the text check."""
    with tempfile.TemporaryDirectory() as d:
        folder = Path(d)
        if draft is not None:
            (folder / "完整标题.md").write_text(draft, encoding="utf-8")
        for rel in local_files:
            f = folder / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("x", encoding="utf-8")
        rf.write_analysis(folder)
        f = folder / "meta.json"
        f.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run([sys.executable, str(script), str(f)], capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout


failures = []


def check(name: str, ok: bool, out: str = "") -> None:
    if not ok:
        failures.append(f"{name}: {out.strip()!r}")


def accepted(name: str, meta: dict, local_files=(), draft=None) -> None:
    code, out = run(meta, local_files, draft)
    check(name, code == 0 and "ERROR" not in out, out)


def refused(name: str, meta: dict, must_say: str, local_files=(), draft=None) -> None:
    code, out = run(meta, local_files, draft)
    errors = [ln for ln in out.splitlines() if ln.startswith("ERROR")]
    check(name, code == 1 and any(must_say in ln for ln in errors), out)


# --- refused today's shape: no claim record at all
refused("a note with no claims field is refused", post(None), "claims")

# --- accepted
accepted("an empty claim list is accepted", post([]))

accepted(
    "an evidenced claim whose text is in the caption is accepted",
    post([{"text": CAPTION_CLAIM, "evidence_type": "brand_document", "source": "brands/x/listing.md"}]),
)

accepted(
    "a reworded claim whose new wording is in a card is accepted",
    post(
        [{"text": "三天见效", "fallback": "reworded", "now": CARD_NEW_WORDING}],
        card_content=CARD_NEW_WORDING,
    ),
)

accepted(
    "a removed claim whose text is absent from the post is accepted",
    post([{"text": "三天见效", "fallback": "removed"}]),
)

accepted(
    "a local evidence file that exists is accepted",
    post([{"text": CAPTION_CLAIM, "evidence_type": "fetched_reference", "source": "reference/ref_001.md"}]),
    local_files=["reference/ref_001.md"],
)

accepted(
    "a team quote and a web address are only required to be non-empty",
    post([
        {"text": CAPTION_CLAIM, "evidence_type": "team_statement", "source": "The owner: 每天一包"},
        {"text": "字字字", "evidence_type": "fetched_reference", "source": "https://example.com/a"},
    ]),
)

accepted(
    "an evidenced claim found only in the long draft is accepted",
    post([{"text": "这瓶用了三个月", "evidence_type": "user_material", "source": "https://example.com/own-video"}]),
    draft="## 小节\n这瓶用了三个月，没断过。\n",
)

# --- refused
refused(
    "a removed claim still in the long draft is refused",
    post([{"text": "三天见效", "fallback": "removed"}]),
    "三天见效",
    draft="## 小节\n三天见效，真的。\n",
)

refused(
    "an entry with neither evidence nor fallback is refused",
    post([{"text": CAPTION_CLAIM}]),
    "claims[0]",
)

refused(
    "an unknown evidence kind is refused",
    post([{"text": CAPTION_CLAIM, "evidence_type": "hearsay", "source": "someone"}]),
    "hearsay",
)

refused(
    "an unknown fallback is refused",
    post([{"text": "三天见效", "fallback": "softened", "now": "x"}]),
    "softened",
)

refused(
    "an evidenced claim not found in the post (a pack-label phrase) is refused",
    post([{"text": PACK_PHRASE, "evidence_type": "brand_document", "source": "brands/x/pack.jpg"}]),
    PACK_PHRASE,
)

refused(
    "a reworded entry whose new wording is not in the post is refused",
    post([{"text": "三天见效", "fallback": "reworded", "now": CARD_NEW_WORDING}]),
    CARD_NEW_WORDING,
)

refused(
    "a reworded entry with no new wording is refused",
    post([{"text": "三天见效", "fallback": "reworded"}]),
    "now",
)

refused(
    "a removed claim still in the caption is refused",
    post([{"text": CAPTION_CLAIM, "fallback": "removed"}]),
    CAPTION_CLAIM,
)

refused(
    "a missing local evidence file is refused",
    post([{"text": CAPTION_CLAIM, "evidence_type": "fetched_reference", "source": "reference/ref_001.md"}]),
    "reference/ref_001.md",
)

refused(
    "an evidence entry with an empty source is refused",
    post([{"text": CAPTION_CLAIM, "evidence_type": "brand_document", "source": ""}]),
    "source",
)

# --- the written guidance says the same thing as the check
skill = (here / "SKILL.md").read_text(encoding="utf-8")
schema = (here / "references" / "meta-schema.md").read_text(encoding="utf-8")
layout = (here / "references" / "output-spec.md").read_text(encoding="utf-8")
for name, text in (("SKILL.md", skill), ("meta-schema.md", schema), ("output-spec.md", layout)):
    check(f"{name} describes the claim record", "claims" in text, name)
    check(
        f"{name} says pack wording is never a claim or evidence",
        any("包装" in ln and "不算" in ln for ln in text.splitlines()),
        name,
    )
check("SKILL.md makes the record with the draft, before the user confirms it", "确认" in skill and "claims" in skill)
check("meta-schema lists both fallbacks", "removed" in schema and "reworded" in schema)
check("SKILL.md forbids fallbacks that invent personal experience", "亲测" in skill or "伪造" in skill)

if failures:
    print("FAILED:\n- " + "\n- ".join(failures))
    sys.exit(1)
print("ok")
