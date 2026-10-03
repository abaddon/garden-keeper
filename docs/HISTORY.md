# History

What was built, in the order it happened, and what broke on the way. Commit hashes are from the
profile's local repository (`git log` in `/root/.hermes/profiles/garden`); the commit log and this
file must never disagree.

## Phase 1 — the agent and its registry (2026-09-22)

`9a98d82` — the `garden` profile, the registry CLI (`garden/scripts/garden.py`), the
`garden-management` skill with its references, the first capture app, the intake cron worker, and the
Telegram bot.

Decided in this phase: the CLI as the single writer; the app as pure capture; async analysis with the
result delivered to Telegram and Bot Chat.

## Phase 2 — the app starts showing the garden (2026-09-22)

`3465c3d` — plant list, per-plant pages (actions with Done, photo history), and per-plant re-check
uploads. `4be5c85` — documented the display surface in the app README and the skill.

The task-title rule came out of this: a task is titled as the work, not the plant ("Water deeply"),
because the plant's name is already on every surface that shows it — and the first implementation
mangled titles ("Waterdeeply") by stripping the name badly.

## Phase 3 — hardening, and the first two verification waves (2026-09-22)

`43c4c12`, `84818ea`, `af8c660`, `00b8c89`, `514463f`, `99bdfc9`.

The first wave's findings, all fixed in `84818ea`:

- **"The app looks dead."** It was not: a stale `app.js` was being served from the browser's cache
  while the server had the new one. Fixed with `no-cache` on static files and `no-store` on HTML —
  and the rule that a front-end check must defeat the cache before it believes a failure.
- A FastAPI error body puts its message in `detail`; the client read `error`, so the user saw nothing
  while the app knew what was wrong.
- `photo summary` could read a photo file outside `garden/photos/` and window past the table end.
- `task done` on an already-closed task cloned a recurring task instead of changing nothing.

`af8c660` re-composed the plant page (4,427 → 3,838 px tall at 390 px). `00b8c89` and `514463f` then
fixed the clamp: a "More" button that could be clipped away with no way to reopen the text it hid
(the invariant — *a clamp must never outrun the control that opens it* — was subsequently put through
≈45 measured states by a reviewer and could not be falsified).

That round also produced the "More" target rule (31×38 px → 84×44 px), the treatment count taken from
the data rather than a stale literal, and the restoration of a photo's `next_action` line, which a
`||` chain had been silently dropping.

## Phase 4 — where it lives (2026-09-23)

`61db831` — `placement` (`indoor` | `outdoor`) as a first-class field: schema, CLI, validator,
endpoint, dropdown on the plant page, and the rule that it is the **first** field read before any
advice, action or photo assessment. `99c5142` — impossible ids answer "nothing there" instead of
"try again". `1ed9c47` — the two reviewers' findings.

That review was worth its cost twice over:

- **The bug that would have broken a scheduled job.** `brief` printed `placement` from a `SELECT`
  that did not select it: `IndexError`, exit 1, empty stdout. Six plants qualified, so the Saturday
  07:00 brief and the monthly review would both have died, handing the agent a "Script Error" block.
  `py_compile` was green the whole time.
- **A validator whose return was discarded** at the `--set` call sites, quietly storing `''` and the
  literal `"null"`.
- Agent-side gaps of the same family: `plant due` printed no placement, `plant show` hid a NULL
  placement (so a missing field read as "no rule applies"), the intake feed carried placement only
  for re-checks, and both cron prompts said nothing about it at all.
- Rules written before the field existed still assumed the outdoors (`houseplant_out`, hardening off,
  frost/bird overrides) sitting on five indoor plants; and one reference file asked a question and
  then told the agent to assume the opposite answer. All gated on `placement` now.

## Phase 5 — a work list instead of an inventory (2026-09-23)

`d7c878e` — the home screen became what needs action, with 🏠 In house and 🌤️ Outside buttons above
it. `1069ce8` — documented in the app README. `d5be1e0` — one definition of "waiting on the user",
`garden.py needs --days 7`, because the app counted only tasks while the cron digests also counted
follow-ups owed and treatments suggested but not applied. `8a187ec` — a chip may only count the
window it names. `25f6b15` — everything the app counts, the app can clear ("Also waiting" with its
own Done). `ea6b27c`, `c5f22eb` — one photo button, `multiple`, no `capture`.

The reviewer of that round found the worst kind of defect: a plant whose only waiting work was a
follow-up was flagged on the home card and opened on a page that said *"Nothing to do for this plant
right now. 🎉"* — counted on one screen, invisible and unclearable on the other. Alongside it: the
default order was being re-sorted by tasks alone (a five-day-overdue follow-up rendered twelfth,
below plants with nothing pending), and a plant with an unrecognised placement appeared in neither
group (hence 🌿 All).

Two bugs were introduced *during* that round and caught by re-checking: a normaliser line
(`view === 'in' || view === 'out' ? view : ''`) silently swallowed the new `all` view — "the button
does nothing" — and a variable referenced in a callback where it was never a parameter threw *after*
the row had been removed, leaving a stale count and no toast while everything looked fine.

## Phase 6 — the agent running itself (2026-09-26)

No code commit. The 07:00 Saturday brief ran end to end (3rd fire, status `ok`, delivered to Bot Chat
and Telegram, 36 KB of digest in `cron/output/774a81b2fbf4/`) — the job the Phase-4 bug would have
killed.

The agent then reviewed its own output and found two things, recorded in the garden journal and fixed
in the job prompts the same morning:

1. The message covered 7 of the 9 tasks due that weekend and **silently dropped two due that day**
   (task 10, task 11). A due task cannot be optional in a plan whose purpose is to stop things being
   missed: the weekend prompt now requires every item in the digest's `DUE IN THIS WINDOW` list to
   appear, alone or grouped with a sibling.
2. The intake prompt was still telling the agent to reason from "the site / chalk soil / hard water"
   — the root of repeated chalk assertions in plant records, including a rhododendron whose diagnosis
   rested on it. The prompt now carries the corrected fact (the soil has never been tested; chalk
   aquifer tap water says nothing about soil) and sends the question to the user instead.

## Phase 6b — the repository told the truth about itself (2026-09-26)

Writing the docs exposed a contradiction between what `.gitignore` said ("tracked: code, skill,
docs — ignored: machinery") and what the index held: **5,425 of 5,498 tracked files were a vendored
pyright language server** under `lsp/`, roughly 30 MB of history (the public export carries none of it) for a project whose real content is
67 files. Removed from the index (the files stay on disk) and the rule added to `.gitignore`, along
with three Hermes bookkeeping files that had been swept in. The history still carries the old blobs;
the working tree no longer pretends they are the project.

## Phase 7 — feedback the user actually wants to give

`ea6b27c`/`c5f22eb` made the capture picker one button. Then the upload buttons came off the trigger
almost entirely: the plant page's "add photos" became a compose form (batch, one line of what changed,
then **Send**), and tapping **Done** on a job that was due opens the same idea inline — a note and
optional photos, with Save and a one-tap "Done, nothing to add".

Four defects came out of building it, three of them pre-existing:

- **My own:** the Send button was built and never appended (it simply was not in the markup).
- **A missing header:** `api()` sent JSON bodies without `Content-Type`, so the first Save failed with
  a validation error the UI could only render as "that request did not make sense". Fixed in the
  helper, not at the call site, so no future mutation can hit it.
- **The colour used as the fact:** the Done prompt leaned on a styling class that means "within a
  week", so a job due in four days asked what had changed. `dueLabel` now returns the day count as
  well, and only the number decides.
- **A literal `null` on every plant page** with nothing waiting: `replaceChildren` does not filter,
  and an absent block was rendered as the word. Renders that assemble optional blocks now go through
  `mount()`, which filters.

An independent reviewer then broke three things, all fixed and each re-verified with executed
evidence:

- **A note silently lost, with the UI claiming success** — a task already closed out of band (another
  device, or the CLI) made the server's `done` call a no-op, and the app still toasted "Saved ✓
  Garden Keeper has your note". `task done --note` now records a late note once (an identical repeat
  is a no-op, so the idempotency that stops duplicate recurring tasks is intact), returns
  `note_recorded`, and the app says only what happened in each of the three cases.
- **The `null` fix was incomplete** — the re-check status card still passed a missing summary straight
  into `replaceChildren`, printing the literal word. Fixed and reproduced the reviewer's way: an intake
  marked done with `summary=NULL` now renders `Health check updated` and nothing else.
- **A button lost its icon** — the panel's repaint wrote `textContent` over the whole button, taking
  the 🖼️ with it; the icon and a label span are now separate nodes.

Verified in the sandbox against a scratch registry (no upload on pick; a note becoming a `maintenance`
observation; a Done with photos filing a re-check intake *and* closing the task; ✕ leaving the task
open; overdue and due-today prompting while tomorrow, +4 days and next month stay silent), then
read-only against the live garden — 19 plants, 45 photos, 29 tasks, 43 observations, 22 intakes,
unchanged by the checks.

## Phase 8 — a public face, without publishing a person

The project went public on 2026-10-03, and the interesting part was the boundary rather than the push.
A scan of all 24 commits found **nothing secret had ever been committed** — no `.env`, no `app.env`, no
database, no photograph, no token-shaped string — because the ignore rules had held from the first
commit. What the repository *did* hold was the agent's private notes about its owner, the owner's town
and name in four documents, the tailnet host in five, a LAN address in two, and a chat id in the
memory files.

So the public repository is an **export**, not this history: the tracked tree minus the agent's
memory, the tooling's own bundled skills and its lock files, with placeholders for the network details
and the owner described rather than named. The publish script asserts that every redaction pattern
still matches something (a pattern that stops matching silently is how the thing it hid gets
published), then scans the finished tree for known markers and **refuses to create the repository** if
one survives — which it did on the first three runs, catching a phrasing the list had missed, a line
in the public `.gitignore` that named the directory being dropped, and a rule whose text had stopped
matching anything at all.

The export is a single initial commit of 39 files; the private history stays private, which is why the
hashes quoted in these docs do not resolve there.

## Phase 9 — a photo that can be closed (2026-10-03)

`0ae7140` — the plant page's photos open in an in-app viewer, not the bare image in a new tab. On
the phone the old behaviour was a dead end: the image view has no chrome and nothing to close it
with, so the only way back was to kill the app. The viewer closes on ✕, a tap outside the photo,
Escape, or the phone's own back gesture; it owns one history entry while open and hands it back on
close, and the plant page underneath keeps its scroll and focus. The links keep their
`href`/`target`, so long-press, ⌘/Ctrl-click and middle-click still act as ordinary links — only a
plain tap is intercepted. A photo whose file has vanished shows “missing from disk” inside the
viewer and still closes.

Verified by `photoviewer_ui_check.py` (real Chromium over CDP, signed in through the identity
header the proxy injects, against a sandbox copy of code and registry on :9131): 36 checks, three
consecutive full passes — the close paths asserted on computed styles, scroll and focus
restoration, balanced history after every close, 320/390/430 px, ctrl-click stays a link, the
missing-file path, no page errors. An independent reviewer reproduced the suite (36/36) and added
race scenarios of its own: double and triple ✕, open/close bursts with real input timing,
back-during-close, and a synthetic same-task burst. All came back serial-consistent except the
synthetic burst, which under robotic timing can leave one extra history entry — one no-op Back —
and which no human input timing produces; it is recorded here and in `DECISIONS.md` rather than
papered over.

## The registry itself

Separate from the code: the garden. Six houseplant captures on the morning of 2026-09-23, twelve
south-border and fence captures that evening (olive, rhododendron, three pears, rose, sage, lavender,
fig, climber, arching shrub), each processed by the intake worker with `placement` set. The agent's
own journal holds the review of each run — including the corrections it made to its own earlier
conclusions (a pear counted as one tree that the photos show as two; a climber first read as a fig
and then as a grape vine; a diagnosis that leaned on an untested soil).

**Evaluated, not built:** the local System One model (`Von`) that runs on the LAN VM was measured
against this app's real decision points and recorded in [`VON-EVALUATION.md`](VON-EVALUATION.md) —
strong at picking one entity from a bounded list (0.99 confidence on "watered the fig" → the fig),
unreliable on subtle rubrics, and impossible to run on the app host (2 GB of RAM). Not adopted; a
replay against the registry's own 43 assessments is the experiment that would settle it.

**Open threads at the time of writing:** three plants awaiting a name or a confirmed identity, the
climber's stem base, a pH test of the south border (task 29, due 2026-09-27) and the pond — which
exists in the garden but has no record in the registry yet.
