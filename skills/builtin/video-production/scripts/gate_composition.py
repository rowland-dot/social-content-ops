#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""帧检 / 转场门的入口：从写码步骤留下的 composition.json 取合成名与帧号，再调 SDK 的门。

SDK 的这两道门要在命令行里给合成名与帧号，而它们只有写码时才知道，所以写码步骤把它们
记进 <run-dir>/artifacts/gate-inputs/composition.json：
  {"comp": "Main", "frames": [60, 120], "cuts": [120, 213]}
frames 门要 comp + frames；transitions 门要 comp + cuts。缺文件或缺项 = 门 FAIL（不跳过、不算过）。
可选：同目录下 frame-checks.json 作为帧检的区域断言。

用法：gate_composition.py frames|transitions --run-dir <run-dir>
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

GATES = Path(__file__).resolve().parent.parent / "vendor" / "video-pipeline-sdk" / "gates"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["frames", "transitions"])
    ap.add_argument("--run-dir", required=True)
    args = ap.parse_args()
    rd = Path(args.run_dir)
    inputs = rd / "artifacts" / "gate-inputs"
    comp_file = inputs / "composition.json"
    if not comp_file.is_file():
        print(f"FAIL  缺少 {comp_file}：写码步骤须记下合成名与帧号（见 SKILL.md「质量门」）")
        return 1
    data = json.loads(comp_file.read_text(encoding="utf-8"))
    key = "frames" if args.kind == "frames" else "cuts"
    nums = data.get(key) or []
    if not data.get("comp") or not nums:
        print(f"FAIL  {comp_file} 缺 comp 或 {key}")
        return 1
    csv = ",".join(str(n) for n in nums)
    script = "check_frames.py" if args.kind == "frames" else "check_transitions.py"
    cmd = [sys.executable, str(GATES / script), "--project", str(rd / "workdir"), "--comp", str(data["comp"]),
           "--frames" if args.kind == "frames" else "--cuts", csv]
    checks = inputs / "frame-checks.json"
    if args.kind == "frames" and checks.is_file():
        cmd += ["--checks", str(checks)]
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())
