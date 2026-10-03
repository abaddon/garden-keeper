# Outdoor pond care

The pond is a living system: chemistry, temperature and light drive everything. Record readings
(`pond log`) and every product added (`treat add --subject pond:<id>`), and read the history before
changing anything — a single dose without the context of the last month of readings is guesswork.

## Water chemistry targets (freshwater garden pond)

| Measure | Target | What it means |
|---|---|---|
| Temperature | season-dependent | controls feeding, oxygen, disease; 20–24 °C is the fish metabolism sweet spot |
| pH | 7.0–8.5, **stable** | swings are worse than a slightly-off value; sunlight + algae drive daytime swings |
| Ammonia (NH₃/NH₄) | 0 mg/l | any reading = filter/stocking/overfeeding problem or a dead fish/plant |
| Nitrite (NO₂) | 0 mg/l | toxic; the second stage of the nitrogen cycle |
| Nitrate (NO₃) | <25 mg/l ideally, <50 max | plant food — high nitrate = algae |
| KH (carbonate hardness) | 4–8 °dH | buffers pH; below ~3 the pH can crash (especially in soft water or after rain) |
| GH | 6–12 °dH | minerals for fish/plants |
| Phosphate | as low as possible | the other algae driver; leaf/soil run-off and fish food raise it |
| Dissolved oxygen | >6 mg/l; lows at dawn | warm water holds less; aeration matters most in hot, still weather |
| Clarity | see the bottom | green water = suspended algae; brown = silt/tannins |

If ammonia or nitrite is above zero: stop feeding, do a 20–25 % water change with dechlorinated or
rain water, check the filter (is it running? has the media been rinsed in tap water, which kills
the bacteria?), check for dead stock, and re-test daily. Never treat with a chemical before the
cause is understood.

## The seasonal cycle

**Late winter (Feb–Mar)** — restart pump and filter (a filter that has been off goes through a
cycling period — expect a mild ammonia/nitrite blip). Barley straw in late winter/early spring as a
blanketweed preventative (it inhibits it, slowly). First water test as activity resumes. Frog spawn
appears: leave it alone, keep the shallow edges clear.

**Spring (Apr–May)** — green water and blanketweed arrive with light + nutrients. Priorities:
plants (aim for 25–50 % surface cover), shade, oxygenators, manual removal, no tap-water top-ups in
sun, no garden fertiliser anywhere near the pond or its run-off, keep leaves and grass cuttings out.
Start weekly water tests. Fish feeding resumes fully above ~10 °C.

**Summer (Jun–Aug)** — oxygen is the risk: dawn lows, hot still spells. Keep water moving (pump
outlet, air stone, small fountain), top up with rainwater in the evening, remove dead plant
material, don't overfeed fish (uneaten food rots), watch for herons if you have fish (net or
line-and-float), and don't use algaecides that strip oxygen on a hot day.

**Autumn (Sep–Nov)** — the highest-risk period. Net the pond before leaf fall and take leaves out
**the same week** (a handful of leaves in a small pond is enough to kill fish). Cut back dying
marginal growth but leave some stems for emerging insects. Remove excess oxygenator growth before
it dies back. Stop feeding fish progressively as the temperature drops. Sludge can be vacuumed
in early autumn, never in winter.

**Winter (Dec–Feb)** — don't feed fish below ~8–10 °C (their gut is inactive; food rots), don't
break ice (shock waves harm fish — rest a pan of hot water on the surface to make a hole), keep an
air hole for gas exchange, keep filters frost-free and moving water if possible, leave bottom sludge
(frogs, toads and invertebrates hibernate in it — cleaning now kills them). Avoid walking on ice
over deep water, and never let a pond fully freeze solid with fish in it.

## Algae and blanketweed, in order of preference

1. Reduce the cause: nutrients out (leaves, uneaten food, run-off, overstocking), light reduced
   (surface cover 25–50 %), competing plants in (hornwort, elodea, water milfoil; be careful —
   some species are invasive and must not escape into the wild).
2. Manual removal: twirl blanketweed out with a stick or net; do it regularly, not all at once.
3. Barley straw (late winter for spring effect) or a barley-straw extract — a biological
   suppressant, not a killer; it must be kept fresh and may need replacing through the season.
4. Beneficial bacteria/sludge treatments for the bottom — useful support, not a fix for
   overstocking.
5. Only then a commercial treatment, dosed exactly to the label, on a day with good oxygen, with
   fish-safe formulation, and monitored afterwards. Record it in `treatments` with the dose — and
   re-check readings 24–48 h later. Algaecides that kill on contact also consume oxygen as the
   algae decompose: they crash small ponds.

## Fish

- Stocking: conservative is kind — roughly 2.5 cm of fish per 100 litres for goldfish in a
  well-planted, filtered pond; the true constraint is filtration and oxygen, not the volume.
- Feeding: only what is eaten in ~5 minutes; wheatgerm/low-protein food in spring and autumn,
  protein-rich in warm summer; none below 8–10 °C.
- Health: a fish sitting apart, gasping at the surface, clamped fins, or a white spot/fungus is a
  message about water quality first, disease second — test before dosing a fish medication, and
  then record the medication, dose and the readings that led to it.
- Never use a product that is not fish-safe. Anything with a "do not use in ponds containing fish"
  label is refused by us — say so to the user and give the alternative.

## Wildlife

Frogs, toads, newts, dragonflies and damselflies, birds and hedgehogs all use the pond. Make it
safe: **a gently sloping or planted edge** (a steep-sided pond drowns hedgehogs, frogs and other
wildlife — always add a ramp/stones if the sides are vertical), shelter plants, no fish where
there are great crested newts, no heron netting that entangles wildlife (tight netting is a
trap — use a taut net well above the water or a line-and-float). **Great crested newts are
protected in the UK**: sightings are fine, disturbance and work are not — check before any
dredging or major work, and tell the user to get advice rather than act.

**Legal note for invasive species**: letting non-native aquatic plants (water soldier, parrot's
feather, floating pennywort, Himalayan balsam etc.) escape into the wild is an offence in the UK;
never dispose of pond water or plants into a stream, ditch or wild water — bag and bin, or
compost well away from water.

## Clean-out / renovation

Only when needed (silt depth over ~5 cm, or every 5–10 years), and ideally in **early autumn**:
pump water into holding tubs, move plants and then wildlife, remove silt keeping a bucket of the
original water to refill, leave anything removed on the pond edge overnight so hidden wildlife can
crawl back, refill with rain/pond water only, and never use tap water plus cleaning chemicals.
Record the event in `journal` and update `ponds.last_water_change`.
