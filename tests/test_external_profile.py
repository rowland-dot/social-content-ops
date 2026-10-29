"""A profile that lives outside Easel's ``profiles`` folder (issue 75).

The git-ignored setting ``EASEL_PROFILE_DIRS`` maps a profile name to an absolute folder, e.g.
``northwind=/mnt/c/Users/<user>/OneDrive/Client KB/brands/northwind/profile``. Entries are
separated by ``;``. These tests map ``northwind`` to a temporary folder with no
``profiles/northwind`` present.
"""
from __future__ import annotations

import asyncio
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "web"))

import web.app as web  # noqa: E402
import easel.persona as persona  # noqa: E402
from easel.commands import skill as skill_command  # noqa: E402
from easel.harnesses.base import RunRequest  # noqa: E402
from easel.harnesses.codex import CodexAdapter  # noqa: E402
from easel.harnesses.permissions import can_auto_approve  # noqa: E402
from easel.harnesses.workspace import harness_instructions  # noqa: E402

FILE_CHANGE = "item/fileChange/requestApproval"
LOCAL = "http://127.0.0.1:7860"


@pytest.fixture
def mapped(tmp_path, monkeypatch):
    """northwind mapped to a temporary folder; no profiles/northwind; other brands stay local."""
    local = tmp_path / "profiles"
    (local / "orchard").mkdir(parents=True)
    (local / "orchard" / "identity.md").write_text("orchard-identity", encoding="utf-8")
    external = tmp_path / "Client KB" / "brands" / "northwind" / "profile"
    external.mkdir(parents=True)
    (external / "identity.md").write_text("northwind-identity-marker", encoding="utf-8")
    (external / "memory.md").write_text("northwind-memory", encoding="utf-8")
    monkeypatch.setattr(persona, "PROFILES_DIR", local)
    monkeypatch.setattr(web, "PROFILES_DIR", local)
    monkeypatch.setattr(persona, "ENV_FILE", tmp_path / "no-such.env", raising=False)
    monkeypatch.setenv("EASEL_PROFILE_DIRS", f"northwind={external}")
    return external


def client():
    return TestClient(web.app, base_url=LOCAL, client=("127.0.0.1", 51234),
                      headers={"Origin": LOCAL})


# --- profile helper: one resolver -------------------------------------------------------

def test_mapped_profile_is_found_and_listed_once(mapped):
    assert persona.profile_exists("northwind")
    assert persona.list_personas() == ["northwind", "orchard"]
    assert persona.load_profile_text("northwind").startswith("northwind-identity-marker")
    assert persona.load_profile_text("orchard") == "orchard-identity"


def test_mapped_profile_listed_once_even_if_a_local_copy_also_exists(mapped):
    (persona.PROFILES_DIR / "northwind").mkdir()
    (persona.PROFILES_DIR / "northwind" / "identity.md").write_text("stale-local-copy", encoding="utf-8")
    assert persona.list_personas().count("northwind") == 1
    assert "stale-local-copy" not in persona.load_profile_text("northwind")


def test_setting_is_also_read_from_the_env_file(mapped, monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(f"EASEL_PROFILE_DIRS=northwind={mapped}\n", encoding="utf-8")
    monkeypatch.delenv("EASEL_PROFILE_DIRS")
    monkeypatch.setattr(persona, "ENV_FILE", env_file)
    assert persona.profile_exists("northwind")


def test_two_mappings_separated_by_semicolon(mapped, tmp_path, monkeypatch):
    second = tmp_path / "other-profile"
    second.mkdir()
    monkeypatch.setenv("EASEL_PROFILE_DIRS", f"northwind={mapped};second={second}")
    assert persona.list_personas() == ["northwind", "orchard", "second"]


def test_unmapped_profiles_behave_as_before(mapped, monkeypatch):
    monkeypatch.delenv("EASEL_PROFILE_DIRS")
    assert persona.list_personas() == ["orchard"]
    assert not persona.profile_exists("northwind")
    assert persona.persona_prefix("orchard") == (
        "我当前使用的画像是「orchard」。"
        "本会话的账号长期记忆仅使用 profiles/orchard/memory.md，"
        "不要使用工作区全局 MEMORY.md 作为账号记忆。")


def test_mapped_folder_that_does_not_exist_is_reported_and_not_created(mapped, tmp_path, monkeypatch):
    missing = tmp_path / "gone" / "profile"
    monkeypatch.setenv("EASEL_PROFILE_DIRS", f"northwind={missing}")
    assert not persona.profile_exists("northwind")
    assert "northwind" not in persona.list_personas()
    assert persona.load_profile_text("northwind") == ""
    assert str(missing) in persona.profile_problem("northwind")
    assert persona.profile_problem("orchard") == ""
    assert not missing.exists() and not missing.parent.exists()


def test_per_turn_profile_line_names_the_real_absolute_folder(mapped):
    prefix = persona.persona_prefix("northwind")
    assert f"{mapped}/memory.md" in prefix.replace("\\", "/")
    assert "profiles/northwind/memory.md" not in prefix
    assert "profiles/<画像>/" in prefix  # says this folder overrides the skills' path
    assert "我当前使用的画像是「northwind」。" in prefix


def test_cli_and_skill_command_look_the_profile_up_through_the_resolver(mapped, capsys):
    assert skill_command._check_profile_exists("northwind") is True
    assert skill_command._check_profile_exists("nope") is False
    assert "orchard" in capsys.readouterr().err  # listing of available profiles still works


def test_skill_command_reports_a_mapped_folder_that_is_missing(mapped, tmp_path, monkeypatch, capsys):
    missing = tmp_path / "gone"
    monkeypatch.setenv("EASEL_PROFILE_DIRS", f"northwind={missing}")
    assert skill_command._check_profile_exists("northwind") is False
    assert str(missing) in capsys.readouterr().err


# --- web app ------------------------------------------------------------------------------

def test_web_lists_reads_and_shows_files_of_a_mapped_profile(mapped):
    c = client()
    rows = c.get("/api/personas").json()
    assert [row["name"] for row in rows] == ["northwind", "orchard"]
    assert rows[0]["description"] == "northwind-identity-marker"
    assert c.get("/api/persona/northwind").json()["content"].startswith("northwind-identity-marker")
    files = {f["filename"]: f["content"] for f in c.get("/api/persona/northwind/files").json()["files"]}
    assert files["memory.md"] == "northwind-memory"


def test_web_save_writes_into_the_mapped_folder(mapped):
    response = client().put("/api/persona/northwind/file",
                            json={"filename": "memory.md", "content": "new-memory"})
    assert response.status_code == 200
    assert (mapped / "memory.md").read_text(encoding="utf-8") == "new-memory"
    assert not (persona.PROFILES_DIR / "northwind").exists()


@pytest.mark.parametrize("filename", ["../evil.md", "..\\evil.md", ".hidden.md", "notes.txt", "a/b.md"])
def test_web_save_refuses_bad_file_names_for_a_mapped_profile(mapped, filename):
    response = client().put("/api/persona/northwind/file",
                            json={"filename": filename, "content": "x"})
    assert response.status_code in (400, 403, 404)
    assert not (mapped.parent / "evil.md").exists()


def test_web_save_refuses_a_link_inside_the_mapped_folder_that_points_elsewhere(mapped, tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("untouched", encoding="utf-8")
    try:
        (mapped / "escape.md").symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable")
    response = client().put("/api/persona/northwind/file",
                            json={"filename": "escape.md", "content": "overwritten"})
    assert response.status_code == 403
    assert outside.read_text(encoding="utf-8") == "untouched"


def test_web_delete_of_a_mapped_profile_is_refused_and_leaves_the_folder(mapped):
    response = client().delete("/api/persona/northwind")
    assert response.status_code in (403, 409)
    assert "知识库" in response.text or "映射" in response.text
    assert (mapped / "identity.md").read_text(encoding="utf-8") == "northwind-identity-marker"
    assert (mapped / "memory.md").is_file()


def test_web_delete_of_a_local_profile_still_works(mapped):
    assert client().delete("/api/persona/orchard").status_code == 200
    assert not (persona.PROFILES_DIR / "orchard").exists()


def test_web_create_with_a_mapped_name_is_refused(mapped):
    response = client().post("/api/profile/build", json={"name": "northwind", "form": {}})
    assert response.status_code == 409
    assert not (persona.PROFILES_DIR / "northwind").exists()


def test_web_missing_mapped_folder_reads_as_not_found(mapped, tmp_path, monkeypatch):
    monkeypatch.setenv("EASEL_PROFILE_DIRS", f"northwind={tmp_path / 'gone'}")
    response = client().get("/api/persona/northwind/files")
    assert response.status_code == 404
    assert not (tmp_path / "gone").exists()


# --- agent: instructions, Codex write area, automatic approval -----------------------------

def request_in(root: Path, external: Path) -> RunRequest:
    (root / "agents" / "workspace").mkdir(parents=True, exist_ok=True)
    (root / "agents" / "workspace" / "AGENTS.md").write_text("共享业务规则", encoding="utf-8")
    return RunRequest("hello", root, {"EASEL_PROFILE_DIRS": f"northwind={external}"},
                      codex_auto_approve=True)


def test_workspace_instructions_list_mapped_folders_and_say_they_override_skill_paths(mapped, tmp_path):
    instructions = harness_instructions(request_in(tmp_path / "project", mapped))
    assert str(mapped) in instructions
    assert "northwind" in instructions
    assert "profiles/<画像>/" in instructions
    assert "覆盖" in instructions


def test_workspace_instructions_without_a_mapping_name_no_extra_folder(tmp_path):
    root = tmp_path / "project"
    request = replace(request_in(root, tmp_path / "x"), env={})
    assert "profiles/<画像>/" not in harness_instructions(request)


def test_auto_approval_accepts_a_mapped_folder_and_refuses_an_unrelated_outside_path(mapped, tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    request = request_in(root, mapped)
    assert can_auto_approve(FILE_CHANGE, {"grantRoot": str(mapped)}, request)
    assert can_auto_approve(FILE_CHANGE, {"grantRoot": str(mapped / "memory.md")}, request)
    assert can_auto_approve(FILE_CHANGE, {"grantRoot": str(root / "outputs")}, request)
    outside = tmp_path / "unrelated"
    outside.mkdir()
    assert not can_auto_approve(FILE_CHANGE, {"grantRoot": str(outside)}, request)
    assert not can_auto_approve(FILE_CHANGE, {"grantRoot": str(mapped.parent)}, request)
    assert not can_auto_approve(FILE_CHANGE, {"grantRoot": str(mapped)},
                                replace(request, sandbox="read-only"))


def test_codex_writable_area_is_the_project_root_plus_mapped_folders_only(mapped, tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    request = replace(request_in(root, mapped), sandbox="workspace-write",
                      command=(sys.executable, "-c", "pass"))
    sent: list[tuple[str, dict]] = []

    class FakeRpc:
        initialized = True
        native_id = "thread-1"
        notify = None

        async def call(self, method, params, timeout=None):
            sent.append((method, params))
            if method == "turn/start":
                raise RuntimeError("stop after turn/start")
            return {"thread": {"id": "thread-1"}}

        async def send(self, message):
            pass

    class FakeConnection:
        async def __aenter__(self):
            return FakeRpc()

        async def __aexit__(self, *exc):
            return False

    import easel.harnesses.codex as codex_module
    monkeypatch.setattr(codex_module, "connection", lambda *a, **k: FakeConnection())
    with pytest.raises(RuntimeError, match="stop after turn/start"):
        asyncio.run(CodexAdapter().run(request, lambda *a: None, None, lambda identifier: None))
    policy = next(params for method, params in sent if method == "turn/start")["sandboxPolicy"]
    assert policy["type"] == "workspaceWrite"
    assert policy["writableRoots"] == [str(root), str(mapped)]
