# Operations

Everything here is meant to be runnable as written. If a command in this file does not work, fix
the file in the same commit as the fix.

```bash
G=/root/.hermes/profiles/garden
PY=/usr/local/lib/hermes-agent/venv/bin/python     # the venv with fastapi, uvicorn, PIL, pillow_heif
                                                   # (the system python3 does NOT have fastapi)
```

## Daily checks

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:9123/healthz          # 200
systemctl --user is-active hermes-garden-app.service                            # active
$PY $G/garden/scripts/garden.py stats                                           # counts + the db: line
$PY $G/garden/scripts/garden.py brief --mode weekend | head -40                 # the digest the job sends
tailscale serve status | grep 9123                                              # the tailnet route
```

`garden.py stats` prints which database it is talking to. **Read that line first** whenever the
numbers look wrong: a stray `GARDEN_DB` in the environment is the most common false alarm here.

## The app

```bash
systemctl --user restart hermes-garden-app.service      # needed after server.py changes
systemctl --user status hermes-garden-app.service
journalctl --user -u hermes-garden-app.service -n 50 --no-pager
```

- Editing `web/app.js`, `web/index.html`, `web/style.css` needs **no** restart: those are static and
  served `no-cache`. The user's phone picks them up on reload (and if it does not, the fix is a hard
  reload, not a redeploy — see the stale-asset incident in `HISTORY.md`).
- Editing `server.py` **does** need the restart above.
- The app's token lives in `garden/app/app.env`. It is never printed into chat and never committed.

## Backups

The database and the photos are the irreplaceable parts; both are gitignored, so git is *not* a
backup for them.

```bash
$PY - <<'EOF'
import sqlite3, datetime, pathlib
src = '/root/.hermes/profiles/garden/garden/garden.db'
dst = pathlib.Path('/root/.hermes/cache/scratch/backup-%s.db' % datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
c = sqlite3.connect(src); c.execute('VACUUM INTO ?', (str(dst),)); print('wrote', dst)
EOF
```

Take one **before any schema change or migration**, and check the copy opens (`garden.py stats`
against it) before touching the live file. `VACUUM INTO` is safe while the app is running; `cp` of a
live SQLite file is not.

## Sandbox: testing a change without touching the user's garden

Never test against the live registry. A sandbox is a copy of the code with its own DB, its own env
and its own port:

```bash
S=/root/.hermes/cache/scratch/pl2
mkdir -p $S && cd $G && tar -cf - garden/scripts garden/app/server.py garden/app/web garden/app/README.md garden/schema.sql scripts skills | (cd $S && tar -xf -)
$PY - <<'EOF'                        # point the copy's env at ITSELF, never at the live profile
import pathlib, re
p = pathlib.Path('/root/.hermes/cache/scratch/pl2/garden/app/app.env')
out = []
for line in p.read_text().splitlines():
    if line.startswith('GARDEN_PROFILE='): out.append('GARDEN_PROFILE=/root/.hermes/cache/scratch/pl2')
    elif line.startswith('GARDEN_INTAKE_JOB='): out.append('GARDEN_INTAKE_JOB=')
    elif line.startswith('GARDEN_DB='): continue
    elif line.startswith('GARDEN_APP_PORT='): out.append('GARDEN_APP_PORT=9131')
    else: out.append(line)
p.write_text('\n'.join(out) + '\n')
EOF
cd $S/garden/app && set -a && . ./app.env && set +a && exec $PY server.py     # 127.0.0.1:9131
```

Then **prove** the isolation before writing anything:

```bash
env | grep -i '^GARDEN_'                                   # expect nothing, or only sandbox paths
GARDEN_DB=$S/garden/garden.db GARDEN_PROFILE=$S $PY $S/garden/scripts/garden.py stats
```

Two rules that were learned by breaking them:

1. A copy whose `app.env` still names the live `GARDEN_PROFILE` is not a sandbox — it will write the
   user's real registry.
2. Pass `GARDEN_DB` **explicitly** on every CLI call; a variable exported into a shared shell once
   silently redirected a whole verification round to the wrong file.

Kill a scratch server by PID (`ss -ltnp | grep 9131`), never with `pkill -f <pattern>`: the pattern
matched its own command line and killed the shell.

## The registry CLI

Full reference: `CLI.md`. The five commands worth memorising:

```bash
$PY $G/garden/scripts/garden.py --json needs --days 7     # everything waiting on the user
$PY $G/garden/scripts/garden.py plant show 4 --json       # one plant's record, actions, photos
$PY $G/garden/scripts/garden.py task done 12              # idempotent: a second call changes nothing
$PY $G/garden/scripts/garden.py brief --mode weekend      # the digest the Saturday job sends
$PY $G/garden/scripts/garden.py init                      # create/upgrade tables; safe to re-run
```

## The cron jobs

```bash
hermes -p garden cron list
hermes -p garden cron show 774a81b2fbf4          # one job's prompt and schedule
```

The prompts live in `$G/cron/jobs.json`. They are code: patch them, then **read the file back** to
confirm the new wording is stored, and record what changed and why in the journal or in
`HISTORY.md`. Fires are UTC. The intake job is silent when nothing waits, so quiet is good news.

## Adding a plant by hand (when the app is not to hand)

```bash
$PY $G/garden/scripts/garden.py plant add --name "Olive (pot) — patio" --category tree --placement outdoor \
    --bed "Outside — patio, south wall" --status draft
$PY $G/garden/scripts/garden.py plant update 20 --set health_status=watch --set placement=outdoor
$PY $G/garden/scripts/garden.py task add --subject plant:20 --title "Water when the top 3 cm dries" \
    --category water --due 2026-09-27
```

A plant with no `placement` is **not** defaulted: it is a question, and the app says "Not set yet".

## If something looks broken

| Symptom | First thing to check |
|---|---|
| "The app looks dead" | hard reload; then `curl /healthz`; then `tailscale serve status \| grep 9123` |
| An action's Done button does nothing | the panel reports the truth: check `journalctl --user -u hermes-garden-app` for a 502 |
| The home screen shows a plant nothing seems to clear | open the plant: the "Also waiting" block carries the follow-up/suggestion with its own Done |
| Numbers disagree between the app and the CLI | `garden.py stats` → which DB; then compare `needs --days 7` with `/api/plants` |
| A cron job produced nothing | `cron/output/<job-id>/` holds its last runs; a script error appears there as a "Script Error" block |
| Advice that does not fit the plant | read `placement` first — it decides which half of every rule applies |

## Secrets

- `garden/app/app.env` (mode 600): the app token and the app's environment.
- The profile's `.env`: the Telegram bot token.
- Both are gitignored. Tokens are pasted into the profile, never into chat, never into a document,
  never into a commit. If a token is ever needed in a command, read it from the file at runtime
  (`grep -oP 'GARDEN_APP_TOKEN=\K\S+' garden/app/app.env`) rather than copying its value anywhere.

## Publishing the public copy

The public repository is an **export**, never a `git push` of this repository: a curated tree with the
owner's personal data removed. The publish script's exclusion list and redaction list *are* the
privacy boundary.

```bash
cd /root/.hermes/profiles/garden
*(the publish script lives in the private working repository — this export is its output)*
```

The gate scans the finished tree and refuses to publish while any known marker survives: a token
shape, the tailnet id, a LAN address, the town, the owner's name, a device name, the chat id, or a
link into what was dropped. **Adding anything personal to the project means adding its marker to that
script in the same commit** — the gate is the only thing between this project and a leak, and it has
already caught two real misses.

Two rules that follow: the export is rebuilt, never hand-edited (edit the project and re-export), and
the public README plus `.gitignore` live in `docs/tools/public/`, not in this tree.
