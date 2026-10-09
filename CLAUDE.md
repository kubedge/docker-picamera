# CLAUDE.md

Orients a Claude session at the start of every task in this repo, and carries only what is
true for **every** task — depth lives in the skill named below and loads on demand. The other
two owners are [`README.md`](README.md) (a human at a shell: install, run, configuration,
what the tools do) and [`architecture.md`](architecture.md) (whoever is about to change the
code: modules, boundaries, invariants); what was decided and why lives in
[`openspec/ideas.md`](openspec/ideas.md). None of the three is restated here — read the one
you need when you need it.
Per-model advice, when the model changes: [`docs/MODEL-ADVICE.md`](docs/MODEL-ADVICE.md).

## 1. What this project is

An authenticated MJPEG stream of a Raspberry Pi camera, shipped as the arm64 image
`kubedge1/picamera` and the Helm chart `charts/picamera` for Kubernetes camera nodes. It
streams and reports health; it does not record, transcode, or serve more than one camera.

- **Stack:** python · **Run:** `AUTH_PASSWORD=… ./run.sh` on a Pi; `uv run pytest` anywhere ·
  **Layout and invariants:** `architecture.md` — read it before adding a module, a stage, or a
  dependency between packages; do not re-derive it from the tree, and do not summarise it here.

## 2. Where the data lives — and who owns it

Resolve every path from its variable. Never hard-code one, never infer it from a default, and
if a variable is unset, **stop and ask** — do not guess a location and write there.

| tree | resolve it from | nature |
| --- | --- | --- |
| **code** | the session's repo root | private, on GitHub. **Sole owner** — refactor, rename, delete freely |

No data tree and no shared folder: the service holds frames in memory only.

## 3. The skills this project built

None yet. Every command is in `README.md` § Run and § Development.

## 4. What this project produces for others

The image `kubedge1/picamera` (Docker Hub, `linux/arm64`), pushed by hand with
`./build.sh --push` (CI only builds it), and the chart `charts/picamera`.
Their contract is `openspec/specs/` (`camera-streaming`, `container-image`, `helm-deployment`).

## 5. What this project reads

Only its own tree. On the device, picamera2/libcamera come from the Raspberry Pi apt archive.

## 6. Task routing — everything else

| when you're working on… | invoke |
| --- | --- |
| the streaming code, the image or the chart | read `architecture.md` first, then `/opsx:propose` |
| a delivery named in `.local/HANDOFF.md` | `/alemax:complete-update` |

## 7. How we code and spec here — with skills

- `/opsx:propose` → `/opsx:apply` → `/opsx:archive` for anything you would think about for
  more than five minutes before coding. Specs in `openspec/specs/`, in-flight work in
  `openspec/changes/`. This project is its own upstream: changes land here, by PR.
- `/alemax:front-burner` at session start, `/alemax:back-burner` at session end.
- `/alemax:feedback` the moment something bites — a gotcha goes to the skill of the thing that
  bit, or there; **never into this file.**
- A line stays here only while it is true for every task. When it stops being that, move it
  down one level — to the owning skill, `architecture.md`, `README.md` or `openspec/ideas.md` —
  do not delete it.
- Secrets, the dev loop, CI: README § Secrets, § Development.

## Rules of engagement

1. A path comes from its variable; unset means stop and ask.
2. Write only inside what this repo owns (§ 2); outside it, report.
3. Work lands by PR — never a direct push to `main`, even solo.
4. No secret in any tracked file; Keychain holds the values, `.env.example` names the keys.
5. Open questions go to `openspec/ideas.md`; gotchas to `/alemax:feedback`.

Standing constraints from the fleet (claude-meta specs `sibling-access-practice`, `project-environments`) — each names what enforces it:

- A session acts only inside this repo — its root, `.local/`, its worktrees, scratch and toolchain dirs; another repo's checkout or data is reached through that repo's own session, `/alemax:send-msg <drive> <repo>[@env]`, never read or written from here · enforced by: `.claude/hooks/scope-guard.py` (PreToolUse; exit 2 names the address)
- Work in place in your own repo; a write into a sibling repo happens in a worktree of it that you created, never in its primary checkout · enforced by: scope-guard — a sibling's checkout is outside scope; `.claude/worktrees/**` and the `<repo>-claude-meta` delivery worktree are inside
- `.local/env` names this clone's environment, `prod` or `dev`; absent, a clone under `Applications/` is `prod`, anything else `dev`; a `dev` session never writes under a prod clone or the data it declares · enforced by: scope-guard (write-shaped calls under `*/Applications/*` and declared `data:` roots refused while `dev`); `alemax_addr.py self` prints the label
- Two clones of one repo differ only in `.claude/settings.local.json` and `.local/`; everything tracked is identical and reaches both by `git pull`, never by a second delivery · enforced by: none — `bin/reconcile-settings.py check` reports floor drift per clone; a clones-match check must carve those two paths out
- `.local/scope-allow.txt` (one path per line, written by the operator) is the only way scope widens; never loosen a permission rule, a hook or the sandbox to get past a refusal · enforced by: scope-guard reads only that file; `.local/` is gitignored, so a widening never ships
- A corpus, vault or wiki is entered through its schema file, never its `index.md` — an index is a manifest for a tool, not a read path and never an `@import`; and the startup set (this file, every `@import`, every `.claude/rules/*.md` with no `paths:`) stays inside the budget, because a file over 5,000 tokens comes back from a compaction as a path with no content · enforced by: `bin/claude-md-check.py` (pre-commit; refuses the import, reports the budget)
- A prod↔dev channel (`tracking-NN.md`, an inbox) is this project's own file; claude-meta ships none and never writes into it; a brief carries the next action and a path, not the work · enforced by: none — `alemax_addr.py queue` writes only the sender's own `.local/outbox/`
- Data trees are declared in `data.yaml` (`uv run --script bin/data-check.py`); a `dev` session never writes a `prod` one · enforced by: `bin/data-check.py` (pre-commit, staged) · `.claude/hooks/scope-guard.py` (PreToolUse while `dev`)
