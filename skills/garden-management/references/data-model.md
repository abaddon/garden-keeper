# Data model & CLI cheatsheet

Database: `garden/garden.db` (SQLite). Schema: `garden/schema.sql`. CLI: `garden/scripts/garden.py`.
Everything below is per-profile data — nothing is shared with other agents.

## Tables

| Table | Holds |
|---|---|
| `plants` | one row per plant: identity, position, cutting, feeding, health, notes |
| `ponds` | pond physical spec + stock (volume, depth, liner, pump/filter, fish, aquatics) |
| `pond_readings` | dated water tests (temp, pH, ammonia, nitrite, nitrate, KH, GH, phosphate, oxygen, clarity, algae, action) |
| `photos` | every picture filed, with the agent's assessment/diagnosis/next action |
| `observations` | dated things seen (growth, flowering, pest, disease, damage, wildlife, harvest) with optional follow-up |
| `treatments` | everything applied **or suggested**: fertiliser, mulch, sprays, pond doses, water changes |
| `tasks` | work items with due dates, priority, status, recurrence; rule-generated ones carry `rule_key` |
| `journal` | free-form dated entries (user or agent) |
| `advice` | substantive recommendations given, with sources and confidence |
| `rules` | user-specific recurring routines (e.g. "top up pond every Sunday in summer") |
| `weather` | optional local weather record used to ground advice |

Subjects are strings: `plant:12`, `pond:1`, `bed:front border`, `lawn`, `garden`.

**`plants.placement`** is `indoor` or `outdoor` — exactly two values, and every plant should have
one (`plant update <id> --placement indoor|outdoor`; the user can also change it in the app). It is
the first field to read before any action, advice or photo assessment: it decides which half of the
rules applies. Details: `references/indoor-outdoor.md`.

## `plants.notes` — how to write it

The app renders this field on the plant page, so its shape decides how the page reads. Write it as:

1. **One lead line** — what the plant is and how big it is ("Established specimen ~1.4 m tall on a
   coir/moss pole, ~10 leafy stems, pot ~25 cm").
2. **One line per care fact**, each starting `Label: ` — Light, Water, Heat (or Position), Soil, Feed,
   Pests, Watch. Keep each to a sentence: the app shows the label as a small heading with the value
   under it, in a tidy list.
3. **A final `Unknown: …` line** for what the photos could not tell you (pot size, compost, last
   repot). The app shows it as one more row of the same list, so do not turn it into prose.
4. **Then one dated line per check**, `DD Mon YYYY: …`, when you re-check the plant from photos. The
   app puts each in its own card at the bottom, newest last, so keep the last two or three and drop
   the older ones — the photo timeline on the plant page carries the detail.

The app splits on line breaks; a single unbroken paragraph still renders (it falls back to sentences)
but reads as a wall, so keep the line breaks. Stay under ~700 characters per plant: anything longer
belongs in an observation, a task or a treatment, not here.

```text
Established specimen ~1.4 m tall on a coir/moss pole, ~10 leafy stems, pot ~25 cm.
Light: north window — tolerates it, but expect slower growth and fewer holes.
Water: rainwater or filtered only (the local tap is hard); top 2–3 cm almost dry first.
Heat: radiator alongside — move it clear for winter or the leaf edges brown.
Watch: the oldest lower leaf is fully yellowed — rule out overwatering.
Unknown: compost type and age, last repot.
22 Sep 2026: base and leaf re-check clean — green stems, no black patches, no mould, no gnats.
```

## Cheatsheet

```bash
G="python3 $HERMES_HOME/garden/scripts/garden.py"

$G init                                     # create the db (idempotent)
$G plant add --name … --category … --bed … --prune-months 3 --prune-group 6 \
    --prune-method … --feed-months 4,6 --feed-product … --health good
$G plant list [--category rose] [--bed "front"] [--all]
$G plant show 12                            # or a name fragment: plant show "gertrude"
$G plant update 12 --set height_cm=180 --health watch --pruned-on 2026-09-20
$G plant due --days 14                      # cutting windows coming up

$G photo add --file ~/Downloads/x.jpg --plant 12 --kind leaf --note "yellow edges"
$G photo assess 7 --diagnosis "magnesium deficiency" --severity low \
    --next-action "Epsom salt foliar feed" --follow-up 2026-10-01
$G photo list --plant 12 ; $G photo path 7

$G obs add --subject plant:12 --kind pest --severity medium --description "…" --follow-up 2026-10-01
$G obs list --open-followups

$G treat add --subject plant:12 --type fertiliser --product "…" --npk 5-5-5 --dose "…" \
    --method … --status applied --reason … --next-due 2026-10-15
$G treat add --subject pond:1 --type blanketweed_treatment --product … --status suggested
$G treat list --subject plant:12 --since 2026-01-01 ; $G treat due --days 14

$G task add --title "Cut back lavender" --category prune --subject plant:7 --due 2026-09-27 --priority high
$G task list --status open ; $G task done 12 --note "done Saturday" ; $G task generate --days 14

$G pond add --name "Wildlife pond" --kind wildlife --volume 3000 --depth 70 --liner butyl \
    --fish "none" --aquatics "water lily, hornwort" --sun 6 --established 2019
$G pond log 1 --ph 7.9 --temp-c 15 --ammonia 0 --nitrite 0 --nitrate 5 --algae light --notes "…"
$G pond readings 1

$G brief --mode weekend | --mode monthly    # the cron digest (this is what the jobs feed you)
$G task generate --days 14                  # materialise rule-derived work as tasks (idempotent)
$G stats ; $G search lavender ; $G export --format csv|json
```

Add `--json` before the subcommand for machine-readable output (useful in `execute_code`).

**CLI quirks (argparse):** multi-word options take the *hyphenated* name only — `--recommended-by`
works, `--recommended_by` exits 2 with "unrecognized arguments". Long or apostrophe-heavy values
(prune methods, notes, summaries) are safer written from a small Python script using
`subprocess.run([...])` with a list of args than typed into a shell one-liner.

## Generated-task rule keys (idempotency)

`task generate` never duplicates: each derived item has a stable `rule_key`.

| Origin | rule_key |
|---|---|
| cutting window | `prune:<plant_id>:<year>:<month>` |
| feeding due | `feed:<plant_id>:<year>:<month>` |
| photo request | `photo:<plant_id>:<YYYY-MM>` (max 3 per run) |
| pond water test | `pond_test:<pond_id>:<iso_week>:<year>` (Apr–Oct only, if no reading in 6 days) |

Per-plant pruning/feeding cadence comes from `plants.prune_months` / `plants.feed_months`
(`"3,4"` or `"7-9"`); a plant is not re-flagged once `last_pruned` falls inside the window's month.

## Conventions

- Dates are ISO `YYYY-MM-DD`; timestamps ISO with seconds.
- `treatments.status`: `applied` | `suggested` | `planned` | `cancelled` — never record a suggestion as applied.
- `plants.status`: `active` | `removed` | `dead`; archive instead of deleting (history matters).
- Photos always live in `garden/photos/` with `YYYY-MM-DD_<subject>_<slug>.<ext>`; the DB stores the filename only.
- Categories are a controlled vocabulary (`references/plant-categories.md`) — an unrecognised value is accepted with a warning, so fix typos by updating the row.
