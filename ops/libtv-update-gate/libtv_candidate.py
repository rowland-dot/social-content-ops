"""Reading a candidate LibTV version without running any of it.

The program's embedded source is plain JavaScript, so its command tree, its version and its checksums can be read
from the file. Nothing here executes the program, and nothing is unpacked outside memory.
"""

from __future__ import annotations

import difflib
import io
import re
import zipfile
from dataclasses import dataclass, field

PROGRAM_MEMBER = "libtv-linux-x64/libtv"

# ---- the command tree, by full command path -------------------------------------------------------------------

ROOT_FUNCTION = "registerLibtvCommandsForProgram"
_FUNCTION = re.compile(r"function (\w+)\((\w*)\) \{")
_TOKEN = re.compile(
    r'(?P<assign>(?:const|let|var)\s+(?P<var>\w+)\s*=\s*(?P<aparent>\w+)\.command\(\s*"(?P<aname>[^"\\]+)")'
    r'|(?P<cmd>(?P<cparent>\w+)\.command\(\s*"(?P<cname>[^"\\]+)")'
    r'|(?P<opt>(?:(?P<oparent>\w+)|\))\s*\.(?:option|requiredOption)\(\s*"(?P<flags>[^"\\]+)")'
    r'|(?P<call>\b(?P<callee>register\w*)\(\s*(?P<arg>\w+)\s*\))'
)
WINDOW_BEFORE_ROOT = 1_500_000   # the registration functions sit within a few hundred KB before the root function


def read_commands(data: bytes) -> dict[tuple[str, ...], list[str]] | None:
    """{command path: its long option flags}, read from the program's source by following the registration
    functions from the root one. None when the program has no readable command tree.

    A flat list of names would hide which parent a name sits under (`project update` and `workspace update`
    are different commands), so every command is kept by its full path.
    """
    root_at = data.rfind(b"function " + ROOT_FUNCTION.encode() + b"(")
    if root_at < 0:
        return None
    text = data[max(0, root_at - WINDOW_BEFORE_ROOT): root_at + 20000].decode("utf-8", "replace")
    bodies: dict[str, tuple[str, str]] = {}
    for m in _FUNCTION.finditer(text):
        name, param = m.group(1), m.group(2)
        end = text.find(f'__name({name}, "{name}");', m.end())   # the bundler marks the end of every function
        if end >= 0:
            bodies[name] = (param, text[m.end():end])
    if ROOT_FUNCTION not in bodies:
        return None
    tree: dict[tuple[str, ...], list[str]] = {}

    def add(path: tuple[str, ...], flag: str | None = None) -> None:
        options = tree.setdefault(path, [])
        if flag and flag not in options:
            options.append(flag)

    def walk(fn: str, env: dict[str, tuple[str, ...]], depth: int = 0) -> None:
        if depth > 12 or fn not in bodies:
            return
        env = dict(env)
        last: tuple[str, ...] | None = None   # the command a chained .option(...) belongs to
        for m in _TOKEN.finditer(bodies[fn][1]):
            if m.group("assign") or m.group("cmd"):
                parent = env.get(m.group("aparent") or m.group("cparent"))
                if parent is None:
                    continue
                path = parent + ((m.group("aname") or m.group("cname")).split()[0],)
                if m.group("assign"):
                    env[m.group("var")] = path
                add(path)
                last = path
            elif m.group("opt"):
                target = env.get(m.group("oparent")) if m.group("oparent") else last
                if target is None:
                    continue
                flags = [f.strip() for f in m.group("flags").split(",")]
                add(target, next((f.split()[0] for f in flags if f.startswith("--")), flags[0].split()[0]))
            else:
                callee, arg = m.group("callee"), env.get(m.group("arg"))
                if callee in bodies and arg is not None:
                    walk(callee, {bodies[callee][0]: arg}, depth + 1)

    walk(ROOT_FUNCTION, {bodies[ROOT_FUNCTION][0]: ()})
    tree.pop((), None)
    return tree or None


@dataclass
class CommandDiff:
    added: list[tuple[str, ...]] = field(default_factory=list)
    removed: list[tuple[str, ...]] = field(default_factory=list)
    options_added: list[tuple[tuple[str, ...], str]] = field(default_factory=list)
    options_removed: list[tuple[tuple[str, ...], str]] = field(default_factory=list)


def diff_commands(old: dict, new: dict) -> CommandDiff:
    d = CommandDiff()
    d.added = sorted(p for p in new if p not in old)
    d.removed = sorted(p for p in old if p not in new)
    for path in sorted(new):
        for flag in new[path]:
            if path not in old or flag not in old[path]:
                d.options_added.append((path, flag))
    for path in sorted(old):
        for flag in old[path]:
            if path not in new or flag not in new[path]:
                d.options_removed.append((path, flag))
    return d


def program_versions(data: bytes) -> list[str]:
    """The version strings the program carries for itself: its embedded package record."""
    found = []
    for m in re.finditer(rb'@liblib-apps/libtv-cli",\s*version:\s*"(\d+\.\d+\.\d+)"', data):
        v = m.group(1).decode()
        if v not in found:
            found.append(v)
    return found


# ---- the zips -----------------------------------------------------------------------------------------------------


def zip_members(source: bytes | str | object) -> dict[str, bytes]:
    """Every file in a zip, by name (directories skipped), read into memory."""
    handle = io.BytesIO(source) if isinstance(source, bytes) else source
    with zipfile.ZipFile(handle) as z:  # type: ignore[arg-type]
        return {i.filename: z.read(i) for i in z.infolist() if not i.is_dir()}


def program_bytes(zip_source) -> bytes | None:
    try:
        with zipfile.ZipFile(zip_source) as z:
            return z.read(PROGRAM_MEMBER)
    except (KeyError, zipfile.BadZipFile, OSError):
        return None


# ---- the documents ------------------------------------------------------------------------------------------------


@dataclass
class DocDiff:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    patches: dict[str, list[str]] = field(default_factory=dict)       # unified diff lines per changed or added file
    added_lines: list[tuple[str, str]] = field(default_factory=list)  # (file, line) the candidate adds or changes


def diff_docs(base: dict[str, bytes], cand: dict[str, bytes]) -> DocDiff:
    d = DocDiff()
    for name in sorted(set(base) | set(cand)):
        old, new = base.get(name), cand.get(name)
        if old == new:
            continue
        if old is None:
            d.added.append(name)
        elif new is None:
            d.removed.append(name)
        else:
            d.changed.append(name)
        a = (old or b"").decode("utf-8", "replace").splitlines()
        b = (new or b"").decode("utf-8", "replace").splitlines()
        patch = list(difflib.unified_diff(a, b, f"pinned/{name}", f"candidate/{name}", lineterm="", n=1))
        d.patches[name] = patch
        d.added_lines += [(name, line[1:]) for line in patch if line.startswith("+") and not line.startswith("+++")]
    return d


# what a document says when it tells the agent to change itself or install something
SELF_CHANGE = re.compile(
    r"self-?update|libtv\s+(?:update|upgrade)\b|install-libtv-cli|rm\s+-rf|\bunzip\b|\bcurl\b|\biwr\b|\birm\b"
    r"|Invoke-WebRequest|\bwget\b|修订(?:本)?\s*skill|更新\s*skill|升级\s*skill|下载.{0,12}(?:skill|zip)"
    r"|download.{0,20}(?:skill|zip|package)",
    re.I,
)
GENERATION_WORDS = re.compile(r"--run\b|--count\b|\blibtv\s+(?:[\w-]+\s+)*?(?:storyboard|shortcut)\b", re.I)


def installer_channels(members: dict[str, bytes]) -> list[str]:
    """The version-channel ids the candidate's own installer and install guide name."""
    ids = []
    for name, data in members.items():
        if name.startswith("scripts/"):
            for m in re.finditer(r"getById\?id=(\d+)", data.decode("utf-8", "replace")):
                if m.group(1) not in ids:
                    ids.append(m.group(1))
    return ids


# ---- paid runs ----------------------------------------------------------------------------------------------------

GENERATING_PATH_WORDS = {"run", "generate", "storyboard", "shortcut", "render", "submit", "regenerate"}
GENERATING_FLAGS = {"--run", "--count", "--generate", "--regenerate", "--submit", "--render", "--batch"}


def listed_paid_commands(claude_md: str) -> tuple[list[list[str]], str] | None:
    """The LibTV commands CLAUDE.md names as needing the owner's yes, as token lists, plus that paragraph's text."""
    section = re.split(r"^## Paid generation needs .*, every run[ \t]*$", claude_md, maxsplit=1, flags=re.M)
    if len(section) < 2:
        return None
    body = section[1].split("\n## ", 1)[0]
    paragraph = next((p for p in body.split("\n\n") if "LibTV" in p and "libtv " in p), "")
    commands = []
    for span in re.findall(r"`(libtv [^`]+)`", paragraph):
        tokens = [t for t in span.split()[1:] if not t.startswith("<")]
        commands.append(tokens)
    return commands, paragraph


def _subsequence(needle: tuple[str, ...], hay: list[str]) -> bool:
    it = iter(hay)
    return all(word in it for word in needle)


def paid_candidates(cmd_diff: CommandDiff) -> list[tuple[tuple[str, ...], str | None]]:
    """(command path, option or None) for each added command or option that can start a generation."""
    found: list[tuple[tuple[str, ...], str | None]] = []
    for path in cmd_diff.added:
        if GENERATING_PATH_WORDS & set(path):
            found.append((path, None))
    for path, flag in cmd_diff.options_added:
        if flag in GENERATING_FLAGS:
            found.append((path, flag))
    return found


def is_listed(candidate: tuple[tuple[str, ...], str | None], listed: tuple[list[list[str]], str]) -> bool:
    commands, paragraph = listed
    path, flag = candidate
    for tokens in commands:
        if _subsequence(path, tokens):
            if flag is None or flag in tokens:
                return True
            if re.search(rf"\b{re.escape(flag.lstrip('-'))}\b", paragraph):
                return True
    return False
