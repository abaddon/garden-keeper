# The registry CLI

`garden/scripts/garden.py` is the **only** writer of the garden registry. The app, the cron workers
and the agent all go through it, which is what keeps one definition of a plant, a task and "what is
waiting on the user". Full command reference is generated at the bottom of this file.

```bash
PY=/usr/local/lib/hermes-agent/venv/bin/python
G=/root/.hermes/profiles/garden
$PY $G/garden/scripts/garden.py <command> [--json]
```

## Conventions

- **`--json` before the subcommand** gives machine-readable output; every tool in this project parses
  JSON rather than scraping text. (A subcommand must never define its own `--json`: a subparser
  default silently overwrites the global flag, and the caller then gets human text where it expected
  JSON.)
- **Subjects are typed**: `plant:4`, `pond:1`. A task's subject says what it is about; its *title*
  says the work ("Water deeply"), never the plant.
- **Ids are validated** before use: non-numeric, ≤ 0, or past SQLite's 64-bit range is "nothing
  there" — exit 1 with a message, never a crash and never a retry suggestion.
- **`init` first** in any script: an uninitialised registry is a first-run state, not an error.
- **`stats` names the database** it is talking to. Read that line whenever numbers surprise you.
- Writes are immediate and idempotent where it matters: `task done` twice changes nothing and never
  clones a recurring task; `obs follow-up-done` and `treat apply` report `already_done` /
  `already_applied` rather than failing.

## The five that carry the system

```bash
# everything waiting on the user, per plant — the app's home screen and the digests both read this
$PY $G/garden/scripts/garden.py --json needs --days 7

# one plant's page: the record, the open work, the photos oldest first
$PY $G/garden/scripts/garden.py --json plant show 4

# close work (the app's Done buttons call exactly this)
$PY $G/garden/scripts/garden.py task done 12
$PY $G/garden/scripts/garden.py obs follow-up-done 26     # a follow-up that was owed
$PY $G/garden/scripts/garden.py treat apply 3             # a suggested feed, now applied

# the digest the Saturday job sends the agent
$PY $G/garden/scripts/garden.py brief --mode weekend

# which database is this, and what is in it
$PY $G/garden/scripts/garden.py stats
```

## Recording a plant the way the app does

```bash
$PY $G/garden/scripts/garden.py intake capture --file photo.jpg --file leaf.jpg \
    --note "purple bush by the gate" --location "front border"
$PY $G/garden/scripts/garden.py plant add --name "Rhododendron" --category shrub \
    --placement outdoor --bed "Outside — south border" --status draft
$PY $G/garden/scripts/garden.py plant update 9 --set health_status=watch --set prune_group=group_9
$PY $G/garden/scripts/garden.py photo assess 20 --assessment "pale new growth, brown tips" \
    --follow-up 2026-10-06
```

`--placement` accepts exactly `indoor` or `outdoor`. Refusing anything else is the point: it decides
which half of every care rule applies.

## Regenerating the reference

```bash
python docs/tools/regen-cli.py     # rewrites the block below from the CLI's own --help output
```

The generator stamps the CLI's hash so a stale reference is visible at a glance. Commit the two files
together.

<!-- generated:begin -->
<!-- garden.py sha256:8cfc70e392 — regenerate with `python docs/tools/regen-cli.py` -->

_Generated from `garden/scripts/garden.py` on 2026-09-26._

Every command takes `--json` (before the subcommand) for machine-readable output.

```text
usage: garden.py [-h] [--json]
                 {init,needs,plant,photo,obs,treat,task,pond,journal,advice,rule,intake,brief,stats,search,export}
                 ...

Garden + pond registry CLI for the garden agent.

positional arguments:
  {init,needs,plant,photo,obs,treat,task,pond,journal,advice,rule,intake,brief,stats,search,export}
    needs               everything waiting on the user, per plant (one
                        definition)

options:
  -h, --help            show this help message and exit
  --json                machine-readable output
```

### `needs` — What is waiting on the user (the one definition)

```text
usage: garden.py needs [-h] [--days DAYS]

options:
  -h, --help   show this help message and exit
  --days DAYS
```

### `plant` — The plant registry

```text
usage: garden.py plant [-h] {add,list,show,update,due} ...

positional arguments:
  {add,list,show,update,due}

options:
  -h, --help            show this help message and exit
```

**`plant add`**

```text
usage: garden.py plant add [-h] --name NAME [--common-name COMMON_NAME]
                           [--botanical BOTANICAL] [--cultivar CULTIVAR]
                           [--category CATEGORY] [--subtype SUBTYPE]
                           [--bed BED] [--position POSITION] [--aspect ASPECT]
                           [--soil SOIL] [--planted-on PLANTED_ON]
                           [--acquired-from ACQUIRED_FROM]
                           [--hardiness HARDINESS] [--wildlife WILDLIFE]
                           [--flower-months FLOWER_MONTHS] [--scent SCENT]
                           [--prune-group PRUNE_GROUP]
                           [--prune-months PRUNE_MONTHS]
                           [--prune-method PRUNE_METHOD]
                           [--last-pruned LAST_PRUNED]
                           [--cut-back-by CUT_BACK_BY]
                           [--feed-months FEED_MONTHS]
                           [--feed-product FEED_PRODUCT]
                           [--water-needs WATER_NEEDS] [--mulch MULCH]
                           [--pests PESTS] [--toxicity TOXICITY]
                           [--health HEALTH] [--notes NOTES] [--container]
                           [--native] [--placement {indoor,outdoor}]
                           [--pot-size POT_SIZE] [--height HEIGHT]
                           [--spread SPREAD] [--set KEY=VALUE]

options:
  -h, --help            show this help message and exit
  --name NAME
  --common-name COMMON_NAME
  --botanical BOTANICAL
  --cultivar CULTIVAR
  --category CATEGORY
  --subtype SUBTYPE
  --bed BED
  --position POSITION
  --aspect ASPECT
  --soil SOIL
  --planted-on PLANTED_ON
  --acquired-from ACQUIRED_FROM
  --hardiness HARDINESS
  --wildlife WILDLIFE
  --flower-months FLOWER_MONTHS
  --scent SCENT
  --prune-group PRUNE_GROUP
  --prune-months PRUNE_MONTHS
  --prune-method PRUNE_METHOD
  --last-pruned LAST_PRUNED
  --cut-back-by CUT_BACK_BY
  --feed-months FEED_MONTHS
  --feed-product FEED_PRODUCT
  --water-needs WATER_NEEDS
  --mulch MULCH
  --pests PESTS
  --toxicity TOXICITY
  --health HEALTH
  --notes NOTES
  --container
  --native
  --placement {indoor,outdoor}
                        indoor | outdoor — where the plant actually lives
                        (drives advice)
  --pot-size POT_SIZE
  --height HEIGHT
  --spread SPREAD
  --set KEY=VALUE
```

**`plant list`**

```text
usage: garden.py plant list [-h] [--category CATEGORY] [--bed BED] [--all]

options:
  -h, --help           show this help message and exit
  --category CATEGORY
  --bed BED
  --all
```

**`plant show`**

```text
usage: garden.py plant show [-h] ref

positional arguments:
  ref

options:
  -h, --help  show this help message and exit
```

**`plant update`**

```text
usage: garden.py plant update [-h] [--set KEY=VALUE] [--pruned-on PRUNED_ON]
                              [--health HEALTH] [--status STATUS]
                              [--notes NOTES] [--placement {indoor,outdoor}]
                              ref

positional arguments:
  ref

options:
  -h, --help            show this help message and exit
  --set KEY=VALUE
  --pruned-on PRUNED_ON
  --health HEALTH
  --status STATUS
  --notes NOTES
  --placement {indoor,outdoor}
                        indoor | outdoor — where the plant actually lives
                        (drives advice)
```

**`plant due`**

```text
usage: garden.py plant due [-h] [--days DAYS]

options:
  -h, --help   show this help message and exit
  --days DAYS
```

### `task` — Work items

```text
usage: garden.py task [-h] {add,list,done,skip,update,generate} ...

positional arguments:
  {add,list,done,skip,update,generate}

options:
  -h, --help            show this help message and exit
```

**`task add`**

```text
usage: garden.py task add [-h] --title TITLE [--detail DETAIL]
                          [--category CATEGORY] [--subject SUBJECT]
                          [--due DUE] [--window-end WINDOW_END]
                          [--priority PRIORITY] [--recurrence RECURRENCE]
                          [--minutes MINUTES] [--agent]

options:
  -h, --help            show this help message and exit
  --title TITLE
  --detail DETAIL
  --category CATEGORY
  --subject SUBJECT
  --due DUE
  --window-end WINDOW_END
  --priority PRIORITY
  --recurrence RECURRENCE
  --minutes MINUTES
  --agent
```

**`task list`**

```text
usage: garden.py task list [-h] [--status STATUS] [--due-before DUE_BEFORE]
                           [--subject SUBJECT] [--category CATEGORY]

options:
  -h, --help            show this help message and exit
  --status STATUS
  --due-before DUE_BEFORE
  --subject SUBJECT
  --category CATEGORY
```

**`task done`**

```text
usage: garden.py task done [-h] [--note NOTE] id

positional arguments:
  id

options:
  -h, --help   show this help message and exit
  --note NOTE
```

**`task skip`**

```text
usage: garden.py task skip [-h] [--note NOTE] id

positional arguments:
  id

options:
  -h, --help   show this help message and exit
  --note NOTE
```

**`task update`**

```text
usage: garden.py task update [-h] --set KEY=VALUE id

positional arguments:
  id

options:
  -h, --help       show this help message and exit
  --set KEY=VALUE
```

**`task generate`**

```text
usage: garden.py task generate [-h] [--days DAYS]

options:
  -h, --help   show this help message and exit
  --days DAYS
```

### `photo` — Photos and their assessments

```text
usage: garden.py photo [-h] {add,assess,list,summary,path} ...

positional arguments:
  {add,assess,list,summary,path}

options:
  -h, --help            show this help message and exit
```

**`photo add`**

```text
usage: garden.py photo add [-h] --file FILE [--plant PLANT] [--pond POND]
                           [--subject SUBJECT] [--kind KIND]
                           [--taken-on TAKEN_ON] [--note NOTE]
                           [--next-action NEXT_ACTION]

options:
  -h, --help            show this help message and exit
  --file FILE
  --plant PLANT
  --pond POND
  --subject SUBJECT
  --kind KIND
  --taken-on TAKEN_ON
  --note NOTE
  --next-action NEXT_ACTION
```

**`photo assess`**

```text
usage: garden.py photo assess [-h] [--assessment ASSESSMENT]
                              [--diagnosis DIAGNOSIS] [--severity SEVERITY]
                              [--next-action NEXT_ACTION]
                              [--follow-up FOLLOW_UP] [--model MODEL]
                              photo_id

positional arguments:
  photo_id

options:
  -h, --help            show this help message and exit
  --assessment ASSESSMENT
  --diagnosis DIAGNOSIS
  --severity SEVERITY
  --next-action NEXT_ACTION
  --follow-up FOLLOW_UP
  --model MODEL
```

**`photo list`**

```text
usage: garden.py photo list [-h] [--plant PLANT] [--limit LIMIT]

options:
  -h, --help     show this help message and exit
  --plant PLANT
  --limit LIMIT
```

**`photo summary`**

```text
usage: garden.py photo summary [-h]

options:
  -h, --help  show this help message and exit
```

**`photo path`**

```text
usage: garden.py photo path [-h] photo_id

positional arguments:
  photo_id

options:
  -h, --help  show this help message and exit
```

### `obs` — Observations, including follow-ups

```text
usage: garden.py obs [-h] {add,list,follow-up-done} ...

positional arguments:
  {add,list,follow-up-done}
    follow-up-done      clear a follow-up the app is still showing as owed

options:
  -h, --help            show this help message and exit
```

**`obs add`**

```text
usage: garden.py obs add [-h] --subject SUBJECT [--kind KIND]
                         [--severity SEVERITY] --description DESCRIPTION
                         [--date DATE] [--photo PHOTO] [--follow-up FOLLOW_UP]

options:
  -h, --help            show this help message and exit
  --subject SUBJECT
  --kind KIND
  --severity SEVERITY
  --description DESCRIPTION
  --date DATE
  --photo PHOTO
  --follow-up FOLLOW_UP
```

**`obs list`**

```text
usage: garden.py obs list [-h] [--subject SUBJECT] [--open-followups]
                          [--limit LIMIT]

options:
  -h, --help         show this help message and exit
  --subject SUBJECT
  --open-followups
  --limit LIMIT
```

**`obs follow-up-done`**

```text
usage: garden.py obs follow-up-done [-h] id

positional arguments:
  id

options:
  -h, --help  show this help message and exit
```

### `treat` — Feeding and treatments

```text
usage: garden.py treat [-h] {add,list,due,apply,update} ...

positional arguments:
  {add,list,due,apply,update}
    apply               mark a suggested treatment as actually applied today

options:
  -h, --help            show this help message and exit
```

**`treat add`**

```text
usage: garden.py treat add [-h] [--subject SUBJECT] --type TYPE
                           [--product PRODUCT] [--brand BRAND] [--npk NPK]
                           [--analysis ANALYSIS] [--dose DOSE]
                           [--dilution DILUTION] [--method METHOD]
                           [--area AREA] [--quantity QUANTITY]
                           [--weather WEATHER] [--applied-by APPLIED_BY]
                           [--recommended-by RECOMMENDED_BY] [--reason REASON]
                           [--date DATE] [--next-due NEXT_DUE]
                           [--status {applied,suggested,planned,cancelled}]
                           [--outcome OUTCOME] [--notes NOTES]

options:
  -h, --help            show this help message and exit
  --subject SUBJECT
  --type TYPE
  --product PRODUCT
  --brand BRAND
  --npk NPK
  --analysis ANALYSIS
  --dose DOSE
  --dilution DILUTION
  --method METHOD
  --area AREA
  --quantity QUANTITY
  --weather WEATHER
  --applied-by APPLIED_BY
  --recommended-by RECOMMENDED_BY
  --reason REASON
  --date DATE
  --next-due NEXT_DUE
  --status {applied,suggested,planned,cancelled}
  --outcome OUTCOME
  --notes NOTES
```

**`treat list`**

```text
usage: garden.py treat list [-h] [--subject SUBJECT] [--since SINCE]
                            [--type TYPE] [--status STATUS] [--limit LIMIT]

options:
  -h, --help         show this help message and exit
  --subject SUBJECT
  --since SINCE
  --type TYPE
  --status STATUS
  --limit LIMIT
```

**`treat due`**

```text
usage: garden.py treat due [-h] [--days DAYS]

options:
  -h, --help   show this help message and exit
  --days DAYS
```

**`treat apply`**

```text
usage: garden.py treat apply [-h] id

positional arguments:
  id

options:
  -h, --help  show this help message and exit
```

**`treat update`**

```text
usage: garden.py treat update [-h] [--set KEY=VALUE] [--status STATUS]
                              [--date DATE]
                              id

positional arguments:
  id

options:
  -h, --help       show this help message and exit
  --set KEY=VALUE
  --status STATUS
  --date DATE
```

### `pond` — The pond and its readings

```text
usage: garden.py pond [-h] {add,list,show,log,readings} ...

positional arguments:
  {add,list,show,log,readings}

options:
  -h, --help            show this help message and exit
```

**`pond add`**

```text
usage: garden.py pond add [-h] --name NAME [--kind KIND] [--volume VOLUME]
                          [--surface SURFACE] [--depth DEPTH]
                          [--shallows SHALLOWS] [--liner LINER] [--pump PUMP]
                          [--filter FILTER] [--uv UV] [--aeration AERATION]
                          [--fish FISH] [--aquatics AQUATICS]
                          [--margin MARGIN] [--wildlife WILDLIFE] [--sun SUN]
                          [--leaves LEAVES] [--established ESTABLISHED]
                          [--notes NOTES]

options:
  -h, --help            show this help message and exit
  --name NAME
  --kind KIND
  --volume VOLUME
  --surface SURFACE
  --depth DEPTH
  --shallows SHALLOWS
  --liner LINER
  --pump PUMP
  --filter FILTER
  --uv UV
  --aeration AERATION
  --fish FISH
  --aquatics AQUATICS
  --margin MARGIN
  --wildlife WILDLIFE
  --sun SUN
  --leaves LEAVES
  --established ESTABLISHED
  --notes NOTES
```

**`pond list`**

```text
usage: garden.py pond list [-h]

options:
  -h, --help  show this help message and exit
```

**`pond show`**

```text
usage: garden.py pond show [-h] id

positional arguments:
  id

options:
  -h, --help  show this help message and exit
```

**`pond log`**

```text
usage: garden.py pond log [-h] [--date DATE] [--temp-c TEMP_C] [--ph PH]
                          [--ammonia AMMONIA] [--nitrite NITRITE]
                          [--nitrate NITRATE] [--kh KH] [--gh GH]
                          [--phosphate PHOSPHATE] [--oxygen OXYGEN]
                          [--clarity CLARITY] [--algae ALGAE]
                          [--water-level WATER_LEVEL] [--action ACTION]
                          [--notes NOTES]
                          id

positional arguments:
  id

options:
  -h, --help            show this help message and exit
  --date DATE
  --temp-c TEMP_C
  --ph PH
  --ammonia AMMONIA
  --nitrite NITRITE
  --nitrate NITRATE
  --kh KH
  --gh GH
  --phosphate PHOSPHATE
  --oxygen OXYGEN
  --clarity CLARITY
  --algae ALGAE
  --water-level WATER_LEVEL
  --action ACTION
  --notes NOTES
```

**`pond readings`**

```text
usage: garden.py pond readings [-h] [--limit LIMIT] id

positional arguments:
  id

options:
  -h, --help     show this help message and exit
  --limit LIMIT
```

### `journal` — The agent's own log

```text
usage: garden.py journal [-h] {add,list} ...

positional arguments:
  {add,list}

options:
  -h, --help  show this help message and exit
```

**`journal add`**

```text
usage: garden.py journal add [-h] --entry ENTRY [--date DATE]
                             [--author AUTHOR] [--tags TAGS]

options:
  -h, --help       show this help message and exit
  --entry ENTRY
  --date DATE
  --author AUTHOR
  --tags TAGS
```

**`journal list`**

```text
usage: garden.py journal list [-h] [--limit LIMIT]

options:
  -h, --help     show this help message and exit
  --limit LIMIT
```

### `advice` — Advice given

```text
usage: garden.py advice [-h] {add,list} ...

positional arguments:
  {add,list}

options:
  -h, --help  show this help message and exit
```

**`advice add`**

```text
usage: garden.py advice add [-h] --advice ADVICE [--topic TOPIC]
                            [--question QUESTION] [--sources SOURCES]
                            [--confidence CONFIDENCE]

options:
  -h, --help            show this help message and exit
  --advice ADVICE
  --topic TOPIC
  --question QUESTION
  --sources SOURCES
  --confidence CONFIDENCE
```

**`advice list`**

```text
usage: garden.py advice list [-h] [--limit LIMIT]

options:
  -h, --help     show this help message and exit
  --limit LIMIT
```

### `rule` — Standing rules

```text
usage: garden.py rule [-h] {add,list,rm} ...

positional arguments:
  {add,list,rm}

options:
  -h, --help     show this help message and exit
```

**`rule add`**

```text
usage: garden.py rule add [-h] --name NAME [--subject SUBJECT]
                          [--category CATEGORY] [--cadence CADENCE]
                          [--detail DETAIL]

options:
  -h, --help           show this help message and exit
  --name NAME
  --subject SUBJECT
  --category CATEGORY
  --cadence CADENCE
  --detail DETAIL
```

**`rule list`**

```text
usage: garden.py rule list [-h]

options:
  -h, --help  show this help message and exit
```

**`rule rm`**

```text
usage: garden.py rule rm [-h] id

positional arguments:
  id

options:
  -h, --help  show this help message and exit
```

### `intake` — The capture queue

```text
usage: garden.py intake [-h]
                        {capture,claim,done,needs-info,reopen,fail,show,list}
                        ...

positional arguments:
  {capture,claim,done,needs-info,reopen,fail,show,list}

options:
  -h, --help            show this help message and exit
```

### `brief` — The digests the cron jobs send

```text
usage: garden.py brief [-h] [--mode {weekend,monthly}]

options:
  -h, --help            show this help message and exit
  --mode {weekend,monthly}
```

**`brief weekend`**

```text
usage: garden.py brief [-h] [--mode {weekend,monthly}]

options:
  -h, --help            show this help message and exit
  --mode {weekend,monthly}
```

**`brief monthly`**

```text
usage: garden.py brief [-h] [--mode {weekend,monthly}]

options:
  -h, --help            show this help message and exit
  --mode {weekend,monthly}
```

### `stats` — Counts, and which database this is

```text
usage: garden.py stats [-h]

options:
  -h, --help  show this help message and exit
```

### `search` — Free-text search across the registry

```text
usage: garden.py search [-h] term

positional arguments:
  term

options:
  -h, --help  show this help message and exit
```

### `export` — Dump the registry

```text
usage: garden.py export [-h] [--format {csv,json}]

options:
  -h, --help           show this help message and exit
  --format {csv,json}
```

**`export csv`**

```text
usage: garden.py export [-h] [--format {csv,json}]

options:
  -h, --help           show this help message and exit
  --format {csv,json}
```

**`export json`**

```text
usage: garden.py export [-h] [--format {csv,json}]

options:
  -h, --help           show this help message and exit
  --format {csv,json}
```

### `init` — Create or upgrade the tables

```text
usage: garden.py init [-h] [--force]

options:
  -h, --help  show this help message and exit
  --force
```

<!-- generated:end -->
