# Garden Keeper capture app

A phone-first web form that turns plant photos into registry entries. It is the capture surface
for the `garden` Hermes profile; all garden data still lives in one place
(`garden/garden.db`, written only through `garden/scripts/garden.py`).

```
phone (Tailscale)                    this machine
─────────────────                    ───────────────────────────────────────────────
https://<tailnet-host>:9123
        │  POST /api/intake  (photos + optional name/location/note)
        ▼
  tailscale serve ──► app/server.py (systemd: hermes-garden-app, 127.0.0.1:9123)
                        │  normalises each photo to JPEG (≤2000px), stores it
                        │  calls: garden.py intake capture …  (one transaction)
                        ▼
                    garden/garden.db   plant(status=draft) + photos + intakes(status=pending)
                        ▲
                        │  cron garden-intake-analysis every 3 min (silent when empty)
                        │  script claims the row, the agent analyses the photos,
                        │  fills the plant record and closes the intake
                        ▼
              Telegram + Bot Chat: the result, and any photo it still needs
```

The user's confirmation is immediate ("photos received, under analysis"); the analysis is async.
The app's status card polls `/api/intake/<id>` and shows the agent's summary and questions as soon
as the intake is closed.

## Files

| Path | What |
|---|---|
| `server.py` | FastAPI app: auth, upload validation/normalisation, the small JSON API |
| `web/index.html`, `web/app.js`, `web/style.css` | the UI (no build step, no framework) |
| `web/manifest.webmanifest`, `web/icon.svg` | so it can be added to the home screen |
| `app.env` | service environment (mode 600): token, one-time login codes, port, cron job id |
| `../../scripts/garden_intake.py` | the cron worker's script (claims + prints pending intakes) |

## API

Six views share one document (`#/` what needs action, `#/in` and `#/out` the two groups,
`#/all` every plant, `#/plant/<id>` one plant, `#/add` capture):

| Method | Path | Notes |
|---|---|---|
| `GET` | `/` | the app (or the login page when unauthenticated) |
| `POST` | `/api/intake` | multipart: `photos` (1–6, ≤15 MB each) + `name`/`location`/`note`; returns `{ok, intake_id, plant_id, photos}` |
| `GET` | `/api/intake/{id}` | `{status, summary, questions, photos, …}` for the status card |
| `GET` | `/api/overview` | queue depth (pending/processing/total) |
| `GET` | `/api/plants` | the plant list: `photo_id` (cover), `photos` count, `health_status`, `status` (`draft` shows as "being identified"), `actions{open,overdue,due_soon,next_due}`, `counts{…}`. Sorted most-overdue first, then health, then name |
| `GET` | `/api/plants/{id}` | one plant's page: the record, `actions[]` with `state` (`overdue`/`due`/`scheduled`/`anytime`), `photos[]` **oldest first** (each with `url`/`full` links and `missing` when the file is gone), `hero`, recent observations and treatments |
| `POST` | `/api/tasks/{id}/done` | flag an action done from the plant page (registry `task done`, idempotent — a second tap changes nothing and never clones a recurring task). Optional JSON body `{"note": "what changed"}` — the user's own account of the work; stored on the task and, for a plant task, added as a `maintenance` observation so the agent reads it in the plant's history |
| `POST` | `/api/observations/{id}/follow-up-done` | clear a follow-up the home view counts (registry `obs follow-up-done`) — without this the plant could never leave the home screen |
| `POST` | `/api/treatments/{id}/apply` | mark a suggested treatment as applied today (registry `treat apply`) |
| `POST` | `/api/plants/{id}/photos` | multipart `photos` + `note`: a **re-check** of a plant that already exists — files an intake against that plant instead of a new draft. 409 when the plant has left the garden (`removed`/`dead`). Sent by the plant page's compose form (batch, note, then Send) and by a Done that carries photos |
| `GET` | `/api/photo/{id}?w=` | a stored photo, downscaled and cached in `app/thumbs/` — `w` ∈ {160, 240, 480, 900}, anything else becomes 480. Only files inside `garden/photos/` are ever served: a row holding an absolute path outside it 404s |
| `GET` | `/healthz` | liveness, unauthenticated |

Reading the garden costs three CLI calls per list request (`plant list`, `task list`,
`photo summary`) and one per plant page (`plant show --json` carries the plant, its open tasks, its
photos, observations and treatments in a single shot). Everything the app writes still goes through
the CLI; the app never touches SQLite itself.

`photo summary` (registry CLI) is what the list reads: per plant it returns the photo count and the
newest **photo whose file still exists**, computed over the whole table. A fixed-size window of the
newest photo rows (the obvious first implementation) silently blanks the cover and the count of
every older plant as the garden grows past the window.

## Missing or unreadable photos

Photos can go missing from disk (a manual clean-up, a restored backup, a bad copy). Nothing in the
UI is allowed to show a broken image because of it:

- the cover falls back to the next photo that exists, and disappears (🪴 placeholder) if none do;
- the plant page marks such entries `missing: true` and draws a placeholder tile in the timeline;
- any `<img>` that still fails (a corrupt JPEG, a dropped connection) is swapped for the placeholder
  client-side by `photoImg()` in `app.js`;
- the full-screen viewer shows “missing from disk” if the file goes between render and tap, and
  stays closable.

## Deploys and the browser cache

The app shell is three files and must never be a stale mix of two versions: `index.html` is
`no-store`, and `app.js` / `style.css` / the manifest are `no-cache` (revalidated against their ETag
on every load — a 304 in practice). Icons keep `max-age=3600`.

Why it matters: with `max-age=3600` on the script, a reload inside that hour after a deploy serves
the **new** markup with the **old** script. The router never runs, the list stays on "Loading your
garden…", nothing is clickable — the app looks dead while the server is perfectly healthy. That is
exactly what happened once, and it is why the shell revalidates now.

## Auth

Access is tailnet-only (`tailscale serve`, no Funnel). Inside it:

1. **Tailscale identity** — `serve` injects `Tailscale-User-Login` and *overwrites* any value a
   client sends (verified: a forged header through the proxy arrives as the real login), so a
   request from `GARDEN_APP_USER` is trusted with no further step. This is how the user's phone
   gets in.
2. **Token** — `GARDEN_APP_TOKEN` as an `X-Garden-Token` header, the `garden_token` cookie, or a
   `?k=` query parameter. Any *one* correct credential is enough (a stale cookie never blocks a
   good header). `?k=` sets the cookie and redirects on page loads only — API calls answer
   normally, so a redirect can never hide the result of a write.
3. **One-time codes** — `GARDEN_APP_LOGIN_CODES` in `app.env`, consumed on first use, for the
   login form on a device that has neither of the above. The form is throttled (8 failures per
   10 minutes).

**Residual risk, deliberately accepted:** the service listens on `127.0.0.1`, so any process
running on this host can reach it and send the identity header itself. The app is meant to be
reached only through `tailscale serve`; on a single-user box (root only) that is equivalent to
being able to read `app.env`. Do not move the app onto a shared host without switching the
listener to a root-only unix socket.

## Operating it

```bash
systemctl --user status hermes-garden-app          # is it up
journalctl --user -u hermes-garden-app -n 50       # uploads, rejections, errors
curl -s localhost:9123/healthz                     # liveness
tailscale serve status | grep 9123                 # still published
```

Restart after changing `server.py` or `app.env`: `systemctl --user restart hermes-garden-app`.
Static files (`web/`) are read per request — but bump the service too if you change
`index.html`, since browsers cache aggressively.

## Behaviour worth knowing

- **One definition of "waiting on the user"**: `garden.py needs` — open tasks, observation
  follow-ups not yet done, and treatments suggested but not applied, within a 7-day window.
  `/api/plants` carries it as `pending` and the home view ranks by it; the agent's brief lists
  the same three sources, so the page and the digest cannot disagree. Recording a follow-up
  (`photo assess --follow-up <date>`) is enough to put a plant in front of the user — no task
  needed as well.
- **The home screen is a work list, not an inventory.** With no filter selected it shows the
  plants that want the user now: work overdue, work due within the week, or health flagged
  `poor`/`watch` — each card naming the item it waits on. The three buttons above it
  (🏠 In house / 🌤️ Outside / 🌿 All) open the full alphabetical list; a second tap on the
  active one returns home. The selection lives in the URL (`#/in`, `#/out`, `#/all`) so a
  reload and the phone's back button keep it. `All` is also where a plant with an
  unrecognised `placement` stays reachable.
- **The definition of "waiting" is `garden.py needs --days 7`, and it is the same one the
  briefs use**: open tasks, observation follow-ups not yet done, treatments suggested but not
  applied. `needs` is the only place that decides; `/api/plants` and `/api/plants/{id}` both
  carry the result as `pending`, and the list card's single number is `pending`.
- **Everything counted can be cleared on the plant page**: tasks have their Done, and the
  "Also waiting" block carries a Done for each follow-up and each suggested-but-unapplied
  treatment — a plant the home screen calls overdue never opens on a page that says there is
  nothing to do.
- **One number, one meaning.** `subtitle`, the card chips and the group counts all count the
  set the page shows; a plant with no usable `placement` is named in the caption rather than
  quietly missing.
- **Photos open in an in-app viewer.** Tapping the hero or a timeline photo opens it full screen
  with its own close — the ✕, a tap outside it, Escape, or the phone's back gesture — and the
  plant page underneath keeps its scroll and focus. The links stay real links (long-press,
  ⌘/Ctrl-click) for anyone who wants the bare image.


- Photos are re-encoded server-side (EXIF rotation applied, max side 2000 px, JPEG q85) and HEIC
  from iPhones is converted; the stored file is what the vision model reads. Each upload is read
  in chunks and abandoned as soon as it passes 15 MB, and a request larger than 6×15 MB is
  refused before it is parsed.
- Limits: 6 photos, 15 MB each, 30 captures/minute (counted per socket, *not* per
  `X-Forwarded-For` — uvicorn's proxy-header trust is off so a header cannot mint a new bucket),
  and the queue refuses new work above 25 waiting intakes. The UI downscales on the phone first,
  so real uploads are typically a few hundred KB each.
- Nothing is analysed in the request: the app never waits on the agent, so a slow or restarted
  agent cannot lose a capture — the row is already in the database.
- If the agent cannot identify a plant it asks for specific extra photos
  (`intake needs-info`), and both the app and Telegram show that question. When the user answers,
  the capture goes back in the queue with `intake reopen <id>`.
- The CLI subprocess runs with a scrubbed environment (PATH/HOME/LANG only): the app's token and
  the profile's other secrets are never inherited by it.
