# Garden Keeper — documentation

Everything known about this project, and — more importantly — **where each kind of knowledge
lives canonically**. A future improvement must not have to guess which file wins.

| Looking for | Read | Canonical? |
|---|---|---|
| What the project is, who it serves, what is in and out of scope | [`PROJECT.md`](PROJECT.md) | yes |
| How the pieces fit: registry, app, crons, Telegram, exposure | [`ARCHITECTURE.md`](ARCHITECTURE.md) | yes |
| How to run, restart, back up, test in a sandbox, fix it at 22:00 | [`OPERATIONS.md`](OPERATIONS.md) | yes |
| How this project proves things (reviewers, evidence, sandboxes) | [`VERIFICATION.md`](VERIFICATION.md) | yes |
| Every command the registry CLI takes | [`CLI.md`](CLI.md) | yes (generated) |
| Why a design decision was taken | [`DECISIONS.md`](DECISIONS.md) | yes |
| Whether the local System One model (Von) is worth using here | [`VON-EVALUATION.md`](VON-EVALUATION.md) | yes |
| What changed, when, and what broke on the way | [`HISTORY.md`](HISTORY.md) | yes |
| How the **agent** should behave in the garden | [`../skills/garden-management/SKILL.md`](../skills/garden-management/SKILL.md) | yes |
| Plant, prune, feed and pond reference knowledge | [`../skills/garden-management/references/`](../skills/garden-management/references/) | yes |
| The app's endpoints and UI behaviour | [`../garden/app/README.md`](../garden/app/README.md) | yes |
| The data directory as a place on disk (layout, filings, exports) | [`../garden/README.md`](../garden/README.md) | yes |
| The data model as the agent must understand it | [`../skills/garden-management/references/data-model.md`](../skills/garden-management/references/data-model.md) | yes |
| The tables and columns as they really are | [`../garden/schema.sql`](../garden/schema.sql) (and the live `garden/garden.db`) | yes |
| The agent's own persona and standing orders | [`../SOUL.md`](../SOUL.md) | yes |
| What the agent has learned about this user and this garden | *(private — not part of this export)* | — |
| The garden itself — plants, photos, tasks, treatments, journal | `garden/garden.db` (query it; never copy it) | yes |

## The rule that keeps this from rotting

**One fact, one canonical home.** Everything else points at it.

- Behaviour the *agent* must follow → the skill and its references (never here).
- Endpoints and UI behaviour → the app README.
- Schema → `schema.sql`.
- System knowledge (how to operate, verify and extend the thing) → these docs.
- What happened → `HISTORY.md`, and the commit log (`git log`), which must never contradict it.

When a change makes one of these stale, the change is not finished. The docs are updated in the
same commit as the behaviour — that is the only reason they are worth having.

## Keeping this current

```bash
cd /root/.hermes/profiles/garden
git log --oneline                 # what actually happened, newest first
garden/scripts/garden.py --help   # the CLI's real surface
python docs/tools/regen-cli.py    # rewrite CLI.md from the CLI itself
```

Anything a document asserts about the running system should be checkable with a command. If you
cannot check it, say so in the document rather than phrasing it as fact.


## About this public copy

This is an export of a working private project. A publish step copies the tracked
tree, drops what is not the project — the agent's private memory, and the registry, photographs and
cron output (which were never committed in the first place) — and replaces the private network
details with `<tailnet-host>` and `<lan-host>`. Commit hashes quoted in `HISTORY.md`,
`OPERATIONS.md` and `DECISIONS.md` refer to the private development repository; this export is a
single initial commit, so they will not resolve here.
