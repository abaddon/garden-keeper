# Verification

How this project decides that something works. Written from what actually caught real defects here —
every rule below is the residue of a specific failure, not a principle someone liked.

## The standard

An improvement is finished when it has been **run**, not when it has been read. Code that compiles is
not evidence; `py_compile` and `node --check` were green throughout the whole time a crash that would
have killed the Saturday brief sat in the query behind it.

Three things are required before "done" is said out loud:

1. **A reproducible check** of the claim, with the command or the JS that produced it.
2. **Ground truth from the data**, computed independently — fresh SQL, not the app's own helper
   function. When the page says "2 due this week", someone recomputes that from `garden.db`.
3. **The honest limit stated**: what was *not* verified, and why (no iOS sheet, no real resize event
   under emulation, a platform behaviour that cannot be exercised here).

## Independent reviewers

For anything non-trivial, a subagent is dispatched whose job is to **falsify** the change. Reviewers
must be given: the exact unit under test, a sandbox they may write to, the live app as read-only, the
traps (env overrides), and one instruction — *report only, fix nothing*.

What that has been worth:

- It found the bug that would have broken a scheduled job (a `SELECT` that omitted the column its
  consumer read).
- It found a contradiction between two screens (a plant flagged on the home card whose own page said
  "Nothing to do 🎉") — the kind of thing a green test suite never sees.
- It found that the default order was being re-sorted by the wrong field, burying a five-day-overdue
  item.
- Its *own* probes have twice found defects nobody was looking for (an id past SQLite's 64-bit range
  crashing into a "try again" message that could never work).

## Hard-won mechanics

- **Reviewers write their report incrementally.** Two batches died mid-run and took their conclusions
  with them; the third, told to append each finding as it made it, delivered 285 lines. Assume a
  child can die at any moment and design so that its evidence survives it.
- **Recover from evidence, not from summaries.** When a batch dies, the transcripts under
  `~/.hermes/cache/delegation/live/<id>/` and any files it wrote are the record. Read them; a
  reviewer's *probe output* is often enough to reconstruct a finding even with no prose report.
- **A child's claim is a claim.** `status=completed` is not completion, and "I verified X" must be
  re-checked by the parent before it is written into a commit message or a report to the user.
- **Do not re-dispatch before reading what already ran.** Twice, work that looked lost was sitting on
  disk in the dead child's scratch directory.

## Sandboxes

- Live data is read-only during verification. No exception: the user's garden is real.
- Every sandbox proves its isolation before it writes (`env | grep -i '^GARDEN_'`, and the `db:` line
  from `garden.py stats`).
- A verification that writes to a copy nobody can identify afterwards is worthless: name the copy,
  its port and its DB in the report.

## Front-end verification specifically

The traps, in the order they bite:

1. **The cache lies about deploys.** A stale `app.js` looks exactly like a broken feature. Always
   reload with the cache disabled, and assert on the *served* file (hash the file the server returns).
2. **Reading too early looks like a bug.** The views are async: poll until the DOM matches the state
   you asked for, then read. Two "failures" in one afternoon were a 2.6 s wait against a 3 s render.
3. **Emulation does not emit `resize`.** Dispatch real resize events when layout depends on it, and
   say in the report that the emulation was like that.
4. **Measure, do not eyeball.** Tap targets, overflow and contrast are numbers:
   `getBoundingClientRect()` ≥ 44 px tall, `document.documentElement.scrollWidth` ≤ viewport at 320,
   390 and 430 px, in both colour schemes.

## Schema and data verification

- A migration is proven by a before/after count of every table plus a spot-check of the rows that
  should have changed — never by "the command exited 0".
- Every query must select the column it reads. This is the single most expensive bug this project has
  had, and it is invisible to a syntax check.
- Values that arrive from outside pass through one validator, and the validator's **return** is used.
  A discarded return value silently stored `''` and the literal `"null"`.

## Reporting results

- Say what was run, what it returned, and what remains unverified. Prefer the number to the
  adjective.
- When a reviewer's finding is fixed, say which one found it and what the bug would have done in
  production — that is what tells a future reader whether to trust the fix.
- If a hit rate is partial, report the partial number ("4 of 11 plants qualified") rather than the
  flattering one.
