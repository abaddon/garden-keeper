# Garden & pond registry

This directory is the private data store of the `garden` Hermes profile — the garden and outdoor
pond agent. Nothing here is read or written by any other agent.

```
garden/
├── garden.db          SQLite registry (plants, pond, photos, observations, treatments, tasks, journal, advice, intakes)
├── schema.sql         the schema, with per-column notes (the data dictionary)
├── photos/            every picture the user sends, filed as YYYY-MM-DD_<subject>_<slug>.<ext>
├── exports/           csv/json dumps (garden.py export)
├── app/               the phone capture app (server.py + web/) — see app/README.md
└── scripts/
    ├── garden.py      the registry CLI — the only supported way to read/write the data
    └── (wrappers live one level up, in the profile's scripts/, for the cron jobs)
```

`intakes` is the async work queue behind the capture app: an upload creates a draft plant, its
photos and a `pending` intake in one transaction; the cron worker claims rows (`processing`,
attempts) and the agent closes each one `done` / `needs-info` / `fail`. Nothing else may leave a
row in `processing`.

## Use

```bash
python3 garden/scripts/garden.py --help
python3 garden/scripts/garden.py plant list
python3 garden/scripts/garden.py brief --mode weekend   # the digest the weekend cron job feeds the agent
python3 garden/scripts/garden.py stats
```

Inside the profile, `$HERMES_HOME` is this profile's directory, so
`python3 $HERMES_HOME/garden/scripts/garden.py …` resolves to the same file.

## Rules

- All garden facts go in the database — never only in a chat reply or only in a memory file.
- Photos are copied into `photos/` (garden.py does it); the DB stores the filename only.
- `treatments.status = 'suggested'` for anything recommended but not yet applied; switch it to
  `applied` once the user confirms (with the real date and dose).
- Archive plants (`status = removed|dead`) rather than deleting rows — the history is what makes
  next year's advice better.
- Back up with `garden.py export --format json`, or copy the whole directory.
