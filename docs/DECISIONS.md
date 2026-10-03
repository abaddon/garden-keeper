# Decisions

Each entry: what was decided, why, and what it costs. Newest concerns last, not newest-first — this
list is a story about the system, and reordering it loses the argument.

## Data and model

**One SQLite file, one writer.** All writes go through `garden/scripts/garden.py`, including the
app's. *Why:* one definition of a plant, one of a task, one of what is pending; the app can be
rewritten without touching the data. *Cost:* the app pays a subprocess per write (~0.2 s) and must
interpret the CLI's JSON.

**`plants.notes` has a shape, not a font.** Lead line, `Label: fact` lines, an `Unknown:` line, then
one `DATED:` line per check, under ~700 characters. *Why:* the same notes are read by the agent, by
the app's prose block and by a human on a phone; undifferentiated prose becomes unreadable in all
three. *Cost:* the agent must compose, not dump.

**`placement` is `indoor` | `outdoor`, exactly two values.** A dropdown on the plant page, a CLI flag,
an endpoint; anything else is refused. *Why:* it decides which half of every rule applies (frost,
rain, slugs, wind vs radiators, dry air, lime in tap water). A third value ("greenhouse",
"conservatory") was rejected as a category error — that nuance belongs in `bed`. *Cost:* a plant in a
conservatory is `indoor` for frost but behaves `outdoor` for light and humidity, so the nuance has to
be written down in `bed` rather than inferred.

**A missing placement is a question, not a guess.** New plants surface "NOT SET — decide, then
record"; an undecided plant shows "Not set yet" instead of a default. *Why:* a wrong guess here
poisons every later piece of advice. *Cost:* one more interaction.

**A task on a plant is titled as the work, not the plant.** "Water deeply", not "Monstera".
*Why:* the plant's name is already on every surface that shows the task; repeating it wastes the
line and produced mangled titles ("Waterdeeply"). *Cost:* enforced in four places (data, client,
skill, cron prompts) so it cannot drift.

**Health vocabulary is fixed** (`good`→All good, `watch`→Needs attention, `poor`→Unwell,
`unknown`→Not checked yet, `draft`→Being identified…). *Why:* "sick" reads as a diagnosis to a
gardener; "Needs attention" is what it actually means. *Cost:* two mappings to keep in step (CLI →
UI).

**An impossible id is "nothing there", not "try again".** Ids outside SQLite's 64-bit range can never
match a row. *Why:* a reviewer pasted `99999999999999999999` into a live probe and got a 502 telling
the user to try again — advice that can never work. *Cost:* `safe_id()` at every entry point.

**Recommended-but-not-applied products are `treatments.status='suggested'`.** *Why:* the difference
between "I told him to feed it" and "he fed it" is the whole point of the record. *Cost:* a second
source of pending work, which is why `needs` exists.

## The agent's behaviour

**Everything the agent is told to do lives in the skill** (`skills/garden-management/`), which is
loaded at the start of every garden session, rather than in a long system prompt. *Why:* it can be
edited and versioned like code, and its references (calendar, pruning groups, pond care, indoor vs
outdoor) are only loaded when relevant. *Cost:* the skill **is** production code and must be
verified as such.

**The registry is the truth: read before advising, record immediately after.** *Why:* the whole value
of the agent is that it remembers what the user has forgotten. *Cost:* every session starts with
reads.

**Safety is allowed to refuse.** Nothing toxic to pets, wildlife, amphibians or fish; peat-free; UK
label law; no algaecide or pesticide without saying what it does to everything else. *Why:* the pond
is a wildlife pond, and the user asked for a specific competence, not general enthusiasm. *Cost:* the
agent sometimes answers "no, and here is what instead".

**A judgement that depends on seeing the plant asks for a photo**, naming the shot and why. *Cost:*
a round trip; the alternative is a confident wrong diagnosis.

**No soil type is ever stated.** The garden's soil has never been tested. Hard water from a chalk
aquifer says nothing about it. *Why:* a run of plant records and messages had "that is the chalk"
built into them, and a rhododendron diagnosis rested on it; the agent itself caught and corrected
this on 2026-09-26 by fixing the intake prompt that introduced it. *Cost:* the question goes to the
user when it matters.

## The app

**Phone-first, no framework, no build step.** Three static files and FastAPI. *Why:* it has to work
on an iPhone over Tailscale, be editable in one sitting, and never need a toolchain. *Cost:* hand-
written DOM code, which is why the front-end verification rules exist.

**Tailnet-only with Tailscale identity plus a token.** No public exposure, no login form, no CSP/HSTS
for an app only reachable inside the tailnet. *Why:* the data is one person's garden, and a login
screen on a tailnet-only app is theatre. *Cost:* nothing is reachable without the tailnet.

**Async capture.** Uploads land as an `intakes` row and are analysed by a cron job; the app says
"photos received" and polls. *Why:* identification is slow and the phone should not wait. *Cost:* an
intake can be left `processing` if the agent crashes — the intake worker's rule is that every intake
is closed, always.

**The home screen is a work list, not an inventory**, defaulting to what needs action, with three
buttons (🏠 In house, 🌤️ Outside, 🌿 All) for the full lists. *Why:* the user asked for exactly that
— and a plant needing nothing is not news. *Cost:* `All` had to be added so that a plant with an
unrecognised placement stays reachable.

**One definition of "waiting on the user": `garden.py needs --days 7`** — open tasks, follow-ups not
done, treatments suggested but not applied. *Why:* the app's home screen and the cron digests had
different ideas of what was pending, so a plant could be flagged on one and invisible on the other.
*Cost:* the app depends on a CLI command (fine — it already did).

**A count describes the window it names.** "2 due this week", never "12 to do this week" when two are
due. *Cost:* two numbers where one would be tidier.

**Everything the app counts, the app can clear.** Tasks have Done; follow-ups and unapplied
suggestions have Done in "Also waiting". *Why:* counting work on one screen that no screen can clear
is a nag with no end. *Cost:* two extra endpoints and two CLI verbs.

**One button to add photos: `multiple`, no `capture`.** *Why:* an image picker without a capture hint
still offers the camera, and `multiple` hands over a whole batch in one tap. *Cost:* the camera path
still returns one photo per shutter press — a platform limit, stated plainly rather than papered
over.

**Static `no-cache`, HTML `no-store`.** *Why:* a stale `app.js` once made a healthy app look dead and
cost a diagnostic detour. *Cost:* a little more traffic.

**A photo opens in a viewer that closes, never a dead-end tab.** Tapping the hero or a timeline
photo used to open the bare image in a new tab — on the phone that view has no chrome and nothing
to close it with. It now opens in an in-app dialog: the ✕, a tap outside the photo, Escape and the
phone's back gesture all close it, and the page underneath keeps its scroll and focus. The viewer
owns exactly one history entry while open, so the back gesture closes the photo and lands on the
plant page rather than skipping past it; the links keep `href`/`target` so long-press and
⌘/Ctrl-click still act as links, and only a plain tap is intercepted. *Cost:* a synthetic
same-task burst of open/close can leave one extra history entry (one no-op Back) — real input
timing does not produce it, measured — and the router carries one more surface to reason about.

## Feedback and prompts

**A prompt must be skippable, and only for work that was actually due.** *Why:* tapping Done on an
overdue job opens one line of "what changed" plus optional photos, with "Done, nothing to add" one
tap away and a ✕ that leaves the task open; a form that blocks is a form that gets resented, and a
prompt that fires for a job due next month trains the user to dismiss it. *Cost:* the app must tell
"due today" from "due in four days" — and only the **number** may decide that, never the colour: the
styling class `due` covers everything inside a week, and using it as the fact made a job due in four
days ask what had changed.

**The user's own account of the work is stored where the agent reads it, three ways.** *Why:* a note
on a closed task row is invisible to every digest, so `task done --note` also writes a `maintenance`
observation on the plant, and photos sent with a Done become a normal health re-check. *Cost:* the
same text exists in three places; the intake prompt and the skill both say which is authoritative
(the observation for history, `user_note` for the photos' context).

**A note is never dropped, even late.** *Why:* the registry is what decides whether a note was
kept, and the app must not claim otherwise — a task closed out of band still records the note
(once; an identical repeat is a no-op) because the user took the trouble to write it. *Cost:*
`note_recorded` travels from the CLI through the server to the toast, so three layers have to
agree on what happened.

**Nothing is uploaded on pick; the user presses Send.** *Why:* choosing photos is browsing, not
sending — a mis-tap used to file an intake and spend an agent run. A batch that fails keeps its queue
and its note, and the task stays open until the send succeeds. *Cost:* one extra tap on every send.

**A string body is JSON, so the client sets the header itself.** *Why:* FastAPI refuses to parse a
body without `Content-Type: application/json`, and the failure reads as nonsense on screen; setting it
inside `api()` removes the trap for every future call site. *Cost:* none worth naming.

## Process

**Git for code, schema, skill and docs; not for the DB, photos or runtime state.** *Why:* the
irreplaceable parts are the data and the images; versioning a 250 KB SQLite file that changes hourly
buys nothing and risks a wrong merge. *Cost:* backups must be deliberate (see `OPERATIONS.md`).

**The working repository stays private; the project is published as a scrubbed export.** *Why:* the
first call was "local only, nothing to publish" — until the project earned a public face. But this
repository also holds the agent's private notes about its owner, and it names the owner's town and
network, so publishing it as-is would publish a person. The export copies the tracked tree, drops what
is not the project, and **refuses to publish while any known personal marker survives** — a token
shape, the tailnet, a LAN address, the town, the name, a device, the chat id. *Cost:* two histories to
keep straight (the export is a single commit, so the hashes quoted in these docs do not resolve
there); the redaction list must be extended in the same commit as anything personal added here; and
the export must never be hand-edited — it is rebuilt, not patched.

**Every non-trivial change gets an independent reviewer, and its findings are fixed in the same
round.** *Why:* three reviewer waves each found a real defect that syntax checks, unit reasoning and
the author's own re-reads had all missed. *Cost:* time, and a discipline of writing the report before
believing the change.
