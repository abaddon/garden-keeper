# Plant categories (controlled vocabulary)

Use exactly these values in `plants.category` so grouping, filtering and the briefs stay
consistent. A value outside the list is accepted with a warning — treat that as a bug to fix,
not a new category. Put the detail in `plants.subtype` (free text).

| category | What belongs here | Care notes that follow from the category |
|---|---|---|
| `tree` | Any woody plant with a single trunk / mature canopy | Structural pruning in dormancy (not *Prunus*/*Acer*/*Betula* — late summer); mulch; stakes and ties; arborist above your comfort zone |
| `conifer` | Evergreen/deciduous conifers, hedging or specimen | Prune late spring–early summer; never cut into bare old wood; growth hard to correct |
| `shrub` | Multi-stemmed woody plants (deciduous or evergreen) | Pruning group decides timing (see pruning reference); feed in spring; renew oldest stems |
| `rose` | All roses (shrub/bush, climber, rambler, species, patio, standard) | Type decides pruning; blackspot/rust watch; potassium feed through the season |
| `climber` | Woodys climbers (`Wisteria`, jasmine, clematis, honeysuckle, ivy) | Training/support and directional pruning matter more than cutting hard; group-specific timing |
| `perennial` | Herbaceous plants returning each year | Cut back/divide on their own cycle; stake; feed as growth starts |
| `annual` | Completes its life in one year | Sowing calendar, thinning, deadheading, nothing survives winter |
| `biennial` | Flowers in the second year (foxglove, wallflower, parsley) | Sowing window and knowing that the plant dies after flowering |
| `bulb` | Bulbs, corms, tubers (daffodil, tulip, allium, crocus; dahlias/gladioli get their own note) | Leave foliage 6 weeks after flowering; naturalising vs lifting; planting depth; divide clumps |
| `grass` | Ornamental grasses | Evergreen = comb; deciduous = cut to the ground late winter |
| `fern` | Ferns | Fronds off after winter, shade + moisture, no hard sun |
| `herb` | Culinary/medicinal herbs (also `shrub` if woody — pick the one that drives the care) | Most want lean soil, sun, and frequent harvesting; annual/perennial matters for winter |
| `vegetable` | Edible crops, salads, legumes, brassicas, roots | Rotation, sowing/planting windows, feeding by crop family, harvest |
| `fruit` | Top and soft fruit (apple, pear, plum, raspberry, currant, strawberry) | Pollination partner, pruning by fruit type (trained vs bush vs cane), netting at ripening |
| `hedge` | Plants used as a hedge/screen as a unit | Trimming cycle, nesting birds, the sheer number of plants — register as one row with a count in `notes` |
| `aquatic` | True aquatics submerged/free-floating in the pond (hornwort, elodea, water milfoil) | Oxygenation, invasive-species rules, cut back before die-back in autumn |
| `marginal` | Pond-edge plants in shallow water (`Iris ensata`, reeds, *Lythrum*, marsh marigold) | Water depth band, spread control, cut back in autumn leaving some stems |
| `bog` | Moist-soil plants beside the pond, not in it | Keep damp, no drought, no fertiliser |
| `water_lily` | *Nymphaea* and similar floaters | Basket depth (usually 30–60 cm), leaf coverage % of surface, divide every few years |
| `oxygenator` | Submerged oxygenating plants | Cover for wildlife/fish spawning, needs thinning, oxygen by day too |
| `floating` | Free-floating plants (water hyacinth in a UK pond is seasonal/at risk) | Nutrient uptake but invasive risk; never let it leave the pond |
| `houseplant_out` | Houseplant that *can* go outside for the summer | The date-out (after last frost) / date-back-in (before first frost) routine applies **only to one that is actually `placement='outdoor'`**. Most rows with this category live indoors year-round: never schedule a "date out" for a plant the registry says lives indoors — offer it as a choice instead. |
| `other` | Genuinely unclassifiable for now | Revisit — most "other" rows are a plant that just needs identifying from a photo |

## Deciding a category

1. If the plant is in the pond water → `aquatic`, `marginal`, `water_lily`, `oxygenator`, `floating`.
2. If it is beside the water in damp soil → `bog`.
3. If it dies back to the ground and returns → `perennial` (or `bulb` if it stores in a bulb/corm).
4. If it has woody stems that persist → `shrub` / `rose` / `climber` / `tree` / `conifer` / `hedge`.
5. If it is grown for eating → `vegetable` / `fruit` / `herb`.
6. Only then `other`, with a task to identify it.

Category drives the default cutting/feeding template — so a plant filed in the wrong category
gets wrong advice. If unsure, leave it as the best guess and say so in `notes`, then confirm from
the photo.
