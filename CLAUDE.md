# CLAUDE.md

<!-- Filling this in: CLAUDE-TEMPLATE-NOTES.md, beside this file. Delete the notes when done. -->

Orients a Claude session at the start of every task in this repo, and carries only what is
true for **every** task — depth lives in the skill named below and loads on demand. The other
two owners are [`README.md`](README.md) (a human at a shell: install, run, configuration,
what the tools do) and [`architecture.md`](architecture.md) (whoever is about to change the
code: modules, boundaries, invariants); what was decided and why lives in
[`openspec/ideas.md`](openspec/ideas.md). None of the three is restated here — read the one
you need when you need it.
Per-model advice, when the model changes: [`docs/MODEL-ADVICE.md`](docs/MODEL-ADVICE.md).

> **Just bootstrapped via `/alemax:new-project`?** Run `/opsx:propose` to spec out your first change.
> *(This nudge can be removed once you've made your first commit beyond bootstrap.)*

## 1. What this project is

<TBD>

<two sentences: what it produces, for whom, and what it deliberately does not do>

- **Stack:** python · **Run:** `<the one command — e.g. uv run docker-picamera …>` ·
  **Layout and invariants:** `architecture.md` — read it before adding a module, a stage, or a
  dependency between packages; do not re-derive it from the tree, and do not summarise it here.
- <domain doc, if any> — read it before <moment> *(e.g. `MODEL.md` before writing a record; delete this line if there is none)*

## 2. Where the data lives — and who owns it

Resolve every path from its variable. Never hard-code one, never infer it from a default, and
if a variable is unset, **stop and ask** — do not guess a location and write there.

| tree | resolve it from | nature |
| --- | --- | --- |
| **code** | the session's repo root | private, on GitHub. **Sole owner** — refactor, rename, delete freely |
| **data** | `<PROJECT>_<TIER>_DIR` — one variable per tier, catalogued in README § Configuration | private, local. **Sole owner** — <rebuild cost per tier> |
| **shared** | `<SHARED_ROOT>/docker-picamera/` | private, and **shared** — write **only** inside our own folder; outside it, report, never fix |

## 3. The skills this project built

Everything this project does is driven through its own skills, each a thin wrapper around one
command. The command is documented for humans in `README.md`; this is the routing, not a manual.

| skill | what it is for |
| --- | --- |
| `/<prefix>:<action>` | <one line — the job it does, not how> |

<pipeline order, if one exists: `/<prefix>:<first>` → `/<prefix>:<second>`, with the one reason a step must precede another>

## 4. What this project produces for others

<the contract it publishes — a corpus, a library, an image, a CRD — where it lands (`<SHARED_ROOT>/docker-picamera/`, a tag, a registry), and the skill that produces it. Or: "nothing — a leaf.">

## 5. What this project reads

<the bundle, wiki, library or upstream it consumes, and the one document to read first — e.g. `<bundle>/wiki/vault_schema.md` before querying or writing that bundle; a generated index is a manifest, not a read path. Or: "only its own tree.">

## 6. Task routing — everything else

| when you're working on… | invoke |
| --- | --- |
| <subsystem> | `/<prefix>:<action>` |
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
