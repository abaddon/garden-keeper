# Garden Keeper

An agent that keeps a real garden's records and hands back a plan. Three pieces, one SQLite file:

| Piece | What it does |
|---|---|
| **`garden/scripts/garden.py`** | The registry CLI — the *only* writer of the data. Stdlib only, no dependencies, no framework. |
| **`garden/app/`** | A phone-first capture app (FastAPI + vanilla JS, no build step): photograph a plant, send today's pictures for a health re-check, browse the garden, tick jobs off with a note about what changed. |
| **`scripts/` and the profile files** | The agent around it: cron jobs that build a weekend plan and a monthly review from the registry, an intake worker that reads new captures, and the persona (`SOUL.md`) and config (`config.yaml`, `profile.yaml`) that wire it to [Hermes Agent](https://hermes-agent.nousresearch.com). |

The whole point is that the *data* is the agent's memory: plants, photos, tasks, observations,
treatments, pond readings, and a journal. Advice is generated from that record, never from a generic
garden calendar — and anything the record does not know is asked, not guessed.

## The shape of it

```
garden/garden.db        the registry (12 tables: plants, photos, tasks, observations, treatments,
                        ponds, pond_readings, rules, advice, weather, journal, intakes)
garden/photos/          the pictures themselves, filed by date and plant
garden/scripts/garden.py  plant/photo/task/obs/treat/pond/rule/advice/brief/needs/stats/search/export
garden/app/             the capture app (server.py + web/), systemd-friendly
scripts/                the cron worker scripts (weekend brief, monthly review, intake queue)
docs/                   how it is built, run, verified and why — start at docs/README.md
skills/garden-management/  the agent's working knowledge: UK calendar, pruning groups, pond care,
                        indoor-vs-outdoor rules, plant categories, intake procedure
```

## Trying it without an agent

The registry CLI needs nothing but Python 3.11+:

```bash
cd garden/scripts
python3 garden.py init                                   # creates garden/garden.db
python3 garden.py plant add --name "Fig" --category fruit --placement outdoor
python3 garden.py task add --subject plant:1 --title "Water deeply" --category water --due 2026-06-01
python3 garden.py needs --days 7                         # everything waiting on the user, one definition
python3 garden.py brief --mode weekend                   # the digest the agent writes the plan from
python3 garden.py --help
```

The app needs `fastapi`, `uvicorn`, `pillow` (plus `pillow-heif` if your phone sends HEIC):

```bash
python3 garden/app/server.py          # serves on 127.0.0.1:9123; see garden/app/README.md
```

It is built to sit behind `tailscale serve` on a private tailnet, so the phone reaches it over the
tailnet with identity, and no login is needed. That is the deployment it was written for; a plain
reverse proxy with the token in `garden/app/app.env` works too.

## Running it as an agent

The agent layer expects [Hermes Agent](https://hermes-agent.nousresearch.com): the profile directory
in this repository is exactly what Hermes loads (persona in `SOUL.md`, settings in `config.yaml` and
`profile.yaml`, skills under `skills/`, cron jobs created with `hermes -p <profile> cron …`, delivery
to a Telegram bot). `docs/ARCHITECTURE.md` describes the five pieces and how they are wired;
`docs/OPERATIONS.md` has the runnable commands, including the sandbox recipe used to test changes
without touching live data.

## What this copy is

A public export of a working private project. The owner's personal data is not here: their notes
about the garden and themselves, the registry itself, the photographs, the cron output and the
secret files are all excluded, and placeholders replace the private network details (`<tailnet-host>`,
`<lan-host>`). Commit hashes mentioned in `docs/HISTORY.md` refer to the private development
repository, which is where the full trail of what broke and why lives — this export is a single
initial commit.

No licence has been chosen for this code yet, so all rights are reserved by default. If you want to
reuse any of it, ask.

## Where to read next

| Looking for | Read |
|---|---|
| What the project is, and what is in and out of scope | `docs/PROJECT.md` |
| How the pieces fit and how it is exposed | `docs/ARCHITECTURE.md` |
| How to run, restart, back up, sandbox-test it | `docs/OPERATIONS.md` |
| How changes get proven here (adversarial reviewers, evidence) | `docs/VERIFICATION.md` |
| The whole CLI surface | `docs/CLI.md` |
| Why each design decision was taken, and what it cost | `docs/DECISIONS.md` |
| What was built, in order, and what broke on the way | `docs/HISTORY.md` |
| The map of every kind of knowledge | `docs/README.md` |
| Whether the local System One model is worth using here | `docs/VON-EVALUATION.md` |
