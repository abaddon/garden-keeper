-- Garden + pond registry for the `garden` Hermes profile.
-- Authoritative schema. All garden data the agent keeps lives in this database
-- (garden.db) plus the photos/ directory. Nothing here is shared with other agents.
PRAGMA foreign_keys = ON;

-- ── plants ────────────────────────────────────────────────────────────────────
-- One row per plant the user owns (or owned). `category` uses the controlled
-- vocabulary in references/plant-categories.md — keep it consistent so grouping works.
CREATE TABLE IF NOT EXISTS plants (
  id            INTEGER PRIMARY KEY,
  name          TEXT NOT NULL,              -- name the user actually uses ("the big rose by the shed")
  common_name   TEXT,                       -- proper common name ("Rosa 'Gertrude Jekyll'")
  botanical     TEXT,                       -- genus / species / hybrid
  cultivar      TEXT,
  category      TEXT,                       -- tree|shrub|rose|climber|perennial|annual|biennial|bulb|grass|fern|herb|vegetable|fruit|aquatic|marginal|bog|water_lily|oxygenator|floating|hedge|conifer|houseplant_out
  subtype       TEXT,                       -- "evergreen shrub", "herbaceous perennial", "climbing rose"...
  bed           TEXT,                       -- bed / border / area / container group
  placement     TEXT,                       -- indoor | outdoor — where it actually lives; decides frost/rain/slugs vs radiator/tap-water/humidity advice
  position      TEXT,                       -- full sun | part shade | shade | sheltered | exposed
  aspect        TEXT,                       -- N/S/E/W facing
  soil          TEXT,                       -- clay | loam | sandy | chalk | silt | peat-free compost
  in_container  INTEGER DEFAULT 0,
  pot_size_cm   INTEGER,
  planted_on    TEXT,                       -- ISO date planted / acquired into the garden
  acquired_from TEXT,                       -- nursery / gift / cutting / seed
  height_cm     INTEGER,
  spread_cm     INTEGER,
  hardiness     TEXT,                       -- RHS rating, e.g. H4, H5 (UK temperate default H4-H5)
  uk_native     INTEGER DEFAULT 0,
  wildlife      TEXT,                       -- pollinators / birds / larval food / berries
  flower_months TEXT,                       -- CSV or ranges, 1-12: "5,6,7" or "3-4"
  scent         TEXT,
  prune_group   TEXT,                       -- RHS pruning group 1-13 (see references/pruning-groups.md)
  prune_months  TEXT,                       -- months this plant gets cut: "3,4" / "7-8" / "2,7"
  prune_method  TEXT,                       -- exactly how THIS plant is cut (height, technique, what to remove)
  last_pruned   TEXT,                       -- ISO date of last cut
  cut_back_by   TEXT,                       -- e.g. "1/3", "to 30cm", "deadhead only"
  feed_months   TEXT,                       -- months this plant is fed
  feed_product  TEXT,                       -- preferred feed/product
  water_needs   TEXT,                       -- low | medium | high | drought-tolerant
  mulch         TEXT,
  pests_known   TEXT,                       -- recurring problems seen here
  toxicity      TEXT,                       -- pets / children / fish / livestock notes
  health_status TEXT DEFAULT 'unknown',     -- good | watch | poor | unknown | dead
  status        TEXT DEFAULT 'active',      -- active | removed | dead | dormant_check
  notes         TEXT,
  created_at    TEXT,
  updated_at    TEXT
);

-- ── ponds ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ponds (
  id             INTEGER PRIMARY KEY,
  name           TEXT NOT NULL,
  kind           TEXT,                      -- wildlife | fish | koi | mixed | container
  volume_litres  INTEGER,
  surface_m2     REAL,
  max_depth_cm   INTEGER,
  shallows_cm    INTEGER,
  liner          TEXT,                      -- butyl | preformed | clay | lined | none
  pump           TEXT,
  filter         TEXT,
  uv             TEXT,
  aeration       TEXT,
  fish           TEXT,                      -- species + rough counts
  aquatics       TEXT,                      -- planting summary
  margin_plants  TEXT,
  wildlife       TEXT,                      -- frogs/newts/dragonflies observed
  sun_exposure   TEXT,                      -- hours of sun
  leaves_ingress TEXT,                      -- nearby trees dropping leaves
  established    TEXT,                      -- when built / how old
  last_water_change TEXT,
  notes          TEXT,
  created_at     TEXT
);

CREATE TABLE IF NOT EXISTS pond_readings (
  id           INTEGER PRIMARY KEY,
  pond_id      INTEGER REFERENCES ponds(id) ON DELETE CASCADE,
  date         TEXT,
  temp_c       REAL,
  ph           REAL,
  ammonia      REAL,                        -- mg/l
  nitrite      REAL,
  nitrate      REAL,
  kh           REAL,
  gh           REAL,
  phosphate    REAL,
  oxygen       REAL,                        -- mg/l if measured
  clarity      TEXT,
  algae        TEXT,                        -- none | light | blanketweed | bloom
  water_level  TEXT,                        -- normal | low | topped up
  action_taken TEXT,
  notes        TEXT,
  created_at   TEXT
);

-- ── photos ────────────────────────────────────────────────────────────────────
-- Every picture the user sends is copied into garden/photos/ and recorded here,
-- with the agent's assessment attached to the same row.
CREATE TABLE IF NOT EXISTS photos (
  id           INTEGER PRIMARY KEY,
  plant_id     INTEGER REFERENCES plants(id) ON DELETE SET NULL,
  pond_id      INTEGER REFERENCES ponds(id) ON DELETE SET NULL,
  subject      TEXT,                        -- 'plant:12' | 'pond:1' | 'bed:front border'
  path         TEXT NOT NULL,               -- relative to garden/photos
  kind         TEXT,                        -- whole|leaf|leaf_underside|flower|fruit|stem|trunk|root|damage|pest|symptom|pond|water|fish|bed|label
  taken_on     TEXT,
  added_at     TEXT,
  user_note    TEXT,                        -- what the user said about it
  assessment   TEXT,                        -- what the agent concluded from the image
  diagnosis    TEXT,                        -- best identification / problem
  severity     TEXT,                        -- none|low|medium|high
  next_action  TEXT,
  follow_up_on TEXT,
  model        TEXT
);

-- ── observations ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS observations (
  id           INTEGER PRIMARY KEY,
  subject      TEXT NOT NULL,               -- 'plant:12' | 'pond:1' | 'bed:front' | 'garden'
  date         TEXT,
  kind         TEXT,                        -- growth|flowering|emerging|senescence|pest|disease|damage|weather|wildlife|harvest|dieback|other
  severity     TEXT,                        -- none|low|medium|high
  description  TEXT,
  photo_id     INTEGER REFERENCES photos(id) ON DELETE SET NULL,
  follow_up_on TEXT,
  follow_up_done INTEGER DEFAULT 0,
  created_at   TEXT
);

-- ── treatments ────────────────────────────────────────────────────────────────
-- EVERYTHING applied to the garden or pond — given or suggested. `status` separates
-- what actually went on the ground from what the agent recommended.
CREATE TABLE IF NOT EXISTS treatments (
  id             INTEGER PRIMARY KEY,
  subject        TEXT,                      -- 'plant:12' | 'pond:1' | 'bed:front' | 'lawn' | 'garden'
  date           TEXT,                      -- date applied (NULL while status='suggested')
  type           TEXT,                      -- fertiliser|feed|foliar_feed|tonic|mulch|compost|soil_improver|lime|ericaceous|pesticide|fungicide|insecticide|herbicide|slug_control|repot|prune_seal|pond_treatment|blanketweed_treatment|barley_straw|beneficial_bacteria|water_change|sludge_remover|algae_treatment|fish_medication|other
  product        TEXT,                      -- trade name
  brand          TEXT,
  npk            TEXT,                      -- "5-5-5" / "N-rich" / "tomato feed"
  analysis       TEXT,                      -- extra detail: magnesium, seaweed, trace elements...
  dose           TEXT,                      -- "30 ml in 5 L", "handful per m2", "15 g/m3"
  dilution       TEXT,
  method         TEXT,                      -- watering can|root drench|foliar|broadcast|top dress|spot treat|injected|granules
  area           TEXT,                      -- bed / plant / litres treated
  quantity       TEXT,
  weather        TEXT,                      -- conditions at application
  applied_by     TEXT,                      -- user | agent-suggested-and-user-applied | contractor
  recommended_by TEXT,                      -- agent | user | nursery | rhs | label
  reason         TEXT,                      -- what problem/goal
  status         TEXT DEFAULT 'applied',    -- applied | suggested | planned | cancelled
  next_due       TEXT,                      -- when to repeat / re-assess
  outcome        TEXT,                      -- effect observed later
  notes          TEXT,
  created_at     TEXT
);

-- ── tasks ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tasks (
  id            INTEGER PRIMARY KEY,
  title         TEXT NOT NULL,
  detail        TEXT,
  category      TEXT,                       -- prune|feed|water|plant|move|divide|deadhead|mulch|weed|lawn|pond|inspect|harvest|protect|sow|photo|other
  subject       TEXT,
  due_on        TEXT,                       -- ISO date (window start)
  window_end    TEXT,                       -- last sensible day
  priority      TEXT DEFAULT 'normal',      -- low | normal | high
  status        TEXT DEFAULT 'open',        -- open | done | skipped
  recurrence    TEXT,                       -- NULL | 'weekly' | 'annual:3' | 'monthly:6'
  est_minutes   INTEGER,
  source        TEXT,                       -- rule | agent | user
  rule_key      TEXT,                       -- dedupe key for generated tasks
  created_at    TEXT,
  completed_on  TEXT,
  notes         TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_rulekey
  ON tasks(rule_key) WHERE rule_key IS NOT NULL;

-- ── journal / advice / rules ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS journal (
  id         INTEGER PRIMARY KEY,
  date       TEXT,
  author     TEXT,                          -- user | agent
  entry      TEXT,
  tags       TEXT,
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS advice (
  id          INTEGER PRIMARY KEY,
  created_at  TEXT,
  topic       TEXT,
  question    TEXT,
  advice      TEXT,
  sources     TEXT,                         -- URLs / references used
  confidence  TEXT,
  followed    TEXT                          -- did the user act on it
);

-- User-specific recurring routines the agent should honour (beyond plant rows):
-- e.g. "feed tomatoes weekly June-Sept", "top up pond every Sunday in summer".
CREATE TABLE IF NOT EXISTS rules (
  id         INTEGER PRIMARY KEY,
  name       TEXT NOT NULL,
  subject    TEXT,
  category   TEXT,
  cadence    TEXT,                          -- 'weekly' | 'monthly' | 'annual:5' | 'months:6,7,8'
  detail     TEXT,
  active     INTEGER DEFAULT 1,
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS weather (
  id       INTEGER PRIMARY KEY,
  date     TEXT,
  min_c    REAL,
  max_c    REAL,
  rain_mm  REAL,
  wind     TEXT,
  notes    TEXT
);

-- ── intakes ───────────────────────────────────────────────────────────────────
-- A capture waiting for (or processed by) the agent: photos the user uploaded from
-- the mobile app or sent in, plus the state of the asynchronous analysis. One row
-- per "here are pictures of a new plant" submission.
CREATE TABLE IF NOT EXISTS intakes (
  id           INTEGER PRIMARY KEY,
  created_at   TEXT,
  claimed_at   TEXT,                       -- when a worker picked it up
  started_at   TEXT,
  finished_at  TEXT,
  source       TEXT DEFAULT 'app',         -- app | telegram | desktop | cli
  status       TEXT DEFAULT 'pending',     -- pending | processing | done | needs_info | failed
  user_note    TEXT,                       -- what the user typed with the photos
  location_hint TEXT,                      -- bed / area the user typed (best effort)
  plant_id     INTEGER REFERENCES plants(id) ON DELETE SET NULL,
  photo_ids    TEXT,                       -- CSV of photos.id, in upload order
  attempts     INTEGER DEFAULT 0,
  summary      TEXT,                       -- short user-facing result of the analysis
  questions    TEXT,                       -- newline-separated follow-up questions (needs_info)
  error        TEXT,
  notified_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_intakes_status ON intakes(status, created_at);

CREATE INDEX IF NOT EXISTS idx_plants_category ON plants(category);
CREATE INDEX IF NOT EXISTS idx_plants_bed ON plants(bed);
CREATE INDEX IF NOT EXISTS idx_photos_plant ON photos(plant_id);
CREATE INDEX IF NOT EXISTS idx_obs_subject ON observations(subject);
CREATE INDEX IF NOT EXISTS idx_treat_subject ON treatments(subject);
CREATE INDEX IF NOT EXISTS idx_tasks_status_due ON tasks(status, due_on);
