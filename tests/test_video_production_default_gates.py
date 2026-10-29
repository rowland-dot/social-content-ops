"""video-production must give every run a quality-gate list that really checks.

Seam: the skill's `video_pipeline.py start` command, read through what it leaves in
the run folder (`gates.json`, `run-state.json`) and through the SDK stages that then
run against it. Set VIDEO_PRODUCTION_SKILL_DIR to run the same checks against the
OpenClaw workspace copy instead of this repo.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = Path(os.environ.get("VIDEO_PRODUCTION_SKILL_DIR")
                 or ROOT / "skills" / "builtin" / "video-production")
WRAPPER = SKILL_DIR / "scripts" / "video_pipeline.py"
SDK = SKILL_DIR / "vendor" / "video-pipeline-sdk"

VERIFY_GATES = {"dup", "timeline", "layout", "frames", "transitions"}
RENDER_GATES = {"meta", "match", "audio"}
EIGHT_GATES = VERIFY_GATES | RENDER_GATES

PYTHON = sys.executable.replace("\\", "/")


def _posix(path) -> str:
    return str(path).replace("\\", "/")


def _start(base: Path, *extra: str, source: Path | None = None) -> subprocess.CompletedProcess:
    # Any existing file passes the wrapper's own source check; the gate list is written
    # before the SDK touches the source, so these tests need no real video.
    src = source or Path(__file__)
    return subprocess.run(
        [sys.executable, str(WRAPPER), "start", "--source", str(src), "--base", str(base), *extra],
        capture_output=True, text=True, encoding="utf-8", errors="replace")


def _run_dir(base: Path) -> Path:
    return Path((base / "current.txt").read_text(encoding="utf-8").strip())


@pytest.fixture(scope="module")
def default_run(tmp_path_factory) -> Path:
    base = tmp_path_factory.mktemp("default-run")
    _start(base)  # exactly the quick start: no --gates
    return _run_dir(base)


def _gates(rd: Path) -> dict:
    data = json.loads((rd / "gates.json").read_text(encoding="utf-8"))
    return {g["id"]: g for g in data["gates"]}


def test_run_started_without_gates_gets_all_eight_gates_in_their_phases(default_run):
    gates = _gates(default_run)
    assert set(gates) == EIGHT_GATES
    assert {i for i, g in gates.items() if g["phase"] == "verify"} == VERIFY_GATES
    assert {i for i, g in gates.items() if g["phase"] == "render"} == RENDER_GATES


def test_every_gate_command_runs_under_the_pipeline_interpreter(default_run):
    for gate_id, gate in _gates(default_run).items():
        cmd = gate["cmd"]
        assert not re.search(r"(^|[\s;&|\"'])python3?\s", cmd), f"{gate_id}: bare python in {cmd!r}"
        assert PYTHON in cmd, f"{gate_id}: not run by {PYTHON}: {cmd!r}"
        assert "{" not in cmd, f"{gate_id}: unfilled placeholder in {cmd!r}"


def test_duplicate_and_timeline_gates_read_the_runs_scene_file(default_run):
    gates = _gates(default_run)
    scenes = _posix(default_run / "artifacts" / "scenes.json")
    for gate_id in ("dup", "timeline"):
        assert scenes in gates[gate_id]["cmd"], gates[gate_id]["cmd"]


def test_render_phase_gates_point_at_the_film_in_the_working_output(default_run):
    gates = _gates(default_run)
    film = _posix(default_run / "workdir" / "out" / "final.mp4")
    assert film in gates["audio"]["cmd"], gates["audio"]["cmd"]
    # The delivery folder is only filled after the render stage.
    out_dir = json.loads((default_run / "run-state.json").read_text(encoding="utf-8"))["out_dir"]
    for gate_id, gate in gates.items():
        assert _posix(Path(out_dir) / "final.mp4") not in gate["cmd"], gate_id


def test_default_run_installs_the_rendering_engine_into_the_work_folder(default_run):
    state = json.loads((default_run / "run-state.json").read_text(encoding="utf-8"))
    assert state["config"]["scaffold_install"] is True


def test_callers_own_config_still_decides_scaffold_install(tmp_path):
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"scaffold_install": False}), encoding="utf-8")
    _start(tmp_path / "base", "--config", str(cfg))
    state = json.loads((_run_dir(tmp_path / "base") / "run-state.json").read_text(encoding="utf-8"))
    assert state["config"]["scaffold_install"] is False


def test_explicit_gates_file_replaces_the_default(tmp_path):
    custom = tmp_path / "mine.json"
    custom.write_text(json.dumps({"gates": [
        {"id": "mine", "title": "mine", "phase": "verify", "cmd": "echo {run_dir}"}]}), encoding="utf-8")
    _start(tmp_path / "base", "--gates", str(custom))
    rd = _run_dir(tmp_path / "base")
    gates = _gates(rd)
    assert set(gates) == {"mine"}
    assert gates["mine"]["cmd"] == f"echo {_posix(rd)}"


# ---------------------------------------------------------------- end to end ----

needs_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg/ffprobe not installed")


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def _wrapper(base: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(WRAPPER), *args, "--base", str(base)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


@pytest.fixture(scope="module")
def checked_run(tmp_path_factory):
    """Quick start as SKILL.md shows it (no --gates), driven to the checking stage with
    stand-in material. Only the work-folder install is switched off (network, ~540 MB)."""
    work = tmp_path_factory.mktemp("e2e")
    source = work / "raw.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=5",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=5", "-shortest", str(source))
    (work / "raw.srt").write_text("1\n00:00:00,000 --> 00:00:02,500\n你好\n\n"
                                  "2\n00:00:02,500 --> 00:00:05,000\n再见\n", encoding="utf-8")
    scenes = {"scenes": [
        {"id": i + 1, "start": i * 1.5, "end": (i + 1) * 1.5, "transition": t,
         "cards": [{"slot": "center", "form": "rings", "variant": f"v{i}"}]}
        for i, t in enumerate(["wipe", "slide", "zoom"])]}
    (work / "scenes.json").write_text(json.dumps(scenes), encoding="utf-8")
    (work / "design-table.md").write_text("# 设计表\n", encoding="utf-8")
    (work / "cfg.json").write_text(json.dumps({"scaffold_install": False}), encoding="utf-8")
    base = work / "base"

    first = _start(base, "--brief", "测试", "--transcript", str(work / "raw.srt"),
                   "--scenes", str(work / "scenes.json"), "--design-table", str(work / "design-table.md"),
                   "--config", str(work / "cfg.json"), source=source)
    rd = _run_dir(base)
    assert first.returncode == 3, first.stdout + first.stderr  # waiting at checkpoint-1
    _wrapper(base, "answer", "--id", "checkpoint-1", "--values", "approve")
    (rd / "workdir").mkdir(exist_ok=True)
    (rd / "workdir" / ".build-ok").touch()
    result = _wrapper(base, "resume")
    return rd, result


@needs_ffmpeg
def test_quick_start_run_reaches_the_checking_stage_and_reports_each_gate(checked_run):
    rd, result = checked_run
    assert "未配置质量门" not in result.stdout + result.stderr
    assert result.returncode == 2, result.stdout + result.stderr  # gates ran; some FAIL
    assert result.stdout.rstrip().endswith("STATE: gate-failed")
    report = json.loads((rd / "gate-report.json").read_text(encoding="utf-8"))
    status = {g["id"]: g["status"] for g in report["gates"] if g["phase"] == "verify"}
    assert set(status) == VERIFY_GATES
    assert status["dup"] == "PASS" and status["timeline"] == "PASS"
    for gate_id in ("layout", "frames", "transitions"):
        assert status[gate_id] == "FAIL", gate_id  # build-step inputs absent: never skipped, never passed
    for gate in report["gates"]:
        assert "not found" not in " ".join(gate["tail"]), gate["id"]
    tails = {g["id"]: " ".join(g["tail"]) for g in report["gates"]}
    assert "layout.json" in tails["layout"]
    assert "composition.json" in tails["frames"] and "composition.json" in tails["transitions"]


@needs_ffmpeg
def test_render_stage_loudness_gate_reads_the_film_in_the_working_output(checked_run, tmp_path):
    rd, _ = checked_run
    film = rd / "workdir" / "out" / "final.mp4"
    film.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg("-f", "lavfi", "-i", "color=c=blue:size=320x240:rate=25:duration=1",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1,volume=8",
            "-shortest", "-c:v", "libx264", "-c:a", "aac", str(film))
    subprocess.run([sys.executable, str(SDK / "gates" / "aggregate.py"),
                    "--run-dir", str(rd), "--phase", "render"], capture_output=True)
    report = json.loads((rd / "gate-report.json").read_text(encoding="utf-8"))
    audio = next(g for g in report["gates"] if g["id"] == "audio")
    assert audio["status"] == "PASS", audio["tail"]
    assert "mean=" in " ".join(audio["tail"])  # a loudness verdict, not a missing-file failure
