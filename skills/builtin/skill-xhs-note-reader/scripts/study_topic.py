#!/usr/bin/env python3
"""Topic study (issue 84): save the whole image sets of the best posts on one topic, with an index and a check.

    python skills/builtin/skill-xhs-note-reader/scripts/study_topic.py --brand <brand> --keyword "<topic>" [-n 5]

One search through the guarded reader (`redbook search`), the top N image posts by likes plus favourites (the ranking
of skill-post-scorer, not a copy of it), each read once and every image saved by the whole-note reader (`read_note.py`,
whose downloads go through the guard's `fetch-file` step). Each set is filed as one folder under the brand's
`对标笔记库/image-sets` folder, with a contact sheet and a record. The study folder under `对标笔记库/research/`
holds `index.md` (written here), `summary.md` (written by the Easel agent from the saved images; the study is not
complete without it) and `raw/`, the platform's own answers untouched, the only place an access code may sit.

Running the same command again is the way to finish or check a study: it spends no second search, reads no post whose
set is already saved, and re-checks every saved image. Exit codes: 0 complete, 1 failed (a missing or broken image,
a post that could not be read), 2 bad arguments, 3 stopped by a guard refusal, 4 saved but the summary is not done.
"""
from __future__ import annotations

import argparse
import dataclasses
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import read_note as rn  # noqa: E402  (the whole-note reader: its read, its guarded download, its per-note folder)

from PIL import Image  # noqa: E402

SCORER = SCRIPTS.parents[1] / "skill-post-scorer" / "scripts" / "score.py"
SHEET_WIDTH = 360          # each image's width on the contact sheet
SHEET_GAP = 8
SUMMARY_NAME = "summary.md"
STOP_WORDS = re.compile(r"tripped|safety signal|daily cap|using the account|no login", re.I)
NOTE_ID = re.compile(r"/(?:explore|discovery/item)/([A-Za-z0-9_-]+)")
UNSAFE_NAME = re.compile(r'[\\/:*?"<>|\r\n]')


def _load_scorer():
    """The likes-plus-favourites formula lives in skill-post-scorer (issue 83); it is loaded, never copied."""
    spec = importlib.util.spec_from_file_location("post_scorer_score", SCORER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


score = _load_scorer()


class StudyError(Exception):
    """The study cannot go on and has nothing to report as sets (no search answer, no posts in it)."""


@dataclass(frozen=True)
class StudyDeps:
    search: Callable[[str], dict]    # topic keyword -> the search answer (redbook search --json)
    note: rn.Deps                    # the whole-note reader's own stand-ins


# --- the ranking ---------------------------------------------------------------------------------------------

def parse_count(value) -> int:
    """A count as the platform prints it: '987', '1,024', '1.2万' (12000). Anything else is 0."""
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(万|w|W)?\+?", str(value or "").strip().replace(",", ""))
    if not match:
        return 0
    return int(round(float(match.group(1)) * (10000 if match.group(2) else 1)))


def rank_posts(answer, n: int) -> list:
    """The top n posts of a search answer by likes plus favourites, highest first, ties in the platform's own order."""
    items = answer if isinstance(answer, list) else (answer.get("items") or answer.get("notes") or [])
    posts = []
    for item in items:
        card = item.get("note_card") if isinstance(item, dict) else None
        if not isinstance(card, dict):    # the search also returns query suggestions
            continue
        info = card.get("interact_info") or {}
        likes, favourites = parse_count(info.get("liked_count")), parse_count(info.get("collected_count"))
        link = item.get("webUrl") or ""
        found = NOTE_ID.search(link)
        posts.append({
            "link": link, "note_id": found.group(1) if found else "", "title": card.get("display_title") or "",
            "author": (card.get("user") or {}).get("nickname") or "", "type": card.get("type") or "normal",
            "likes": likes, "favourites": favourites,
            "score": score.engagement({"likes": likes, "favourites": favourites}),
        })
    posts.sort(key=lambda p: p["score"], reverse=True)
    return posts[:n]


# --- stops ------------------------------------------------------------------------------------------------------

def is_stop(error: Exception) -> bool:
    """The guard has refused (cap, tripped, no login, account busy) or the platform raised a safety signal."""
    return getattr(error, "code", None) in rn.GUARD_REASONS or bool(STOP_WORDS.search(str(error)))


# --- the files ------------------------------------------------------------------------------------------------------

def _clean(text: str, limit: int = 30) -> str:
    return UNSAFE_NAME.sub("", text or "").strip()[:limit]


def _cell(text) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _file_problem(path: Path) -> str | None:
    if not path.is_file():
        return "missing"
    if path.stat().st_size == 0:
        return "empty"
    try:
        with Image.open(path) as image:
            image.load()
    except Exception:  # noqa: BLE001  (any reason the picture cannot be opened is the same finding)
        return "does not open as an image"
    return None


def _contact_sheet(images: list, dest: Path) -> None:
    thumbs = []
    for path in images:
        try:
            with Image.open(path) as image:
                rgb = image.convert("RGB")
                thumbs.append(rgb.resize((SHEET_WIDTH, max(1, round(rgb.height * SHEET_WIDTH / rgb.width)))))
        except Exception:  # noqa: BLE001  (a broken image is reported by the check, not hidden by the sheet)
            continue
    if not thumbs:
        return
    sheet = Image.new("RGB", (SHEET_WIDTH * len(thumbs) + SHEET_GAP * (len(thumbs) - 1), max(t.height for t in thumbs)), "white")
    for index, thumb in enumerate(thumbs):
        sheet.paste(thumb, (index * (SHEET_WIDTH + SHEET_GAP), 0))
    sheet.save(dest, quality=85)


def _load_state(study_dir: Path) -> dict:
    path = study_dir / "state.json"
    if path.is_file():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            return {"reads_used": int(state.get("reads_used", 0)), "sets": dict(state.get("sets", {}))}
        except (ValueError, TypeError):
            pass
    return {"reads_used": 0, "sets": {}}


def _save_state(study_dir: Path, state: dict) -> None:
    (study_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _file_set(post: dict, pick: int, record: dict, raw_note: Path, keyword: str, date: str, image_sets: Path) -> dict:
    """Copy one read note's images into its set folder (names kept, so a gap shows), then the sheet and the record."""
    read = json.loads((raw_note / "read.json").read_text(encoding="utf-8"))
    note = rn._note(read)
    listed = len(note.get("image_list") or [])
    title = note.get("title") or post["title"]
    folder_name = f"{date}-{_clean(keyword)}-{pick}-{_clean(title) or 'untitled'}"
    folder = image_sets / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    saved = []
    for relative in (record["parts"].get("images") or {}).get("files") or []:
        source = raw_note / relative
        if source.is_file():
            shutil.copy2(source, folder / source.name)
            saved.append(source.name)
    _contact_sheet([folder / name for name in saved], folder / "contact-sheet.jpg")
    total = post["likes"] + post["favourites"]
    (folder / "record.md").write_text("\n".join([
        f"# {title}", "",
        "| 项目 | 内容 |", "|---|---|",
        f"| 标题 | {_cell(title)} |", f"| 作者 | {_cell((note.get('user') or {}).get('nickname') or post['author'])} |",
        f"| 赞 | {post['likes']} |", f"| 藏 | {post['favourites']} |", f"| 合计 | {total} |", f"| 图数 | {listed} |",
        f"| 笔记地址 | https://www.xiaohongshu.com/explore/{post['note_id']} |",
        f"| 搜索词 | {_cell(keyword)} |", f"| 日期 | {date} |", "",
    ]), encoding="utf-8")
    return {"pick": pick, "note_id": post["note_id"], "title": title, "author": post["author"], "likes": post["likes"],
            "favourites": post["favourites"], "sum": total, "listed": listed, "saved": len(saved),
            "folder": folder_name, "complete": listed > 0 and len(saved) == listed}


def check_sets(sets: list, image_sets: Path) -> list:
    """Every image each read listed must be in its set folder, non-empty and openable; the sheet too."""
    problems = []
    for entry in sets:
        folder = image_sets / entry["folder"]
        names = [f"{k:02d}.jpg" for k in range(1, entry["listed"] + 1)] + ["contact-sheet.jpg"]
        for name in names:
            problem = _file_problem(folder / name)
            if problem:
                problems.append({"set": entry["folder"], "image": name, "problem": problem})
    return problems


def check_summary(study_dir: Path, sets: list) -> dict:
    """The written summary must exist and name every saved set (by the folder name the index gives it)."""
    path = study_dir / SUMMARY_NAME
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if not text.strip():
        return {"missing": True, "not_named": []}
    return {"missing": False, "not_named": [s["folder"] for s in sets if s["folder"] not in text]}


def _write_index(study_dir: Path, keyword: str, date: str, result: dict, rows: list) -> None:
    lines = [
        f"# {keyword}：高赞图文研究", "",
        f"- 话题：{keyword}", f"- 搜索词：{keyword}", f"- 日期：{date}",
        f"- 已用读取次数：{result['reads_used']}（含搜索 1 次；下载图片不计）",
        f"- 状态：{result['status']}", "",
        "| # | 套（文件夹） | 标题 | 作者 | 赞 | 藏 | 合计 | 图数 | 情况 |", "|---|---|---|---|---|---|---|---|---|",
    ]
    lines += [f"| {r['pick']} | {_cell(r['folder'])} | {_cell(r['title'])} | {_cell(r['author'])} | {r['likes']} | {r['favourites']} "
              f"| {r['likes'] + r['favourites']} | {r['images']} | {_cell(r['note'])} |" for r in rows]
    lines.append("")
    stopped = result["stopped"]
    if stopped:
        where = "搜索时" if stopped["pick"] == 0 else f"第 {stopped['pick']} 篇「{stopped['title']}」"
        lines += [f"停下来了：{where}。原因：{stopped['reason']}", "已存的套照旧留着，没有重试。守卫放行后再跑一遍同样的命令就接着做。", ""]
    if result["problems"]:
        lines += ["检查没通过："] + [f"- {p['set']} / {p['image']}：{p['problem']}" for p in result["problems"]] + [""]
    summary = result["summary"]
    if summary["missing"]:
        lines.append(f"小结：还没写。写到 {SUMMARY_NAME}（每一套的图是怎么做的，再写几套的共同点），并点名上面每一套的文件夹。")
    elif summary["not_named"]:
        lines.append("小结：没点名这几套：" + "；".join(summary["not_named"]))
    else:
        lines.append("小结：已写，点名了每一套。")
    (study_dir / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# --- the study --------------------------------------------------------------------------------------------------------

def run_study(keyword: str, n: int, deps: StudyDeps, *, image_sets, study_dir, date: str) -> dict:
    image_sets, study_dir = Path(image_sets), Path(study_dir)
    raw = study_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    image_sets.mkdir(parents=True, exist_ok=True)
    state = _load_state(study_dir)
    stop: dict = {"error": None}   # the first guard refusal seen by any wrapped call

    def remember(error: Exception) -> None:
        if stop["error"] is None and is_stop(error):
            stop["error"] = error

    def read(link: str) -> dict:
        try:
            answer = deps.note.read(link)
        except Exception as error:
            remember(error)
            if not is_stop(error):
                state["reads_used"] += 1
            raise
        state["reads_used"] += 1
        return answer

    def download(url: str, dest: Path) -> None:
        if stop["error"] is not None:     # stopped at once: nothing more is fetched
            raise rn.DownloadFailed(f"not fetched, the study has stopped: {stop['error']}")
        try:
            deps.note.download(url, dest)
        except Exception as error:
            remember(error)
            raise

    def no_text_in_images(path: Path) -> str:
        raise rn.PartUnavailable("a topic study saves the images only")

    note_deps = dataclasses.replace(deps.note, read=read, download=download, ocr=no_text_in_images)

    stopped = None
    search_file = raw / "search.json"
    if search_file.is_file():          # a rerun never spends a second search
        answer = json.loads(search_file.read_text(encoding="utf-8"))
    else:
        try:
            answer = deps.search(keyword)
        except Exception as error:
            if not is_stop(error):
                raise StudyError(f"the search failed: {error}") from error
            answer, stopped = None, {"pick": 0, "title": "", "reason": str(error)[:300]}
        else:
            state["reads_used"] += 1
            search_file.write_text(json.dumps(answer, ensure_ascii=False, indent=2), encoding="utf-8")
    picks = rank_posts(answer, n) if answer is not None else []
    if answer is not None and not picks:
        raise StudyError("the search returned no posts")

    sets: list = []
    skipped: list = []
    failed_reads: list = []
    rows: list = []

    def row(pick, post, folder, images, note):
        rows.append({"pick": pick, "folder": folder, "title": post["title"], "author": post["author"], "likes": post["likes"],
                     "favourites": post["favourites"], "images": images, "note": note})

    for pick, post in enumerate(picks, start=1):
        if stopped is not None:
            row(pick, post, "", "", "没读（已停止）")
            continue
        if post["type"] == "video":
            skipped.append({"pick": pick, "title": post["title"], "reason": "video"})
            row(pick, post, "", "", "跳过：视频帖，这里只研究图文")
            continue
        saved = state["sets"].get(post["note_id"])
        if saved and saved["complete"]:    # a saved post is never read again
            sets.append(saved)
            row(pick, post, saved["folder"], saved["listed"], "已存")
            continue
        try:
            if not post["note_id"] or not rn.NOTE_ADDRESS.match(post["link"]):
                raise rn.ReadFailed("the search result has no note address")
            record = rn.read_note(post["link"], raw, note_deps, want_diandian=False)
        except rn.ReadFailed as error:
            if stop["error"] is not None:
                stopped = {"pick": pick, "title": post["title"], "reason": str(stop["error"])[:300]}
                row(pick, post, "", "", "没读（守卫拒绝）")
            else:
                failed_reads.append({"pick": pick, "title": post["title"], "reason": str(error)[:300]})
                row(pick, post, "", "", f"读取失败：{str(error)[:120]}")
            continue
        if stop["error"] is not None:      # the read worked, a download was refused: the set is not filed half-made
            stopped = {"pick": pick, "title": post["title"], "reason": str(stop["error"])[:300]}
            row(pick, post, "", "", "没存完（守卫拒绝）")
            continue
        if record["type"] == "video":      # the search called it an image post and the read says otherwise
            skipped.append({"pick": pick, "title": post["title"], "reason": "video"})
            row(pick, post, "", "", "跳过：视频帖，这里只研究图文")
            continue
        entry = _file_set(post, pick, record, raw / record["note_id"], keyword, date, image_sets)
        if entry["listed"] == 0:
            skipped.append({"pick": pick, "title": post["title"], "reason": "no images"})
            row(pick, post, "", "", "跳过：这篇没有图")
            continue
        state["sets"][post["note_id"]] = entry
        sets.append(entry)
        row(pick, post, entry["folder"], entry["listed"], "已存" if entry["complete"] else f"不全：存了 {entry['saved']} / {entry['listed']} 张")

    problems = check_sets(sets, image_sets)
    summary = check_summary(study_dir, sets)
    if stopped:
        status = "stopped"
    elif problems or failed_reads:
        status = "failed"
    elif summary["missing"] or summary["not_named"]:
        status = "incomplete"
    else:
        status = "complete"
    result = {"status": status, "keyword": keyword, "date": date, "reads_used": state["reads_used"], "sets": sets,
              "skipped": skipped, "failed_reads": failed_reads, "problems": problems, "stopped": stopped, "summary": summary,
              "study_folder": str(study_dir), "image_sets_folder": str(image_sets)}
    _save_state(study_dir, state)
    _write_index(study_dir, keyword, date, result, rows)
    return result


# --- the real stand-ins' replacements -----------------------------------------------------------------------------

def default_folders(brand: str, keyword: str, date: str) -> tuple:
    base = Path("outputs") / brand / "品牌资料" / "对标笔记库"
    return base / "image-sets", base / "research" / f"{date}-{_clean(keyword, 60)}"


def default_deps(redbook: list | None = None) -> StudyDeps:
    """The real set: the guarded `redbook` command for the search, the whole-note reader's own real set for the rest."""
    redbook = redbook or shlex.split(os.environ.get("XHS_NOTE_REDBOOK") or "redbook")

    def search(keyword: str) -> dict:
        try:
            done = rn._run(redbook + ["search", keyword, "--sort", "popular", "--type", "image", "--json"], 900)
        except subprocess.TimeoutExpired as error:
            raise rn.ReadFailed("the search timed out after 900 s") from error
        if done.returncode != 0:
            raise rn.ReadFailed(rn._gist(done.stderr) or f"the search exited {done.returncode}", code=done.returncode)
        starts = [i for i in (done.stdout.find("{"), done.stdout.find("[")) if i >= 0]
        try:
            return json.loads(done.stdout[min(starts):]) if starts else {}
        except ValueError as error:
            raise rn.ReadFailed("the search did not return a list of posts") from error

    return StudyDeps(search=search, note=rn.default_deps(redbook))


# --- the command line -----------------------------------------------------------------------------------------------------

def main(argv: list | None = None, deps: StudyDeps | None = None) -> int:
    parser = argparse.ArgumentParser(description="Save the whole image sets of the best posts on one topic.")
    parser.add_argument("--brand", required=True, help="the brand's folder name under outputs/ (the brand's profile name)")
    parser.add_argument("--keyword", required=True, help="the topic keyword, one search")
    parser.add_argument("-n", type=int, default=5, help="how many top image posts to save (default 5)")
    parser.add_argument("--image-sets", help="the brand's image-sets folder (default: outputs/<brand>/品牌资料/对标笔记库/image-sets)")
    parser.add_argument("--study-dir", help="the study's own folder (default: .../对标笔记库/research/<date>-<keyword>)")
    parser.add_argument("--date", help="the study's date, YYYY-MM-DD (default: today); the same date and keyword is the same study")
    args = parser.parse_args(argv)
    keyword = args.keyword.strip()
    if not keyword or keyword.startswith("-") or args.n < 1:
        print("study_topic: give a topic keyword (not starting with '-') and -n of at least 1.", file=sys.stderr)
        return 2
    import datetime
    date = args.date or datetime.date.today().isoformat()
    image_sets, study_dir = (Path(args.image_sets) if args.image_sets else None, Path(args.study_dir) if args.study_dir else None)
    default_sets, default_study = default_folders(args.brand, keyword, date)
    image_sets, study_dir = image_sets or default_sets, study_dir or default_study
    if deps is None:   # the real run: keep the project's outputs layout
        sys.path.insert(0, str(rn.SHARED_SCRIPTS))
        from output_paths import validate_output_path
        image_sets = validate_output_path(image_sets / ".check").parent
        study_dir = validate_output_path(study_dir / ".check").parent
        deps = default_deps()
    try:
        result = run_study(keyword, args.n, deps, image_sets=image_sets, study_dir=study_dir, date=date)
    except StudyError as error:
        print(f"study_topic: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] == "stopped":
        print(f"study_topic: stopped at {result['stopped']['pick'] or 'the search'}: {result['stopped']['reason']}. "
              "Tell the owner; do not retry in a loop.", file=sys.stderr)
    return {"complete": 0, "failed": 1, "stopped": 3, "incomplete": 4}[result["status"]]


if __name__ == "__main__":
    sys.exit(main())
