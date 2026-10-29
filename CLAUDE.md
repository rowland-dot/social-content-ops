# social-content-ops

A changed copy of ZJU-REAL/Easel (Apache License 2.0, see `LICENSE`), run in WSL Ubuntu. Easel's own files stay as upstream ships them, except where a booked issue allows a change.

This project is public. The owner's and the team's own working material (the full project rules, specs, plans, reports, research, agent guides, issue records, the team's photo-scene package and the list of who each role is) is in a private folder, `work/`, which has its own git repository and is ignored by this one. An agent on the owner's PC reads that folder's rules file right here:

@work/CLAUDE.md

If `work/` is not there (a fresh copy of the public project), this copy holds only the engine: say so plainly and carry on with what the engine can do. Nothing in the engine needs `work/` to start; the few places that read it say so when it is missing.

The private rules file is kept word for word, so the paths it writes (`docs/specs/...`, `docs/plans/...`, `docs/agents/...`, `.scratch/...`, `TODOS.md`, `archive/jimeng-dreamina/`, `brand-files/...`) mean the same path inside `work/`; the team's photo-scene package is `work/team-packages/xhs-reference-visual/`. Easel's own documentation in `docs/` (the files upstream ships) is not moved.

## Who is who

Tracked files name people by role, never by name: "the owner", "the new-media teammate", "a teammate". `work/roles.md` says which person each role is. Read it to resolve a role to a person (for example, which DingTalk chat belongs to the new-media teammate). That file stays in `work/` and is never copied into a tracked file.

## Three standing rules for every tracked file

Every push to this project is public, so these hold for all work, not for one clean-up. The issue that settled them is issue 136 (kept in `work/.scratch/easel-setup-gaps/issues/`).

1. **Rules only.** Skill text states rules and nothing else: a skill, a shared script, a skill's tests and the profile template state each rule plainly, with no names and no quotes. A rule keeps a pointer to the issue that records the ruling ("issue 91"), never the words.
2. **Names are roles; places are placeholders.** Write "the owner" or "the new-media teammate", never a person's name or user name. Write `C:\Users\<user>` and `/mnt/c/Users/<user>`, never a real user folder. DingTalk staff, user and union ids, phone numbers and keys never appear; the real values live only in git-ignored local settings.
3. **Quotes are softened.** Where a ruling is quoted in a tracked document, profane words are replaced with plain ones and the meaning is unchanged.

## Where things are

- The engineering skills look up `docs/agents/issue-tracker.md`, `triage-labels.md` and `domain.md`. Issue records live in `work/.scratch/<feature>/issues/`.
- Easel's own documentation is in `docs/` (upstream's files). Specs, plans, reports and research are in `work/docs/`.
