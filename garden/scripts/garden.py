#!/usr/bin/env python3
"""garden.py — the registry CLI for the `garden` Hermes profile.

Everything the garden agent records about the user's garden and pond goes through
this script so the data stays consistent and queryable. Stdlib only.

Data root (default): <this file>/../  ->  garden.db, photos/, exports/
Override with --db or $GARDEN_DB.

Typical calls
  garden.py init
  garden.py plant add --name "Gertrude Jekyll rose" --category rose --botanical "Rosa" \
      --bed "shed border" --prune-months 2 --prune-group 16 --last-pruned 2026-02-10
  garden.py plant list --category rose
  garden.py photo add --plant 3 --file ~/Downloads/leaf.jpg --kind leaf --note "yellow edges"
  garden.py photo assess 5 --diagnosis "magnesium deficiency" --severity low --next-action "foliar feed Epsom salts"
  garden.py treat add --subject plant:3 --type fertiliser --product "Vitax Q4" --dose "handful/m2"
  garden.py task add --title "Cut back lavender" --category prune --subject plant:7 --due 2026-09-27
  garden.py task done 12
  garden.py pond log 1 --ph 7.9 --temp-c 15 --ammonia 0
  garden.py brief --mode weekend
  garden.py stats
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # .../garden/
DB_PATH = Path(os.environ.get("GARDEN_DB") or (ROOT / "garden.db"))
PHOTO_DIR = ROOT / "photos"
EXPORT_DIR = ROOT / "exports"
SCHEMA = ROOT / "schema.sql"

TODAY = lambda: dt.date.today().isoformat()  # noqa: E731

CATEGORIES = [
    "tree", "conifer", "shrub", "rose", "climber", "perennial", "annual", "biennial",
    "bulb", "grass", "fern", "herb", "vegetable", "fruit", "hedge",
    "aquatic", "marginal", "bog", "water_lily", "oxygenator", "floating",
    "houseplant_out", "other",
]

# Where a plant actually lives. Exactly two values: it decides which half of the advice applies
# (frost, hardening off, rain, slugs, wind vs radiators, tap-water hardness, humidity, repotting).
PLACEMENTS = ["indoor", "outdoor"]


def check_placement(value):
    """placement is indoor or outdoor — exactly those two words, wherever the value came from.

    An empty string or the word "null" is refused rather than stored: the app, the brief and every
    rule downstream treat this field as a two-value switch, and a third spelling would quietly read
    as "no rule applies".  Returns the normalised value; callers must store what it returns.
    """
    if value is None:
        return None
    v = str(value).strip().lower()
    if v not in PLACEMENTS:
        sys.exit(f"placement must be '{PLACEMENTS[0]}' or '{PLACEMENTS[1]}' (got {value!r})")
    return v

UK_MONTH_HEADLINES = {
    1: "Deep winter: structural pruning of dormant trees/shrubs, plan the year, protect tender plants, keep pond ice-free (do not smash ice).",
    2: "Late winter: finish winter pruning, cut back grasses/dogwoods, chit early potatoes, divide snowdrops after flowering, start feeding pond fish only if active.",
    3: "Early spring: mulch beds, first feed of the season, prune roses/shrubs, sow hardy annuals, pond pumps/filters back on, start blanketweed watch.",
    4: "Mid spring: mow weekly, feed lawns, plant out hardy veg, deadhead daffodils, divide perennials, pond water tests begin weekly.",
    5: "Late spring: watch for frost (last frost ~mid May here), harden off, plant out tender veg, stake perennials, watch aphids and pond algae.",
    6: "Early summer: deadhead, feed flowering plants, water containers daily, thin fruit, pond water tests, trim hedges (birds nested).",
    7: "Mid summer: deadhead, water, harvest, summer-prune wisteria and trained fruit, net the pond against herons if fish, top up pond with rain water.",
    8: "Late summer: deadhead, cut lavender after flowering, trim evergreen hedges, sow autumn salads, divide bearded iris, keep pond aerated.",
    9: "Early autumn: autumn feed for lawns, plant spring bulbs, sow green manure, tidy pond (remove excess weed before it dies back), collect seeds.",
    10: "Mid autumn: plant bare-root trees/shrubs, cut back tired perennials, clear fallen leaves from the pond (netting), mulch, last lawn feed.",
    11: "Late autumn: leaf clearance, insulate pond/pumps, plant tulips, prune acers/ferns as needed, net pond, hose-tap hygiene.",
    12: "Winter: structural pruning, rose pruning can start after Christmas, protect pots, check pond for ice and gas exchange, order seeds.",
}


# ── plumbing ──────────────────────────────────────────────────────────────────
def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        sys.exit(f"No garden database at {DB_PATH}. Run: garden.py init")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(force: bool = False) -> Path:
    """Create the database if missing and apply schema.sql (idempotent: every statement is
    CREATE ... IF NOT EXISTS, so this also migrates an existing database to the current schema)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists() and force:
        for suffix in ("", "-wal", "-shm"):
            Path(str(DB_PATH) + suffix).unlink(missing_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA.read_text())
    conn.commit()
    conn.close()
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    return DB_PATH


def out(obj, as_json: bool = False):
    if as_json:
        print(json.dumps(obj, indent=2, default=str))
    else:
        if isinstance(obj, (list, tuple)):
            for row in obj:
                print(row if isinstance(row, str) else _fmt_row(row))
        elif isinstance(obj, dict):
            for k, v in obj.items():
                print(f"{k}: {v}")
        else:
            print(obj)


def _fmt_row(row) -> str:
    if isinstance(row, sqlite3.Row):
        return "  ".join(f"{k}={row[k]}" for k in row.keys() if row[k] not in (None, ""))
    return str(row)


def month_set(spec) -> set[int]:
    """'3,4' / '3-4' / '2,7' / '6-9' -> {3,4}. Also accepts 'March'. Returns empty set for None."""
    if spec in (None, ""):
        return set()
    months: set[int] = set()
    for part in str(spec).replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            try:
                a, b = (int(x) for x in part.split("-", 1))
            except ValueError:
                continue
            if a <= b:
                months.update(range(a, b + 1))
            else:  # wrap-around e.g. 11-2
                months.update(list(range(a, 13)) + list(range(1, b + 1)))
        elif part.isdigit():
            months.add(int(part))
    return {m for m in months if 1 <= m <= 12}


def parse_date(value) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def safe_id(value) -> int | None:
    """A row id we can actually hand to SQLite, or None.

    Anything non-numeric, zero/negative, or past SQLite's 64-bit integer range cannot match a row —
    and passing it straight to a query makes sqlite3 raise OverflowError, so a typo like #99999999999999999999
    crashed the CLI instead of reading as "no such row".
    """
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if 0 < n <= 2 ** 63 - 1 else None


def resolve_plant(conn, ref: str):
    """Accept an id (3), 'plant:3', or a name fragment ('gertrude')."""
    if ref is None:
        return None
    s = str(ref).strip()
    if s.lower().startswith("plant:"):
        s = s.split(":", 1)[1]
    if s.isdigit():
        row_id = safe_id(s)
        row = conn.execute("SELECT * FROM plants WHERE id=?", (row_id,)).fetchone() if row_id else None
        if not row:
            sys.exit(f"No plant #{s}")
        return row
    like = f"%{s.lower()}%"
    rows = conn.execute(
        "SELECT * FROM plants WHERE lower(name) LIKE ? OR lower(coalesce(common_name,'')) LIKE ?"
        " OR lower(coalesce(botanical,'')) LIKE ? ORDER BY status='active' DESC, id LIMIT 2",
        (like, like, like),
    ).fetchall()
    if not rows:
        sys.exit(f"No plant matches {ref!r}")
    if len(rows) > 1:
        sys.exit("Ambiguous plant ref %r: matches %s" % (ref, [f"{r['id']}:{r['name']}" for r in rows]))
    return rows[0]


def subject_ref(conn, ref: str) -> str:
    """Normalise a subject to 'plant:<id>' / 'pond:<id>' / free text."""
    if not ref:
        return ""
    s = str(ref).strip()
    low = s.lower()
    if low.startswith(("plant:", "pond:", "bed:", "garden", "lawn")):
        if low.startswith("plant:"):
            p = resolve_plant(conn, s)
            return f"plant:{p['id']}"
        if low.startswith("pond:"):
            pid = s.split(":", 1)[1]
            return f"pond:{pid}"
        return s
    if s.isdigit():
        return f"plant:{resolve_plant(conn, s)['id']}"
    p = resolve_plant(conn, s)
    return f"plant:{p['id']}"


def insert(conn, table: str, data: dict, *, commit: bool = True) -> int:
    cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})")]
    if not cols:
        sys.exit(f"Table {table!r} does not exist in {DB_PATH} — run: garden.py init")
    data = {k: v for k, v in data.items() if k in cols and v is not None}
    if "created_at" in cols:
        data.setdefault("created_at", dt.datetime.now().isoformat(timespec="seconds"))
    keys = list(data)
    sql = f"INSERT INTO {table} ({','.join(keys)}) VALUES ({','.join('?' * len(keys))})"
    cur = conn.execute(sql, [data[k] for k in keys])
    if commit:
        conn.commit()
    return cur.lastrowid


def update_row(conn, table: str, row_id: int, data: dict) -> int:
    cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})")]
    data = {k: v for k, v in data.items() if k in cols and v is not None}
    if not data:
        return 0
    sets = ",".join(f"{k}=?" for k in data)
    cur = conn.execute(f"UPDATE {table} SET {sets} WHERE id=?", [*data.values(), row_id])
    conn.commit()
    return cur.rowcount


def kv_pairs(items) -> dict:
    """--set key=value pairs plus argparse dests."""
    d = {}
    for item in items or []:
        if "=" not in item:
            sys.exit(f"--set expects key=value, got {item!r}")
        k, v = item.split("=", 1)
        d[k.strip()] = v.strip()
    return d


# ── photo storage (shared by `photo add` and `intake capture`) ───────────────
def store_photo(conn, src, *, plant_id=None, pond_id=None, kind="whole", taken_on=None,
                note=None, next_action=None, subject=None, ext=None, commit=True) -> dict:
    """Copy one image into photos/ and record it. Returns the new photos row id + stored path."""
    src = Path(src).expanduser()
    if not src.exists():
        sys.exit(f"No such photo: {src}")
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    stamp = taken_on or TODAY()
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", src.stem)[:60] or "photo"
    tag = f"plant{plant_id}" if plant_id else (f"pond{pond_id}" if pond_id else "garden")
    suffix = ext or src.suffix.lower() or ".jpg"
    if suffix == ".jpeg":
        suffix = ".jpg"
    dest_name = f"{stamp}_{tag}_{safe}{suffix}"
    dest = PHOTO_DIR / dest_name
    if dest.exists():
        dest = PHOTO_DIR / f"{stamp}_{tag}_{safe}-{dt.datetime.now().strftime('%H%M%S')}{suffix}"
        dest_name = dest.name
    shutil.copy2(src, dest)
    pid = insert(conn, "photos", {
        "plant_id": plant_id, "pond_id": pond_id, "subject": subject or None,
        "path": dest_name, "kind": kind, "taken_on": taken_on,
        "added_at": dt.datetime.now().isoformat(timespec="seconds"),
        "user_note": note, "next_action": next_action,
    }, commit=commit)
    return {"photo_id": pid, "stored": str(dest), "file": dest_name, "kind": kind}


# ── command handlers ─────────────────────────────────────────────────────────
def cmd_plant(args):
    conn = connect()
    if args.plant_cmd == "add":
        if args.category and args.category not in CATEGORIES:
            print(f"⚠ category {args.category!r} is not in the standard list; saved anyway. "
                  f"Standard: {', '.join(CATEGORIES)}", file=sys.stderr)
        data = {
            "name": args.name, "common_name": args.common_name, "botanical": args.botanical,
            "cultivar": args.cultivar, "category": args.category, "subtype": args.subtype,
            "bed": args.bed, "position": args.position, "aspect": args.aspect, "soil": args.soil,
            "placement": check_placement(args.placement),
            "in_container": 1 if args.container else None, "pot_size_cm": args.pot_size,
            "planted_on": args.planted_on, "acquired_from": args.acquired_from,
            "height_cm": args.height, "spread_cm": args.spread, "hardiness": args.hardiness,
            "uk_native": 1 if args.native else None, "wildlife": args.wildlife,
            "flower_months": args.flower_months, "scent": args.scent, "prune_group": args.prune_group,
            "prune_months": args.prune_months, "prune_method": args.prune_method,
            "last_pruned": args.last_pruned, "cut_back_by": args.cut_back_by,
            "feed_months": args.feed_months, "feed_product": args.feed_product,
            "water_needs": args.water_needs, "mulch": args.mulch, "pests_known": args.pests,
            "toxicity": args.toxicity, "health_status": args.health, "notes": args.notes,
            "created_at": dt.datetime.now().isoformat(timespec="seconds"), "updated_at": TODAY(),
        }
        data.update(kv_pairs(args.set))
        data["placement"] = check_placement(data.get("placement"))
        pid = insert(conn, "plants", data)
        out({"plant_id": pid, "name": args.name, "registered": True}, args.json)
    elif args.plant_cmd == "list":
        q = "SELECT * FROM plants WHERE 1=1"
        params: list = []
        if args.category:
            q += " AND category=?"; params.append(args.category)
        if args.bed:
            q += " AND bed LIKE ?"; params.append(f"%{args.bed}%")
        if not args.all:
            q += " AND status='active'"
        q += " ORDER BY category, bed, name"
        rows = conn.execute(q, params).fetchall()
        if args.json:
            out([dict(r) for r in rows], True)
        else:
            if not rows:
                print("(no plants registered)")
            for r in rows:
                print(f"[{r['id']:>3}] {r['name']:<34} {r['category'] or '?':<12} "
                      f"{(r['bed'] or '-'):<20} {r['placement'] or 'in/out not set':<16} "
                      f"prune:{r['prune_months'] or '-':<6} "
                      f"fed:{r['feed_months'] or '-':<6} health:{r['health_status'] or '-'}")
    elif args.plant_cmd == "show":
        p = resolve_plant(conn, args.ref)
        if args.json:
            extra = {
                "photos": [dict(r) for r in conn.execute(
                    "SELECT id,path,kind,taken_on,added_at,user_note,assessment,next_action "
                    "FROM photos WHERE plant_id=? ORDER BY id DESC", (p["id"],))],
                "treatments": [dict(r) for r in conn.execute(
                    "SELECT id,date,type,product,dose,status,next_due FROM treatments WHERE subject=? ORDER BY date DESC", (f"plant:{p['id']}",))],
                "observations": [dict(r) for r in conn.execute(
                    "SELECT id,date,kind,severity,description,photo_id FROM observations WHERE subject=? ORDER BY date DESC", (f"plant:{p['id']}",))],
                "tasks": [dict(r) for r in conn.execute(
                    "SELECT id,title,detail,category,due_on,window_end,status,priority,recurrence,est_minutes "
                    "FROM tasks WHERE subject=? AND status='open' ORDER BY coalesce(due_on,'9999'), id", (f"plant:{p['id']}",))],
            }
            out({"plant": dict(p), **extra}, True)
        else:
            for k in p.keys():
                if p[k] not in (None, ""):
                    print(f"  {k:<14} {p[k]}")
            if not p["placement"]:
                # never let a missing value read as "no rule applies"
                print(f"  {'placement':<14} NOT SET — decide indoor or outdoor "
                      f"(plant update {p['id']} --placement …), it decides which rules apply")
            print("  --- photos ---")
            for r in conn.execute("SELECT id,path,kind,taken_on,next_action FROM photos WHERE plant_id=? ORDER BY id DESC LIMIT 5", (p["id"],)):
                print(f"  #{r['id']} {r['taken_on']} {r['kind']} {r['path']} {r['next_action'] or ''}")
            print("  --- treatments ---")
            for r in conn.execute("SELECT id,date,type,product,dose FROM treatments WHERE subject=? ORDER BY date DESC LIMIT 8", (f"plant:{p['id']}",)):
                print(f"  #{r['id']} {r['date']} {r['type']} {r['product']} {r['dose']}")
            print("  --- open tasks ---")
            for r in conn.execute("SELECT id,title,due_on,priority FROM tasks WHERE subject=? AND status='open'", (f"plant:{p['id']}",)):
                print(f"  #{r['id']} {r['due_on']} [{r['priority']}] {r['title']}")
    elif args.plant_cmd == "update":
        p = resolve_plant(conn, args.ref)
        data = kv_pairs(args.set)
        data["placement"] = check_placement(data.get("placement"))
        if args.pruned_on:
            data["last_pruned"] = args.pruned_on
        if args.health:
            data["health_status"] = args.health
        if args.status:
            data["status"] = args.status
        if args.notes:
            data["notes"] = args.notes
        if args.placement:
            data["placement"] = check_placement(args.placement)
        data["updated_at"] = TODAY()
        n = update_row(conn, "plants", p["id"], data)
        out({"plant_id": p["id"], "fields_updated": sorted(k for k in data if k != "updated_at"), "rows": n}, args.json)
    elif args.plant_cmd == "due":
        rows = pruning_due(conn, horizon=args.days)
        if args.json:
            out(rows, True)
        else:
            if not rows:
                print("(nothing in a pruning window in the next %d days)" % args.days)
            for r in rows:
                print(f"[{r['id']:>3}] {r['name']:<32} window {r['month']:02d} "
                      f"{r['placement'] or 'IN/OUT NOT SET'} "
                      f"group {r['prune_group'] or '-'} last cut {r['last_pruned'] or 'never'}  "
                      f"{(r['prune_method'] or '')[:60]}")


def pruning_due(conn, horizon: int = 14, ref_date: dt.date | None = None) -> list[dict]:
    """Active plants whose prune_months fall inside [today, today+horizon] and that
    have not already been cut in this calendar year (or last year's window for winter work)."""
    ref = ref_date or dt.date.today()
    days = [(ref + dt.timedelta(days=i)) for i in range(horizon + 1)]
    out_rows = []
    for p in conn.execute("SELECT * FROM plants WHERE status='active' AND prune_months IS NOT NULL").fetchall():
        months = month_set(p["prune_months"])
        for d in days:
            if d.month not in months:
                continue
            lp = parse_date(p["last_pruned"])
            # already cut for the current season? (cut on/after the 1st of this window's month)
            if lp and lp >= dt.date(d.year, d.month, 1) and lp <= d:
                continue
            out_rows.append({**dict(p), "month": d.month, "window_start": d.isoformat()})
            break
    return out_rows


def feeding_due(conn, horizon: int = 14, ref_date: dt.date | None = None) -> list[dict]:
    ref = ref_date or dt.date.today()
    days = [(ref + dt.timedelta(days=i)) for i in range(horizon + 1)]
    rows = []
    for p in conn.execute("SELECT * FROM plants WHERE status='active' AND feed_months IS NOT NULL").fetchall():
        months = month_set(p["feed_months"])
        hit = next((d for d in days if d.month in months), None)
        if not hit:
            continue
        last = conn.execute(
            "SELECT date, product, dose FROM treatments WHERE subject=? AND type IN "
            "('fertiliser','feed','foliar_feed','mulch','compost','tonic') AND status='applied' "
            "ORDER BY date DESC LIMIT 1", (f"plant:{p['id']}",)).fetchone()
        if last and last["date"] and parse_date(last["date"]) and parse_date(last["date"]) > hit - dt.timedelta(days=28):
            continue  # fed within the last month, don't nag
        rows.append({**dict(p), "month": hit.month, "window_start": hit.isoformat(),
                     "last_feed": last["date"] if last else None,
                     "last_product": last["product"] if last else None})
    return rows


def due_state(due_on, ref: dt.date | None = None, horizon: int = 7) -> str:
    """overdue | due | scheduled | anytime — the words the app colours rows with."""
    if not due_on:
        return "anytime"
    ref = ref or dt.date.today()
    if due_on < ref.isoformat():
        return "overdue"
    return "due" if due_on <= (ref + dt.timedelta(days=horizon)).isoformat() else "scheduled"


def pending_work(conn, horizon: int = 7, ref_date: dt.date | None = None) -> list[dict]:
    """Everything waiting on the user's hand, from ONE place.

    The same three sources the brief lists — open tasks, observation follow-ups not yet done,
    and treatments suggested but not applied — so the app's home screen and the agent's digest
    cannot disagree about what a plant is waiting for. Undated work is 'anytime': real, but it
    never makes a plant look urgent.
    """
    ref = ref_date or dt.date.today()
    rank = {"high": 0, "normal": 1, "low": 2}
    items: list[dict] = []
    for r in conn.execute("SELECT id, subject, title, due_on, priority FROM tasks WHERE status='open'"):
        items.append({"kind": "task", "icon": "📌", "ref": r["id"], "subject": r["subject"],
                      "title": r["title"], "due_on": r["due_on"], "priority": r["priority"] or "normal"})
    for r in conn.execute("SELECT id, subject, follow_up_on, description FROM observations "
                          "WHERE follow_up_on IS NOT NULL AND coalesce(follow_up_done, 0) = 0"):
        # an observation's description is prose written for the plant page, not a card title:
        # drop the "Photo #n: " prefix and keep it to one readable line
        text = str(r["description"] or "").strip()
        if text.startswith("Photo #") and ": " in text:
            text = text.split(": ", 1)[1]
        text = text or "Check the follow-up"
        items.append({"kind": "check", "icon": "🔍", "ref": r["id"], "subject": r["subject"],
                      "title": text[:88], "due_on": r["follow_up_on"], "priority": "normal"})
    for r in conn.execute("SELECT id, subject, type, product, next_due FROM treatments WHERE status='suggested'"):
        items.append({"kind": "feed", "icon": "🌱", "ref": r["id"], "subject": r["subject"],
                      "title": f"{r['type'] or 'treatment'} suggested: {r['product'] or 'not applied yet'}",
                      "due_on": r["next_due"], "priority": "normal"})

    per_plant: dict[int, list[dict]] = {}
    for it in items:
        subject = it["subject"] or ""
        if not subject.startswith("plant:"):
            continue                       # pond/bed/lawn work is not a plant card
        try:
            pid = int(subject.split(":", 1)[1])
        except ValueError:
            continue
        per_plant.setdefault(pid, []).append(it)

    out_rows = []
    for row in conn.execute("SELECT id, name, placement, health_status, status FROM plants"):
        if row["status"] in ("removed", "dead"):
            continue
        mine = per_plant.get(row["id"], [])
        for it in mine:
            it["state"] = due_state(it["due_on"], ref, horizon)
        mine.sort(key=lambda t: (t["due_on"] or "9999-99-99", rank.get(t["priority"], 1), t["kind"]))
        dated = [t for t in mine if t["due_on"]]
        nxt = mine[0] if mine else {}
        out_rows.append({
            "plant_id": row["id"], "name": row["name"], "placement": row["placement"],
            "health_status": row["health_status"], "status": row["status"],
            "open": len(mine),
            "overdue": sum(1 for t in dated if t["state"] == "overdue"),
            "due_soon": sum(1 for t in dated if t["state"] == "due"),
            "next": ({k: nxt.get(k) for k in ("kind", "icon", "ref", "title", "due_on", "state", "priority")}
                     if nxt else None),
            "items": mine,
        })
    out_rows.sort(key=lambda p: (-p["overdue"], -p["due_soon"], (p["name"] or "").lower()))
    return out_rows


def photo_requests(conn, stale_days: int = 45, limit: int = 4) -> list[dict]:
    cutoff = (dt.date.today() - dt.timedelta(days=stale_days)).isoformat()
    rows = []
    for p in conn.execute("SELECT * FROM plants WHERE status='active'").fetchall():
        last = conn.execute(
            "SELECT id, taken_on, added_at, kind, assessment FROM photos WHERE plant_id=? "
            "ORDER BY coalesce(taken_on, added_at) DESC LIMIT 1", (p["id"],)).fetchone()
        stamp = (last["taken_on"] or last["added_at"]) if last else None
        if last is None or (stamp and stamp[:10] < cutoff):
            rows.append({"id": p["id"], "name": p["name"], "category": p["category"],
                         "bed": p["bed"], "placement": p["placement"], "last_photo": stamp, "health": p["health_status"]})
    rows.sort(key=lambda r: (r["last_photo"] is not None, r["last_photo"] or ""))
    return rows[:limit]


def generate_tasks(conn, horizon: int = 14) -> list[dict]:
    """Materialise rule-derived work items as tasks (idempotent via rule_key)."""
    created = []
    today = dt.date.today()
    year = today.year

    def ensure(rule_key, **task):
        exists = conn.execute("SELECT id FROM tasks WHERE rule_key=?", (rule_key,)).fetchone()
        if exists:
            return
        task.setdefault("source", "rule")
        task["rule_key"] = rule_key
        task.setdefault("created_at", dt.datetime.now().isoformat(timespec="seconds"))
        created.append({"task_id": insert(conn, "tasks", task), "title": task["title"], **task})

    for p in pruning_due(conn, horizon=horizon):
        ensure(f"prune:{p['id']}:{year}:{p['month']}",
               title=f"Cut back {p['name']}", category="prune", subject=f"plant:{p['id']}",
               due_on=p["window_start"], window_end=(today + dt.timedelta(days=horizon)).isoformat(),
               priority="high" if p["month"] in (today.month, today.month + 1) else "normal",
               detail=(p["prune_method"] or "") + (f" (RHS group {p['prune_group']})" if p["prune_group"] else ""),
               est_minutes=30)
    for p in feeding_due(conn, horizon=horizon):
        ensure(f"feed:{p['id']}:{year}:{p['month']}",
               title=f"Feed {p['name']}", category="feed", subject=f"plant:{p['id']}",
               due_on=p["window_start"], priority="normal",
               detail=(p["feed_product"] or "check the feeding plan"), est_minutes=15)
    for p in photo_requests(conn, limit=3):
        ensure(f"photo:{p['id']}:{today.strftime('%Y-%m')}",
               title=f"Photo check: {p['name']}", category="photo", subject=f"plant:{p['id']}",
               due_on=(today + dt.timedelta(days=3)).isoformat(), priority="low",
               detail="Ask the user for a fresh whole-plant + leaf close-up photo.", est_minutes=5)
    # pond: weekly water test through the growing season
    for pond in conn.execute("SELECT * FROM ponds").fetchall():
        if 4 <= today.month <= 10:
            last = conn.execute("SELECT date FROM pond_readings WHERE pond_id=? ORDER BY date DESC LIMIT 1",
                                (pond["id"],)).fetchone()
            if not last or (parse_date(last["date"]) or today) < today - dt.timedelta(days=6):
                ensure(f"pond_test:{pond['id']}:{today.isocalendar()[1]}:{year}",
                       title=f"Test {pond['name']} water (pH, ammonia, nitrite, nitrate, temp)",
                       category="pond", subject=f"pond:{pond['id']}",
                       due_on=today.isoformat(), window_end=(today + dt.timedelta(days=2)).isoformat(),
                       priority="normal", detail="Weekly during the growing season.", est_minutes=15)
    return created


def stored_photo(rel: str | None) -> Path | None:
    """The file behind a stored photo path — only if it really lives inside PHOTO_DIR.

    `PHOTO_DIR / "/etc/hostname"` is `/etc/hostname`, so a row holding an absolute path (hand-edit,
    bad migration) would otherwise be reported as a perfectly good cover that the app then refuses
    to serve. Same rule as the app's `_photo_file()`.
    """
    if not rel:
        return None
    try:
        candidate = (PHOTO_DIR / rel).resolve()
        if not candidate.is_relative_to(PHOTO_DIR.resolve()) or not candidate.is_file():
            return None
    except OSError:
        return None
    return candidate


def cmd_photo(args):
    conn = connect()
    if args.photo_cmd == "add":
        subject = subject_ref(conn, args.plant or args.subject) if (args.plant or args.subject) else ""
        plant_id = None
        if subject.startswith("plant:"):
            plant_id = int(subject.split(":")[1])
        pond_id = None
        if args.pond:
            pond_id = int(str(args.pond).split(":")[-1])
            subject = f"pond:{pond_id}"
        res = store_photo(conn, args.file, plant_id=plant_id, pond_id=pond_id, kind=args.kind,
                          taken_on=args.taken_on, note=args.note, next_action=args.next_action,
                          subject=subject or None)
        out({**res, "subject": subject}, args.json)
    elif args.photo_cmd == "assess":
        if not safe_id(args.photo_id):
            sys.exit(f"No photo #{args.photo_id}")
        data = {"assessment": args.assessment, "diagnosis": args.diagnosis,
                "severity": args.severity, "next_action": args.next_action,
                "follow_up_on": args.follow_up, "model": args.model}
        n = update_row(conn, "photos", args.photo_id, data)
        if args.follow_up:
            row = conn.execute("SELECT * FROM photos WHERE id=?", (args.photo_id,)).fetchone()
            insert(conn, "observations", {
                "subject": row["subject"] or (f"plant:{row['plant_id']}" if row["plant_id"] else ""),
                "date": TODAY(), "kind": "other", "severity": args.severity,
                "description": f"Photo #{args.photo_id}: {args.diagnosis or args.assessment or ''}",
                "photo_id": args.photo_id, "follow_up_on": args.follow_up,
            })
        out({"photo_id": args.photo_id, "updated": n}, args.json)
    elif args.photo_cmd == "list":
        q = ("SELECT id, plant_id, subject, path, kind, taken_on, added_at, user_note, assessment, "
             "diagnosis, severity, next_action, follow_up_on FROM photos WHERE 1=1")
        params: list = []
        if args.plant:
            params.append(resolve_plant(conn, args.plant)["id"])
            q += " AND plant_id=?"
        q += " ORDER BY id DESC"
        if args.limit:
            params.append(args.limit); q += " LIMIT ?"
        rows = conn.execute(q, params).fetchall()
        if args.json:
            out([dict(r) for r in rows], True)
        else:
            for r in rows:
                print(f"#{r['id']:>3} {r['taken_on'] or r['added_at'] or '':<11} plant:{r['plant_id'] or '-':<4} "
                      f"{r['kind'] or '':<14} {r['path']}\n     → {r['diagnosis'] or r['next_action'] or '(not assessed)'}")
    elif args.photo_cmd == "summary":
        # One row per plant: how many photos it has and which one to show as its cover. The cover is
        # the newest photo whose FILE still exists, so a plant never gets a broken thumbnail just
        # because one image went missing from disk. This is what the app's plant list reads — a
        # fixed-width `photo list` window would lose the cover and the count of older plants.
        rows = conn.execute(
            "SELECT plant_id, COUNT(*) AS photos FROM photos WHERE plant_id IS NOT NULL GROUP BY plant_id"
        ).fetchall()
        summaries = []
        for r in rows:
            shots = conn.execute(
                "SELECT id, path, coalesce(taken_on, added_at) AS shot_on FROM photos "
                "WHERE plant_id=? ORDER BY coalesce(taken_on, added_at) DESC, id DESC",
                (r["plant_id"],)).fetchall()
            cover = next((c["id"] for c in shots if stored_photo(c["path"])), None)
            summaries.append({"plant_id": r["plant_id"], "photos": r["photos"], "cover_photo_id": cover,
                              "latest_on": shots[0]["shot_on"] if shots else None})
        if args.json:
            out(summaries, True)
        else:
            for s in summaries:
                print(f"plant:{s['plant_id']:<4} photos:{s['photos']:<4} cover:{s['cover_photo_id'] or '-':<5} {s['latest_on'] or ''}")
    elif args.photo_cmd == "path":
        pid = safe_id(args.photo_id)
        row = conn.execute("SELECT * FROM photos WHERE id=?", (pid,)).fetchone() if pid else None
        if not row:
            sys.exit(f"No photo #{args.photo_id}")
        if args.json:
            out({"photo_id": row["id"], "path": row["path"],
                 "abs_path": str(PHOTO_DIR / row["path"])}, True)
        else:
            print(PHOTO_DIR / row["path"])


def cmd_obs(args):
    conn = connect()
    if args.obs_cmd == "follow-up-done":
        # a follow-up the user has done — the home screen keeps showing it until this is recorded,
        # so nothing in the app may leave it owed for ever
        oid = safe_id(args.id)
        row = conn.execute("SELECT * FROM observations WHERE id=?", (oid,)).fetchone() if oid else None
        if not row:
            sys.exit(f"No observation #{args.id}")
        if not row["follow_up_on"]:
            out({"observation_id": row["id"], "cleared": False,
                 "note": "this observation has no follow-up on it"}, args.json)
            return
        if row["follow_up_done"]:
            out({"observation_id": row["id"], "cleared": False, "already_done": True,
                 "follow_up_on": row["follow_up_on"]}, args.json)
            return
        conn.execute("UPDATE observations SET follow_up_done=1 WHERE id=?", (row["id"],))
        conn.commit()
        out({"observation_id": row["id"], "cleared": True, "was_due": row["follow_up_on"]}, args.json)
        return
    if args.obs_cmd == "add":
        subject = subject_ref(conn, args.subject)
        oid = insert(conn, "observations", {
            "subject": subject, "date": args.date or TODAY(), "kind": args.kind,
            "severity": args.severity, "description": args.description,
            "photo_id": args.photo, "follow_up_on": args.follow_up,
        })
        out({"observation_id": oid, "subject": subject}, args.json)
    else:
        q = "SELECT * FROM observations WHERE 1=1"
        params: list = []
        if args.subject:
            params.append(subject_ref(conn, args.subject)); q += " AND subject=?"
        if args.open_followups:
            q += " AND follow_up_on IS NOT NULL AND coalesce(follow_up_done,0)=0"
        q += " ORDER BY date DESC LIMIT ?"
        params.append(args.limit)
        rows = conn.execute(q, params).fetchall()
        if args.json:
            out([dict(r) for r in rows], True)
        else:
            for r in rows:
                print(f"#{r['id']:>3} {r['date']:<11} {r['subject']:<12} {r['kind'] or '':<12} "
                      f"{r['severity'] or '':<7} {(r['description'] or '')[:90]}"
                      f"{'  ↳ follow-up ' + r['follow_up_on'] if r['follow_up_on'] and not r['follow_up_done'] else ''}")


def cmd_treat(args):
    conn = connect()
    if args.treat_cmd == "apply":
        tid = safe_id(args.id)
        row = conn.execute("SELECT * FROM treatments WHERE id=?", (tid,)).fetchone() if tid else None
        if not row:
            sys.exit(f"No treatment #{args.id}")
        if row["status"] == "applied":
            out({"treatment_id": row["id"], "applied": False, "already_applied": True,
                 "date": row["date"]}, args.json)
            return
        data = {"status": "applied"}
        if not row["date"]:
            data["date"] = TODAY()          # applying it now is the day it was applied
        update_row(conn, "treatments", row["id"], data)
        out({"treatment_id": row["id"], "applied": True, "date": data.get("date") or row["date"],
             "was": row["status"]}, args.json)
        return
    if args.treat_cmd == "add":
        subject = subject_ref(conn, args.subject) if args.subject else ""
        tid = insert(conn, "treatments", {
            "subject": subject, "date": args.date or (None if args.status == "suggested" else TODAY()),
            "type": args.type, "product": args.product, "brand": args.brand, "npk": args.npk,
            "analysis": args.analysis, "dose": args.dose, "dilution": args.dilution, "method": args.method,
            "area": args.area, "quantity": args.quantity, "weather": args.weather,
            "applied_by": args.applied_by, "recommended_by": args.recommended_by, "reason": args.reason,
            "status": args.status, "next_due": args.next_due, "outcome": args.outcome, "notes": args.notes,
        })
        if args.type in ("fertiliser", "feed", "foliar_feed", "mulch", "compost") and args.status == "applied" \
                and subject.startswith("plant:"):
            conn.execute("UPDATE plants SET updated_at=? WHERE id=?", (TODAY(), int(subject.split(":")[1])))
            conn.commit()
        out({"treatment_id": tid, "subject": subject, "status": args.status}, args.json)
    elif args.treat_cmd == "list":
        q = "SELECT * FROM treatments WHERE 1=1"
        params: list = []
        if args.subject:
            params.append(subject_ref(conn, args.subject)); q += " AND subject=?"
        if args.since:
            params.append(args.since); q += " AND date>=?"
        if args.type:
            params.append(args.type); q += " AND type=?"
        if args.status:
            params.append(args.status); q += " AND status=?"
        q += " ORDER BY coalesce(date, created_at) DESC LIMIT ?"
        params.append(args.limit)
        rows = conn.execute(q, params).fetchall()
        if args.json:
            out([dict(r) for r in rows], True)
        else:
            for r in rows:
                print(f"#{r['id']:>3} {str(r['date'] or '(suggested)'):<11} {r['subject']:<12} {r['type'] or '':<18} "
                      f"{(r['product'] or ''):<24} {(r['dose'] or ''):<20} {r['status'] or ''}"
                      f"{'  ↳ next ' + r['next_due'] if r['next_due'] else ''}")
    elif args.treat_cmd == "due":
        rows = conn.execute(
            "SELECT * FROM treatments WHERE next_due IS NOT NULL AND next_due<=? AND status!='cancelled' "
            "ORDER BY next_due", ((dt.date.today() + dt.timedelta(days=args.days)).isoformat(),)).fetchall()
        if args.json:
            out([dict(r) for r in rows], True)
        else:
            for r in rows:
                print(f"#{r['id']:>3} due {r['next_due']} {r['subject']} {r['type']} {r['product']}")
    elif args.treat_cmd == "update":
        data = kv_pairs(args.set)
        if args.status:
            data["status"] = args.status
        if args.date:
            data["date"] = args.date
        out({"updated": update_row(conn, "treatments", args.id, data)}, args.json)


def cmd_task(args):
    conn = connect()
    if args.task_cmd == "add":
        subject = subject_ref(conn, args.subject) if args.subject else None
        tid = insert(conn, "tasks", {
            "title": args.title, "detail": args.detail, "category": args.category, "subject": subject,
            "due_on": args.due or TODAY(), "window_end": args.window_end, "priority": args.priority,
            "recurrence": args.recurrence, "est_minutes": args.minutes, "source": "agent" if args.agent else "user",
        })
        out({"task_id": tid, "title": args.title, "due_on": args.due or TODAY()}, args.json)
    elif args.task_cmd == "list":
        q = "SELECT * FROM tasks WHERE 1=1"
        params: list = []
        if args.status:
            params.append(args.status); q += " AND status=?"
        if args.due_before:
            params.append(args.due_before); q += " AND due_on<=?"
        if args.subject:
            params.append(subject_ref(conn, args.subject)); q += " AND subject=?"
        if args.category:
            params.append(args.category); q += " AND category=?"
        q += " ORDER BY coalesce(due_on, '9999'), CASE priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END, id"
        rows = conn.execute(q, params).fetchall()
        if args.json:
            out([dict(r) for r in rows], True)
        else:
            if not rows:
                print("(no tasks)")
            for r in rows:
                flag = "!" if r["priority"] == "high" else " "
                print(f"[{r['id']:>3}]{flag} {str(r['due_on'] or ''):<11} {r['status']:<7} {r['category'] or '':<9} "
                      f"{r['title']}  {r['subject'] or ''}")
    elif args.task_cmd in ("done", "skip"):
        tid = safe_id(args.id)
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone() if tid else None
        if not row:
            sys.exit(f"No task #{args.id}")
        status = "done" if args.task_cmd == "done" else "skipped"
        # Closing a task is idempotent. Without this guard a second tap (two devices, a retry, an
        # impatient double-press) spawned a SECOND copy of a recurring task — the same job then
        # appeared twice in the weekend plan — and rewrote completed_on with today's date.
        late = (args.note or "").strip()
        if row["status"] in ("done", "skipped"):
            # …but a NOTE arriving with a second tap is new information: the user wrote what changed
            # and the app promised to keep it. Record it once (an identical repeat is a no-op) rather
            # than reporting success over a silently dropped note.
            obs_id, recorded = None, False
            if late and late not in (row["notes"] or ""):
                update_row(conn, "tasks", args.id, {"notes": (row["notes"] or "") + f" | {late}"})
                recorded = True
                if row["status"] == "done" and str(row["subject"] or "").startswith("plant:"):
                    obs_id = insert(conn, "observations", {
                        "subject": row["subject"], "date": TODAY(), "kind": "maintenance",
                        "description": f"{row['title']} — {late}"})
            out({"task_id": args.id, "status": row["status"], "already_closed": True,
                 "completed_on": row["completed_on"], "note": late or None,
                 "note_recorded": recorded, "observation_id": obs_id,
                 "next_occurrence": None}, args.json)
            return
        note = late
        update_row(conn, "tasks", args.id, {"status": status, "completed_on": TODAY(),
                                            "notes": (row["notes"] or "") + (f" | {note}" if note else "")})
        # A note on a task the user has actually DONE is feedback they took the trouble to write:
        # it belongs in the plant's history, where the agent reads it, not only on a closed task row
        # that no digest lists. Skips are not work done, so they get no observation.
        obs_id = None
        if status == "done" and note and str(row["subject"] or "").startswith("plant:"):
            obs_id = insert(conn, "observations", {
                "subject": row["subject"], "date": TODAY(), "kind": "maintenance",
                "description": f"{row['title']} — {note}"})
        made = []
        rec = row["recurrence"]
        if status == "done" and rec:
            nxt = None
            if rec == "weekly":
                nxt = (parse_date(row["due_on"]) or dt.date.today()) + dt.timedelta(days=7)
            elif rec == "monthly":
                nxt = (parse_date(row["due_on"]) or dt.date.today()) + dt.timedelta(days=30)
            elif rec.startswith("annual"):
                nxt = (parse_date(row["due_on"]) or dt.date.today()).replace(year=(parse_date(row["due_on"]) or dt.date.today()).year + 1)
            if nxt:
                tid = insert(conn, "tasks", {"title": row["title"], "detail": row["detail"],
                                             "category": row["category"], "subject": row["subject"],
                                             "due_on": nxt.isoformat(), "priority": row["priority"],
                                             "recurrence": rec, "source": "rule"})
                made.append(tid)
        out({"task_id": args.id, "status": status, "note": note or None,
             "observation_id": obs_id, "next_occurrence": made or None}, args.json)
    elif args.task_cmd == "update":
        out({"updated": update_row(conn, "tasks", args.id, kv_pairs(args.set))}, args.json)
    elif args.task_cmd == "generate":
        created = generate_tasks(conn, horizon=args.days)
        if args.json:
            out(created, True)
        else:
            if not created:
                print("(nothing new to schedule)")
            for c in created:
                print(f"+ task #{c['task_id']}: {c['title']} (due {c['due_on']})")


def cmd_pond(args):
    conn = connect()
    if args.pond_cmd == "add":
        pid = insert(conn, "ponds", {
            "name": args.name, "kind": args.kind, "volume_litres": args.volume,
            "surface_m2": args.surface, "max_depth_cm": args.depth, "shallows_cm": args.shallows,
            "liner": args.liner, "pump": args.pump, "filter": args.filter, "uv": args.uv,
            "aeration": args.aeration, "fish": args.fish, "aquatics": args.aquatics,
            "margin_plants": args.margin, "wildlife": args.wildlife, "sun_exposure": args.sun,
            "leaves_ingress": args.leaves, "established": args.established, "notes": args.notes,
        })
        out({"pond_id": pid, "name": args.name}, args.json)
    elif args.pond_cmd == "show":
        p = conn.execute("SELECT * FROM ponds WHERE id=?", (args.id,)).fetchone()
        if not p:
            sys.exit(f"No pond #{args.id}")
        if args.json:
            out(dict(p), True)
        else:
            for k in p.keys():
                if p[k] not in (None, ""):
                    print(f"  {k:<16} {p[k]}")
    elif args.pond_cmd == "list":
        rows = conn.execute("SELECT * FROM ponds").fetchall()
        out([dict(r) for r in rows] if args.json else [f"[{r['id']}] {r['name']} ({r['kind']}) {r['volume_litres'] or '?'} L" for r in rows], args.json)
    elif args.pond_cmd == "log":
        rid = insert(conn, "pond_readings", {
            "pond_id": args.id, "date": args.date or TODAY(), "temp_c": args.temp_c, "ph": args.ph,
            "ammonia": args.ammonia, "nitrite": args.nitrite, "nitrate": args.nitrate, "kh": args.kh,
            "gh": args.gh, "phosphate": args.phosphate, "oxygen": args.oxygen, "clarity": args.clarity,
            "algae": args.algae, "water_level": args.water_level, "action_taken": args.action, "notes": args.notes,
        })
        out({"reading_id": rid, "pond_id": args.id}, args.json)
    elif args.pond_cmd == "readings":
        rows = conn.execute("SELECT * FROM pond_readings WHERE pond_id=? ORDER BY date DESC LIMIT ?",
                            (args.id, args.limit)).fetchall()
        if args.json:
            out([dict(r) for r in rows], True)
        else:
            for r in rows:
                print(f"{r['date']:<11} temp {r['temp_c'] or '-':<5} pH {r['ph'] or '-':<5} NH3 {r['ammonia'] or '-':<5} "
                      f"NO2 {r['nitrite'] or '-':<5} NO3 {r['nitrate'] or '-':<6} algae {r['algae'] or '-':<10} {r['notes'] or ''}")


def cmd_journal(args):
    conn = connect()
    if args.journal_cmd == "add":
        jid = insert(conn, "journal", {"date": args.date or TODAY(), "author": args.author,
                                       "entry": args.entry, "tags": args.tags})
        out({"journal_id": jid}, args.json)
    else:
        rows = conn.execute("SELECT * FROM journal ORDER BY date DESC, id DESC LIMIT ?", (args.limit,)).fetchall()
        if args.json:
            out([dict(r) for r in rows], True)
        else:
            for r in rows:
                print(f"#{r['id']:>3} {r['date']} [{r['author'] or '?'}] {r['entry']}")


def cmd_advice(args):
    conn = connect()
    if args.advice_cmd == "add":
        aid = insert(conn, "advice", {"topic": args.topic, "question": args.question, "advice": args.advice,
                                      "sources": args.sources, "confidence": args.confidence})
        out({"advice_id": aid}, args.json)
    else:
        rows = conn.execute("SELECT * FROM advice ORDER BY id DESC LIMIT ?", (args.limit,)).fetchall()
        if args.json:
            out([dict(r) for r in rows], True)
        else:
            for r in rows:
                print(f"#{r['id']:>3} {r['created_at']} [{r['topic']}] {r['advice'][:110]}")


def cmd_rule(args):
    conn = connect()
    if args.rule_cmd == "add":
        rid = insert(conn, "rules", {"name": args.name, "subject": args.subject, "category": args.category,
                                     "cadence": args.cadence, "detail": args.detail})
        out({"rule_id": rid}, args.json)
    elif args.rule_cmd == "rm":
        conn.execute("UPDATE rules SET active=0 WHERE id=?", (args.id,)); conn.commit()
        out({"rule_id": args.id, "active": 0}, args.json)
    else:
        rows = conn.execute("SELECT * FROM rules WHERE active=1 ORDER BY id").fetchall()
        if args.json:
            out([dict(r) for r in rows], True)
        else:
            for r in rows:
                print(f"#{r['id']:>3} {r['name']} — {r['cadence']} — {r['detail'] or ''}")


def cmd_stats(args):
    conn = connect()
    data = {
        "plants_active": conn.execute("SELECT count(*) c FROM plants WHERE status='active'").fetchone()["c"],
        "plants_total": conn.execute("SELECT count(*) c FROM plants").fetchone()["c"],
        "by_category": {r["category"] or "unset": r["c"] for r in conn.execute(
            "SELECT category, count(*) c FROM plants WHERE status='active' GROUP BY category ORDER BY c DESC")},
        "by_bed": {r["bed"] or "unset": r["c"] for r in conn.execute(
            "SELECT bed, count(*) c FROM plants WHERE status='active' GROUP BY bed ORDER BY c DESC")},
        "photos": conn.execute("SELECT count(*) c FROM photos").fetchone()["c"],
        "observations": conn.execute("SELECT count(*) c FROM observations").fetchone()["c"],
        "treatments": conn.execute("SELECT count(*) c FROM treatments").fetchone()["c"],
        "tasks_open": conn.execute("SELECT count(*) c FROM tasks WHERE status='open'").fetchone()["c"],
        "tasks_overdue": conn.execute("SELECT count(*) c FROM tasks WHERE status='open' AND due_on<?",
                                      (TODAY(),)).fetchone()["c"],
        "ponds": conn.execute("SELECT count(*) c FROM ponds").fetchone()["c"],
        "pond_readings": conn.execute("SELECT count(*) c FROM pond_readings").fetchone()["c"],
        "db": str(DB_PATH),
    }
    if args.json:
        out(data, True)
    else:
        for k, v in data.items():
            if isinstance(v, dict):
                print(f"{k}:")
                for kk, vv in v.items():
                    print(f"   {kk:<16} {vv}")
            else:
                print(f"{k}: {v}")


def cmd_search(args):
    conn = connect()
    like = f"%{args.term.lower()}%"
    hits = []
    for r in conn.execute("SELECT id,name,common_name,botanical,notes,prune_method,bed FROM plants "
                          "WHERE lower(name||' '||coalesce(common_name,'')||' '||coalesce(botanical,'')||' '||"
                          "coalesce(notes,'')||' '||coalesce(prune_method,'')) LIKE ?", (like,)):
        hits.append(f"plant #{r['id']} {r['name']} ({r['common_name'] or r['botanical'] or '-'}) [{r['bed']}]")
    for tbl, cols in (("observations", "description"), ("treatments", "product||' '||coalesce(notes,'')||' '||coalesce(reason,'')"),
                      ("journal", "entry"), ("advice", "advice||' '||coalesce(topic,'')")):
        for r in conn.execute(f"SELECT id, {cols} AS txt FROM {tbl} WHERE lower({cols}) LIKE ? LIMIT 20", (like,)):
            hits.append(f"{tbl} #{r['id']}: {str(r['txt'])[:120]}")
    out(hits or ["(no matches)"], args.json)


def cmd_export(args):
    conn = connect()
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    written = []
    for table in ("plants", "photos", "observations", "treatments", "tasks", "ponds", "pond_readings", "journal", "advice"):
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        if not rows:
            continue
        if args.format == "json":
            path = EXPORT_DIR / f"{table}-{stamp}.json"
            path.write_text(json.dumps([dict(r) for r in rows], indent=2, default=str))
        else:
            import csv
            path = EXPORT_DIR / f"{table}-{stamp}.csv"
            with path.open("w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(rows[0].keys())
                w.writerows([tuple(r) for r in rows])
        written.append(str(path))
    out(written, args.json)


# ── intakes: async photo capture → agent analysis ────────────────────────────
INTAKE_STALE_MINUTES = 20
INTAKE_MAX_ATTEMPTS = 3
INTAKE_OPEN = ("pending", "processing", "needs_info")


def _now_iso() -> str:
    """Microsecond precision: the intake queue compares these stamps, and second-truncated
    values made a `--stale-minutes 0` reclaim miss by up to a second (and hid a live claim
    from the reaper)."""
    return dt.datetime.now().isoformat(timespec="microseconds")


def _intake_row(conn, intake_id) -> dict:
    row = conn.execute("SELECT * FROM intakes WHERE id=?", (intake_id,)).fetchone()
    if not row:
        sys.exit(f"No intake #{intake_id}")
    d = dict(row)
    pids = [int(x) for x in str(d.get("photo_ids") or "").split(",") if x.strip().isdigit()]
    d["photos"] = []
    for pid in pids:
        pr = conn.execute("SELECT id,path,kind,taken_on,user_note FROM photos WHERE id=?", (pid,)).fetchone()
        if pr:
            d["photos"].append({**dict(pr), "abs_path": str(PHOTO_DIR / pr["path"])})
    d["plant"] = None
    if d.get("plant_id"):
        pl = conn.execute("SELECT * FROM plants WHERE id=?", (d["plant_id"],)).fetchone()
        d["plant"] = dict(pl) if pl else None
    return d


def cmd_intake(args):
    conn = connect()
    cmd = args.intake_cmd

    if cmd == "capture":
        files = list(args.file or [])
        if not files:
            sys.exit("intake capture needs at least one --file")
        # Two shapes of capture share this queue and the same worker:
        #   new plant  → a draft plant row is created; the agent identifies and fills it in
        #   re-check   → --plant <ref>: the photos hang off the plant that already exists,
        #                so the agent updates its health instead of identifying it again
        existing = resolve_plant(conn, args.plant) if args.plant else None
        if args.plant and not existing:
            sys.exit(f"No plant matches {args.plant!r}")
        mode = "recheck" if (existing and existing["status"] != "draft") else "new"
        kind = (args.kind or "").strip() or ("whole" if existing else "intake")
        if existing and args.location and not existing["bed"]:
            update_row(conn, "plants", existing["id"], {"bed": args.location, "updated_at": TODAY()})
        # One transaction: a failure must not leave an orphan draft plant or half-stored photos.
        written: list[Path] = []
        try:
            if existing:
                plant_id = existing["id"]
            else:
                name = (args.name or "").strip() or f"New plant ({TODAY()})"
                plant_id = insert(conn, "plants", {
                    "name": name, "status": "draft", "bed": args.location, "health_status": "unknown",
                    "notes": args.note, "created_at": _now_iso(), "updated_at": TODAY(),
                }, commit=False)
            photo_ids = []
            for f in files:
                res = store_photo(conn, f, plant_id=plant_id, kind=kind, taken_on=args.taken_on,
                                  note=args.note, subject=f"plant:{plant_id}", commit=False)
                written.append(Path(res["stored"]))
                photo_ids.append(res["photo_id"])
            intake_id = insert(conn, "intakes", {
                "created_at": _now_iso(), "source": args.source, "status": "pending",
                "user_note": args.note, "location_hint": args.location, "plant_id": plant_id,
                "photo_ids": ",".join(str(i) for i in photo_ids), "attempts": 0,
            }, commit=False)
            conn.commit()
        except BaseException:
            conn.rollback()
            for path in written:                    # the DB rolled back; the copied images must too
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise
        plant_row = conn.execute("SELECT name, health_status FROM plants WHERE id=?", (plant_id,)).fetchone()
        out({"intake_id": intake_id, "plant_id": plant_id, "plant_name": plant_row["name"],
             "health_status": plant_row["health_status"], "photo_ids": photo_ids,
             "photos": len(photo_ids), "status": "pending", "mode": mode}, args.json)

    elif cmd == "claim":
        # Claiming is the queue's only concurrency control, so it must be atomic: the UPDATE
        # predicate (not the earlier SELECT) decides ownership, and the batch is wrapped in
        # BEGIN IMMEDIATE so two workers cannot read the same row and both update it.
        stale = (dt.datetime.now() - dt.timedelta(minutes=args.stale_minutes)).isoformat(timespec="microseconds")
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError:            # a transaction is already open — the guards still hold
            pass
        # A worker that died on its last allowed attempt used to strand the row in 'processing'
        # for ever (invisible to every later claim, and eating a queue slot). Reap those first.
        conn.execute(
            "UPDATE intakes SET status='failed', finished_at=?, error=coalesce(error, ?) "
            "WHERE status='processing' AND attempts >= ? AND coalesce(claimed_at,'') <= ?",
            (_now_iso(), "analysis attempts exhausted", INTAKE_MAX_ATTEMPTS, stale))
        claimed = []
        candidates = conn.execute(
            "SELECT id, attempts FROM intakes WHERE status='pending' "
            "   OR (status='processing' AND coalesce(claimed_at,'') <= ? AND attempts < ?) "
            "ORDER BY created_at LIMIT ?", (stale, INTAKE_MAX_ATTEMPTS, args.limit)).fetchall()
        for cand in candidates:
            cur = conn.execute(
                "UPDATE intakes SET status='processing', claimed_at=?, started_at=coalesce(started_at, ?), "
                "       attempts=attempts+1, error=NULL "
                "WHERE id=? AND status IN ('pending','processing') AND attempts=? AND attempts < ?",
                (_now_iso(), _now_iso(), cand["id"], cand["attempts"], INTAKE_MAX_ATTEMPTS))
            if cur.rowcount != 1:                   # another worker claimed it between SELECT and UPDATE
                continue
            claimed.append(_intake_row(conn, cand["id"]))
        conn.commit()
        out(claimed, True)

    elif cmd in ("done", "needs-info"):
        row = conn.execute("SELECT * FROM intakes WHERE id=?", (args.intake_id,)).fetchone()
        if not row:
            sys.exit(f"No intake #{args.intake_id}")
        status = "done" if cmd == "done" else "needs_info"
        update_row(conn, "intakes", args.intake_id, {
            "status": status, "finished_at": _now_iso(), "notified_at": _now_iso(),
            "summary": args.summary, "questions": getattr(args, "questions", None),
        })
        if cmd == "done":
            # a closed intake must not keep showing follow-up questions from an earlier needs-info
            conn.execute("UPDATE intakes SET questions=NULL, error=NULL WHERE id=?", (args.intake_id,))
            conn.commit()
        activate = (cmd == "done" and not getattr(args, "keep_draft", False)) or getattr(args, "activate", False)
        if row["plant_id"] and activate:
            conn.execute("UPDATE plants SET status='active', updated_at=? WHERE id=? AND status='draft'",
                         (TODAY(), row["plant_id"]))
            conn.commit()
        out({"intake_id": args.intake_id, "status": status, "plant_id": row["plant_id"]}, args.json)

    elif cmd == "reopen":
        # the user sent the extra photos / answered the questions: put the capture back in the queue
        row = conn.execute("SELECT * FROM intakes WHERE id=?", (args.intake_id,)).fetchone()
        if not row:
            sys.exit(f"No intake #{args.intake_id}")
        conn.execute("UPDATE intakes SET status='pending', attempts=0, claimed_at=NULL, finished_at=NULL, "
                     "notified_at=NULL, error=NULL WHERE id=?", (args.intake_id,))
        if getattr(args, "note", None):
            note = (row["user_note"] or "").strip()
            conn.execute("UPDATE intakes SET user_note=? WHERE id=?",
                         (f"{note}\n[reopened] {args.note}".strip(), args.intake_id))
        conn.commit()
        out({"intake_id": args.intake_id, "status": "pending", "plant_id": row["plant_id"]}, args.json)

    elif cmd == "fail":
        row = conn.execute("SELECT * FROM intakes WHERE id=?", (args.intake_id,)).fetchone()
        if not row:
            sys.exit(f"No intake #{args.intake_id}")
        attempts = row["attempts"] or 0
        if row["status"] != "processing":
            # an explicit failure outside a claim has to cost an attempt, otherwise failing a
            # never-claimed row would leave it 'pending' for ever (unbounded retry budget)
            attempts += 1
        status = "failed" if attempts >= INTAKE_MAX_ATTEMPTS else "pending"
        conn.execute("UPDATE intakes SET status=?, error=?, attempts=?, claimed_at=NULL, "
                     "finished_at=? WHERE id=?",
                     (status, args.error, attempts, _now_iso() if status == "failed" else None, args.intake_id))
        conn.commit()
        out({"intake_id": args.intake_id, "status": status, "attempts": attempts}, args.json)

    elif cmd == "show":
        d = _intake_row(conn, args.intake_id)
        if args.json:
            out(d, True)
        else:
            print(f"intake #{d['id']}  status={d['status']}  created={d['created_at']}  "
                  f"plant={d['plant_id']}  attempts={d['attempts']}")
            if d.get("user_note"):
                print(f"  note: {d['user_note']}")
            if d.get("location_hint"):
                print(f"  location: {d['location_hint']}")
            for p in d["photos"]:
                print(f"  photo #{p['id']} {p['abs_path']}")
            if d.get("summary"):
                print(f"  summary: {d['summary']}")
            if d.get("questions"):
                print(f"  questions: {d['questions']}")
            if d.get("error"):
                print(f"  error: {d['error']}")

    elif cmd == "list":
        q = "SELECT id, created_at, status, plant_id, attempts, substr(coalesce(summary,''),1,80) summary FROM intakes WHERE 1=1"
        params: list = []
        if args.status:
            params.append(args.status); q += " AND status=?"
        q += " ORDER BY id DESC LIMIT ?"; params.append(args.limit)
        rows = conn.execute(q, params).fetchall()
        if args.json:
            out([dict(r) for r in rows], True)
        else:
            if not rows:
                print("(no intakes)")
            for r in rows:
                print(f"#{r['id']:>3} {r['created_at']} {r['status']:<10} plant:{r['plant_id'] or '-':<4} {r['summary'] or ''}")


def cmd_needs(args):
    """The app's home screen and the agent both ask this — same three sources, one window."""
    conn = connect()
    rows = pending_work(conn, horizon=args.days)
    if args.json:
        out({"today": TODAY(), "window_days": args.days, "plants": rows,
             "totals": {"plants": len(rows),
                        "open": sum(r["open"] for r in rows),
                        "overdue": sum(r["overdue"] for r in rows),
                        "due_soon": sum(r["due_soon"] for r in rows)}}, True)
        return
    if not rows:
        print("(nothing on file)")
        return
    for r in rows:
        nxt = r["next"] or {}
        when = nxt.get("due_on") or "anytime"
        print(f"[{r['plant_id']:>3}] {str(r['name'])[:34]:34} {str(r['placement'] or 'in/out not set'):16} "
              f"open {r['open']:>2} overdue {r['overdue']:>2} due<=7d {r['due_soon']:>2}  "
              f"next {nxt.get('icon', '·')} {when} {str(nxt.get('title') or '')[:52]}")


def cmd_brief(args):
    conn = connect()
    today = dt.date.today()
    mode = args.mode
    horizon = 3 if mode == "weekend" else 31
    end = today + dt.timedelta(days=horizon)
    new_tasks = generate_tasks(conn, horizon=horizon)

    lines: list[str] = []
    stats = conn.execute("SELECT count(*) c FROM plants WHERE status='active'").fetchone()["c"]
    lines.append(f"GARDEN BRIEF — {mode.upper()} — {today.isoformat()} ({today.strftime('%A')}), "
                 f"covering {today.isoformat()} → {end.isoformat()}")
    lines.append(f"Season: {UK_MONTH_HEADLINES.get(today.month, '')}")
    lines.append(f"Registry: {stats} active plants, "
                 f"{conn.execute('SELECT count(*) c FROM ponds').fetchone()['c']} pond(s), "
                 f"{conn.execute('SELECT count(*) c FROM photos').fetchone()['c']} photos, "
                 f"{conn.execute('SELECT count(*) c FROM treatments').fetchone()['c']} treatment records.")
    tally = conn.execute("SELECT coalesce(placement,'unset') p, count(*) c FROM plants "
                         "WHERE status='active' GROUP BY 1").fetchall()
    lines.append("Where they live: " + ", ".join(f"{r['c']} {r['p']}" for r in tally)
                 + " — advice that ignores this is wrong advice.")

    if new_tasks:
        lines.append("")
        lines.append("NEWLY GENERATED WORK ITEMS:")
        for t in new_tasks:
            lines.append(f"  - task #{t['task_id']}: {t['title']} (due {t['due_on']}, {t['category']})")

    for label, sql, params in (
        ("OVERDUE TASKS", "SELECT * FROM tasks WHERE status='open' AND due_on<? ORDER BY due_on", (today.isoformat(),)),
        ("DUE IN THIS WINDOW", "SELECT * FROM tasks WHERE status='open' AND due_on>=? AND due_on<=? ORDER BY due_on",
         (today.isoformat(), end.isoformat())),
    ):
        rows = conn.execute(sql, params).fetchall()
        lines.append("")
        lines.append(f"{label} ({len(rows)}):")
        for r in rows:
            plant = conn.execute("SELECT name, placement FROM plants WHERE id=?",
                                 (str(r["subject"] or "").split(":")[-1],)).fetchone() \
                if str(r["subject"] or "").startswith("plant:") else None
            pname = plant["name"] if plant and plant["name"].lower() not in (r["title"] or "").lower() else None
            # indoor/outdoor travels with every work item: it decides which advice even applies
            where = f" [{plant['placement']}]" if plant and plant["placement"] else \
                    (" [in/out not set]" if plant else "")
            lines.append(f"  - [{r['id']}] {r['due_on']} {r['category']} :: {r['title']}"
                         f"{where}{' — ' + pname if pname else ''}{' — ' + r['detail'] if r['detail'] else ''}"
                         f" (priority {r['priority']})")

    pd = pruning_due(conn, horizon=horizon)
    lines.append("")
    lines.append(f"CUTTING WINDOW (next {horizon} days) — {len(pd)} plant(s):")
    for p in pd:
        lines.append(f"  - #{p['id']} {p['name']} [{p['category']}/{p['bed']}] {p['placement'] or 'in/out not set'} "
                     f"group {p['prune_group'] or '-'} "
                     f"last cut {p['last_pruned'] or 'never'} :: {p['prune_method'] or 'no method recorded'}")

    fd = feeding_due(conn, horizon=horizon)
    lines.append("")
    lines.append(f"FEEDING DUE — {len(fd)} plant(s):")
    for p in fd:
        lines.append(f"  - #{p['id']} {p['name']} [{p['category']}] {p['placement'] or 'in/out not set'} "
                     f"preferred: {p['feed_product'] or 'not set'} "
                     f"| last feed: {p['last_feed'] or 'no record'} {p['last_product'] or ''}")

    pr = photo_requests(conn, stale_days=30 if mode == "monthly" else 45, limit=4)
    lines.append("")
    lines.append(f"PHOTO REQUESTS (no recent picture) — {len(pr)} plant(s):")
    for p in pr:
        lines.append(f"  - #{p['id']} {p['name']} [{p['category']}/{p['bed']}] {p['placement'] or 'in/out not set'} "
                     f"last photo: {p['last_photo'] or 'never'}")

    for pond in conn.execute("SELECT * FROM ponds").fetchall():
        last = conn.execute("SELECT * FROM pond_readings WHERE pond_id=? ORDER BY date DESC LIMIT 1", (pond["id"],)).fetchone()
        lines.append("")
        lines.append(f"POND — {pond['name']} (id {pond['id']}, {pond['kind'] or 'type unset'}, "
                     f"{pond['volume_litres'] or '?'} L, fish: {pond['fish'] or 'none recorded'})")
        if last:
            lines.append(f"  last reading {last['date']}: temp {last['temp_c']} pH {last['ph']} "
                         f"NH3 {last['ammonia']} NO2 {last['nitrite']} NO3 {last['nitrate']} algae {last['algae']}")
            if last["action_taken"]:
                lines.append(f"  last action: {last['action_taken']}")
            if last["notes"]:
                lines.append(f"  notes: {last['notes']}")
        else:
            lines.append("  no water readings recorded yet")
        season_note = ("Growing season: weekly water test, watch algae/blanketweed, feed fish per temperature."
                       if 4 <= today.month <= 10 else
                       "Dormant season: no fish feeding below 8-10 °C, keep a hole open in ice, keep filters frost-free.")
        lines.append(f"  seasonal: {season_note}")

    rows = conn.execute("SELECT * FROM observations WHERE follow_up_on IS NOT NULL AND coalesce(follow_up_done,0)=0 "
                        "AND follow_up_on<=? ORDER BY follow_up_on", (end.isoformat(),)).fetchall()
    lines.append("")
    lines.append(f"OPEN FOLLOW-UPS ({len(rows)}):")
    for r in rows:
        lines.append(f"  - obs #{r['id']} {r['subject']} due {r['follow_up_on']}: {str(r['description'] or '')[:110]}")

    since = (today - dt.timedelta(days=14 if mode == "weekend" else 31)).isoformat()
    rows = conn.execute("SELECT * FROM treatments WHERE date>=? ORDER BY date DESC", (since,)).fetchall()
    lines.append("")
    lines.append(f"TREATMENTS APPLIED SINCE {since} ({len(rows)}):")
    for r in rows:
        lines.append(f"  - {r['date']} {r['subject']} {r['type']} {r['product'] or ''} {r['dose'] or ''}"
                     f"{' | next due ' + r['next_due'] if r['next_due'] else ''}")

    due = conn.execute("SELECT * FROM treatments WHERE status='suggested' ORDER BY id DESC LIMIT 10").fetchall()
    if due:
        lines.append("")
        lines.append("SUGGESTED BUT NOT YET APPLIED:")
        for r in due:
            # `subject` holds "plant:1" — print the plant's name instead, so a raw id can never be
            # parroted into a message to the user.
            subject = r["subject"] or ""
            if subject.startswith("plant:"):
                p = conn.execute("SELECT name FROM plants WHERE id=?",
                                 (subject.split(":", 1)[1],)).fetchone()
                subject = p["name"] if p else subject
            lines.append(f"  - #{r['id']} {subject} {r['type']} {r['product'] or ''} {r['dose'] or ''} ({r['reason'] or ''})")

    new_plants = conn.execute("SELECT id,name,category,bed,placement,created_at FROM plants WHERE created_at>=?",
                              ((today - dt.timedelta(days=7)).isoformat(),)).fetchall()
    if new_plants:
        lines.append("")
        lines.append("NEW PLANTS IN THE REGISTRY (last 7 days):")
        for r in new_plants:
            lines.append(f"  - #{r['id']} {r['name']} ({r['category']}, {r['bed']}) "
                         f"{r['placement'] or 'in/out NOT SET — ask or infer, then set it'}")

    lines.append("")
    lines.append("HOW TO USE THIS: see the garden-management skill. Write the user a short, warm, "
                 "actionable message: what to do this weekend in priority order, why now, the exact "
                 "technique, and one photo request. Keep it under ~250 words. If the registry is empty, "
                 "invite the user to start it instead of inventing plants.")

    text = "\n".join(lines)
    if args.json:
        print(json.dumps({"mode": mode, "brief": text}, indent=2))
    else:
        print(text)


def cmd_init(args):
    path = init_db(force=args.force)
    out({"database": str(path), "photo_dir": str(PHOTO_DIR), "schema": str(SCHEMA)}, args.json)


# ── argparse ─────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Garden + pond registry CLI for the garden agent.")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(func=cmd_init)
    sub.choices["init"].add_argument("--force", action="store_true")

    n = sub.add_parser("needs", help="everything waiting on the user, per plant (one definition)")
    n.add_argument("--days", type=int, default=7)     # --json is the global flag, set before the subcommand
    n.set_defaults(func=cmd_needs)

    pl = sub.add_parser("plant").add_subparsers(dest="plant_cmd", required=True)
    a = pl.add_parser("add")
    a.add_argument("--name", required=True)
    for flag in ("--common-name", "--botanical", "--cultivar", "--category", "--subtype", "--bed",
                 "--position", "--aspect", "--soil", "--planted-on", "--acquired-from", "--hardiness",
                 "--wildlife", "--flower-months", "--scent", "--prune-group", "--prune-months",
                 "--prune-method", "--last-pruned", "--cut-back-by", "--feed-months", "--feed-product",
                 "--water-needs", "--mulch", "--pests", "--toxicity", "--health", "--notes"):
        a.add_argument(flag)
    a.add_argument("--container", action="store_true")
    a.add_argument("--native", action="store_true")
    a.add_argument("--placement", choices=PLACEMENTS,
                   help="indoor | outdoor — where the plant actually lives (drives advice)")
    a.add_argument("--pot-size", type=int)
    a.add_argument("--height", type=int)
    a.add_argument("--spread", type=int)
    a.add_argument("--set", action="append", metavar="KEY=VALUE")
    a.set_defaults(func=cmd_plant)
    a = pl.add_parser("list"); a.add_argument("--category"); a.add_argument("--bed"); a.add_argument("--all", action="store_true"); a.set_defaults(func=cmd_plant)
    a = pl.add_parser("show"); a.add_argument("ref"); a.set_defaults(func=cmd_plant)
    a = pl.add_parser("update"); a.add_argument("ref"); a.add_argument("--set", action="append", metavar="KEY=VALUE")
    a.add_argument("--pruned-on"); a.add_argument("--health"); a.add_argument("--status"); a.add_argument("--notes")
    a.add_argument("--placement", choices=PLACEMENTS,
                   help="indoor | outdoor — where the plant actually lives (drives advice)")
    a.set_defaults(func=cmd_plant)
    a = pl.add_parser("due"); a.add_argument("--days", type=int, default=14); a.set_defaults(func=cmd_plant)

    ph = sub.add_parser("photo").add_subparsers(dest="photo_cmd", required=True)
    a = ph.add_parser("add"); a.add_argument("--file", required=True); a.add_argument("--plant"); a.add_argument("--pond")
    a.add_argument("--subject"); a.add_argument("--kind", default="whole"); a.add_argument("--taken-on")
    a.add_argument("--note"); a.add_argument("--next-action"); a.set_defaults(func=cmd_photo)
    a = ph.add_parser("assess"); a.add_argument("photo_id", type=int); a.add_argument("--assessment")
    a.add_argument("--diagnosis"); a.add_argument("--severity"); a.add_argument("--next-action")
    a.add_argument("--follow-up"); a.add_argument("--model"); a.set_defaults(func=cmd_photo)
    a = ph.add_parser("list"); a.add_argument("--plant"); a.add_argument("--limit", type=int, default=20); a.set_defaults(func=cmd_photo)
    a = ph.add_parser("summary"); a.set_defaults(func=cmd_photo)
    a = ph.add_parser("path"); a.add_argument("photo_id", type=int); a.set_defaults(func=cmd_photo)

    ob = sub.add_parser("obs").add_subparsers(dest="obs_cmd", required=True)
    a = ob.add_parser("add"); a.add_argument("--subject", required=True); a.add_argument("--kind", default="other")
    a.add_argument("--severity"); a.add_argument("--description", required=True); a.add_argument("--date")
    a.add_argument("--photo", type=int); a.add_argument("--follow-up"); a.set_defaults(func=cmd_obs)
    a = ob.add_parser("list"); a.add_argument("--subject"); a.add_argument("--open-followups", action="store_true")
    a.add_argument("--limit", type=int, default=20); a.set_defaults(func=cmd_obs)
    a = ob.add_parser("follow-up-done", help="clear a follow-up the app is still showing as owed")
    a.add_argument("id", type=int); a.set_defaults(func=cmd_obs)

    tr = sub.add_parser("treat").add_subparsers(dest="treat_cmd", required=True)
    a = tr.add_parser("add"); a.add_argument("--subject"); a.add_argument("--type", required=True)
    a.add_argument("--product"); a.add_argument("--brand"); a.add_argument("--npk"); a.add_argument("--analysis")
    a.add_argument("--dose"); a.add_argument("--dilution"); a.add_argument("--method"); a.add_argument("--area")
    a.add_argument("--quantity"); a.add_argument("--weather"); a.add_argument("--applied-by"); a.add_argument("--recommended-by")
    a.add_argument("--reason"); a.add_argument("--date"); a.add_argument("--next-due")
    a.add_argument("--status", default="applied", choices=["applied", "suggested", "planned", "cancelled"])
    a.add_argument("--outcome"); a.add_argument("--notes"); a.set_defaults(func=cmd_treat)
    a = tr.add_parser("list"); a.add_argument("--subject"); a.add_argument("--since"); a.add_argument("--type")
    a.add_argument("--status"); a.add_argument("--limit", type=int, default=25); a.set_defaults(func=cmd_treat)
    a = tr.add_parser("due"); a.add_argument("--days", type=int, default=14); a.set_defaults(func=cmd_treat)
    a = tr.add_parser("apply", help="mark a suggested treatment as actually applied today")
    a.add_argument("id", type=int); a.set_defaults(func=cmd_treat)
    a = tr.add_parser("update"); a.add_argument("id", type=int); a.add_argument("--set", action="append", metavar="KEY=VALUE")
    a.add_argument("--status"); a.add_argument("--date"); a.set_defaults(func=cmd_treat)

    tk = sub.add_parser("task").add_subparsers(dest="task_cmd", required=True)
    a = tk.add_parser("add"); a.add_argument("--title", required=True); a.add_argument("--detail"); a.add_argument("--category")
    a.add_argument("--subject"); a.add_argument("--due"); a.add_argument("--window-end"); a.add_argument("--priority", default="normal")
    a.add_argument("--recurrence"); a.add_argument("--minutes", type=int); a.add_argument("--agent", action="store_true")
    a.set_defaults(func=cmd_task)
    a = tk.add_parser("list"); a.add_argument("--status", default="open"); a.add_argument("--due-before")
    a.add_argument("--subject"); a.add_argument("--category"); a.set_defaults(func=cmd_task)
    for name in ("done", "skip"):
        a = tk.add_parser(name); a.add_argument("id", type=int); a.add_argument("--note"); a.set_defaults(func=cmd_task)
    a = tk.add_parser("update"); a.add_argument("id", type=int); a.add_argument("--set", action="append", metavar="KEY=VALUE", required=True)
    a.set_defaults(func=cmd_task)
    a = tk.add_parser("generate"); a.add_argument("--days", type=int, default=14); a.set_defaults(func=cmd_task)

    po = sub.add_parser("pond").add_subparsers(dest="pond_cmd", required=True)
    a = po.add_parser("add"); a.add_argument("--name", required=True); a.add_argument("--kind"); a.add_argument("--volume", type=int)
    a.add_argument("--surface", type=float); a.add_argument("--depth", type=int); a.add_argument("--shallows", type=int)
    a.add_argument("--liner"); a.add_argument("--pump"); a.add_argument("--filter"); a.add_argument("--uv"); a.add_argument("--aeration")
    a.add_argument("--fish"); a.add_argument("--aquatics"); a.add_argument("--margin"); a.add_argument("--wildlife")
    a.add_argument("--sun"); a.add_argument("--leaves"); a.add_argument("--established"); a.add_argument("--notes")
    a.set_defaults(func=cmd_pond)
    a = po.add_parser("list"); a.set_defaults(func=cmd_pond)
    a = po.add_parser("show"); a.add_argument("id", type=int); a.set_defaults(func=cmd_pond)
    a = po.add_parser("log"); a.add_argument("id", type=int); a.add_argument("--date"); a.add_argument("--temp-c", type=float)
    a.add_argument("--ph", type=float); a.add_argument("--ammonia", type=float); a.add_argument("--nitrite", type=float)
    a.add_argument("--nitrate", type=float); a.add_argument("--kh", type=float); a.add_argument("--gh", type=float)
    a.add_argument("--phosphate", type=float); a.add_argument("--oxygen", type=float); a.add_argument("--clarity")
    a.add_argument("--algae"); a.add_argument("--water-level"); a.add_argument("--action"); a.add_argument("--notes")
    a.set_defaults(func=cmd_pond)
    a = po.add_parser("readings"); a.add_argument("id", type=int); a.add_argument("--limit", type=int, default=10); a.set_defaults(func=cmd_pond)

    jr = sub.add_parser("journal").add_subparsers(dest="journal_cmd", required=True)
    a = jr.add_parser("add"); a.add_argument("--entry", required=True); a.add_argument("--date"); a.add_argument("--author", default="user")
    a.add_argument("--tags"); a.set_defaults(func=cmd_journal)
    a = jr.add_parser("list"); a.add_argument("--limit", type=int, default=20); a.set_defaults(func=cmd_journal)

    ad = sub.add_parser("advice").add_subparsers(dest="advice_cmd", required=True)
    a = ad.add_parser("add"); a.add_argument("--advice", required=True); a.add_argument("--topic"); a.add_argument("--question")
    a.add_argument("--sources"); a.add_argument("--confidence"); a.set_defaults(func=cmd_advice)
    a = ad.add_parser("list"); a.add_argument("--limit", type=int, default=20); a.set_defaults(func=cmd_advice)

    ru = sub.add_parser("rule").add_subparsers(dest="rule_cmd", required=True)
    a = ru.add_parser("add"); a.add_argument("--name", required=True); a.add_argument("--subject"); a.add_argument("--category")
    a.add_argument("--cadence"); a.add_argument("--detail"); a.set_defaults(func=cmd_rule)
    a = ru.add_parser("list"); a.set_defaults(func=cmd_rule)
    a = ru.add_parser("rm"); a.add_argument("id", type=int); a.set_defaults(func=cmd_rule)

    it = sub.add_parser("intake").add_subparsers(dest="intake_cmd", required=True)
    a = it.add_parser("capture"); a.add_argument("--file", action="append", required=True)
    a.add_argument("--name"); a.add_argument("--note"); a.add_argument("--location")
    a.add_argument("--taken-on"); a.add_argument("--source", default="app")
    a.add_argument("--plant", help="photos of a plant that is already registered (health re-check)")
    a.add_argument("--kind"); a.set_defaults(func=cmd_intake)
    a = it.add_parser("claim"); a.add_argument("--limit", type=int, default=1)
    a.add_argument("--stale-minutes", type=int, default=INTAKE_STALE_MINUTES); a.set_defaults(func=cmd_intake)
    a = it.add_parser("done"); a.add_argument("intake_id", type=int); a.add_argument("--summary")
    a.add_argument("--keep-draft", action="store_true"); a.set_defaults(func=cmd_intake)
    a = it.add_parser("needs-info"); a.add_argument("intake_id", type=int); a.add_argument("--summary")
    a.add_argument("--questions"); a.add_argument("--activate", action="store_true"); a.set_defaults(func=cmd_intake)
    a = it.add_parser("reopen"); a.add_argument("intake_id", type=int); a.add_argument("--note"); a.set_defaults(func=cmd_intake)
    a = it.add_parser("fail"); a.add_argument("intake_id", type=int); a.add_argument("--error"); a.set_defaults(func=cmd_intake)
    a = it.add_parser("show"); a.add_argument("intake_id", type=int); a.set_defaults(func=cmd_intake)
    a = it.add_parser("list"); a.add_argument("--status"); a.add_argument("--limit", type=int, default=20)
    a.set_defaults(func=cmd_intake)

    a = sub.add_parser("brief"); a.add_argument("--mode", default="weekend", choices=["weekend", "monthly"]); a.set_defaults(func=cmd_brief)
    a = sub.add_parser("stats"); a.set_defaults(func=cmd_stats)
    a = sub.add_parser("search"); a.add_argument("term"); a.set_defaults(func=cmd_search)
    a = sub.add_parser("export"); a.add_argument("--format", default="csv", choices=["csv", "json"]); a.set_defaults(func=cmd_export)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
