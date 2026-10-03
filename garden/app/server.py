#!/usr/bin/env python3
"""Garden Keeper capture app — the mobile web interface for the `garden` Hermes profile.

One job: take pictures of a plant from a phone, store them in the garden registry as an
*intake*, and let the Garden Keeper agent analyse them asynchronously (it fills in the plant
record and messages the result to the user's Telegram).

Served on 127.0.0.1 (<GARDEN_APP_PORT>, default 9123) and published to the tailnet only, via
`tailscale serve`. Auth: a Tailscale identity header (injected by `serve`, which overwrites any
client-supplied value) or a token. Everything the app writes goes through the registry CLI.

Env (from the garden profile's .env):
  GARDEN_APP_TOKEN        long-lived access token (cookie / ?k= / X-Garden-Token)
  GARDEN_APP_LOGIN_CODES  comma-separated one-time codes (consumed on use) for first login
  GARDEN_APP_USER         tailnet login to trust from the identity header (e.g. user@example.com)
  GARDEN_APP_PORT         listen port (default 9123)
  GARDEN_INTAKE_JOB       cron job id of the analysis worker (only for the optional nudge)
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse, PlainTextResponse,
                               RedirectResponse)
from fastapi.staticfiles import StaticFiles

log = logging.getLogger("garden-app")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

PROFILE = Path(os.environ.get("GARDEN_PROFILE", "/root/.hermes/profiles/garden"))
GARDEN = PROFILE / "garden"
CLI = GARDEN / "scripts" / "garden.py"
WEB = Path(__file__).resolve().parent / "web"
PHOTOS = GARDEN / "photos"
THUMBS = Path(__file__).resolve().parent / "thumbs"
PORT = int(os.environ.get("GARDEN_APP_PORT", "9123"))
THUMB_SIZES = (160, 240, 480, 900)          # what the UI may ask for; anything else becomes 480

TOKEN = (os.environ.get("GARDEN_APP_TOKEN") or "").strip()
LOGIN_CODES = {c.strip() for c in (os.environ.get("GARDEN_APP_LOGIN_CODES") or "").split(",") if c.strip()}
TRUSTED_USER = (os.environ.get("GARDEN_APP_USER") or "").strip().lower()
INTAKE_JOB = (os.environ.get("GARDEN_INTAKE_JOB") or "").strip()

MAX_FILES = 6
MAX_NOTE_CHARS = 500      # a note is a sentence about the work, not an essay
MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_BODY_BYTES = MAX_FILES * MAX_FILE_BYTES + 2 * 1024 * 1024   # hard ceiling on one request
MAX_PENDING = 25
MAX_SIDE = 2000
JPEG_QUALITY = 85
CHUNK = 256 * 1024

COOKIE = "garden_token"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365
_codes_lock = threading.Lock()
_recent: dict[str, list[float]] = {}          # request timestamps per client (rate limit)
_login_lock = threading.Lock()
_login_attempts: list[float] = []             # failed /login attempts, global (single-user app)

# Set by __main__ when we bind a unix socket instead of a TCP port.
SOCKET_PATH: str | None = None


# ── registry CLI ──────────────────────────────────────────────────────────────
def cli(*args: str, timeout: int = 120) -> dict:
    """Run the garden registry CLI and return its parsed JSON.

    The child gets a minimal environment: the app's own secrets (token, cron id, API keys that
    may live in the same env file) have no business being inherited by a subprocess.
    """
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/root"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "PYTHONUNBUFFERED": "1",
    }
    proc = subprocess.run([sys.executable, str(CLI), "--json", *args],
                          capture_output=True, text=True, timeout=timeout, env=env)
    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout or "the registry CLI failed").strip()
        raise RuntimeError(message[:600])
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"unreadable registry output: {proc.stdout[:200]}")


def nudge_worker() -> None:
    """Optional: ask the cron scheduler to run the analysis job now instead of at its next tick.

    OFF by default and deliberately so: a manual `cron run` claims the job cross-process, so the
    scheduled tick that lands while it is in flight is recorded as a *failed* run ("fire claim
    lost") — noise, and a failure notice. The job ticks every 3 minutes anyway, which is plenty
    for an async capture. Enable only if a capture must be analysed immediately.
    """
    if not INTAKE_JOB or os.environ.get("GARDEN_INTAKE_NUDGE", "0") != "1":
        return
    try:
        subprocess.Popen(
            ["hermes", "-p", "garden", "cron", "run", INTAKE_JOB],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        )
        log.info("nudged analysis job %s", INTAKE_JOB)
    except Exception as exc:                                    # never fail a capture over this
        log.warning("could not nudge %s: %s", INTAKE_JOB, exc)


def normalise_image(src: Path, dest: Path) -> tuple[int, int]:
    """Re-encode one upload as a sane JPEG (orientation applied, bounded size). Returns (w, h)."""
    from PIL import Image, ImageOps
    try:                                                        # HEIC/HEIF from iPhones
        import pillow_heif
        pillow_heif.register_heif_opener()
    except Exception:
        pass
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        w, h = im.size
        scale = min(1.0, MAX_SIDE / max(w, h))
        if scale < 1.0:
            im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
        im.save(dest, "JPEG", quality=JPEG_QUALITY, optimize=True)
        return im.size


# ── auth ──────────────────────────────────────────────────────────────────────
def identity_ok(request: Request) -> bool:
    """True when tailscale serve vouched for a tailnet user we trust.

    `serve` replaces any client-supplied Tailscale-User-* header, so over the proxy this is the
    peer's real identity. Directly on the loopback socket it is a plain header — which is why the
    app is meant to be reachable only through `serve` (see app/README.md).
    """
    if not TRUSTED_USER:
        return False
    login = (request.headers.get("Tailscale-User-Login") or "").strip().lower()
    return bool(login) and login == TRUSTED_USER


def token_ok(request: Request) -> bool:
    """Any one correct credential is enough — a stale cookie must not shadow a good header."""
    if not TOKEN:
        return False
    supplied = [request.cookies.get(COOKIE), request.headers.get("X-Garden-Token"),
                request.query_params.get("k")]
    return any(value and _constant_eq(value.strip(), TOKEN) for value in supplied)


def code_ok(code: str) -> bool:
    with _codes_lock:
        if code and code in LOGIN_CODES:
            LOGIN_CODES.discard(code)                            # one-time
            return True
    return False


def _constant_eq(a: str, b: str) -> bool:
    import hmac
    return hmac.compare_digest(a.encode(), b.encode())


def authorised(request: Request) -> bool:
    return identity_ok(request) or token_ok(request)


def rate_ok(limit: int = 30, window: int = 60, *, client: str = "?") -> bool:
    """Global request limiter. Behind the proxy every request shares one bucket, which is the
    intent: this is a one-user app, and keying on a client-supplied header would let anyone
    step around the limit."""
    now = time.time()
    with _codes_lock:
        for key in list(_recent):                                # keep the dict from growing for ever
            bucket = [t for t in _recent[key] if now - t < window]
            if bucket:
                _recent[key] = bucket
            else:
                _recent.pop(key, None)
        bucket = _recent.setdefault(client, [])
        bucket.append(now)
        return len(bucket) <= limit


def login_ok() -> bool:
    """Throttle the login form: it is the one place a two-character code could be guessed."""
    now = time.time()
    with _login_lock:
        cutoff = now - 600
        _login_attempts[:] = [t for t in _login_attempts if t > cutoff]
        if len(_login_attempts) >= 8:
            return False
        _login_attempts.append(now)
        return True


def _is_api(path: str) -> bool:
    """Tolerant API detection: '/api/x', '//api/x' and '/API/x' must all answer JSON."""
    cleaned = ""
    for part in path.lower().split("/"):
        if part:
            cleaned = part
            break
    return cleaned == "api"


# ── app ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Garden Keeper capture", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=str(WEB)), name="static")

LOGIN_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Garden Keeper</title>
<meta name="theme-color" content="#f6faf7" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0f1c14" media="(prefers-color-scheme: dark)">
<link rel="manifest" href="/static/manifest.webmanifest">
<link rel="stylesheet" href="/static/style.css">
<link rel="icon" href="/static/icon.svg">
<link rel="apple-touch-icon" href="/static/apple-touch-icon.png"></head>
<body class="login-body"><main class="login">
<div class="brand"><img src="/static/icon.svg" alt="" width="44" height="44"><h1>Garden Keeper</h1></div>
{message}
<p class="muted">Enter the access code to add plants from this device.</p>
<form method="post" action="/login" class="card">
  <label for="code">Access code</label>
  <input id="code" name="code" type="text" inputmode="text" autocomplete="one-time-code"
         autocapitalize="off" spellcheck="false" placeholder="paste the code here" required>
  <button type="submit" class="primary">Open Garden Keeper</button>
</form>
<p class="muted small">Private — reachable only from your own devices.</p>
</main></body></html>"""


def _login_page(message: str = "", status: int = 401) -> HTMLResponse:
    banner = f'<p class="error">{message}</p>' if message else ""
    return HTMLResponse(LOGIN_HTML.replace("{message}", banner), status_code=status)


def _decorate(response, request: Request):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    path = request.url.path
    if path.startswith("/static/") and path.endswith((".js", ".css", ".html", ".webmanifest")):
        # The app shell must never be a stale copy of itself: index.html is no-store, but the cached
        # script and stylesheet live for an hour otherwise, and a reload in that window serves the
        # NEW markup with the OLD script — the app then looks dead. Revalidate instead; the ETag
        # turns it into a cheap 304.
        response.headers.setdefault("Cache-Control", "no-cache")
    elif path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "public, max-age=3600")   # icons: safe to keep
    else:
        response.headers["Cache-Control"] = "no-store"
    return response


@app.middleware("http")
async def _guard(request: Request, call_next):
    path = request.url.path
    if path in ("/healthz", "/login") or path.startswith("/static/"):
        return _decorate(await call_next(request), request)

    if not authorised(request):
        if _is_api(path):
            return _decorate(JSONResponse({"error": "not signed in"}, status_code=401), request)
        return _decorate(_login_page(), request)

    response = await call_next(request)
    # ?k=<token> is a convenience for opening the app by link: keep the token out of the address
    # bar by setting a cookie and redirecting — but never for API calls, where a redirect would
    # hide the result of a request that has already been carried out.
    if request.method == "GET" and request.query_params.get("k") and not _is_api(path):
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(COOKIE, TOKEN or request.query_params["k"], max_age=COOKIE_MAX_AGE,
                            httponly=True, samesite="lax", secure=True)
    return _decorate(response, request)


@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    return "ok"


@app.post("/login")
async def login(request: Request):
    if not login_ok():
        log.warning("too many login attempts — throttled")
        return _login_page("Too many attempts — wait ten minutes and try again.")
    form = await request.form()
    code = str(form.get("code") or "").strip()
    if code_ok(code) or (TOKEN and _constant_eq(code, TOKEN)):
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(COOKIE, TOKEN or code, max_age=COOKIE_MAX_AGE, httponly=True,
                            samesite="lax", secure=True)
        log.info("login ok from %s", request.client.host if request.client else "?")
        return _decorate(response, request)
    log.warning("rejected login attempt")
    return _login_page("That code is not valid.")


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse((WEB / "index.html").read_text())


@app.get("/api/intake/{intake_id}")
def intake_status(intake_id: int):
    if not _reasonable(intake_id):
        return _no_such("capture")
    try:
        data = cli("intake", "show", str(intake_id))
    except RuntimeError as exc:
        detail = str(exc)
        if "No intake" in detail or "does not exist" in detail:
            return JSONResponse({"error": "unknown capture"}, status_code=404)
        log.error("intake show failed: %s", detail)
        return JSONResponse({"error": "the registry could not answer — try again"}, status_code=502)
    photos = data.get("photos") or []
    # How many captures are queued ahead of this one: the worker claims a batch and analyses it in
    # one agent run (a few minutes), so a card that just says "soon" is a lie when others are ahead.
    try:
        queued = cli("intake", "list", "--limit", "100")
        ahead = sum(1 for r in queued
                    if r["status"] in ("pending", "processing") and r["id"] < data["id"])
    except RuntimeError:
        ahead = 0
    return {
        "intake_id": data["id"],
        "status": data["status"],
        "created_at": data.get("created_at"),
        "plant_id": data.get("plant_id"),
        "photos": len(photos),
        "summary": data.get("summary"),
        "questions": [q for q in (data.get("questions") or "").split("\n") if q.strip()],
        "attempts": data.get("attempts") or 0,
        "ahead": ahead,
    }


@app.get("/api/overview")
def overview():
    """Tiny status for the header: how many captures are waiting."""
    try:
        rows = cli("intake", "list", "--limit", "50")
    except RuntimeError as exc:
        log.error("overview failed: %s", exc)
        return JSONResponse({"error": "the registry could not answer — try again"}, status_code=502)
    return {"pending": sum(1 for r in rows if r["status"] == "pending"),
            "processing": sum(1 for r in rows if r["status"] == "processing"),
            "total": len(rows)}


async def _read_capped(upload: UploadFile, cap: int) -> bytes | None:
    """Read an upload in chunks, stopping as soon as it passes the cap (never buffers a huge body)."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > cap:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


def _clean(text: str, limit: int) -> str:
    """Collapse whitespace so a multi-line field cannot smuggle formatting into the registry."""
    return re.sub(r"\s+", " ", text or "").strip()[:limit]


async def _collect_photos(uploads: list[UploadFile], tmpdir: Path) -> tuple[list[Path], JSONResponse | None]:
    """Validate + re-encode every upload. Returns (stored JPEG paths, error response for the user)."""
    stored: list[Path] = []
    for idx, upload in enumerate(uploads, 1):
        raw = await _read_capped(upload, MAX_FILE_BYTES)
        if raw is None:
            return [], JSONResponse({"error": f"Photo {idx} is larger than 15 MB."}, status_code=413)
        if not raw:
            return [], JSONResponse({"error": f"Photo {idx} arrived empty — try sending it again."},
                                    status_code=400)
        src = tmpdir / f"upload-{idx}{Path(upload.filename or '').suffix.lower()[:5]}"
        src.write_bytes(raw)
        dest = tmpdir / f"photo-{idx}.jpg"
        try:
            normalise_image(src, dest)
        except Exception as exc:
            log.warning("rejected photo %s (%s): %s", idx, upload.filename, exc)
            return [], JSONResponse({"error": f"Photo {idx} is not a picture I can read."},
                                    status_code=400)
        stored.append(dest)
    return stored, None


def _backlog_error() -> JSONResponse | None:
    """The queue is a fixed-size thing: refuse new work rather than let it grow without bound."""
    try:
        state = cli("intake", "list", "--limit", "100")
    except RuntimeError:
        return None
    if sum(1 for r in state if r["status"] in ("pending", "processing")) >= MAX_PENDING:
        return JSONResponse({"error": "Garden Keeper is still working through a backlog — "
                                      "try again in a few minutes."}, status_code=429)
    return None


@app.post("/api/intake")
async def create_intake(request: Request,
                        photos: list[UploadFile] = File(default=[]),
                        name: str = Form(default=""),
                        location: str = Form(default=""),
                        note: str = Form(default="")):
    if not rate_ok(client="captures", limit=30):
        return JSONResponse({"error": "Too many photos just now — try again in a minute."},
                            status_code=429)
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        return JSONResponse({"error": "That upload is too big — send at most 6 photos."}, status_code=413)

    photos = [p for p in photos if p and p.filename]
    if not photos:
        return JSONResponse({"error": "No photos arrived with that request."}, status_code=400)
    if len(photos) > MAX_FILES:
        return JSONResponse({"error": f"At most {MAX_FILES} photos at a time."}, status_code=400)
    backlog = _backlog_error()
    if backlog is not None:
        return backlog

    tmpdir = Path(tempfile.mkdtemp(prefix="garden-intake-"))
    stored: list[Path] = []
    try:
        stored, bad = await _collect_photos(photos, tmpdir)
        if bad is not None:
            return bad

        # `--flag=value` form: a name like "-x" or "--help" is data, not an option.
        cli_args = ["intake", "capture", "--source=app"]
        for path in stored:
            cli_args.append(f"--file={path}")
        if _clean(name, 120):
            cli_args.append(f"--name={_clean(name, 120)}")
        if _clean(location, 120):
            cli_args.append(f"--location={_clean(location, 120)}")
        if _clean(note, 600):
            cli_args.append(f"--note={_clean(note, 600)}")
        result = cli(*cli_args)
    except RuntimeError as exc:
        log.error("capture failed: %s", exc)                      # detail stays in the log
        return JSONResponse({"error": "The photos could not be filed — nothing was saved. "
                                      "Try again, or tell Garden Keeper on Telegram."}, status_code=502)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    nudge_worker()
    log.info("intake %s stored (%s photos) from %s",
             result["intake_id"], len(stored), request.client.host if request.client else "?")
    return {"ok": True, "intake_id": result["intake_id"], "plant_id": result["plant_id"],
            "photos": len(stored), "status": "pending"}


# ── the garden itself: the plant list, one plant, its actions and its photos ──
def _open_actions(tasks: list[dict]) -> dict:
    """Summarise a plant's open actions: how many, how urgent, what the next one actually is.

    `next_*` describes the single most urgent open action (earliest due date, high priority
    breaking ties) so the home screen can say *why* a plant is asking for attention instead of
    only how many rows it has.
    """
    today = dt.date.today()
    soon = (today + dt.timedelta(days=7)).isoformat()
    rank = {"high": 0, "normal": 1, "low": 2}
    open_tasks = [t for t in tasks if (t.get("status") or "open") == "open"]
    dated = [t for t in open_tasks if t.get("due_on")]
    ordered = sorted(open_tasks, key=lambda t: (t.get("due_on") or "9999-99-99",
                                                rank.get(t.get("priority"), 1)))
    nxt = ordered[0] if ordered else {}
    return {
        "open": len(open_tasks),
        "overdue": sum(1 for t in dated if t["due_on"] < today.isoformat()),
        "due_soon": sum(1 for t in dated if today.isoformat() <= t["due_on"] <= soon),
        "next_due": min((t["due_on"] for t in dated), default=None),
        "next_title": nxt.get("title"),
        "next_category": nxt.get("category"),
        "next_state": _action_state(nxt.get("due_on")),
    }


def _action_state(due_on: str | None) -> str:
    """Where an action sits in time — the UI colours the row from this."""
    if not due_on:
        return "anytime"
    today = dt.date.today()
    if due_on < today.isoformat():
        return "overdue"
    if due_on <= (today + dt.timedelta(days=7)).isoformat():
        return "due"
    return "scheduled"


MAX_ROW_ID = 2 ** 63 - 1        # SQLite's integer range: past it, no query can match a row


def _no_such(what: str) -> JSONResponse:
    """An id that cannot be a row here is 'nothing there', not a failure worth retrying."""
    return JSONResponse({"error": f"that {what} is not in the registry"}, status_code=404)


def _reasonable(row_id: int) -> bool:
    return 0 < row_id <= MAX_ROW_ID


def _slim_plant(row: dict) -> dict:
    keep = ("id", "name", "common_name", "botanical", "cultivar", "category", "subtype", "bed",
            "placement",
            "position", "aspect", "soil", "in_container", "pot_size_cm", "planted_on",
            "acquired_from", "height_cm", "spread_cm", "hardiness", "uk_native", "wildlife",
            "flower_months", "scent", "prune_group", "prune_months", "prune_method", "last_pruned",
            "cut_back_by", "feed_months", "feed_product", "water_needs", "mulch", "pests_known",
            "toxicity", "health_status", "status", "notes", "created_at", "updated_at")
    return {k: row.get(k) for k in keep if row.get(k) not in (None, "")}


@app.get("/api/plants")
def plant_list():
    """What the home screen shows: every plant with its picture, health and open actions."""
    try:
        rows = cli("plant", "list", "--all")
        tasks = cli("task", "list", "--status", "open")
        # one definition of "waiting on the user" — open tasks, observation follow-ups still owed,
        # and treatments suggested but not applied — so the home screen cannot disagree with the
        # digest the agent writes from
        needs = cli("needs", "--days", "7")
        # Per-plant photo counts and covers, computed by the CLI over the whole table: a fixed-size
        # window of the newest photo rows would silently blank the cover of older plants.
        covers = cli("photo", "summary")
    except RuntimeError as exc:
        log.error("plant list failed: %s", exc)
        return JSONResponse({"error": "the registry could not answer — try again"}, status_code=502)

    summary = {c["plant_id"]: c for c in covers if c.get("plant_id")}
    pending = {p["plant_id"]: p for p in (needs.get("plants") or [])}

    by_subject: dict[str, list[dict]] = {}
    for task in tasks:
        by_subject.setdefault(task.get("subject") or "", []).append(task)

    live = []
    for row in rows:
        if row.get("status") in ("removed", "dead"):
            continue
        actions = _open_actions(by_subject.get(f"plant:{row['id']}", []))
        shots = summary.get(row["id"]) or {}
        live.append({
            "id": row["id"], "name": row.get("name"), "common_name": row.get("common_name"),
            "botanical": row.get("botanical"), "category": row.get("category"),
            "subtype": row.get("subtype"), "bed": row.get("bed"),
            "placement": row.get("placement"),
            "health_status": row.get("health_status") or "unknown",
            "status": row.get("status") or "active",
            "photo_id": shots.get("cover_photo_id"), "photos": int(shots.get("photos") or 0),
            "actions": actions,
            # what the home view sorts and explains itself with (tasks + follow-ups + unapplied)
            "pending": pending.get(row["id"]) or {"open": 0, "overdue": 0, "due_soon": 0, "next": None},
        })

    rank = {"poor": 0, "watch": 1, "unknown": 2, "good": 3}
    live.sort(key=lambda p: (-p["pending"]["overdue"], rank.get(p["health_status"], 2),
                             (p["name"] or "").lower()))
    return {"plants": live, "counts": {
        "plants": len(live),
        "needs_attention": sum(1 for p in live if p["health_status"] in ("poor", "watch")),
        "with_actions": sum(1 for p in live if p["actions"]["open"]),
        "drafts": sum(1 for p in live if p["status"] == "draft"),
        "indoor": sum(1 for p in live if p["placement"] == "indoor"),
        "outdoor": sum(1 for p in live if p["placement"] == "outdoor"),
        "unplaced": sum(1 for p in live if p["placement"] not in ("indoor", "outdoor")),
    }}


@app.get("/api/plants/{plant_id}")
def plant_detail(plant_id: int):
    if not _reasonable(plant_id):
        return _no_such("plant")
    """One plant's page: the record, everything still waiting, the photo history (oldest first)."""
    try:
        data = cli("plant", "show", str(plant_id))
        needs = cli("needs", "--days", "7")          # one definition, shared with the home screen
    except RuntimeError as exc:
        detail = str(exc)
        if "No plant" in detail or "Ambiguous" in detail:
            return JSONResponse({"error": "unknown plant"}, status_code=404)
        log.error("plant show %s failed: %s", plant_id, detail)
        return JSONResponse({"error": "the registry could not answer — try again"}, status_code=502)

    plant = data.get("plant") or {}
    actions = []
    for task in data.get("tasks") or []:
        if (task.get("status") or "open") != "open":
            continue
        due = task.get("due_on") or None
        actions.append({"id": task["id"], "title": task.get("title"), "detail": task.get("detail"),
                        "category": task.get("category"), "priority": task.get("priority") or "normal",
                        "due_on": due, "window_end": task.get("window_end"),
                        "est_minutes": task.get("est_minutes"), "state": _action_state(due)})
    actions.sort(key=lambda a: (a["due_on"] or "9999-12-31", a["priority"] != "high", a["id"]))

    photos = []
    for shot in data.get("photos") or []:
        # A photo row whose file went missing must not become a broken image on the phone: tell the
        # page, and let it draw the placeholder instead.
        present = _photo_file(shot.get("path")) is not None
        photos.append({"id": shot["id"], "date": shot.get("taken_on") or shot.get("added_at"),
                       "kind": shot.get("kind"), "user_note": shot.get("user_note"),
                       "assessment": shot.get("assessment"), "next_action": shot.get("next_action"),
                       "missing": not present,
                       "url": f"/api/photo/{shot['id']}?w=480",
                       "full": f"/api/photo/{shot['id']}?w=900"})
    photos.sort(key=lambda p: ((p["date"] or ""), p["id"]))       # oldest first: a growth story

    pend = next((row for row in (needs.get("plants") or []) if row["plant_id"] == plant_id), None) or \
        {"open": 0, "overdue": 0, "due_soon": 0, "next": None, "items": []}
    # the page must be able to account for every item the home screen counted: tasks are the
    # Actions list, everything else (follow-ups owed, suggestions not applied) gets its own block
    pending_extra = [i for i in (pend.get("items") or []) if i.get("kind") != "task"]

    hero = next((p["id"] for p in reversed(photos) if not p["missing"]), None)
    return {"plant": _slim_plant(plant), "actions": actions, "photos": photos,
            "pending": {**{k: pend[k] for k in ("open", "overdue", "due_soon", "next")},
                        "extra": pending_extra},
            "hero": ({"id": hero, "url": f"/api/photo/{hero}?w=900"} if hero else None),
            "observations": [o for o in (data.get("observations") or []) if o.get("description")][:8],
            "treatments": [t for t in (data.get("treatments") or []) if t.get("date")][:6],
            "counts": {"actions": len(actions),
                       "overdue": sum(1 for a in actions if a["state"] == "overdue"),
                       "photos": len(photos),
                       # what the registry actually holds, not what fits a display filter — a
                       # suggested treatment with no date yet is still recorded against the plant
                       "observations": len(data.get("observations") or []),
                       "treatments": len(data.get("treatments") or [])}}


@app.post("/api/plants/{plant_id}/placement")
def set_placement(plant_id: int, payload: dict = Body(...)):
    """Where the plant lives — indoor or outdoor, the only two answers.

    It is not decoration: it decides which half of the advice applies (frost, rain, slugs and wind
    vs radiators, tap-water hardness and humidity), so the agent reads it before every action,
    recommendation and photo assessment.
    """
    if not _reasonable(plant_id):
        return _no_such("plant")
    if not rate_ok(limit=60, client="placement"):
        return JSONResponse({"error": "Too many changes just now — give it a second."}, status_code=429)
    value = str((payload or {}).get("placement") or "").strip().lower()
    if value not in ("indoor", "outdoor"):
        return JSONResponse({"error": "placement must be indoor or outdoor"}, status_code=400)
    try:
        cli("plant", "update", str(plant_id), "--placement", value)
        fresh = cli("plant", "show", str(plant_id))
    except RuntimeError as exc:
        detail = str(exc)
        if "No plant" in detail or "Ambiguous" in detail:
            return JSONResponse({"error": "that plant is not in the registry"}, status_code=404)
        log.error("placement update %s failed: %s", plant_id, detail)
        return JSONResponse({"error": "the registry could not save that — try again"}, status_code=502)
    return {"ok": True, "plant_id": plant_id, "placement": (fresh.get("plant") or {}).get("placement") or value}


@app.post("/api/tasks/{task_id}/done")
def task_done(task_id: int, payload: dict | None = Body(default=None)):
    """Flag an action done from the plant page — it disappears from the list straight away.

    An optional {"note": "what changed"} is the user's feedback about the work: it is stored on the
    task and (for a plant task) becomes a maintenance observation, so the agent reads it in the
    plant's history rather than only on a closed row nothing lists.
    """
    if not _reasonable(task_id):
        return _no_such("action")
    if not rate_ok(limit=60, client="tasks"):
        return JSONResponse({"error": "Too many taps just now — give it a second."}, status_code=429)
    note = str((payload or {}).get("note") or "").strip()[:MAX_NOTE_CHARS]
    try:
        args = ["task", "done", str(task_id)] + (["--note", note] if note else [])
        result = cli(*args)
    except RuntimeError as exc:
        detail = str(exc)
        if "No task" in detail:
            return JSONResponse({"error": "that action is no longer on the list"}, status_code=404)
        log.error("task done %s failed: %s", task_id, detail)
        return JSONResponse({"error": "the registry could not record that — try again"}, status_code=502)
    return {"ok": True, "task_id": task_id,
            "already_closed": bool(result.get("already_closed")),
            # note_recorded is what the client keys its confirmation on: "" already ticked off "" must
            # never be reported as "nothing new to record" when the note did land.
            "note": result.get("note"), "note_recorded": bool(result.get("note_recorded")),
            "observation_id": result.get("observation_id"),
            "completed_on": result.get("completed_on") or dt.date.today().isoformat()}


@app.post("/api/observations/{observation_id}/follow-up-done")
def follow_up_done(observation_id: int):
    """Clear a follow-up the home screen is still showing as owed.

    Nothing in the app could clear one before: a follow-up the user had actually done kept the
    plant on the home screen for ever.
    """
    if not _reasonable(observation_id):
        return _no_such("follow-up")
    try:
        res = cli("obs", "follow-up-done", str(observation_id))
    except RuntimeError as exc:
        detail = str(exc)
        if "No observation" in detail:
            return JSONResponse({"error": "that follow-up is not in the registry"}, status_code=404)
        log.error("follow-up-done %s failed: %s", observation_id, detail)
        return JSONResponse({"error": "the registry could not save that — try again"}, status_code=502)
    return {"ok": True, **res}


@app.post("/api/treatments/{treatment_id}/apply")
def treatment_apply(treatment_id: int):
    """Mark a suggested treatment as applied today — the other way work leaves the home screen."""
    if not _reasonable(treatment_id):
        return _no_such("treatment")
    try:
        res = cli("treat", "apply", str(treatment_id))
    except RuntimeError as exc:
        detail = str(exc)
        if "No treatment" in detail:
            return JSONResponse({"error": "that treatment is not in the registry"}, status_code=404)
        log.error("treatment apply %s failed: %s", treatment_id, detail)
        return JSONResponse({"error": "the registry could not save that — try again"}, status_code=502)
    return {"ok": True, **res}


@app.post("/api/plants/{plant_id}/photos")
async def add_plant_photos(plant_id: int, request: Request,
                           photos: list[UploadFile] = File(default=[]),
                           note: str = Form(default="")):
    if not _reasonable(plant_id):
        return _no_such("plant")
    """'Here are today's pictures of a plant I already have' — a health re-check, not a new plant."""
    if not rate_ok(client="captures", limit=30):
        return JSONResponse({"error": "Too many photos just now — try again in a minute."},
                            status_code=429)
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        return JSONResponse({"error": "That upload is too big — send at most 6 photos."}, status_code=413)
    try:
        existing = cli("plant", "show", str(plant_id))     # does it exist? (fails cleanly if not)
    except RuntimeError as exc:
        if "No plant" in str(exc):
            return JSONResponse({"error": "unknown plant"}, status_code=404)
        log.error("plant lookup %s failed: %s", plant_id, exc)
        return JSONResponse({"error": "the registry could not answer — try again"}, status_code=502)

    if ((existing.get("plant") or {}).get("status") or "active") in ("removed", "dead"):
        return JSONResponse(
            {"error": "That plant is no longer in the garden, so there is nothing to re-check."},
            status_code=409)

    photos = [p for p in photos if p and p.filename]
    if not photos:
        return JSONResponse({"error": "No photos arrived with that request."}, status_code=400)
    if len(photos) > MAX_FILES:
        return JSONResponse({"error": f"At most {MAX_FILES} photos at a time."}, status_code=400)
    backlog = _backlog_error()
    if backlog is not None:
        return backlog

    tmpdir = Path(tempfile.mkdtemp(prefix="garden-recheck-"))
    try:
        stored, bad = await _collect_photos(photos, tmpdir)
        if bad is not None:
            return bad
        cli_args = ["intake", "capture", "--source=app", f"--plant={plant_id}"]
        for path in stored:
            cli_args.append(f"--file={path}")
        if _clean(note, 600):
            cli_args.append(f"--note={_clean(note, 600)}")
        result = cli(*cli_args)
    except RuntimeError as exc:
        log.error("re-check failed: %s", exc)             # detail stays in the log
        return JSONResponse({"error": "The photos could not be filed — nothing was saved. "
                                      "Try again, or tell Garden Keeper on Telegram."}, status_code=502)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    nudge_worker()
    log.info("re-check intake %s stored (%s photos) for plant %s",
             result["intake_id"], len(stored), plant_id)
    return {"ok": True, "intake_id": result["intake_id"], "plant_id": plant_id,
            "photos": len(stored), "mode": result.get("mode", "recheck")}


def _photo_file(rel: str | None) -> Path | None:
    """Resolve a stored photo path, but only if it really lives inside the photos directory.

    Rows can hold junk, a relative name, or (after a hand-fix or a bug) an absolute path — and
    `PHOTOS / "/etc/passwd"` silently becomes "/etc/passwd". Anything outside the photos dir is
    treated as missing rather than served.
    """
    if not rel:
        return None
    try:
        candidate = (PHOTOS / rel).resolve()
        if not candidate.is_relative_to(PHOTOS.resolve()) or not candidate.is_file():
            return None
    except OSError:
        return None
    return candidate


def _thumbnail(photo_id: int, width: int) -> Path | None:
    """One stored photo, downscaled and cached on disk (phones don't need 2000 px)."""
    try:
        row = cli("photo", "path", str(photo_id))
    except RuntimeError:
        return None
    src = _photo_file(row.get("path"))
    if src is None:
        return None
    THUMBS.mkdir(parents=True, exist_ok=True)
    cache = THUMBS / f"{photo_id}-{width}.jpg"
    try:
        fresh = cache.is_file() and cache.stat().st_mtime >= src.stat().st_mtime
    except OSError:
        fresh = False
    if fresh:
        return cache
    try:
        from PIL import Image, ImageOps
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im)
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            im.thumbnail((width, width), Image.LANCZOS)
            tmp = cache.with_name(f"{cache.name}.{os.getpid()}.tmp")
            im.save(tmp, "JPEG", quality=82, optimize=True)
        os.replace(tmp, cache)                 # atomic: parallel requests never see a half file
        return cache
    except Exception as exc:                   # noqa: BLE001 - any decode failure falls back
        log.warning("thumb %s failed (%s), serving the original", photo_id, exc)
        return src


@app.get("/api/photo/{photo_id}")
def photo(photo_id: int, w: int = 480):
    if not _reasonable(photo_id):
        return JSONResponse({"error": "that photo is not in the registry"}, status_code=404)
    """Serve one stored photo, downscaled. Widths other than 160/240/480/900 fall back to 480."""
    if not rate_ok(client="photos", limit=240):
        return JSONResponse({"error": "too many photo requests just now"}, status_code=429)
    width = w if w in THUMB_SIZES else 480
    served = _thumbnail(photo_id, width)
    if served is None:
        return JSONResponse({"error": "that photo is missing from disk"}, status_code=404)
    return FileResponse(served, media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=604800"})


@app.get("/whoami", response_class=PlainTextResponse)
def whoami(request: Request):
    """Debug helper: which identity did the proxy pass through? (also proves the auth path)"""
    return json.dumps({k: v for k, v in request.headers.items() if k.lower().startswith("tailscale-")},
                      indent=2)


if __name__ == "__main__":
    import uvicorn
    uds = os.environ.get("GARDEN_APP_UDS") or None
    SOCKET_PATH = uds
    if uds:
        Path(uds).parent.mkdir(parents=True, exist_ok=True)
        log.info("listening on unix socket %s", uds)
        uvicorn.run(app, uds=uds, log_level="info", access_log=False,
                    proxy_headers=False, server_header=False)
    else:
        log.info("listening on 127.0.0.1:%s", PORT)
        # proxy_headers=False: the X-Forwarded-For of a request must never decide anything
        # (uvicorn trusts it by default from 127.0.0.1, which is exactly who the proxy is).
        uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info", access_log=False,
                    proxy_headers=False, server_header=False)
