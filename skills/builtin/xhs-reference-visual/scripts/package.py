#!/usr/bin/env python3
"""Finds the style package the photo-scene skill works from (issue 136, answer 8).

    package.py find [--choice default|own]   the package folder in use, or the choice to put to the user
    package.py show-default                  the default package's files and what each holds

The team's own package lives in the private work folder (`work/team-packages/xhs-reference-visual/`). When it is
there, it is used and nothing is asked. When it is not, the user chooses between the default package that ships in
this skill and building their own. Exit codes: 0 a folder is chosen, 3 the choice must be put to the user, 4 the
user chose to build their own and must fill the folder first.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

TEAM_REL = "work/team-packages/xhs-reference-visual"
DEFAULT_REL = "skills/builtin/xhs-reference-visual/references/defaults"

CHOICE_MESSAGE = (
    "没有找到团队的风格资料包。你可以选：\n"
    "A. 使用默认资料包：通用的风格记忆、流程手册和设计标准，不含参考图；参考来自这篇帖子主题下的真实高赞帖子。\n"
    "B. 建立你自己的资料包：我列出需要哪几个文件、每个文件写什么，你填好后放进资料包文件夹。\n"
    "想先看看默认资料包里写了什么，随时说一声，我把文件拿给你看。")

# (path inside a package, what it holds, needed for the user's own package)
FILES = (
    ("INDEX.md", "这个资料包里每个文件是做什么的，以及阅读顺序", False),
    ("skill/SKILL.md", "入口：什么时候用，先读什么", True),
    ("file/DESIGN-MEMORY.md", "风格记忆：字体、文字容器、配色、风格分支、事实边界", True),
    ("playbook/PLAYBOOK.md", "流程手册：锁定需求、选方向、封面、检查", True),
    ("playbook/EXECUTION-BRIEF.md", "单张图的执行说明模板", True),
    ("standards/STANDARD.md", "摄影标准、项目开始前的步骤、验收清单、去 AI 感标准", False),
    ("standards/REFERENCE-BREAKDOWN.md", "怎样拆解一张参考图", False),
    ("methods/PRODUCT-REPLACEMENT.md", "把商品放进参考场景的步骤和经验", False),
    ("methods/PORTRAIT-WORKFLOW.md", "人像与修图的步骤和经验", False),
    ("methods/PORTRAIT-PROMPT-RULES.md", "人像摄影模块，一次只用适用的几个", False),
)


def default_root() -> Path:
    return Path(__file__).resolve().parents[4]


def find(root: Path, choice: str | None) -> int:
    if (root / TEAM_REL / "skill" / "SKILL.md").is_file():
        print(f"资料包目录：{TEAM_REL}（团队资料包）")
        return 0
    if choice == "default":
        print(f"资料包目录：{DEFAULT_REL}（默认资料包）")
        return 0
    if choice == "own":
        print(f"把你的资料包放进这个文件夹：{TEAM_REL}")
        print("需要这些文件，文件夹里的相对位置要照下面写：")
        for rel, what, needed in FILES:
            if needed:
                print(f"- {rel}：{what}")
        print("下面这些可选，有就更好：")
        for rel, what, needed in FILES:
            if not needed:
                print(f"- {rel}：{what}")
        print("放好以后告诉我，我再从头开始。")
        return 4
    print(CHOICE_MESSAGE)
    return 3


def show_default() -> int:
    for rel, what, _ in FILES:
        print(f"{DEFAULT_REL}/{rel}：{what}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None, help="the project folder (default: this project)")
    sub = parser.add_subparsers(dest="command", required=True)
    finder = sub.add_parser("find")
    finder.add_argument("--choice", choices=("default", "own"))
    sub.add_parser("show-default")
    args = parser.parse_args(argv)
    if args.command == "find":
        return find(args.root or default_root(), args.choice)
    return show_default()


if __name__ == "__main__":
    sys.exit(main())
