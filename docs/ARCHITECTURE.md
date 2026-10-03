# Architecture

Five pieces, one database, one writer. Everything else is a view of that database.

```
        iPhone (Tailscale)                      desktop / phone Telegram
              │                                            │
              │ https://<tailnet-host>:9123/     │
              ▼                                            │
   tailscale serve ──► app/server.py (FastAPI)             │
                        │  · normalises photos to JPEG ≤2000px
                        │  · writes ONLY via the CLI        │
                        ▼                                   │
                 ┌──────────────────┐                       │
                 │  garden/garden.db│◄──── garden/scripts/garden.py  (THE writer)
                 │  12 tables       │            ▲  ▲  ▲
                 └──────────────────┘            │  │  └── agent sessions (skill-driven)
                        ▲                        │  └───── garden_intake.py   */3 min
                        │                        └──────── garden_weekend.py  Sat 07:00
                        │                                   garden_monthly.py  1st 08:00
                        └────────── agent reads, decides, records
```

## 1. The registry (`garden/garden.db`)

SQLite, one file, 12 tables: `plants, photos, tasks, observations, treatments, ponds, pond_readings,
rules, advice, weather, journal, intakes`. Schema of record: `garden/schema.sql`. Row counts and the
column list are always obtainable — never copy them into prose:

```bash
python - <<'EOF'
import sqlite3; c=sqlite3.connect('garden/garden.db')
for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
    print(t, [r[1] for r in c.execute(f"PRAGMA table_info({t})")])
EOF
```

Two shape rules that are easy to get wrong:

- `plants.notes` is not free prose: a lead line, one `Label: fact` line per care fact, a final
  `Unknown:` line, then one `DATED:` line per check, under ~700 characters.
- A task attached to a plant is titled as **the work**, not the plant ("Water deeply", not
  "Monstera"). Enforced in data, in the app's client, in the skill and in the cron prompts.

## 2. The CLI (`garden/scripts/garden.py`) — the single writer

Every write in the system goes through it, including the app's. That is what keeps one definition
of a plant, one of a task, and one of "waiting on the user". Full command reference: `CLI.md`.

Design rules that matter:

- **`--json` everywhere**; the app and the crons parse JSON, they never scrape text.
- **`safe_id()`**: an id that cannot be a row (non-numeric, ≤ 0, past SQLite's 64-bit range) is
  "nothing there" → 404 / exit 1, never a crash and never "try again", which is advice that can
  never work.
- **`needs --days N` is the single definition of what is waiting on the user**: open tasks (📌),
  observation follow-ups not yet done (🔍), treatments suggested but not applied (🌱). The app's
  home screen and the cron digests both read it, so the two cannot disagree.
- **`init` first** in cron scripts: an uninitialised registry yields the intake invitation, not an
  error.

## 3. The app (`garden/app/`)

FastAPI + three static files, no build step, no framework, no JS dependencies. Views share one
document: `#/` (what needs action), `#/in`, `#/out`, `#/all`, `#/plant/<id>`, `#/add`.

- **Auth**: Tailscale identity plus a token (`GARDEN_APP_TOKEN`); `POST` without it → 401. Tailnet
  only — nothing is exposed to the public internet.
- **Caching**: static `no-cache`, HTML `no-store`. This was learned the hard way: a stale `app.js`
  made a healthy app look dead (see `HISTORY.md`).
- **Uploads** are normalised server-side to JPEG ≤ 2000 px (HEIC included) and stored under
  `garden/photos/`; only files inside that directory are ever served.
- **Two upload paths**: a new plant (creates a `draft` plant + a pending `intakes` row) and a
  re-check of an existing plant (same, but filed against that plant). Endpoints and exact
  behaviour: `../garden/app/README.md`.
- **The home screen is a work list, not an inventory** — the plants that want the user now, ranked
  by everything waiting; the three buttons open the full lists.
- **Everything the app counts, the app can clear**: tasks have Done, and follow-ups/suggestions have
  their own Done in the plant page's "Also waiting" block. Counting something on one screen and
  being unable to clear it on the other makes a page that contradicts itself.

## 4. The scheduled jobs

| Job | Schedule (UTC) | What it does |
|---|---|---|
| `garden-intake-analysis` `928581257cf1` | `*/3 * * * *` | runs `garden_intake.py`; silent when nothing waits; claims each pending capture, looks at every photo, fills or compares the record, **always** closes the intake |
| `garden-weekend-plan` `774a81b2fbf4` | `0 7 * * 6` | runs `garden_weekend.py` (the digest), then the agent writes the weekend plan from it |
| `garden-monthly-review` `60c003c426a6` | `0 8 1 * *` | the month ahead, 31-day horizon |

- All three load the `garden-management` skill.
- Delivery: `bot-chat,telegram` (Bot Chat and the user's own Telegram bot). Cron fires in UTC;
  Sat 07:00 UTC ≈ 08:00 UK.
- **A digest item that is due must appear in the plan.** The 2026-09-26 run silently dropped two
  tasks due that day; the weekend prompt now requires every item in `DUE IN THIS WINDOW` to appear,
  alone or grouped with a sibling.
- Cron prompts are *code*: they are patched with the same care as the skill, and their wording is
  verified in `cron/jobs.json` after every change.

## 5. The agent

Profile `garden`, persona in `SOUL.md`, behaviour in the skill (`skills/garden-management/`), its
own private memory, which is not part of this export. It is the only agent that reads or writes this data.

## Isolation — the rule that must never break

**Nothing here is read or written by any other agent.** Concretely:

- Garden data lives only in `/root/.hermes/profiles/garden/`. No other profile's skill, cron or
  session touches it.
- A **sandbox copy must not inherit live environment**. `GARDEN_DB` and `GARDEN_PROFILE` override
  the paths; a copy whose `app.env` still names the live profile is not a sandbox, and a reviewer
  that exported `GARDEN_DB` into a shared shell has already sent test writes to the wrong file
  (it happened twice — see `HISTORY.md`). Before trusting any isolation claim:
  `env | grep -i '^GARDEN_'` and the `db:` line of `garden.py stats`.
- Never test against the user's real registry. Sandboxes live in
  `/root/.hermes/cache/scratch/<name>/` with their own `app.env`, their own port and their own DB.

## Deployment shape

| Thing | Value |
|---|---|
| Service | `hermes-garden-app.service` (systemd **user** unit, `/root/.config/systemd/user/`) |
| Process | `/usr/local/lib/hermes-agent/venv/bin/python .../garden/app/server.py` |
| Listens | `127.0.0.1:9123` (and the tailnet address, via Tailscale) |
| Exposed | `tailscale serve` → `https://<tailnet-host>:9123/` (tailnet only) |
| Health | `GET /healthz` → 200, unauthenticated |
| Secrets | `garden/app/app.env` (600) and the profile's `.env`: app token, Telegram bot token. Never in git, never in chat. |
| Git | the profile directory is a **local-only** repo (no remote). Code, schema, skill and docs are tracked; the DB, photos and Hermes runtime state are ignored. |

Front-end files are static and cache-busted by `no-cache`, so a UI change is live on the next
reload; `server.py` needs a service restart.
