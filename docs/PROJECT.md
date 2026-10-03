# Garden Keeper

A dedicated Hermes agent — **Garden Keeper** — that owns one person's garden and outdoor pond:
a plant registry, a cutting/feeding calendar, photo-based health diagnosis, seasonal advice, a
weekend plan, and a phone-first web app where that person records what is in the garden and what
is wrong with it.

It is not a chatbot with a gardening prompt. It is a small system with one database at the centre,
one writer, three scheduled jobs, its own Telegram bot, and an app that both *captures* and *shows*
the garden.

## Who it is for

The owner, in a temperate-maritime site in southern England (UK). Keen gardener, an outdoor garden and a pond, reaches his
Linux box from an iPhone over Tailscale. Works by short, direct instructions; wants phone-first,
minimal, clean interfaces; expects judgement calls to be made and stated rather than asked about.

## What "done" means here

- **The registry is the truth.** Every plant, cut, feed, treatment, photo and observation is a row.
  The agent reads before it advises and records immediately after it is told something.
- **Nothing is invented.** An honest blank beats a guessed botanical name, pruning group or dose.
- **The plan is short and doable.** One priority decision and the few tasks that matter this week.
- **Advice fits where the plant actually lives** — `placement` is `indoor` or `outdoor`, exactly two
  values, and it is the first field read before any advice, action or photo assessment.
- **Safety before enthusiasm.** Nothing toxic to pets, wildlife, amphibians or fish; peat-free;
  UK label law; no algaecide or pesticide without saying what else it affects.
- **Sunlight matters to the user, not to the agent's comfort.** If a judgement needs a photo, ask
  for a specific one.

## Climate and site facts the advice depends on

- A temperate-maritime site in southern England, RHS H4–H5. Last air frost ~mid-May, first ~late
  October; inland late frosts into May are real.
- Tap water is hard and alkaline (chalk aquifer): rainwater for ericaceous plants and **all** pond
  top-ups.
- **The garden's soil has never been tested.** Hard tap water says nothing about the soil. Never
  assume, state or hint that the soil is chalk — if care depends on it, ask.
- Unknown so far: soil, aspect, bed layout, pond size, pets, water source, how much weekend time the
  user has.

## Surfaces

| Surface | What it is for |
|---|---|
| The app (`https://<tailnet-host>:9123/`) | photograph a new plant or re-check an existing one; browse the garden; see what needs doing |
| Telegram (its own bot) | the weekend plan, monthly review, results of an analysis, questions back |
| Bot Chat in the desktop app | the same messages, and a place to talk to the agent |
| The CLI (`garden/scripts/garden.py`) | the single writer of the registry — everything above goes through it |
| Cron | `garden-intake-analysis` (every 3 min), `garden-weekend-plan` (Sat 07:00 UTC), `garden-monthly-review` (1st, 08:00 UTC) |

## Scope

**In:** the plant registry and its care calendar; photo diagnosis of plant health; seasonal advice;
the outdoor pond and its wildlife; the weekend plan; the capture/browse app; the two notification
jobs.

**Out:** anything outside this garden (no other agent's data — see the isolation rule in
`ARCHITECTURE.md`); shopping or supplier accounts; weather-station hardware; identification to
cultivar when the photo cannot support it (the agent says so instead).

## Where the project is now (2026-09-26)

- Registry: 19 plants (14 active, 5 awaiting confirmation of identity), 45 photos, 43 observations,
  29 tasks, 3 treatments, 22 captures processed, 9 pieces of advice, 8 journal entries, 1 standing
  rule. **No pond is registered yet** — the pond exists in the garden but nothing is on file for it.
- The app is live and in daily use: two capture sessions on 2026-09-23 (six houseplants in the
  morning, twelve south-border and fence plants in the evening) went through it.
- The 2026-09-26 07:00 weekend brief ran end to end and was delivered; the agent's own review of it
  produced two prompt fixes the same morning (see `HISTORY.md`).
- Open threads the garden itself is waiting on: the naming/merging of a climber over an obelisk,
  an arching shrub by the water butt, three pear captures that may be two trees, and a pH test of
  the south border (task 29, due 27 Sep).

## Reading order for someone new

1. This file.
2. `ARCHITECTURE.md` — how it hangs together.
3. `OPERATIONS.md` — how to do things to it safely.
4. The skill (`../skills/garden-management/SKILL.md`) — how the agent behaves.
5. `VERIFICATION.md` — how it is checked, and what was found the hard way.
