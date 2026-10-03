#!/usr/bin/env python3
"""Feed for the `garden-intake-analysis` cron job.

Claims the captures waiting in the intake queue and prints them (with the absolute photo paths)
as the agent's context. If there is nothing to do the script prints the wake gate
`{"wakeAgent": false}` and the job ends without an LLM run.

Two shapes arrive here and the difference matters:

  * a NEW plant (the registry row is still a `draft`) — identify and categorise it;
  * a RE-CHECK (`--plant`, the row is already `active`) — the user photographed a plant
    that is already registered; compare against what is on file, do not re-identify it.

Claiming here (rather than in the agent turn) is what makes the queue safe: a row that is already
`processing` is not claimed again until it goes stale (default 20 min) or runs out of attempts.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

PROFILE = pathlib.Path(__file__).resolve().parents[1]
CLI = PROFILE / "garden" / "scripts" / "garden.py"
BATCH = 3


def run(*args: str):
    proc = subprocess.run([sys.executable, str(CLI), "--json", *args],
                          capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout or "null")
    except json.JSONDecodeError:
        return None


def claim() -> list[dict]:
    claimed = run("intake", "claim", "--limit", str(BATCH))
    if claimed is None:
        print("intake claim failed — leaving the queue alone this tick", file=sys.stderr)
        print(json.dumps({"wakeAgent": False}))
        sys.exit(0)
    return claimed


def history(plant_id) -> dict:
    """What is already on file for this plant, so the agent can compare rather than re-derive."""
    return run("plant", "show", str(plant_id)) or {}


def describe(item: dict) -> list[str]:
    plant = item.get("plant") or {}
    fresh = plant.get("status") == "draft"
    out = [f"### intake #{item['id']} — attempt {item.get('attempts')}/3, "
           f"{'NEW plant' if fresh else 'EXISTING plant (health re-check)'}"]
    out.append(f"plant_id: {item.get('plant_id')}   registry name: {plant.get('name')!r}   "
               f"row status: {plant.get('status')}")
    if item.get("location_hint"):
        out.append(f"user says where: {item['location_hint']}")
    if fresh:
        # a new row has no placement yet: say so where the agent cannot miss it, and make the
        # decision part of registering the plant
        stale = plant.get("placement")
        out.append("lives: " + (f"{stale} (already recorded — confirm it fits the photos and the "
                                "user's words)" if stale else
                                "NOT SET — decide indoor or outdoor from the photos and the user's "
                                "words and record it: garden.py plant update <id> --placement "
                                "indoor|outdoor. If it is genuinely unclear, it goes in --questions."))
    if item.get("user_note"):
        out.append(f"user note: {item['user_note']}")
    photos = item.get("photos") or []
    out.append(f"uploaded now ({len(photos)} photo(s)) — look at every one, not just the first:")
    for photo in photos:
        out.append(f"  - {photo['abs_path']}   (kind {photo.get('kind')}, "
                   f"user said: {photo.get('user_note') or '—'})")

    if not fresh:
        seen = history(item.get("plant_id"))
        p = seen.get("plant") or {}
        out.append("")
        out.append("ON FILE for this plant (do not re-identify it — compare the new photos with this):")
        out.append(f"  name/botanical: {p.get('name')!r} / {p.get('botanical') or '—'} "
                   f"({p.get('category') or 'category unknown'})")
        homes = p.get("placement") or ("NOT SET — decide indoor or outdoor from the photos and where "
                                       "the user says it is, then record it with: "
                                       "plant update <id> --placement indoor|outdoor")
        out.append(f"  lives: {homes}   bed: {p.get('bed') or '—'}")
        out.append(f"  health now: {p.get('health_status')}   "
                   f"last pruned: {p.get('last_pruned') or '—'}")
        out.append(f"  prune months: {p.get('prune_months') or '—'}   feed months: "
                   f"{p.get('feed_months') or '—'}   pests seen before: {p.get('pests_known') or '—'}")
        earlier = [ph for ph in (seen.get("photos") or []) if str(ph.get("id")) not in
                   [str(x.get("id")) for x in photos]]
        for ph in earlier[:2]:
            out.append(f"  previous photo #{ph['id']} ({ph.get('taken_on') or '—'}): "
                       f"{ph.get('assessment') or ph.get('next_action') or 'no assessment'}")
        for ob in (seen.get("observations") or [])[:3]:
            out.append(f"  observation {ob.get('date')} [{ob.get('kind')}/{ob.get('severity') or '-'}]: "
                       f"{ob.get('description')}")
        open_tasks = [t for t in (seen.get("tasks") or []) if t.get("status") == "open"]
        for t in open_tasks[:5]:
            out.append(f"  open task #{t['id']} ({t.get('due_on') or 'no date'}): {t.get('title')}")
        if not open_tasks:
            out.append("  open tasks: none")
    out.append("")
    return out


def main() -> None:
    pending = claim()
    if not pending:
        print(json.dumps({"wakeAgent": False}))          # nothing waiting — stay silent, no cost
        return

    out = [f"{len(pending)} capture(s) from the phone app are waiting to be analysed.", ""]
    for item in pending:
        out.extend(describe(item))
    out.append("Work each one through to a closed intake (done / needs-info / failed) and record "
               "everything you conclude in the registry — the user then sees it in the app and on "
               "Telegram.")
    print("\n".join(out))


if __name__ == "__main__":
    main()
