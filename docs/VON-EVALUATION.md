# Von — where it could be useful here, and where it could not

**Status: evaluated, not adopted, nothing wired up.** Written 2026-09-27 against `von-1.2.0` as served
on the LAN VM. Every number below was measured or read from a named source; nothing is quoted from a
README and presented as a fact about this garden.

## What it is

A 395 M-parameter bidirectional encoder (ModernBERT, Apache 2.0, ~1.5 GB) that **never generates text**.
You send a *state* and N typed *questions*; it returns, per question:

| Primitive | Answer | Use it for |
|---|---|---|
| `choice` | one option + the full distribution + `confidence` | picking one thing from a bounded list |
| `noul` | a calibrated 0–1 posterior on one condition | checking a claim |
| `score` | an ordinal expected value + a legend (2–10 levels) | rating on a rubric |

`confidence` is the *margin* between the top two options, not a probability. It is a decision layer,
not a chat model: no prose, no code, no arithmetic, no vision, no multi-hop indirection.

It runs on the LAN VM (`von.service`, N100-class, 2 vCPU / 5.7 GiB RAM), speaking the TypeSafe
`/v1/systemone` protocol — so the hosted service and this one are a base-URL swap. It is **not**
installed on the app host and cannot be: that box has 2 GB of RAM total, and Von holds ~1.9 GB
resident / ~3.2 GB peak at load. Anything using it here is a LAN HTTP call that must degrade to
today's behaviour if the VM is down.

```bash
curl -s http://<lan-host>:8000/v1/models          # von-latest, von-1.2.0, von-1.1.0
```

## Reaching it, and the two shape traps

```bash
curl -s http://<lan-host>:8000/v1/systemone -H 'Content-Type: application/json' -d '{
  "state": "Registered plants: Fig, south fence (outdoor, fruit); Rose, back border (outdoor, rose).\nIncoming message from the owner: \"watered the fig\"",
  "model": "von-latest",
  "questions": {
    "plant": {"type":"choice","instructions":"Which plant is this message about?",
              "criteria":{"Fig, south fence":"The message refers to Fig, south fence",
                          "Rose, back border":"The message refers to Rose, back border",
                          "not stated":"No plant can be told from the message",
                          "new plant":"A plant that is not on the registered list"}}
  }}'
```

- `criteria` for a `choice` is a **dict** (option → what it means), for a `score` a **list** of ordered
  levels. A string there is rejected with a pydantic 422 naming the field.
- Filter the state before sending it: only what the question needs. Long option descriptions and long
  option lists both cost latency (below).
- The example above answers `Fig, south fence` at 0.588 confidence — with only two candidates and a
  one-line state there is less to be sure with. The 0.99 in the table below came from the real
  14-plant list, which is the case that actually matters here.

## What was measured from this box on 2026-09-27

| Probe | Answer | Verdict |
|---|---|---|
| `watered the fig` → which of the 14 active plants | **Fig, south fence — confidence 0.99** (runners-up: the two pears at 0.004 / 0.001) | works |
| what does the message want (record / schedule / answer / capture / report-done) | `ask_question` 0.319 over the correct `report_done` 0.251, **confidence 0.15** | wrong, and honestly unsure |
| should this interrupt the owner now / digest / never | `never` 0.394, confidence 0.09 | wrong, and honestly unsure |
| QA gate: "does this line assert soil facts not on file?" against the chalk-soil line this project has actually written | `noul` **0.17** (i.e. "no") — but the companion verdict landed on `rewrite` (0.45) | check unreliable; the action was right |
| latency, 2 questions / tiny state | **2.33 s** total (71 input tokens) | fine off the request path |
| latency, 3 questions / 16 options / long criteria | **9.61 s** total | cost tracks option count, not just questions |

Two caveats on my own probes: the criteria for the two failures were written quickly (overlapping
descriptions, the exact mismatch the vendor's guidance warns about), and three calls is a sample, not a
benchmark. The negative results are *suggestive*, not proof — but they are consistent with the
published gap (Von 72.0 % macro / 83.0 % choice macro on the independent 49-task jabr v2 suite, vs
hosted Jev 1.13's 96.6 % / 96.8 %), and with where its benchmark is strong: triage-shaped pockets
(symptom triage 100 %, home services 95.7 %, city routing 94.7 %).

## Where it fits this app

Ranked by fit. "Now" means on today's data, with no new infrastructure beyond a base URL.

| Use | Shape | Evidence / caveat |
|---|---|---|
| Route an incoming message to the plant it is about | `choice` over the registered names + `not stated` + `new plant` | Measured 0.99 confidence over 14 real names. The agent currently reads the whole registry to work out what "watered the fig" means. Map names back to ids in code afterwards |
| Type free text into the registry's controlled vocabularies (task category, observation kind, severity band) | `choice` over the vocabulary | Removes the free-string drift the CLI already has to police (`⚠ category 'x' is not in the standard list`). Only where a wrong pick is cheap |
| A **flag-only** QA gate before a digest goes to Telegram | `noul` per risky class | The class of defect is real (the chalk-soil assertions; indoor/outdoor reasoning leaking). My probe says the check itself is unreliable → usable as "flag for a second look", never as the decider |
| Symptom described in words → kind (`pest`/`disease`/`growth`/…) + a `score` severity | `choice` + `score` | Its strongest benchmark family. Text only: it can sit *after* the vision model, which makes it a second opinion on a judgement already made |
| Triage the user's note inside the app before the agent wakes | `choice` over {fact, job request, completion} | Would classify locally and privately; ~2–3 s means a background step on the intake row, never a blocking submit |
| Pick which reference file answers a question | `choice` over the skill's sections | Low value — the agent loads the skill anyway |

## Where it does not fit — which is most of the project

- **Plant identification and photo diagnosis.** No vision. This is the heaviest judgement load in
  Garden Keeper and the one thing it cannot touch.
- **Any advice, plan, brief or summary.** It chooses; it does not author.
- **Dates, counts, "due in N days", ranking.** Arithmetic is explicitly out of scope, and this project
  already keeps scheduling in code (`garden.py needs`, the brief scripts) for good reasons.
- **Multi-hop reasoning across the record.** 72 % macro on the independent suite against the hosted
  model's 96.6 % — not where a wrong answer is worth a plant.
- **Anything on the phone's critical path.** ~1–3 s per question over the LAN, on a single VM service.

## The cost question, answered honestly

Self-hosted Von is free per call; hosted Jev is $0.042 per million input tokens. Neither matters here.
The real volumes: **22 intakes ever (16 analysed), 45 photos (43 assessed), 43 observations, 3
weekend-brief digests** — and the intake cron, which fires every 3 minutes, has its agent woken by a
deterministic script gate only when something actually waits (50 of 50 recent runs skipped it). Any
saving is in cents. The reasons to reach for Von would be **locality** (garden text stays on the LAN),
**typed output** (no parse step, no invalid category), and **calibrated confidence** for act/ask
bands — a policy this project already uses in words ("a missing placement is a question, not a guess").

## The experiment that would settle it

Not a build: a replay. Take the registry's own history — 43 recorded photo assessments and 43
observations with human/agent-assigned kinds — and ask Von the same questions, then compare against
what is on file. This is an `offline-replay-evaluation` job and changes nothing live.

Adopt a use only if it clears a stated bar on that replay, e.g. "≥ 90 % agreement with the recorded
`kind`, and ≥ 95 % of disagreements have confidence < 0.4" (i.e. its uncertainty, not its accuracy, is
what routes to a human). If it cannot clear that on data from *this* garden, it does not go in,
whatever the model card says.

## Decision

**Not adopted. No code, no dependency, no call site.** Revisit when (a) the replay above clears a bar,
or (b) a use appears whose answer space is small, whose input is already text, and whose mistakes are
cheap — with the VM's availability accepted as a dependency that fails soft.
