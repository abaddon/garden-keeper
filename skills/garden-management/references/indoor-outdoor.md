# Indoor or outdoor — the first thing to check

Every plant row carries `placement`: **`indoor`** or **`outdoor`**, the only two values. The user can
set or change it in the app (plant page → *Where it lives*). Read it **before** you generate an
action, give advice, or assess a new photo — and if a re-check suggests the plant has moved (an
indoor plant photographed on a balcony, a pot suddenly on a windowsill), ask and update it.

Why it matters: it decides which rules apply *at all*. Getting it wrong produces confident, wrong
advice — the worst kind.

## What changes with it

| | Indoors (`indoor`) | Outdoors (`outdoor`) |
|---|---|---|
| Frost / last & first frost (this site: last ~mid-May, first ~late Oct) | not relevant — never use it to time a move or a feed | the main timing driver: harden off, protect, fleece |
| Rain | no rain: every drop is water you gave it | rain can water it, drown it, or splash soil-borne disease onto it |
| Watering | tap water is fine for most, **never** for ericaceous or carnivorous plants; hard tap water leaves lime, so rainwater or filtered for ferns, citrus, calathea, dracaena, banana | rainwater is the default; water deeply and less often, in the morning |
| Light | window orientation decides everything (N = gentle, S = scorch risk behind glass); rotate for even growth | real sun/shade, aspect, and the sun moving through the season |
| Heat | radiators, draughts, air conditioning, humidity trays, misting, grouping plants together | wind, shelter, sun scald in a heatwave |
| Pests & disease | red spider mite (dry air), fungus gnats (wet compost), mealybug, scale, thrips; usually confined to one plant | slugs/snails, aphids, vine weevil, caterpillars, blight, blackspot, rabbit/deer |
| Feeding | houseplant feed through the growing season (~Apr–Sep), nothing in winter | seasonal feeds, mulches, soil-based fertilisers; nothing after late summer for woody plants |
| Pruning | light shaping any time, structural work in spring; deadheading; repotting is a root job | RHS pruning groups, the seasonal windows, and the wildlife rules (nesting birds, hedge cutting) |
| Pots & compost | soilless compost, drainage holes, saucer discipline, repot when root-bound; terracotta dries faster | soil *and* containers; winter wet kills more than cold does |
| Seasons | no dormancy signals to read — the plant never sees winter; growth stalls with light, not temperature | full seasonal cycle; the UK calendar is the clock |

## How to use it in practice

1. **Actions**: an action for an indoor plant never mentions frost dates, hardening off, slugs or
   rain; one for an outdoor plant never mentions radiators, humidity trays or tap-water softening.
2. **Advice**: lead with what the placement makes true. A north window indoors is *low light*, not
   *part shade* — say what that means for growth, watering and rotation.
3. **Photos**: assess against that context. Yellow leaves indoors → overwatering, dry-air edges, low
   light, root-bound pot, before you reach for nutrient deficiency. Yellow leaves outside → often
   the opposite (drought, waterlogging, cold, soil).
4. **Pond** work is always outdoors — `placement` does not apply to `pond:*` subjects.
5. **Missing placement**: set it from the photos and the user's own words. Order of resolution —
   ask first, guess second, and always say which way you went:
   (a) **Ask once**, in the same reply as the identification (a `--questions` entry on the intake,
   or the Telegram message) whenever it is genuinely ambiguous: conservatory, bright porch, unheated
   greenhouse, garage, sunroom.
   (b) **If there is no answer** (a cron run cannot wait for one), record `indoor` — the conservative
   reading, because an indoor plant is never handed frost-dependent work — put the nuance in `bed`
   ("conservatory, unheated"), and say plainly in the summary that you recorded indoor and one tap in
   the app changes it.
   (c) **Balconies, roof terraces, window boxes: `outdoor`.** Rain, wind and frost all reach them. If
   it sits under an overhang, say so in `bed` and check the compost by hand rather than assuming
   rainfall has watered it.
   Cold frames, conservatories, greenhouses and porches count as **indoor** for frost purposes even
   though light and humidity behave outdoors — a single word in `placement`, the nuance in `bed`.
   A photo taken on a balcony is **not** proof of a move: it may be a summer holiday out. Ask before
   flipping a plant's placement on the evidence of one picture.
6. **Winter**: indoor plants still need less water and no feed; outdoor plants need drainage and
   protection. Same season, opposite instructions — which is exactly why the field exists.
