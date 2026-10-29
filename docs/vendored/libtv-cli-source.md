# Where the libtv-cli skill and the libtv program come from

Issue: `.scratch/easel-setup-gaps/issues/32-libtv-agent-skill-in-easel.md`. Checked 2026-10-14.

## The skill (vendored)

| Item | Value |
|---|---|
| Files in this repo | `skills/builtin/libtv-cli/references/vendor/`, LibTV's own 44-file package with no change. `skills/builtin/libtv-cli/SKILL.md` is Easel's wrapper: it carries `layer: produce` and a Chinese trigger description, which Easel's skill-contract check requires and LibTV's header lacks, and it tells the agent to read the vendor files before any `libtv` command |
| Version | 1.1.3, the version LibTV's version channel names (below) |
| Source | `https://liblibai-web-static.liblib.cloud/cli/1.1.3/libtv-cli-skill.zip`, 91,299 bytes, last modified 2026-08-09 |
| sha256 of that zip | `b3277d4a07bb1c28442e12db3023bdd9634b64ab23f26e3bf7ad9bf2d3c84072` |
| Per-file sha256 | `docs/vendored/libtv-cli-1.1.3-files.sha256`, one line per file of the zip (44 lines) |
| Check | `python3 ops/wsl-setup/libtv-vendor-compare.py docs/vendored/libtv-cli-1.1.3-files.sha256 skills/builtin/libtv-cli/references/vendor` reports the same 44 files byte for byte (exit 0). Given the downloaded zip as its first argument instead, it does the same comparison against the package itself. `tests/test_libtv_cli_skill.py` runs both |
| Licence | None is published with it: no licence file |

Do not edit anything under `skills/builtin/libtv-cli/references/vendor/`; the wrapper `SKILL.md` is ours to edit. LibTV's own text tells the agent to update the skill, to download a newer package and to revise the files; the wrapper says Easel does none of that by itself.

## The program (not in git)

| Item | Value |
|---|---|
| Installed by | `bash ops/wsl-setup/setup.sh --only libtv`, never by LibTV's own installer (`install-libtv-cli.sh`) |
| Download address | `https://liblibai-web-static.liblib.cloud/cli/1.1.3/libtv-linux-x64.zip`, a versioned address, 28,385,926 bytes, last modified 2026-08-09 |
| sha256 of that zip | `cf86f462c5aed60f95dca978cc91ece98c60bcfa27337da008ad59953c3ea7da` (identical on two fetches); the setup step checks it before anything is unpacked |
| The program inside | one file, `libtv-linux-x64/libtv`, 77,667,686 bytes, ELF x86-64, needs glibc 2.28 or newer; sha256 `e79ad52170556b44e957174f880c8a69057f668ddd0b9a4011524cac072c31f3`, which the setup check re-reads every run |
| Where it goes | `/usr/local/bin/libtv`, which the gateway's own PATH includes. LibTV's installer would use `~/.libtv`, append a PATH line to a shell profile and take whatever `latest` names; none of that is done |
| Source and licence | Closed program: no source, no licence |
| Login | By account, not by key: `libtv login web` serves a callback on `127.0.0.1` inside WSL and the owner approves on LibTV's page in his Windows browser. The login is stored in `credentials.json` under `LIBTV_CONFIG_DIR` (default `/root/.libtv/credentials.json`) for the user the gateway runs as. It is a full account session, in plain text, and cannot be revoked separately from the account. The callback address carries the token, so it also appears in the browser's history |
| Reporting | By default the program reports every command (its command line with prompt text, exit code, up to five error lines) to LibTV. The owner's ruling, 2026-10-14: turn it off. The setup step puts `LIBTV_DISABLE_REPORT=1` in the gateway's own environment (the OpenClaw config's `env.vars`), not in a shell profile |

## What was seen on the machine (2026-10-14)

- `libtv --version` prints `1.1.3`, and it runs with the network cut off, so it does not need LibTV's server.
- The first call of the program creates nothing in `~/.libtv`; that folder appears only at login.
- The login file `credentials.json` holds five fields: `usertoken`, `useruuid`, `webid`, `savedAt` and `activeAccountId`.
- None of the program's `--help` texts (the top level and 32 subcommands) mention credits, balance, price or cost. After login, `libtv account info` shows the user, the active account (with a `memberAccount` entry giving the member level) and the team, and no credit figure either. Where to see the credit balance is not known from the CLI.
- `openclaw config set` writes the `LIBTV_DISABLE_REPORT` setting into the config's env block and OpenClaw reloads its config in place; the running gateway's own process environment (as `/proc` shows it) does not change, so the setting is proved from inside the agent's shell, not from there.

## Which version is current

LibTV's version channel is `https://api2.liblib.art/api/www/landing-activities/getById?id=240`. On 2026-10-14 it answered version 1.1.3 with the 1.1.3 skill package and installers. `cli/latest/manifest.json` on the file server still says 1.0.2, but that is the pointer only the old 1.0.x installer reads. The folders 1.1.0 to 1.1.3 exist on the file server; 1.1.4 and later answered 404.

## Moving to a newer version

Download the new package and program, read them as issue 32's probe did, then change the two pins in `ops/wsl-setup/checks.sh`, the address in `ops/wsl-setup/setup.sh`, the vendored folder, `libtv-cli-1.1.3-files.sha256` (renamed to the new version) and this note together, as a booked issue. The update gate in issue 37 decides what is shown to the owner before he approves one.

The gate is `ops/libtv-update-gate/libtv_gate.py`. It reads LibTV's public answers with no login, never runs the `libtv` program and never changes a pin. It keeps its own files, outside git, in `.scratch/libtv-update-gate/`.

| Command (from the repo root) | What it does |
|---|---|
| `python ops/libtv-update-gate/libtv_gate.py check` | The on-demand check: the version channel against the pin, folders above the pin, LibTV's notice channel, the canary route that would show a retirement, whether the pinned files changed, and the run-time settings (models, shortcut scenes, camera controls, voices; the 1.1.3 program reads only the first two). `--json` for a machine-readable form, `--deep` to re-hash the pinned package. Installs nothing |
| `python ops/libtv-update-gate/libtv_gate.py candidate <version>` | Downloads a newer version twice into the store and reports what it changes: document diff, command tree by full path, checksums, version strings found inside the program, and a paid-run section checked against the LibTV list in `CLAUDE.md`. Nothing is run |
| `python ops/libtv-update-gate/libtv_gate.py book <version>` | After the owner's yes through the question tool: writes a ready-filled issue (`Status: needs-triage`) in `.scratch/easel-setup-gaps/issues/`. Moves no pin |
| `python ops/libtv-update-gate/libtv_gate.py decline <version>` | After the owner's no: that version is not offered again unless the channel moves past it |
| `python ops/libtv-update-gate/libtv_gate.py ack-settings` | After the owner has seen a run-time settings change: the settings as reported become the snapshot later checks compare with |
| `python ops/libtv-update-gate/libtv_gate.py keep-pin` | Keeps a checked copy of the pinned program package in the store, so a rollback runs the setup step from it (`LIBTV_ZIP_FILE=<copy> bash ops/wsl-setup/setup.sh --only libtv`) even if LibTV removes old folders |
| `python ops/libtv-update-gate/libtv_gate.py hook` | The note a Claude Code session gets when it opens in this project (the project hook in `.claude/settings.json`) |

The 1.1.3 program itself carries no update check and no self-update. A forced upgrade from LibTV would arrive as a success with no data (the old skill's retirement did), which the program passes through silently, so the gate watches for it from outside.
