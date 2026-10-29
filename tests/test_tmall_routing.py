import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "builtin" / "tmall-product-content" / "scripts"
SHARED = ROOT / "skills" / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(SHARED))

import json, re
import pytest
import web.app as web

def desc(name): return next(s for s in web.get_skills() if s["name"] == name)["description"]

def test_the_old_skill_points_tmall_requests_to_the_new_one():
    d = desc("ecom-details-image")
    assert "tmall-product-content" in d and "天猫" in d

def test_the_new_skill_claims_tmall_main_images_and_detail_pages_first():
    d = desc("tmall-product-content")
    assert d.index("天猫") < d.index("ecom-details-image")

# The two "before the Tmall pointer" backups. Each is the skill's whole folder exactly as git stored it at commit 391c93d^ (the
# parent of the Tmall merge). The lists below were computed once from that commit: SHA-256 of every file's stored bytes. The
# checks read only the backup folder, never today's live page and never git, so a later legitimate edit of a live page, or a CI
# checkout with no history, cannot change the result.
BACKUPS = ROOT / "archive" / "skill-backups"
BACKUP_FOLDER = "2026-10-29-before-tmall-pointer"
needs_backups = pytest.mark.skipif(not BACKUPS.is_dir(), reason="skill backups are kept only on the owner's PC")
ECOM_FINGERPRINTS = """
82ace11882beedf8ed593c2517919111d9c45f1fe56b81d1f30e12ffcef4e341  .env.example
f8bbe1ccaeca96d5e1f94ea8a630ca4b3c31db6176845b16bd35d50fa1e1be04  EASEL-META.md
08e05dfbd1813b66b212babdd8de07410d546e9372a90754c8a70682d8530ceb  SKILL.md
982480fbe03c33227bc1b24cf727555e325266d37342a34624f23d3f89e14289  codex-route.test.py
9a3edf2b32a0179e3c838939873b047ad51c07ab0d3392f6a3265d0e28debae4  references/campaign-style-lock.md
3fbf423977519abb59dedbd8a150e11a869fcd74bb7f101eb8decefa3f6e0429  references/image-gen-rules.md
2addc541d8d4256032d475e23852f1d0743d0eebdabc7ef7e7696c0bf0c33a5b  references/pdp-sequences.md
9c2312602a39929696c4c6e9785bf70e80d7c3f899d94fe85dab1248f909cd9e  references/templates.md
8cb2d3a042f23ea95b4eae0bbc9ab8631754c35d5c4e0c038c137c46f30f3b62  references/templates/01-hero-image.json
d2772aaa8729ff9a4d9e72f508e38c6c0b53b30ef279b5ba33aacd0046e9c33f  references/templates/02-lifestyle-scene.json
08ad2ea0a3d02047f960ba4c871621a230e51813f08172e0d7968910ffe5c01c  references/templates/03-flat-lay.json
0ae3b9f2a7b2daa38d29aae618c51538f2d8fe583c316eba458c0d64ca033653  references/templates/04-detail-macro.json
610d0dafd3e13e02b3099db0fe0f97965c5099ca646c6b656f583d66695b375c  references/templates/05-poster-banner.json
873b64c0c8cea8a6a939a1b0c54379788505b397a4193d6754fb123e72dca894  references/templates/06-social-media.json
61e378a82034a5d6559a72279af6336bfb9ef112bb831b0f051d55e0ded0f774  references/templates/07-ugc-style.json
810d376c3a7dbdf7fd919f16c104481bc34fd0d7a61cc1994da167cdeeef936e  references/templates/08-model-showcase.json
bd72c4b2c63bab5b093ee63c950c18c19839ad83e3f777acd73b4c2142ce8f4e  references/templates/09-before-after.json
662b2eec9d01839e72806ae11669fa070862b61b838cfdb436a5935469fda66a  references/templates/10-packaging.json
9f8f6d2e871fd1d6ff8b5a5bfdb6c5203d5c6cbb069c4e317dc98aae19c149bd  references/templates/11-infographic.json
536239f6a82b777030ed18a6459f03d75feb8ef559166ddf8f4acbb7436d8ff3  references/templates/12-creative-concept.json
7b71d88b389dbb769b837125d83a07078096e2d13574bd428d7adbe16a34a420  references/templates/13-size-spec.json
e737a2e74f8581b8577a7f7a4111a9d378ce7f2a7197ad51ca1f12fdabb05b2d  references/templates/14-multi-product.json
daf659fba18d0e2f6b7e1e4177e2d925097c6b20b7834567aba5b636f9044e6f  references/templates/15-livestream.json
dfc83281104dd60f02771665a96ce03e01ab239095b9437111b8b5ee6eae05f3  references/templates/16-try-on-virtual.json
8935d5c04a538873d54287dd92e21c628a525580386e3aad2cbff6a1385ee6dc  references/templates/17-exploded-view.json
e73d32e63537d97d51ab540088989a8ead3c82ed5748a5dae080e66bb0188ce6  references/templates/18-ghost-mannequin.json
14f9012adfa4b0a0c3441f0f2d6b227396e050af2ffa91c0eac27508bb9ff50b  references/templates/19-multi-angle-grid.json
00e50c51ae259c90ec5f872738fd413455e45a0eb68ae4e60532a7e60fc5c47e  references/templates/20-magazine-editorial.json
eef6ee7796fa5ecf8c520b2db253b31b4d3f51a91d557ab00ae4b28c788280a8  references/templates/21-seasonal-campaign.json
dc8e435dc4c21be89a0e4e8f26fce3853d07700a26521afadb5166de4f6da72e  references/templates/22-luxury-atmospherics.json
7929557fa53c02fb8b975a65da0cab4b76081d0ddf4c6fb7f9d7869be6ec51c9  references/templates/23-device-mockup.json
bb95fc8d391d850b719ba990d206ba4b34b7eace46e1e84d4c8bc311d118d6dd  references/templates/24-storefront.json
80dfda893bde1439d94a30776e712dc98e3821ba19f1e1271c057e6ba20be253  references/templates/25-sports-campaign.json
cc999e3a395f6c6ade596f7fc5147080a7d32f3679b1dcee83e4e19ee7eb45d1  scripts/generate_image.py
"""
AI_IMAGE_FINGERPRINTS = """
7cb5ce8d85afa2edbc0aba9f0e59bf5a63992bd690e362fdef51ee1b69ccab35  EASEL-META.md
d67aff1d929b3cf661604c4c5ef3a19c65c562ed0f635fa1ea4b04e14e20dd61  SKILL.md
cf296b21a759bed5a6df04b15d6db6c162846708a62889cef454383b48d74b1a  codex-route.test.py
"""

def _fingerprints(block):
    return {path: digest for digest, path in (line.split("  ", 1) for line in block.strip().splitlines())}

def _backup_problems(folder, fingerprints, pointer_texts):
    """What is wrong with a before-the-pointer backup folder: missing folder, missing or extra file, altered file, or a Tmall pointer in it."""
    import hashlib
    if not folder.is_dir():
        return [f"the backup folder {folder.name} does not exist"]
    found = {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    problems = [f"file missing from the backup: {p}" for p in sorted(set(fingerprints) - set(found))]
    problems += [f"extra file in the backup: {p}" for p in sorted(set(found) - set(fingerprints))]
    problems += [f"file altered: {p}" for p in sorted(set(found) & set(fingerprints)) if hashlib.sha256(found[p]).hexdigest() != fingerprints[p]]
    problems += [f"the Tmall pointer is in {p}" for p, data in sorted(found.items())
                 if any(t.encode("utf-8") in data for t in pointer_texts)]
    return problems

@needs_backups
def test_a_backup_of_the_whole_old_skill_folder_is_the_page_as_it_was_before_the_edit():
    folder = BACKUPS / "ecom-details-image" / BACKUP_FOLDER
    assert _backup_problems(folder, _fingerprints(ECOM_FINGERPRINTS), ["tmall-product-content"]) == []

OLD_LINE = "- **ecom-details-image**：电商详情页 / 商品主图专用出图（25 场景模板、PDP 序列）。要做电商商品图走它。"
NEW_LINE = ("- **ecom-details-image**：电商详情页 / 商品主图专用出图（25 场景模板、PDP 序列）。要做电商商品图走它；"
            "天猫 / Tmall 商品主图和商详页不走它，走 `tmall-product-content`。")
AI_IMAGE = ROOT / "skills" / "builtin" / "ai-image-gen"

def test_the_general_image_skill_no_longer_sends_tmall_product_pictures_to_the_older_skill():
    now = (AI_IMAGE / "SKILL.md").read_text(encoding="utf-8")
    assert NEW_LINE in now and OLD_LINE not in now

@needs_backups
def test_a_backup_of_the_whole_general_image_skill_folder_is_the_page_as_it_was_before_the_edit():
    folder = BACKUPS / "ai-image-gen" / BACKUP_FOLDER
    assert _backup_problems(folder, _fingerprints(AI_IMAGE_FINGERPRINTS), ["tmall-product-content", NEW_LINE]) == []
    assert OLD_LINE in (folder / "SKILL.md").read_text(encoding="utf-8")      # the page still has the line before it was changed

# The backup check must catch each way a backup can go wrong. Tried on a scratch copy of the real backup, never on the backup itself.
def _scratch(tmp_path, skill):
    import shutil
    copy = tmp_path / BACKUP_FOLDER
    shutil.copytree(BACKUPS / skill / BACKUP_FOLDER, copy)
    return copy

def _case_problems(tmp_path, skill, case):
    prints = _fingerprints(ECOM_FINGERPRINTS if skill == "ecom-details-image" else AI_IMAGE_FINGERPRINTS)
    pointers = ["tmall-product-content"]
    copy = _scratch(tmp_path, skill)
    if case == "folder removed":
        import shutil; shutil.rmtree(copy)
    elif case == "one file removed":
        (copy / "SKILL.md").unlink()
    elif case == "one extra file":
        (copy / "extra.txt").write_text("x", encoding="utf-8")
    elif case == "one file's bytes changed":
        with (copy / "SKILL.md").open("ab") as f: f.write(b" ")
    elif case == "Tmall pointer added":
        with (copy / "SKILL.md").open("ab") as f: f.write("\n走 `tmall-product-content`。\n".encode("utf-8"))
    return _backup_problems(copy, prints, pointers)

import pytest

@needs_backups
@pytest.mark.parametrize("skill", ["ecom-details-image", "ai-image-gen"])
@pytest.mark.parametrize("case", ["folder removed", "one file removed", "one extra file", "one file's bytes changed", "Tmall pointer added"])
def test_the_backup_check_fails_when_a_backup_is_missing_partial_altered_or_holds_the_pointer(tmp_path, skill, case):
    assert _case_problems(tmp_path, skill, case) != []

@needs_backups
@pytest.mark.parametrize("skill", ["ecom-details-image", "ai-image-gen"])
def test_the_backup_check_passes_on_an_untouched_copy_of_the_backup(tmp_path, skill):
    assert _case_problems(tmp_path, skill, "no change") == []

def _menu():
    text = (ROOT / "web" / "frontend" / "src" / "lib" / "capabilityMenu.ts").read_text(encoding="utf-8")
    data = json.loads(text.split("tabs: CapabilityTab[] } = ", 1)[1].strip().rstrip(";"))      # the literal is plain JSON
    return data, [i for t in data["tabs"] for g in t["groups"] for i in g["items"]]

def test_the_web_chat_menu_offers_the_tmall_item_first_and_the_older_item_points_to_it():
    data, items = _menu()
    skills = [i.get("skill") for i in items]
    assert skills.count("tmall-product-content") == 1 and skills.index("tmall-product-content") < skills.index("ecom-details-image")
    new, old = items[skills.index("tmall-product-content")], items[skills.index("ecom-details-image")]
    assert new["label"] == "天猫主图与商详页" and new["desc"] and new["status"] == "need"      # needs the Taobao login
    assert old["desc"].startswith("天猫请用「天猫主图与商详页」") and "电商" in old["desc"]
    assert len(set(skills)) == len(skills) and sum(data["meta"]["counts"].values()) == len(items)

# Moved here from tmall-routing.test.py files that sat inside the two upstream skill folders (new files there are outside the
# allowed area). The checks take the page text so a failing case can be tried on a scratch copy.
def _ai_image_boundary_problems(text):
    line = next((l for l in text.splitlines() if l.startswith("- **ecom-details-image**")), "")
    problems = []
    if "要做电商商品图走它" not in line:
        problems.append("the ecom-details-image boundary line is missing or no longer says what the older skill is for")
    if "天猫" not in line or "tmall-product-content" not in line:
        problems.append("the boundary line does not send Tmall product pictures to tmall-product-content")
    return problems

def _ecom_description_problems(text):
    head = text.split("\n---", 1)[0]
    problems = []
    if "tmall-product-content" not in head or "天猫" not in head:
        problems.append("the description does not send Tmall requests to tmall-product-content")
    desc = re.search(r"(?s)description:\s*>-?\n(.*?)\nlayer:", head)
    if not desc or len(" ".join(l.strip() for l in desc.group(1).splitlines())) > 300:
        problems.append("the description is missing or over the validator's 300 characters")
    return problems

def test_the_general_image_skill_boundary_line_sends_tmall_to_the_new_skill():
    assert _ai_image_boundary_problems((AI_IMAGE / "SKILL.md").read_text(encoding="utf-8")) == []

def test_the_older_skill_description_sends_tmall_to_the_new_skill_within_the_length_limit():
    page = ROOT / "skills" / "builtin" / "ecom-details-image" / "SKILL.md"
    assert _ecom_description_problems(page.read_text(encoding="utf-8")) == []
