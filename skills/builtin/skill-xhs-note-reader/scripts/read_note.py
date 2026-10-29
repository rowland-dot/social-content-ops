#!/usr/bin/env python3
"""Save the whole content of ONE Xiaohongshu note a team member gave Easel (issue 70).

    python skills/builtin/skill-xhs-note-reader/scripts/read_note.py "<note link>" [--out outputs/<topic>] [--skip-diandian]

One read through the guarded reader (`redbook read --json`, which also follows xhslink.com short links), then, into
a folder per note: the read itself, the caption, every image, the text inside each image, and for a video note the
video, a frame every 5 s plus scene changes, and the speech, then the 点点 summary. A record.json lists every part as
produced, partial, skipped or failed, with the reason. One failed part never deletes or hides the others.

Every request to Xiaohongshu or its file servers goes through the guard (`redbook`): the read, `fetch-file` for each
download, `diandian` for the summary. This script holds no cookie and sends nothing itself.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import diandian_reply  # noqa: E402  (the 点点 reply rules, a port of FavSense's)

# skills/shared/scripts: the transcriber (asr.py) and the outputs layout (output_paths.py)
SHARED_SCRIPTS = Path(__file__).resolve().parents[3] / "shared" / "scripts"

# The step's bounds (FavSense's numbers for frames, the issue's for speech).
FRAME_STEP_SECONDS = 5.0
SCENE_MERGE_SECONDS = 1.0     # a scene change this close to a frame already chosen adds nothing
MAX_FRAMES = 60
MAX_FRAME_BYTES = 20 * 1024 * 1024
MAX_FRAME_SECONDS = 120
SPEECH_CAP_SECONDS = 600

FILE_HOST = re.compile(r"^https?://([A-Za-z0-9-]+\.)*(xhscdn|xiaohongshu)\.com/")
NOTE_ADDRESS = re.compile(r"^https?://(www\.)?xiaohongshu\.com/(discovery/item|explore)/[A-Za-z0-9_-]+")
SHORT_LINK = re.compile(r"^https?://([A-Za-z0-9-]+\.)*xhslink\.com([/?#]|$)")
VIDEO_HOST = "https://sns-video-bd.xhscdn.com/"

# What the guard's exit codes mean for the 点点 step (redbook-guard.sh).
GUARD_REASONS = {
    65: "the daily cap of reads is used up",
    66: "the guard is tripped: the platform raised a safety signal earlier; tell the owner",
    70: "no login: the scanning browser is not running or not logged in",
    71: "favsense or an SOP scan is using the account right now",
}


class ReadFailed(Exception):
    """The note could not be read at all; nothing is saved. `code` is the guard's exit code when it refused (a study stops on it)."""

    def __init__(self, message: str = "", code: int | None = None):
        super().__init__(message)
        self.code = code


class DownloadFailed(RuntimeError):
    """A file could not be downloaded. `code` is the guard's exit code, None when the guard did not refuse."""

    def __init__(self, message: str = "", code: int | None = None):
        super().__init__(message)
        self.code = code


class PartUnavailable(Exception):
    """A part cannot run on this machine (a tool is not installed); the part is skipped with this reason."""


@dataclass(frozen=True)
class Deps:
    """Everything the step does outside itself. Tests replace these; default_deps() is the real set."""
    read: Callable[[str], dict]                       # note link -> the note object (redbook read --json)
    download: Callable[[str, Path], None]             # address, destination (redbook fetch-file)
    ocr: Callable[[Path], str]                        # image -> the text on it
    video_duration: Callable[[Path], float]
    grab_frame: Callable[[Path, float, Path], None]   # video, second, destination
    scene_times: Callable[[Path], list]               # video -> seconds at which the picture changes
    contact_sheet: Callable[[list, Path], None]       # frames, destination
    transcribe: Callable[[Path, float], dict]         # video, longest audio to read -> {text, partial, segments}
    diandian: Callable[[str, Path], int]              # full note address, reply file -> the guard's exit code
    clock: Callable[[], float] = time.monotonic


# --- the read -----------------------------------------------------------------------------------

def _note(read: dict) -> dict:
    """The note object, whether the read hands it back directly or one level down."""
    for key in ("note", "note_card"):
        if isinstance(read.get(key), dict):
            return read[key]
    return read


def pick_video_address(read: dict) -> str | None:
    """Where the video can be downloaded from, or None when the read carries no usable address.

    The original-quality key first (`video.consumer.origin_video_key` in the feed's spelling, `originVideoKey` on the
    note page), else the largest `video.media.stream.*` entry's backup address, else its main address. Only the
    platform's own file servers are accepted: the note is untrusted content.
    """
    video = _note(read).get("video") or {}
    consumer = video.get("consumer") or {}
    key = consumer.get("origin_video_key") or consumer.get("originVideoKey")
    if isinstance(key, str) and re.fullmatch(r"[A-Za-z0-9_./-]+", key):
        return VIDEO_HOST + key.lstrip("/")
    streams = (video.get("media") or {}).get("stream") or {}
    entries = [e for kind in streams.values() if isinstance(kind, list) for e in kind if isinstance(e, dict)]
    entries.sort(key=lambda e: e.get("size") or (e.get("width") or 0) * (e.get("height") or 0), reverse=True)
    for entry in entries:
        backups = entry.get("backup_urls") or entry.get("backupUrls") or []
        for url in (backups[0] if backups else None, entry.get("master_url") or entry.get("masterUrl")):
            if isinstance(url, str) and FILE_HOST.match(url):
                return url
    return None


# --- frames --------------------------------------------------------------------------------------

def sample_times(duration: float, step: float = FRAME_STEP_SECONDS) -> list:
    """One second every `step` seconds from 0, all inside the video."""
    count = int(duration // step) + (0 if duration % step == 0 else 1)
    return [i * step for i in range(max(count, 1))]


def sample_frames(video: Path, folder: Path, deps: Deps) -> dict:
    """A frame every 5 s, plus scene changes, stopping at 60 frames, 20 MB or 120 s of work, whichever comes first.

    The even spacing is taken first, so a cap that cuts the run short cuts scene changes before it cuts coverage.
    """
    started = deps.clock()
    duration = deps.video_duration(video)
    chosen = sample_times(duration)
    try:
        scenes = sorted(deps.scene_times(video))
    except Exception:  # noqa: BLE001  (scene changes are an extra; the spaced frames stand without them)
        scenes = []
    for second in scenes:
        if 0 <= second < duration and all(abs(second - t) >= SCENE_MERGE_SECONDS for t in chosen):
            chosen.append(second)

    frames = folder / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    taken: list = []
    total = 0
    stopped_by = None
    for second in chosen:
        if len(taken) >= MAX_FRAMES:
            stopped_by = "frames"
            break
        if deps.clock() - started >= MAX_FRAME_SECONDS:
            stopped_by = "seconds"
            break
        path = frames / f"t{second:09.3f}.jpg"
        deps.grab_frame(video, second, path)
        size = path.stat().st_size
        if total + size > MAX_FRAME_BYTES:
            path.unlink()
            stopped_by = "bytes"
            break
        total += size
        taken.append((second, path))

    final = []
    for number, (_, path) in enumerate(sorted(taken), start=1):
        final.append(path.rename(frames / f"frame-{number:03d}.jpg"))
    sheet = frames / "contact-sheet.jpg"
    if final:
        deps.contact_sheet(final, sheet)
    return {
        "status": "produced", "count": len(final), "times": [round(s, 3) for s, _ in sorted(taken)],
        "stopped_by": stopped_by, "contact_sheet": "frames/contact-sheet.jpg" if final else None,
    }


# --- the parts -----------------------------------------------------------------------------------

def _why(error: Exception) -> str:
    return (str(error) or type(error).__name__)[:300]


def _guarded(fn: Callable[[], dict]) -> dict:
    try:
        return fn()
    except PartUnavailable as error:
        return {"status": "skipped", "reason": _why(error)}
    except Exception as error:  # noqa: BLE001  (one failed part must not stop the others)
        return {"status": "failed", "reason": _why(error)}


def _caption(folder: Path, note: dict) -> dict:
    info = note.get("interact_info") or {}
    counts = " · ".join(f"{label} {info[key]}" for key, label in (
        ("liked_count", "赞"), ("collected_count", "收藏"), ("comment_count", "评论"), ("share_count", "转发")) if key in info)
    tags = " ".join(f"#{t.get('name')}" for t in note.get("tag_list") or [] if isinstance(t, dict) and t.get("name"))
    lines = [f"# {note.get('title') or ''}".rstrip(), "", str(note.get("desc") or "").strip(), ""]
    if tags:
        lines += [f"标签：{tags}", ""]
    if counts:
        lines += [counts, ""]
    (folder / "caption.md").write_text("\n".join(lines), encoding="utf-8")
    return {"status": "produced"}


def _images(folder: Path, note: dict, deps: Deps) -> tuple:
    items = note.get("image_list") or []
    if not items:
        return {"status": "skipped", "reason": "the note has no images"}, []
    saved: list = []
    failed: list = []
    for number, item in enumerate(items, start=1):
        name = f"{number:02d}.jpg"
        dest = folder / "images" / name
        try:
            url = item.get("url_default") or item.get("url")
            if not url:
                raise ValueError("the read lists no address for this image")
            deps.download(url, dest)
            if not dest.is_file() or dest.stat().st_size == 0:
                raise RuntimeError("nothing was downloaded")
            saved.append(name)
        except Exception as error:  # noqa: BLE001
            dest.unlink(missing_ok=True)
            failed.append({"image": name, "reason": _why(error)})
    part = {"status": "produced" if not failed else ("partial" if saved else "failed"),
            "count": len(saved), "files": [f"images/{n}" for n in saved]}
    if failed:
        part["failed"] = failed
        if not saved:
            part["reason"] = failed[0]["reason"]
    return part, saved


def _image_text(folder: Path, saved: list, deps: Deps) -> dict:
    if not saved:
        return {"status": "skipped", "reason": "no image was saved"}
    entries: list = []
    for name in saved:
        entry = {"image": f"images/{name}"}
        try:
            entry["text"] = deps.ocr(folder / "images" / name).strip()
        except PartUnavailable:
            raise
        except Exception as error:  # noqa: BLE001  (a gap in the text, not a hole in the order)
            entry.update(text=None, error=_why(error))
        entries.append(entry)
    (folder / "image-text.json").write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    errors = sum(1 for e in entries if "error" in e)
    return {"status": "produced" if not errors else ("partial" if errors < len(entries) else "failed"),
            "count": len(entries) - errors, "file": "image-text.json"}


def _speech(folder: Path, video: Path, deps: Deps) -> dict:
    result = deps.transcribe(video, SPEECH_CAP_SECONDS)
    text = (result.get("text") or "").strip()
    partial = bool(result.get("partial"))
    (folder / "speech.json").write_text(json.dumps(
        {"text": text, "partial": partial, "segments": result.get("segments") or []}, ensure_ascii=False, indent=2), encoding="utf-8")
    if not text:
        return {"status": "produced", "note": "no speech found"}
    return {"status": "partial" if partial else "produced", "file": "speech.json"}


def _diandian(folder: Path, read: dict, link: str, deps: Deps) -> dict:
    address = next((a for a in (_note(read).get("webUrl"), read.get("webUrl"), link)
                    if isinstance(a, str) and NOTE_ADDRESS.match(a)), None)
    if address is None:
        return {"status": "skipped", "reason": "no full note address in the read, and the 点点 step needs one"}
    reply_file = folder / ".diandian-reply.txt"
    try:
        code = deps.diandian(address, reply_file)
        if code != 0:
            if code in GUARD_REASONS:
                return {"status": "skipped", "reason": GUARD_REASONS[code]}
            return {"status": "failed", "reason": f"the 点点 chat gave no reply (the guard exited {code})"}
        text = reply_file.read_text(encoding="utf-8") if reply_file.is_file() else ""
    finally:
        reply_file.unlink(missing_ok=True)
    problem = diandian_reply.summary_problem(text)
    if problem:
        return {"status": "failed", "reason": f"reply not saved: {problem}"}
    (folder / "diandian.md").write_text(diandian_reply.usable_summary(text) + "\n", encoding="utf-8")
    return {"status": "produced", "file": "diandian.md"}


def read_note(link: str, out_root, deps: Deps, *, want_diandian: bool = True) -> dict:
    """Read the note once and save everything it holds under <out_root>/<note id>/. Returns the record.

    Raises ReadFailed when the read itself fails; nothing is written then.
    """
    read = deps.read(link)
    note = _note(read)
    note_id = str(note.get("note_id") or note.get("noteId") or read.get("note_id") or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", note_id):
        raise ReadFailed("the read has no usable note id")
    folder = Path(out_root) / note_id
    folder.mkdir(parents=True, exist_ok=True)
    parts: dict = {}

    # The read as it came back is the one file that may hold the note's own access code.
    (folder / "read.json").write_text(json.dumps(read, ensure_ascii=False, indent=2), encoding="utf-8")
    parts["read"] = {"status": "produced"}
    parts["caption"] = _guarded(lambda: _caption(folder, note))

    saved: list = []

    def images() -> dict:
        part, names = _images(folder, note, deps)
        saved.extend(names)
        return part

    parts["images"] = _guarded(images)
    parts["image_text"] = _guarded(lambda: _image_text(folder, saved, deps))

    is_video = note.get("type") == "video" or bool(note.get("video"))
    video_file = folder / "video" / "note.mp4"
    if not is_video:
        parts["video"] = {"status": "skipped", "reason": "not a video note"}
        parts["frames"] = parts["speech"] = {"status": "skipped", "reason": "not a video note"}
    else:
        address = pick_video_address(read)
        if address is None:
            parts["video"] = {"status": "skipped", "reason": "video address not in read"}
        else:
            def fetch() -> dict:
                deps.download(address, video_file)
                if not video_file.is_file() or video_file.stat().st_size == 0:
                    raise RuntimeError("nothing was downloaded")
                return {"status": "produced", "file": "video/note.mp4"}
            parts["video"] = _guarded(fetch)
        if parts["video"]["status"] == "produced":
            parts["frames"] = _guarded(lambda: sample_frames(video_file, folder, deps))
            parts["speech"] = _guarded(lambda: _speech(folder, video_file, deps))
        else:
            parts["frames"] = parts["speech"] = {"status": "skipped", "reason": "no video file"}

    if want_diandian:
        parts["diandian"] = _guarded(lambda: _diandian(folder, read, link, deps))
    else:
        parts["diandian"] = {"status": "skipped", "reason": "left out by request"}

    record = {"note_id": note_id, "type": "video" if is_video else "normal", "title": note.get("title") or "", "parts": parts}
    (folder / "record.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


# --- the real stand-ins' replacements ---------------------------------------------------------------

def _gist(text: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return " ".join(lines[-3:])[:300]


def _run(command: list, timeout: int) -> subprocess.CompletedProcess:
    # stdin is closed: ffmpeg reads commands from it and, run by an agent, would wait on it forever
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=timeout, stdin=subprocess.DEVNULL)


def default_deps(redbook: list | None = None) -> Deps:
    """The real set: the guarded `redbook` command (WSL), ffmpeg, the local text-in-image engine, the shared transcriber."""
    redbook = redbook or shlex.split(os.environ.get("XHS_NOTE_REDBOOK") or "redbook")

    def guard(args: list, timeout: int) -> subprocess.CompletedProcess:
        try:
            return _run(redbook + args, timeout)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"timed out after {timeout} s") from error

    def read(link: str) -> dict:
        try:
            done = guard(["read", link, "--json"], 900)
        except RuntimeError as error:
            raise ReadFailed(str(error)) from error
        if done.returncode != 0:
            raise ReadFailed(_gist(done.stderr) or f"the reader exited {done.returncode}", code=done.returncode)
        try:
            return json.loads(done.stdout[done.stdout.index("{"):])
        except ValueError as error:
            raise ReadFailed("the reader did not return a note") from error

    def download(url: str, dest: Path) -> None:
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        done = guard(["fetch-file", url, str(dest)], 900)
        if done.returncode != 0:
            raise DownloadFailed(_gist(done.stderr) or f"the download exited {done.returncode}", code=done.returncode)

    def diandian(address: str, dest: Path) -> int:
        try:
            done = guard(["diandian", address, str(dest)], 1500)
        except RuntimeError:
            return 124
        if done.returncode != 0:
            print(f"read_note: 点点 step: {_gist(done.stderr)}", file=sys.stderr)
        return done.returncode

    engine: list = []

    def ocr(path: Path) -> str:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as error:
            raise PartUnavailable("rapidocr_onnxruntime is not installed (run ops/wsl-setup/setup.sh --only python-packages)") from error
        if not engine:
            engine.append(RapidOCR())
        found, _ = engine[0](str(path))
        return "\n".join(item[1] for item in found or [])

    def ffmpeg(args: list, timeout: int) -> subprocess.CompletedProcess:
        done = _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], timeout)
        if done.returncode != 0:
            raise RuntimeError(f"ffmpeg exited {done.returncode}: {_gist(done.stderr)}")
        return done

    def video_duration(video: Path) -> float:
        done = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video)], 60)
        if done.returncode != 0:
            raise RuntimeError(f"ffprobe exited {done.returncode}: {_gist(done.stderr)}")
        return float(json.loads(done.stdout)["format"]["duration"])

    def grab_frame(video: Path, second: float, dest: Path) -> None:
        ffmpeg(["-ss", f"{second:.3f}", "-i", str(video), "-frames:v", "1", "-vf", "scale='min(1600,iw)':-2", "-q:v", "3", str(dest)], 60)

    def scene_times(video: Path) -> list:
        done = _run(["ffmpeg", "-hide_banner", "-i", str(video), "-an", "-vf", "select='gt(scene,0.22)',showinfo", "-f", "null", "-"], 60)
        return [float(m) for m in re.findall(r"pts_time:([0-9.]+)", done.stderr)]

    def contact_sheet(frames: list, dest: Path) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            listing = Path(tmp) / "frames.txt"
            listing.write_text("".join(f"file '{Path(f).resolve().as_posix()}'\n" for f in frames), encoding="utf-8")
            ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listing), "-vf", "scale=180:-2,tile=10x10:padding=2:margin=2",
                    "-fps_mode", "vfr", "-frames:v", "1", "-q:v", "3", str(dest)], 120)

    def transcribe(video: Path, max_seconds: float) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "speech.json"
            done = _run(
                [sys.executable, str(SHARED_SCRIPTS / "asr.py"), "transcribe", "-i", str(video), "-o", str(out), "--format", "json",
                 "--model", "small", "--language", "zh", "--max-seconds", str(int(max_seconds))],
                int(max_seconds * 1.5) + 600)
            if done.returncode != 0 or not out.is_file():
                raise RuntimeError(_gist(done.stderr) or f"the transcriber exited {done.returncode}")
            data = json.loads(out.read_text(encoding="utf-8"))
        segments = data.get("segments") or []
        return {"text": " ".join(s["text"] for s in segments), "partial": bool(data.get("partial")), "segments": segments}

    return Deps(read=read, download=download, ocr=ocr, video_duration=video_duration, grab_frame=grab_frame,
                scene_times=scene_times, contact_sheet=contact_sheet, transcribe=transcribe, diandian=diandian)


# --- the command line -------------------------------------------------------------------------------

def main(argv: list | None = None, deps: Deps | None = None) -> int:
    parser = argparse.ArgumentParser(description="Save the whole content of one Xiaohongshu note.")
    parser.add_argument("link", help="the note's link (a full address with its access code, or an xhslink.com short link)")
    parser.add_argument("--out", help="folder the note's folder goes into (default: outputs/xhs-reference-notes)")
    parser.add_argument("--skip-diandian", action="store_true", help="leave out the 点点 summary")
    args = parser.parse_args(argv)
    if not (NOTE_ADDRESS.match(args.link) or SHORT_LINK.match(args.link)):
        print("read_note: that is not a note link (expected xiaohongshu.com/explore/<id>?... or an xhslink.com short link).", file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else Path("outputs") / "xhs-reference-notes"
    if deps is None:  # the real run: keep the project's outputs layout
        sys.path.insert(0, str(SHARED_SCRIPTS))
        from output_paths import validate_output_path
        out = validate_output_path(out / ".check").parent
        deps = default_deps()
    try:
        record = read_note(args.link, out, deps, want_diandian=not args.skip_diandian)
    except ReadFailed as error:
        print(f"read_note: the note could not be read: {error}", file=sys.stderr)
        return 1
    print(json.dumps({**record, "folder": str(Path(out) / record["note_id"])}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
