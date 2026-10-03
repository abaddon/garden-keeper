// Garden Keeper — capture app. Plain JS, no build step.
//   #/            my plants (list)
//   #/plant/<id>  one plant: actions to do, photo history, add photos
//   #/add         capture a new plant
const $ = (id) => document.getElementById(id);
const MAX_SIDE = 2000;
const QUALITY = 0.85;
const MAX_FILES = 6;

// What the registry calls a health state, in the words the user uses.
const HEALTH = {
  good:    ['All good', 'ok'],
  watch:   ['Needs attention', 'warn'],
  poor:    ['Unwell', 'bad'],
  unknown: ['Not checked yet', 'plain'],
  dead:    ['Gone', 'plain'],
};
const ACTION_ICON = {
  prune: '✂️', feed: '🌱', water: '💧', plant: '🪴', move: '📦', divide: '✂️', deadhead: '🌼',
  mulch: '🍂', weed: '🌿', lawn: '🌾', pond: '🐟', inspect: '🔍', harvest: '🧺', protect: '🧣',
  sow: '🌰', photo: '📷', other: '•',
};
const KIND_WORDS = {
  whole: 'whole plant', leaf: 'leaf', leaf_underside: 'leaf underside', flower: 'flower',
  fruit: 'fruit', stem: 'stem', trunk: 'trunk', root: 'roots', damage: 'damage', pest: 'pest',
  symptom: 'symptom', intake: 'new capture', update: 'update', bed: 'bed', label: 'label',
};

let files = [];          // { file, url } — the capture form's queue
let pollTimer = null;    // intake polling (capture form and plant page share it)
let intakeId = null;
let pollCount = 0;
let currentUpload = null; // { intakeId } of the plant page's own upload

// ── tiny DOM/clipboard helpers ────────────────────────────────────────────────
// Node.replaceChildren does NOT filter its arguments: a block that is null for this plant would be
// rendered as the literal word "null" on the page. Every render that assembles variable blocks goes
// through mount() so an absent block is simply absent.
function mount(box, ...kids) {
  box.replaceChildren(...kids.flat().filter((k) => k !== null && k !== undefined && k !== false && k !== ''));
  return box;
}

function el(tag, props = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) node.append(kid);
  return node;
}

function plural(n, word) { return `${n} ${word}${n === 1 ? '' : 's'}`; }
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);   // care values and status words read as sentences

function fmtDay(iso) {
  if (!iso) return '';
  const d = new Date(`${String(iso).slice(0, 10)}T12:00:00`);
  if (isNaN(d)) return String(iso);
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

// `cls` says how urgent it looks (anything inside a week is amber); `days` says how many days away it
// actually is, and only the number may decide behaviour — treating the colour as the fact is how a
// job due in four days asked the user what they had changed.
function dueLabel(dateStr) {
  if (!dateStr) return { text: 'whenever you can', cls: 'anytime', days: null };
  const due = new Date(`${dateStr.slice(0, 10)}T12:00:00`);
  const today = new Date(); today.setHours(12, 0, 0, 0);
  const days = Math.round((due - today) / 86400000);
  if (days < 0) return { text: `overdue by ${plural(-days, 'day')}`, cls: 'overdue', days };
  if (days === 0) return { text: 'due today', cls: 'due', days };
  if (days === 1) return { text: 'due tomorrow', cls: 'due', days };
  if (days <= 7) return { text: `due in ${plural(days, 'day')}`, cls: 'due', days };
  return { text: `due ${fmtDay(dateStr)}`, cls: 'scheduled', days };
}

function friendly(message, status) {
  const text = (message || '').toLowerCase();
  if (status === 401) return 'Your session expired — reload the page and try again.';
  if (status === 429 || text.includes('too many')) return 'Too many changes just now — give it a second.';
  if (status === 413) return message || 'That photo is too big — try again, or send a smaller one.';
  if (status === 409) return message || 'That plant is no longer in the garden.';
  if (status === 404) return message || 'That is not there any more — pull the page back.';
  if (text.includes('exceeded maximum size')) return 'That note was too long — just a line or two is plenty.';
  if (status === 400 && text.includes('part')) return 'Something in that upload was too big — try again with fewer or smaller photos.';
  if (status === 0) return "Couldn't reach your garden — check your connection (phone on the Tailscale app?) and try again.";
  if (status >= 500) return 'Something went wrong at my end — nothing was saved. Try again in a moment.';
  return message || 'Something went wrong — try again in a moment.';
}

async function api(path, opts) {
  // A request that never settles is indistinguishable from a dead app: cap it, and say so.
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), 30000);
  // A string body IS json, and FastAPI will not parse it without the header — omitting it turns a
  // perfectly good mutation into a validation error that reads as nonsense on screen. Set it here so
  // no call site has to remember; FormData uploads go through upload() and are untouched.
  const init = Object.assign({}, opts,
    { headers: Object.assign({ Accept: 'application/json' }, (opts && opts.headers) || {}), signal: ctl.signal });
  if (typeof init.body === 'string'
      && !Object.keys(init.headers).some((h) => h.toLowerCase() === 'content-type')) {
    init.headers['Content-Type'] = 'application/json';
  }
  let res;
  try {
    res = await fetch(path, init);
  } catch (err) {
    clearTimeout(timer);
    throw new Error(err && err.name === 'AbortError'
      ? 'This is taking longer than it should — the phone reached the garden but got no answer. Try again.'
      : friendly('', 0));
  }
  clearTimeout(timer);
  let data = {};
  try { data = await res.json(); } catch (e) { /* not JSON */ }
  // FastAPI puts its own messages in `detail` (a bare string, or a list of validation errors).
  const server = typeof data.error === 'string' ? data.error
    : typeof data.detail === 'string' ? data.detail
      : Array.isArray(data.detail) ? 'That request did not make sense.' : '';
  if (!res.ok) throw new Error(friendly(server, res.status));
  return data;
}

function healthChip(status, value) {
  if (status === 'draft') return el('span', { class: 'chip warn', text: 'Being identified…' });
  const [label, tone] = HEALTH[value] || HEALTH.unknown;
  return el('span', { class: `chip ${tone}`, text: label });
}

// One count everywhere: everything waiting — tasks, follow-ups owed, feeds suggested but not
// applied. The plant page's Actions list is the tasks; its "Also waiting" block is the rest, so
// the chip and the page always account for each other.
function waitingChip(p) {
  const a = pendingOf(p);
  if (!a.open) return el('span', { class: 'chip ok', text: '✓ Nothing to do' });
  // the number must describe the window it names: "due this week" counts what is due this week,
  // never the whole backlog (a Monstera with 12 items recorded had only 2 due inside the week)
  if (a.overdue) return el('span', { class: 'chip bad', text: `🗒️ ${a.overdue} due now` });
  if (a.due_soon) return el('span', { class: 'chip warn', text: `🗒️ ${a.due_soon} due this week` });
  return el('span', { class: 'chip plain', text: `🗒️ ${a.open} to do` });
}

// ── routing ───────────────────────────────────────────────────────────────────
function show(view) {
  for (const name of ['list', 'plant', 'add']) $(`view-${name}`).hidden = (name !== view);
  $('add-shortcut').hidden = (view !== 'list');
}

function route() {
  if (viewer.isOpen()) viewer.close(true);   // a navigation beats the viewer: it never sits over another view
  const hash = location.hash.replace(/^#\/?/, '');
  stopPolling();
  const plant = hash.match(/^plant\/(\d+)$/);
  if (plant) { show('plant'); renderPlant(Number(plant[1])); return; }
  if (hash.startsWith('add')) { show('add'); $('app-title').textContent = 'Add a plant';
    $('subtitle').textContent = 'A photo or two is all it takes'; return; }
  // #/in and #/out are the two group views; no selection is the "needs action" home view
  show('list'); renderList(['in', 'out', 'all'].includes(hash) ? hash : '');
}

// ── view: my plants ───────────────────────────────────────────────────────────
// A plant "needs action now" when work is overdue, due within the week, or its health has been
// flagged — the same three reasons the agent would put it at the top of a message. `pending` comes
// from one definition in the registry CLI: open tasks, observation follow-ups still owed, and
// treatments suggested but not applied (so the home screen cannot disagree with the digest).
function pendingOf(p) {
  if (!p) return {};
  if (p.pending) return p.pending;                  // a plant from the list
  if (p.actions) return p.actions;                  // older payload
  return ('open' in p || 'overdue' in p) ? p : {};  // already a pending set (the plant page's cache)
}
const needsNow = (p) => {
  const a = pendingOf(p);
  return a.overdue > 0 || a.due_soon > 0 || p.health_status === 'poor' || p.health_status === 'watch';
};
const byName = (a, b) => String(a.name || '').localeCompare(String(b.name || ''), 'en', { sensitivity: 'base' });
const HEALTH_URGENCY = { poor: 0, watch: 1, unknown: 2, good: 3 };

// One short line saying why this plant is in front of you — the action it is waiting on, or the
// health flag that put it there. Nothing to say is a good answer: no line.
function whyLine(p) {
  const a = pendingOf(p);
  const nxt = a.next || {};                     // {kind, icon, title, due_on, state} when the source is `needs`
  const icon = nxt.icon || '📌';
  const title = nxt.title || a.next_title || 'next action';
  const state = nxt.state || a.next_state;
  const due = nxt.due_on || a.next_due;
  if (state === 'overdue') {
    return el('p', { class: 'card-why bad', text: `⏰ Overdue: ${title}` });
  }
  if (state === 'due') {
    return el('p', { class: 'card-why warn', text: `${icon} ${cap(dueLabel(due).text)}: ${title}` });
  }
  if (p.health_status === 'poor' || p.health_status === 'watch') {
    const words = (HEALTH[p.health_status] || HEALTH.unknown)[0];
    return el('p', { class: 'card-why warn', text: `🩺 ${words} — worth a closer look` });
  }
  return null;
}

async function renderList(view) {
  view = ['in', 'out', 'all'].includes(view) ? view : '';   // one place decides what a view is
  $('app-title').textContent = 'My plants';
  $('subtitle').textContent = 'Your garden, plant by plant';
  const box = $('plants');
  $('list-error').hidden = true;
  if (!box.childElementCount) box.append(el('div', { class: 'loading muted small', text: 'Loading your garden…' }));

  let data, overview = { pending: 0, processing: 0 };
  try {
    [data, overview] = await Promise.all([api('/api/plants'), api('/api/overview').catch(() => overview)]);
  } catch (err) {
    box.replaceChildren();
    $('list-error-text').textContent = err.message;
    $('list-error').hidden = false;
    $('list-empty').hidden = true;
    $('filters').hidden = true;
    return;
  }

  const plants = data.plants || [];
  const counts = data.counts || {};
  $('list-empty').hidden = plants.length > 0;
  $('filters').hidden = plants.length === 0;

  // the buttons carry their own totals, so the choice is informed before it is made
  const unplaced = counts.unplaced || 0;
  const notSet = unplaced ? ` · ${unplaced} with no place set yet` : '';
  const busy = plants.filter(needsNow).length;
  $('n-in').textContent = counts.indoor || 0;
  $('n-out').textContent = counts.outdoor || 0;
  $('n-all').textContent = plants.length;
  for (const [kind, id, word, n] of [['in', 'chip-in', 'In house', counts.indoor || 0],
                                     ['out', 'chip-out', 'Outside', counts.outdoor || 0],
                                     ['all', 'chip-all', 'All plants', plants.length]]) {
    $(id).setAttribute('aria-pressed', String(view === kind));
    $(id).setAttribute('aria-label', `${word} — ${plural(n, 'plant')}` +
      (view === kind ? ', selected. Tap again for what needs action.' : '.'));
  }

  let list, note;
  if (view === 'in' || view === 'out' || view === 'all') {
    const want = { in: 'indoor', out: 'outdoor' }[view];
    list = (want ? plants.filter((p) => p.placement === want) : plants.slice()).sort(byName);
    const label = { in: '🏠 In house', out: '🌤️ Outside', all: '🌿 All plants' }[view];
    // every plant stays reachable: "All" is where one with an unrecognised place is found
    note = `${label} · ${plural(list.length, 'plant')}${view === 'all' ? ` · ${busy} need action` : notSet}`
         + ' — tap it again for what needs action';
  } else {
    // rank by everything waiting (the same numbers the chip and the API use), never by tasks alone
    const pend = pendingOf;
    list = plants.filter(needsNow)
      .sort((a, b) => (pend(b).overdue || 0) - (pend(a).overdue || 0)
            || (pend(b).due_soon || 0) - (pend(a).due_soon || 0)
            || HEALTH_URGENCY[a.health_status] - HEALTH_URGENCY[b.health_status]
            || byName(a, b));
    note = list.length
      ? `Overdue, due this week or flagged${unplaced ? notSet : ''} — tap 🏠 🌤️ or 🌿 for the full lists`
      : `Nothing overdue, nothing due this week and nothing flagged${unplaced ? notSet : ''} — tap 🏠 🌤️ or 🌿 for the full lists`;
  }
  $('filters-note').textContent = note;

  const cards = list.map((p) => plantCard(p, whyLine(p)));
  if (!list.length) {
    cards.push(el('div', { class: 'card empty' },
      el('div', { class: 'status-icon', text: view === '' ? '🌿' : '🪴' }),
      el('h2', { text: view === '' ? 'Nothing needs doing just now'
        : (view === 'in' ? 'No plants in the house yet' : (view === 'out' ? 'No plants recorded as outside yet' : 'No plants yet')) }),
      el('p', { class: 'muted small', text: view === ''
        ? 'No overdue work, nothing due this week and no plant flagged — the buttons above show the full lists.'
        : (view === 'in' ? 'Open a plant and set where it lives to In house.'
           : (view === 'out' ? 'Open a plant and set where it lives to Outside.'
              : 'Add the first one with the ＋ button.')) })));
  }
  box.replaceChildren(...cards);

  const inFlight = (overview.pending || 0) + (overview.processing || 0);
  $('banner').hidden = inFlight === 0;
  if (inFlight) {
    $('banner').textContent = inFlight === 1
      ? '🌱 Looking at 1 new capture — usually a couple of minutes.'
      : `🌱 Looking at ${inFlight} new captures — they go one batch at a time, so give it a few minutes.`;
  }
  // one number, one meaning: how many plants want action now (the same set the page opens with)
  const needs = plants.filter(needsNow).length;
  $('subtitle').textContent = plants.length
    ? `${plural(plants.length, 'plant')}${needs ? ` · ${needs} need action now` : ' · nothing needs doing'}`
    : 'Your garden, plant by plant';
}

// A photo whose file has gone missing must not become a broken-image icon on the phone: swap in the
// placeholder as soon as the load fails (a 404, a corrupt JPEG, an offline moment).
function photoImg(src, alt, extra) {
  const img = el('img', Object.assign({ src, alt, loading: 'lazy' }, extra || {}));
  img.addEventListener('error', () => {
    img.replaceWith(el('span', { class: 'shot-missing', title: 'This photo is missing from disk', text: '🌫️' }));
  });
  return img;
}

// ── the photo viewer ─────────────────────────────────────────────────────────
// Tapping a photo opens it here, over the plant page. It used to navigate to the bare image in a
// new tab, and on the phone that view has no chrome and nothing to close it with — the only way
// out was to kill the app. This is a dialog instead: the ✕ (44 px), a tap anywhere outside the
// photo, Escape, or the phone's own back gesture all close it, and the plant page underneath is
// exactly where it was left. The call sites keep their <a href>, so a long-press (share, open in
// new tab) or a modifier-click still behaves as a plain link.
const viewer = (() => {
  const box = el('div', { class: 'photo-view', hidden: true, role: 'dialog',
                          'aria-modal': 'true', 'aria-label': 'Photo' });
  const pic = el('img', { alt: '' });
  const fail = el('p', { class: 'photo-fail', hidden: true, text: 'This photo is missing from disk.' });
  const shut = el('button', { class: 'photo-shut', type: 'button',
                              'aria-label': 'Close the photo', text: '✕' });
  box.append(pic, fail, shut);
  document.body.append(box);

  let opener = null;     // where focus goes back to when the viewer closes
  let onStack = false;   // the one history entry the viewer owns while it is open
  let ours = false;      // marks the popstate we asked for, so the handler can tell it from a gesture

  const isOpen = () => !box.hidden;

  function close(fromBack) {
    if (!isOpen()) return;
    box.hidden = true;
    pic.removeAttribute('src');            // never let the next open flash the previous photo
    pic.hidden = false;
    fail.hidden = true;
    document.body.classList.remove('photo-open');
    if (opener && document.contains(opener)) opener.focus();
    opener = null;
    const pushed = onStack;
    onStack = false;
    if (pushed && !fromBack) { ours = true; history.back(); }   // keep the history stack balanced
  }

  function open(src, alt, from) {
    if (!src) return;
    pic.hidden = false;
    pic.alt = alt || '';
    pic.src = src;
    fail.hidden = true;
    box.hidden = false;
    document.body.classList.add('photo-open');
    opener = from || null;
    shut.focus();
    if (!onStack) {
      // One entry, so the back gesture closes the photo and lands on the plant page — not on
      // whatever came before it. Without pushState the ✕ still closes it.
      try { history.pushState({ photo: true }, ''); onStack = true; } catch (e) { onStack = false; }
    }
  }

  pic.addEventListener('error', () => { pic.hidden = true; fail.hidden = false; });
  shut.addEventListener('click', () => close(false));
  // a tap anywhere that is not the photo itself is a tap on the backdrop
  box.addEventListener('click', (e) => { if (e.target !== pic) close(false); });
  addEventListener('keydown', (e) => { if (e.key === 'Escape' && isOpen()) close(false); });
  addEventListener('popstate', () => {
    if (ours) { ours = false; return; }    // the entry we popped ourselves
    if (isOpen()) close(true);             // the phone's back gesture: close, stay on the plant
  });
  return { open, close, isOpen };
})();

// A plain tap opens the viewer; everything else (long-press, ⌘-click, middle click) stays a link.
function openFullPhoto(e, alt) {
  if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
  const link = e.currentTarget;
  e.preventDefault();
  viewer.open(link.href, alt, link);
}

function plantCard(p, why) {
  const thumb = el('div', { class: 'thumb' },
    p.photo_id
      ? photoImg(`/api/photo/${p.photo_id}?w=240`, '')
      : el('span', { class: 'thumb-empty', text: '🪴' }));
  const sub = [p.common_name || p.botanical, p.category, p.bed].filter(Boolean).join(' · ');
  const main = el('div', { class: 'pc-main' },
    el('p', { class: 'pc-name', text: p.name || 'Unnamed plant' }),
    sub ? el('p', { class: 'pc-sub muted small', text: sub }) : null,
    el('div', { class: 'pc-badges' }, healthChip(p.status, p.health_status), waitingChip(p)),
    why || null);
  return el('a', { class: 'plant-card', href: `#/plant/${p.id}` }, thumb, main, el('span', { class: 'chev', text: '›' }));
}

// ── view: one plant ───────────────────────────────────────────────────────────
// Where it lives: two answers, and changing it changes the advice — the agent reads this before
// every action it generates, every recommendation and every photo assessment.
function placementRow(p) {
  const select = el('select', { class: 'place-select', id: 'placement',
                                'aria-label': 'Where this plant lives' },
    el('option', { value: 'indoor', text: '🏠 In house' }),
    el('option', { value: 'outdoor', text: '🌤️ Outside' }));
  if (p.placement === 'indoor' || p.placement === 'outdoor') {
    select.value = p.placement;
  } else {
    // never let an unset plant look like a decided one: show that nobody has said yet
    select.insertBefore(el('option', { value: '', text: 'Not set yet', disabled: true }),
                        select.firstChild);
    select.value = '';
  }
  const status = el('span', { class: 'place-status muted small', text: '' });
  select.addEventListener('change', async () => {
    const value = select.value;
    const previous = p.placement || '';
    if (!value) return;
    select.disabled = true;
    status.textContent = 'Saving…';
    try {
      const res = await api(`/api/plants/${p.id}/placement`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ placement: value }) });
      toast(res.placement === 'indoor' ? 'Saved — in house 🏠' : 'Saved — outside 🌤️');
      renderPlant(p.id);            // repaint the facts line under it too
    } catch (err) {
      select.value = previous;      // the screen must not claim a change that did not happen
      status.textContent = '';
      toast(err.message);
      select.disabled = false;
    }
  });
  return el('div', { class: 'place-row' },
    el('span', { class: 'place-lbl', text: 'Where it lives' }), select, status);
}

async function renderPlant(id) {
  const box = $('view-plant');
  box.replaceChildren(el('a', { class: 'back', href: '#/', text: '← My plants' }),
                      el('p', { class: 'loading muted small', text: 'Opening…' }));
  $('app-title').textContent = 'Plant';
  $('subtitle').textContent = '';
  let data;
  try {
    data = await api(`/api/plants/${id}`);
  } catch (err) {
    box.replaceChildren(el('a', { class: 'back', href: '#/', text: '← My plants' }),
      el('div', { class: 'card empty' }, el('p', { class: 'status-icon', text: '⚠️' }),
         el('h2', { text: "Couldn't open that plant" }), el('p', { class: 'muted', text: err.message })));
    return;
  }

  const p = data.plant;
  $('app-title').textContent = p.name || 'Plant';
  $('subtitle').textContent = [p.botanical || p.common_name, p.bed].filter(Boolean).join(' · ');

  // The hero is the newest photo whose file is really there (the API tells us); a plant with no
  // usable photo gets the placeholder instead of a broken image.
  const heroShot = data.hero && data.hero.id ? data.hero.id : null;
  const hero = el('div', { class: 'hero' }, heroShot
    ? el('a', { href: `/api/photo/${heroShot}?w=900`, target: '_blank', rel: 'noopener',
                onclick: (e) => openFullPhoto(e, `Latest photo of ${p.name || 'this plant'}`) },
         photoImg(`/api/photo/${heroShot}?w=480`, `Latest photo of ${p.name || 'this plant'}`))
    : el('div', { class: 'hero-empty' }, el('span', { text: '🪴' }),
         el('p', { class: 'muted small', text: 'No photos yet' })));

  const facts = [
    p.category && [p.category, p.subtype].filter(Boolean).join(' · '),
    p.bed && `📍 ${p.bed}`,
    p.hardiness && `❄️ ${p.hardiness}`,
    p.prune_months && `✂️ cut in ${monthList(p.prune_months)}`,
    p.feed_months && `🌱 fed in ${monthList(p.feed_months)}`,
    p.last_pruned && `last cut ${fmtDay(p.last_pruned)}`,
    p.pests_known && `⚠️ past trouble: ${p.pests_known}`,
  ].filter(Boolean);

  const pending = data.pending || {};
  const extraItems = pending.extra || [];
  plantCache = { ...pending, extra: extraItems, status: p.status, health_status: p.health_status };
  const head = el('div', { class: 'plant-head' },
    el('div', { class: 'ph-badges' }, healthChip(p.status, p.health_status), waitingChip(plantCache)),
    notesElement(p.notes),
    facts.length ? el('ul', { class: 'facts' }, facts.map((f) => el('li', { text: f }))) : null,
    placementRow(p));

  // actions
  const actionsBlock = el('section', { class: 'block' },
    el('h3', { text: data.actions.length ? `Actions (${data.actions.length})` : 'Actions' }),
    el('p', { class: 'muted small', text: data.actions.length
      ? 'Tap Done when you have done it — it leaves the list straight away.'
      : (extraItems.length ? 'No tasks — the work waiting on you is below.'
                           : 'Nothing to do for this plant right now. 🎉') }));
  const list = el('ul', { class: 'actions' });
  const plantNames = [p.name, p.common_name, p.botanical];
  data.actions.forEach((a) => list.append(actionRow(a, plantNames, id)));
  actionsBlock.append(list);
  // anything waiting that is not a task: a follow-up owed, a treatment suggested but not applied
  const waitingBlock = extraItems.length ? el('section', { class: 'block' },
    el('h3', { text: `Also waiting (${extraItems.length})` }),
    el('p', { class: 'muted small', text: 'Recorded work that is not a task — clear it when it is done.' }),
    el('ul', { class: 'actions' }, extraItems.map(waitingRow))) : null;

  // photos, oldest first
  const photosBlock = el('section', { class: 'block' },
    el('h3', { text: `Photos (${data.photos.length})` }));
  if (data.photos.length) {
    photosBlock.append(el('ul', { class: 'timeline' }, data.photos.map(photoRow)));
  } else {
    photosBlock.append(el('p', { class: 'muted small', text: 'No photos on file yet.' }));
  }

  // A compose form, not a tripwire. Choosing photos only fills the queue — the batch and the note
  // go to Garden Keeper when the user taps Send, so a half-considered pick is never uploaded.
  const fileInput = el('input', { id: 'plant-files', type: 'file', accept: 'image/*', multiple: true, hidden: true });
  const upCard = el('div', { class: 'card upload-card', hidden: true });
  const plantQueue = [];
  const thumbs = el('ul', { class: 'thumbs', hidden: true });
  const queueNote = el('p', { class: 'muted small', id: 'plant-queue-note' });
  const picker = el('button', { class: 'ghost', type: 'button', id: 'plant-add-photos' },
                    el('span', { class: 'ico', text: '🖼️' }), 'Choose photos');
  const sendBtn = el('button', { class: 'primary', type: 'button', id: 'plant-send',
                                 text: 'Send to Garden Keeper', disabled: true });
  const clearBtn = el('button', { class: 'ghost', type: 'button', id: 'plant-clear', text: 'Clear', hidden: true });
  const note = el('input', { type: 'text', id: 'plant-note', autocomplete: 'off',
                             placeholder: 'e.g. two yellow leaves at the base' });

  function paintCompose() {
    paintQueue(thumbs, plantQueue);
    clearBtn.hidden = plantQueue.length === 0;
    queueNote.textContent = plantQueue.length
      ? `${plural(plantQueue.length, 'photo')} ready${plantQueue.length >= MAX_FILES ? ` (the most in one batch)` : ` of up to ${MAX_FILES}`}`
      : '';
    sendBtn.disabled = plantQueue.length === 0;
    sendBtn.textContent = plantQueue.length
      ? `Send ${plural(plantQueue.length, 'photo')} to Garden Keeper` : 'Send to Garden Keeper';
  }
  const emptyQueue = () => { plantQueue.forEach((q) => URL.revokeObjectURL(q.url)); plantQueue.length = 0; };
  picker.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', (e) => { addToQueue(plantQueue, e.target.files); e.target.value = ''; paintCompose(); });
  thumbs.addEventListener('queue-change', paintCompose);
  clearBtn.addEventListener('click', () => { emptyQueue(); paintCompose(); });
  sendBtn.addEventListener('click', async () => {
    const picked = plantQueue.map((q) => q.file);
    if (!picked.length) return;
    const res = await uploadPlantPhotos(id, picked, note.value, upCard, [picker, sendBtn, clearBtn]);
    if (res) {
      emptyQueue(); note.value = ''; paintCompose();
      toast(`${plural(picked.length, 'photo')} sent to Garden Keeper`);
    }
  });
  paintCompose();
  const lapsed = ['removed', 'dead'].includes(p.status);
  const addBlock = lapsed
    ? el('section', { class: 'block' },
        el('h3', { text: 'Add photos' }),
        el('p', { class: 'muted small',
                  text: 'This plant is no longer in the garden, so there is nothing to re-check.' }))
    : el('section', { class: 'block' },
        el('h3', { text: 'Add photos' }),
        el('p', { class: 'muted small', text: 'Send today\'s pictures and Garden Keeper re-checks this plant\'s health.' }),
        el('label', { class: 'field' }, 'What has changed? ', el('span', { class: 'muted', text: 'optional' }), note),
        el('div', { class: 'picker-row' }, picker, clearBtn),
        fileInput, thumbs, queueNote,
        el('div', { class: 'picker-row fb-acts' }, sendBtn), upCard);

  mount(box, el('a', { class: 'back', href: '#/', text: '← My plants' }),
             hero, head, actionsBlock, waitingBlock, photosBlock, addBlock,
                      el('p', { class: 'muted small', text: 'Also recorded: '
                        + `${plural(data.counts.observations, 'observation')}, `
                        + `${plural(data.counts.treatments, 'treatment')}. Ask on Telegram for the detail.` }));
  clampDetails(box);   // the view is on screen by now, so the clamped height is real
}

function monthList(months) {
  const names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return String(months).split(',').map((part) => {
    const [a, b] = part.trim().split('-');
    const from = names[Number(a) - 1] || a;
    return b ? `${from}–${names[Number(b) - 1] || b}` : from;
  }).join(', ');
}

// The plant page already names the plant, so a title that repeats it is noise:
// "Swiss cheese plant: cut off the yellow leaf" under the heading "Swiss cheese plant".
// Strip a leading "Name:" / "Name —" and a trailing "of/for the Name", then tidy the joins.
// Left alone when too little is left to read as a sentence.
function withoutPlantName(title, names) {
  let out = String(title || '');
  const list = (names || []).filter((n) => n && n.length >= 4);   // never mangle "fig" / "bay"
  for (const name of list) {
    const esc = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    // "Name: rest" / "Name — rest" / "Name (north window): rest"
    out = out.replace(new RegExp(`^\\s*${esc}\\s*(?:\\([^)]*\\))?\\s*[:—–-]\\s*`, 'i'), '');
    // "…  Name (north window)  ·  … of/for/on/in/to the Name  ·  a bare mention"
    out = out.replace(new RegExp(`\\s*(?:of |for |on |in |to )?(?:the\\s+)?${esc}\\s*\\([^)]*\\)`, 'ig'), ' ');
    out = out.replace(new RegExp(`\\s*(?:of |for |on |in |to )?the\\s+${esc}`, 'ig'), ' ');
    out = out.replace(new RegExp(`\\s*${esc}\\b`, 'ig'), ' ');
  }
  out = out.replace(/\s{2,}/g, ' ').replace(/\s+([,.;:!?])/g, '$1').replace(/\s*[—–-]+\s*$/, '').trim();
  if (out.length < 6) return title;          // "Feed" alone helps nobody: keep the original
  return out[0].toUpperCase() + out.slice(1);
}

// ── reading the registry's free text ───────────────────────────────────────────
// A plant's `notes` is free text, written as a lead line followed by "Label: fact" care lines (the
// skill asks for that). Older notes are one long paragraph, so sentences are the fallback unit and
// anything unrecognised still renders as prose. Nothing here is trusted: a note that does not fit
// the shape simply comes out as paragraphs, exactly as before.
const NOTE_LABEL_RE = /^([A-Z][A-Za-z-]{1,20}(?: [a-z-]{2,12})?):\s+(\S.*)$/;   // "Light:", "Radiator alongside:"
const NOTE_META_RE = /^(?:unknown|not recorded|not yet known|none recorded|no pests|no pets|unclear)\b/i;
const NOTE_LOG_RE = /^((?:[0-9]{1,2}\s+[A-Z][a-z]{2,9}\s+[0-9]{4}|(?:first|second|third|fourth|fifth|latest|recent|final)?\s*review\b[^:]{0,28})):\s*(\S.*)$/i;

function noteUnits(notes) {
  const raw = String(notes || '').trim();
  if (!raw) return [];
  let units = raw.split(/\n+/).map((s) => s.trim()).filter(Boolean);
  if (units.length < 2) {
    // one long line: fall back to sentences (lookbehind is fine on the phones this runs on)
    try { units = raw.split(/(?<=[.!?])\s+(?=[A-Z0-9(❓“"])/).map((s) => s.trim()).filter(Boolean); }
    catch (e) { units = [raw]; }
  }
  return units;
}

function notesElement(notes) {
  const units = noteUnits(notes);
  if (!units.length) return null;
  const lead = [], care = [], body = [], checks = [];
  let current = null;
  for (const u of units) {
    const log = NOTE_LOG_RE.exec(u);
    if (log) {
      current = { when: log[1].trim(), body: [log[2]] };
      checks.push(current);
      continue;
    }
    const label = NOTE_LABEL_RE.exec(u);
    if (label && !NOTE_META_RE.test(u)) {
      care.push([label[1].trim(), label[2]]);
      current = null;
      continue;
    }
    if (NOTE_META_RE.test(u)) {
      // "Unknown: …" is a missing care fact, so it reads as one more row of the same list;
      // anything else that looks like a gap note stays plain prose rather than getting a label.
      const stripped = /^unknown\s*:\s*(.+)$/i.exec(u);
      if (stripped) care.push(['Unknown', stripped[1]]);
      else body.push(u);
      current = null;
      continue;
    }
    if (current) current.body.push(u);
    else if (care.length || body.length) body.push(u);
    else lead.push(u);
  }
  const box = el('div', { class: 'ph-notes' });
  if (lead.length) box.append(el('p', { class: 'note-lead', text: lead.join(' ') }));
  if (care.length) {
    // values read as a sentence under their label, so the first letter is raised
    const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);
    box.append(el('dl', { class: 'care' }, care.map(([k, v]) =>
      el('div', { class: 'care-row' }, el('dt', { text: k }), el('dd', { text: cap(v) })))));
  }
  if (body.length) box.append(...body.map((t) => el('p', { class: 'note-body', text: t })));
  for (const c of checks) {
    box.append(el('div', { class: 'note-check' },
      el('p', { class: 'check-when', text: c.when }),
      ...c.body.map((t) => el('p', { class: 'check-body', text: t }))));
  }
  return box;
}

// A long "why"/assessment is worth keeping but not worth eight lines in a list: clamp it to three
// and offer the rest behind a real button (so it is reachable, not just hidden). One block = one
// button, however many paragraphs it holds.
function clampedBlock(blocks) {
  const wrap = el('div', { class: 'clamp-wrap' },
    ...blocks.map((b) => el('p', { class: b.cls }, ...(Array.isArray(b.parts) ? b.parts : [b.parts]))));
  const btn = el('button', { class: 'more', type: 'button', 'aria-expanded': 'false', text: 'More' });
  btn.addEventListener('click', () => {
    const open = wrap.classList.toggle('open');
    btn.setAttribute('aria-expanded', String(open));
    btn.textContent = open ? 'Less' : 'More';
  });
  wrap.append(btn);
  return wrap;
}

function clamped(parts, cls) { return clampedBlock([{ cls, parts }]); }

// Clamp only where a clamp actually saves space, and decide it here rather than in CSS: the clamp
// is applied by the `.clamped` class this function sets, *after* measuring with the clamp off. So a
// viewport that changes after the first render — a rotate, split screen, a desktop window — gets
// re-measured instead of leaving text cut off behind a button that was never shown. An element we
// cannot measure (hidden view) is left unclamped: showing everything is the safe failure.
function clampDetails(root) {
  root.querySelectorAll('.clamp-wrap').forEach((wrap) => {
    const paras = [...wrap.querySelectorAll(':scope > p')];
    const btn = wrap.querySelector('.more');
    if (!paras.length || !btn) return;
    const wasOpen = wrap.classList.contains('open');
    // measure with the clamp actually applied (and any expansion folded away): scrollHeight then
    // reports the full text of each paragraph, clientHeight its three clamped lines
    wrap.classList.remove('open');
    wrap.classList.add('clamped');
    const overflows = paras.reduce((n, p) => n + Math.max(0, p.scrollHeight - p.clientHeight), 0) > 4;
    const open = overflows && wasOpen;
    wrap.classList.toggle('clamped', overflows);
    wrap.classList.toggle('open', open);
    btn.hidden = !overflows;
    btn.setAttribute('aria-expanded', String(open));
    btn.textContent = open ? 'Less' : 'More';
  });
}

// Re-measure whenever the geometry can have changed underneath us.
let clampTimer = null;
function reclamp() {
  clearTimeout(clampTimer);
  clampTimer = setTimeout(() => {
    const name = ['list', 'plant', 'add'].find((n) => !$(`view-${n}`).hidden);
    if (name) clampDetails($(`view-${name}`));
  }, 120);
}
addEventListener('resize', reclamp, { passive: true });
addEventListener('orientationchange', reclamp);
document.addEventListener('visibilitychange', () => { if (!document.hidden) reclamp(); });
if (document.fonts && document.fonts.ready) document.fonts.ready.then(reclamp).catch(() => {});

function actionRow(a, plantNames, plantId) {
  const due = dueLabel(a.due_on);
  const asks = due.days !== null && due.days <= 0;   // due today or late: work actually done, so ask
  const row = el('li', { class: `action-row ${due.cls}`, 'data-task': a.id },
    el('span', { class: 'a-ico', text: ACTION_ICON[a.category] || ACTION_ICON.other }),
    el('div', { class: 'a-main' },
      el('p', { class: 'a-title', text: withoutPlantName(a.title, plantNames) }),
      el('p', { class: `a-due ${due.cls}`, text: due.text + (a.priority === 'high' ? ' · important' : '') }),
      a.detail ? clamped(a.detail, 'a-detail') : null),
    el('button', { class: 'done-btn', type: 'button', text: 'Done',
                   onclick: (e) => (asks ? openFeedback(row, a, plantId, e.currentTarget)
                                         : markDone(a.id, row, e.currentTarget)) }));
  return row;
}

// Tapping Done on work that was due opens this: what changed (free text) plus optional photos, with
// Save and a one-tap "Done, nothing to add". Photos go in first — if they fail the task stays open and
// the batch is still queued, so a failed send never half-closes the job. The note lands on the task and
// in the plant's history (a maintenance observation), which is where the agent reads it.
function openFeedback(row, task, plantId, doneButton) {
  if (row.querySelector('.fb-panel')) return;
  const queue = [];
  const note = el('input', { class: 'fb-note', type: 'text', autocomplete: 'off',
                             placeholder: 'e.g. watered 2 litres, compost dry to 2 cm' });
  const thumbs = el('ul', { class: 'thumbs', hidden: true });
  const fileInput = el('input', { type: 'file', accept: 'image/*', multiple: true, hidden: true });
  const pick = el('button', { class: 'ghost', type: 'button' },
                  el('span', { class: 'ico', text: '🖼️' }),
                  el('span', { class: 'lbl', text: 'Add photos' }));
  const save = el('button', { class: 'primary', type: 'button', text: 'Save', disabled: true });
  const skip = el('button', { class: 'ghost', type: 'button', text: 'Done, nothing to add' });
  const shut = el('button', { class: 'fb-x', type: 'button', 'aria-label': 'Close, leave this task open', text: '✕' });
  const controls = [save, skip, pick, shut];

  function paint() {
    paintQueue(thumbs, queue);
    save.disabled = !queue.length && !note.value.trim();
    pick.querySelector('.lbl').textContent = queue.length >= MAX_FILES
      ? `${plural(queue.length, 'photo')} chosen` : 'Add photos';
  }
  note.addEventListener('input', paint);
  thumbs.addEventListener('queue-change', paint);
  pick.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', (e) => { addToQueue(queue, e.target.files); e.target.value = ''; paint(); });

  function close() {
    queue.forEach((q) => URL.revokeObjectURL(q.url));
    const panel = row.querySelector('.fb-panel');
    if (panel) panel.remove();
    row.classList.remove('fb-open');
    doneButton.hidden = false;
  }
  shut.addEventListener('click', close);

  async function finish() {
    const text = note.value.trim();
    controls.forEach((c) => { c.disabled = true; });
    save.textContent = 'Saving…';
    try {
      if (queue.length) {
        if (!plantId) throw new Error('These photos have nowhere to go — this plant is not on file.');
        const body = new FormData();
        for (let i = 0; i < queue.length; i++) body.append('photos', await prepare(queue[i].file, i + 1));
        body.append('note', text);
        await upload(`/api/plants/${plantId}/photos`, body, (pct) => {
          save.textContent = pct < 100 ? `Sending… ${pct}%` : 'Saving…';
        });
      }
      const res = await api(`/api/tasks/${task.id}/done`,
                            { method: 'POST', body: JSON.stringify({ note: text }) });
      queue.forEach((q) => URL.revokeObjectURL(q.url));
      dropTaskRow(task.id, row);
      // Say only what actually happened: the registry is the one that decides whether the note stuck.
      if (res.already_closed) {
        toast(res.note_recorded ? 'Saved ✓ — that job was already ticked off; your note is kept'
                                : 'That job was already ticked off — nothing new to record');
      } else {
        toast(text ? 'Saved ✓ Garden Keeper has your note' : 'Done ✓');
      }
    } catch (err) {
      save.textContent = 'Save';
      controls.forEach((c) => { c.disabled = false; });
      paint();
      toast(err.message);
    }
  }
  save.addEventListener('click', finish);
  skip.addEventListener('click', () => { note.value = ''; finish(); });

  row.classList.add('fb-open');
  doneButton.hidden = true;
  row.append(el('div', { class: 'fb-panel' },
    el('div', { class: 'fb-head' }, el('p', { class: 'fb-q', text: 'What changed?' }), shut),
    note,
    el('div', { class: 'picker-row' }, pick),
    fileInput, thumbs,
    el('div', { class: 'picker-row fb-acts' }, save, skip)));
  paint();
  note.focus({ preventScroll: true });
}

// A follow-up owed or a treatment suggested but not applied: the home screen counts these, so the
// plant page must show them and be able to clear them — otherwise a plant the list calls overdue
// opens on a page that says there is nothing to do.
function waitingRow(item) {
  const due = dueLabel(item.due_on);
  const words = { check: 'Check', feed: 'Feed suggested' };   // "Check — due in 3 days", never "due due"
  return el('li', { class: `action-row ${due.cls}`, 'data-wait': `${item.kind}:${item.ref}` },
    el('span', { class: 'a-ico', text: item.icon || (item.kind === 'check' ? '🔍' : '🌱') }),
    el('div', { class: 'a-main' },
      el('p', { class: 'a-title', text: item.title || 'Waiting on you' }),
      el('p', { class: `a-due ${due.cls}`,
                text: `${words[item.kind] || 'Waiting'} — ${due.text}` })),
    el('button', { class: 'done-btn', type: 'button', text: 'Done',
                   onclick: (e) => markWaitingDone(item, row_of(e), e.currentTarget) }));
}

const row_of = (e) => e.currentTarget.closest('.action-row');

async function markWaitingDone(item, row, button) {
  button.disabled = true;
  button.textContent = '…';
  const cls = dueLabel(item.due_on).cls;      // not a parameter: a callback that throws on a
  const url = item.kind === 'check' ? `/api/observations/${item.ref}/follow-up-done`
                                    : `/api/treatments/${item.ref}/apply`;
  try {
    await api(url, { method: 'POST' });       // missing name leaves the count and the toast dead
    const list = row.parentElement;                  // gone once the row is removed
    row.classList.add('leaving');
    setTimeout(() => {
      row.remove();
      const block = list ? list.closest('.block') : null;
      const left = list ? list.childElementCount : 0;
      if (block) {
        block.querySelector('h3').textContent = `Also waiting (${left})`;
        if (!left) {
          block.remove();
          // with the last waiting item gone, the Actions line can say the truth again
          const actions = document.querySelector('.actions');
          if (!actions || !actions.childElementCount) {
            const first = document.querySelector('#view-plant .block p');
            if (first && first.textContent.startsWith('No tasks')) {
              first.textContent = 'Nothing to do for this plant right now. 🎉';
            }
          }
        }
      }
      if (plantCache) {
        plantCache.open = Math.max(0, (plantCache.open || 0) - 1);
        if (cls === 'overdue') plantCache.overdue = Math.max(0, (plantCache.overdue || 0) - 1);
        if (cls === 'due') plantCache.due_soon = Math.max(0, (plantCache.due_soon || 0) - 1);
        plantCache.extra = (plantCache.extra || []).filter((i) => !(i.kind === item.kind && i.ref === item.ref));
        paintPlantBadges();
      }
      toast(item.kind === 'check' ? 'Follow-up cleared ✓' : 'Marked as applied ✓');
    }, 260);
  } catch (err) {
    button.disabled = false;
    button.textContent = 'Done';
    toast(err.message);
  }
}

let plantCache = null;          // what renderPlant last drew, so a Done can repaint the badges

function paintPlantBadges() {
  const box = document.querySelector('.ph-badges');
  if (!box || !plantCache) return;
  box.replaceChildren(healthChip(plantCache.status, plantCache.health_status), waitingChip(plantCache));
}

// Take a finished action off the page: fade it, then fix the heading count and the empty state.
function dropTaskRow(taskId, row) {
  row.classList.add('leaving');
  if (plantCache) {
    plantCache.open = Math.max(0, (plantCache.open || 0) - 1);
    if (plantCache.next && plantCache.next.kind === 'task' && plantCache.next.ref === taskId) plantCache.next = null;
    paintPlantBadges();
  }
  setTimeout(() => {
    row.remove();
    const list = document.querySelector('.actions');
    const block = list ? list.closest('.block') : null;
    const left = list ? list.childElementCount : 0;
    if (block) {
      const heading = block.querySelector('h3');
      heading.textContent = left ? `Actions (${left})` : 'Actions';
      if (!left) {
        block.querySelector('p').textContent = 'Nothing to do for this plant right now. 🎉';
        list.remove();
      }
    }
  }, 220);
}

async function markDone(taskId, row, button) {
  button.disabled = true;
  button.textContent = '…';
  try {
    const res = await api(`/api/tasks/${taskId}/done`, { method: 'POST' });
    dropTaskRow(taskId, row);
    if (res.already_closed) toast('That job was already ticked off');
  } catch (err) {
    button.disabled = false;
    button.textContent = 'Done';
    toast(err.message);
  }
}

function photoRow(ph) {
  const caption = [KIND_WORDS[ph.kind] || ph.kind, fmtDay(ph.date)].filter(Boolean).join(' · ');
  const note = ph.assessment || ph.user_note || ph.next_action;
  // the agent both reads the photo and says what to do about it; showing only the first dropped
  // the instruction, so a distinct next_action gets its own labelled line
  const same = (a, b) => String(a || '').trim().toLowerCase().replace(/\s+/g, ' ') ===
                        String(b || '').trim().toLowerCase().replace(/\s+/g, ' ');
  const next = ph.next_action && !same(ph.next_action, note) ? ph.next_action : null;
  const shot = ph.missing
    ? el('span', { class: 't-shot shot-missing', title: 'This photo is missing from disk', text: '🌫️' })
    : el('a', { class: 't-shot', href: ph.full, target: '_blank', rel: 'noopener',
                onclick: (e) => openFullPhoto(e, caption) },
         photoImg(ph.url, caption));
  return el('li', { class: 't-item' }, shot,
    el('div', { class: 't-main' },
      el('p', { class: 't-date', text: caption }),
      note ? clampedBlock([
        { cls: 't-note', parts: note },
        ...(next ? [{ cls: 't-next', parts: [el('span', { class: 't-next-lbl', text: 'Next: ' }), next] }] : []),
      ]) : null));
}

// ── view: capture a new plant (form in index.html) ────────────────────────────
function renderThumbs() {
  const box = $('thumbs');
  box.replaceChildren(...files.map((item, i) => el('li', {},
    el('img', { src: item.url, alt: item.file.name || `photo ${i + 1}` }),
    el('button', { type: 'button', 'aria-label': 'Remove this photo',
                   onclick: () => { URL.revokeObjectURL(item.url); files.splice(i, 1); renderThumbs();
                                    if (files.length < MAX_FILES) showFormError(''); } }))));
  box.hidden = files.length === 0;
  $('submit').disabled = files.length === 0;
}

function addFiles(incoming) {
  const offered = Array.from(incoming || []);
  const list = offered.filter((f) => f.type.startsWith('image/') || /\.(jpe?g|png|heic|heif|webp)$/i.test(f.name || ''));
  // a pick that yields nothing must say so: a silent no-op reads as a broken button
  if (offered.length && !list.length) { showFormError('Those are not photos — nothing was added.'); return; }
  for (const file of list) {
    if (files.length >= MAX_FILES) { showFormError(`Up to ${MAX_FILES} photos at a time.`); break; }
    files.push({ file, url: URL.createObjectURL(file) });
  }
  if (list.length && files.length < MAX_FILES) showFormError('');
  renderThumbs();
}

// Photos the user has chosen but not sent yet. `queue` items are {file, url}; adding is silent so
// the caller decides when it goes — nothing leaves the phone until a button is tapped.
function addToQueue(queue, incoming) {
  const offered = Array.from(incoming || []);
  const usable = offered.filter((f) => f.type.startsWith('image/') || /\.(jpe?g|png|heic|heif|webp)$/i.test(f.name || ''));
  if (offered.length && !usable.length) { toast('Those are not photos — nothing was added.'); return 0; }
  let added = 0;
  for (const file of usable) {
    if (queue.length >= MAX_FILES) { toast(`Up to ${MAX_FILES} photos at a time.`); break; }
    queue.push({ file, url: URL.createObjectURL(file) });
    added += 1;
  }
  return added;
}

function paintQueue(thumbs, queue) {
  thumbs.replaceChildren(...queue.map((item, i) => el('li', {},
    el('img', { src: item.url, alt: '' }),
    el('button', { type: 'button', 'aria-label': 'Remove photo', text: '✕',
                   onclick: () => { URL.revokeObjectURL(item.url); queue.splice(i, 1); paintQueue(thumbs, queue);
                                    thumbs.dispatchEvent(new Event('queue-change')); } }))));
  thumbs.hidden = queue.length === 0;
}

function showFormError(msg) {
  const box = $('error');
  box.textContent = msg;
  box.hidden = !msg;
}

// Downscale + re-encode on the phone: faster uploads, and HEIC from iOS becomes a JPEG
// the agent can read. Falls back to the original file if the browser can't decode it.
async function prepare(file, index) {
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
    const w = Math.max(1, Math.round(bitmap.width * scale));
    const h = Math.max(1, Math.round(bitmap.height * scale));
    const canvas = document.createElement('canvas');
    canvas.width = w; canvas.height = h;
    canvas.getContext('2d').drawImage(bitmap, 0, 0, w, h);
    const blob = await new Promise((res) => canvas.toBlob(res, 'image/jpeg', QUALITY));
    if (!blob) return file;
    const name = (file.name || `photo-${index}`).replace(/\.[^.]+$/, '') + '.jpg';
    return new File([blob], name, { type: 'image/jpeg' });
  } catch (err) {
    return file;                                   // older browsers: send the original
  }
}

function upload(url, body, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);
    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100));
    });
    xhr.onload = () => {
      let payload = {};
      try { payload = JSON.parse(xhr.responseText || '{}'); } catch (e) { /* keep {} */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(payload);
      else reject(new Error(friendly(payload.error, xhr.status)));
    };
    xhr.onerror = () => reject(new Error(friendly('', 0)));
    xhr.send(body);
  });
}

async function submitNewPlant() {
  if (!files.length) return;
  showFormError('');
  $('submit').disabled = true;
  $('progress').hidden = false;
  $('progress').querySelector('.bar span').style.width = '2%';
  $('progress-text').textContent = 'Preparing photos…';
  try {
    const prepared = [];
    for (let i = 0; i < files.length; i++) prepared.push(await prepare(files[i].file, i + 1));
    const body = new FormData();
    prepared.forEach((f) => body.append('photos', f, f.name));
    body.append('name', $('name').value);
    body.append('location', $('location').value);
    body.append('note', $('note').value);
    const res = await upload('/api/intake', body, (pct) => {
      $('progress').querySelector('.bar span').style.width = `${pct}%`;
      $('progress-text').textContent = pct < 100 ? `Uploading… ${pct}%` : 'Handing over to Garden Keeper…';
    });
    intakeId = res.intake_id;
    logSuccess(res);
    startPolling(showFormResult);
  } catch (err) {
    showFormError(err.message || 'something went wrong');
    $('submit').disabled = false;
  } finally {
    $('progress').hidden = true;
  }
}

function logSuccess(res) {
  $('compose').hidden = true;
  $('statusCard').hidden = false;
  $('statusIcon').textContent = '⏳';
  $('statusTitle').textContent = 'Photos received';
  const n = res.photos;
  $('statusText').textContent = `${plural(n, 'photo')} saved. Garden Keeper is looking at ${n > 1 ? 'them' : 'it'} now — you can close this and get on with your day.`;
  $('summary').hidden = true;
  $('questions').hidden = true;
  $('see-plants').hidden = true;
  $('statusHint').hidden = false;
  $('statusHint').textContent = "I'll message you on Telegram when it's done.";
  $('statusCard').scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function showFormResult(intake) {
  const s = intake.status;
  $('statusHint').hidden = false;
  $('see-plants').hidden = false;
  if (s === 'done') {
    $('statusIcon').textContent = '🌿';
    $('statusTitle').textContent = 'Added to your garden';
    $('statusText').textContent = 'Identified, categorised and filed — with a first health check and anything it needs.';
    $('statusHint').textContent = "I've messaged you on Telegram.";
  } else if (s === 'needs_info') {
    $('statusIcon').textContent = '🔍';
    $('statusTitle').textContent = 'Almost there';
    $('statusText').textContent = 'Garden Keeper needs a bit more to be sure:';
    $('statusHint').textContent = 'Answer on Telegram — or add another photo here.';
  } else if (s === 'failed') {
    $('statusIcon').textContent = '⚠️';
    $('statusTitle').textContent = 'Could not work with those photos';
    $('statusText').textContent = 'Send them again, or ask me on Telegram and I will sort it out.';
    $('statusHint').hidden = true;
  }
  if (intake.summary) { $('summary').textContent = intake.summary; $('summary').hidden = false; }
  if (intake.questions && intake.questions.length) {
    $('questions').replaceChildren(...intake.questions.map((q) => el('li', { text: q })));
    $('questions').hidden = false;
  }
  files.forEach((f) => URL.revokeObjectURL(f.url));
  files = [];
  renderThumbs();
}

function resetForm() {
  stopPolling();
  files.forEach((f) => URL.revokeObjectURL(f.url));
  files = [];
  renderThumbs();
  $('name').value = ''; $('location').value = ''; $('note').value = '';
  showFormError('');
  $('statusCard').hidden = true;
  $('compose').hidden = false;
  $('submit').disabled = true;
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ── asynchronous analysis: poll one intake until it is closed ──────────────────
function startPolling(onClosed) {
  stopPolling();
  pollCount = 0;
  const icon = $('statusIcon');
  icon.classList.add('spin');
  setTimeout(() => icon.classList.remove('spin'), 300);
  const tick = () => pollIntake(onClosed);
  tick();
  pollTimer = setInterval(tick, 5000);
}

function stopPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
}

async function pollIntake(onClosed) {
  const id = intakeId;
  if (!id) return;
  pollCount += 1;
  try {
    const data = await api(`/api/intake/${id}`);
    if (id !== intakeId) return;                     // the user moved on; ignore this answer
    if (['done', 'needs_info', 'failed'].includes(data.status)) {
      stopPolling();
      onClosed(data);
      return;
    }
    if (data.status === 'processing') {
      $('statusIcon').textContent = '🔎';
      $('statusTitle').textContent = 'Under analysis';
      $('statusText').textContent = 'Garden Keeper is working through this now — usually a couple of minutes.';
    } else if (data.ahead > 0) {
      // Honest about the queue: the worker takes one batch at a time, so say what is in front.
      $('statusIcon').textContent = '🌱';
      $('statusTitle').textContent = 'Queued';
      $('statusText').textContent = data.ahead === 1
        ? 'One capture is ahead of yours — a few minutes at most.'
        : `${data.ahead} captures are ahead of yours — a few minutes at most.`;
    }
  } catch (err) { /* keep polling: a blip must not stop the wait */ }
  if (pollCount > 150) {                             // ~12 min: stop, but say so honestly
    stopPolling();
    $('statusIcon').textContent = '🌱';
    $('statusTitle').textContent = 'Still working on it';
    $('statusText').textContent = 'This one is taking a while — the answer will arrive on Telegram.';
  }
}

// ── adding photos to a plant that already exists ──────────────────────────────
async function uploadPlantPhotos(plantId, picked, note, card, controls = []) {
  const setEnabled = (on) => controls.forEach((c) => { if (c) c.disabled = !on; });
  card.hidden = false;
  card.replaceChildren(el('p', { class: 'muted small', text: 'Preparing photos…' }));
  setEnabled(false);
  try {
    const prepared = [];
    for (let i = 0; i < picked.length; i++) prepared.push(await prepare(picked[i], i + 1));
    const body = new FormData();
    prepared.forEach((f) => body.append('photos', f, f.name));
    body.append('note', note || '');
    const bar = el('div', { class: 'bar' }, el('span', {}));
    const line = el('p', { class: 'muted small', text: 'Uploading… 2%' });
    card.replaceChildren(el('h2', { text: 'Sending…' }), bar, line);
    const res = await upload(`/api/plants/${plantId}/photos`, body, (pct) => {
      bar.firstChild.style.width = `${pct}%`;
      line.textContent = pct < 100 ? `Uploading… ${pct}%` : 'Handing over to Garden Keeper…';
    });
    intakeId = res.intake_id;
    card.replaceChildren(el('h2', { text: 'Photos received' }),
      el('p', { class: 'muted small', text: `${plural(res.photos, 'photo')} saved — re-checking this plant now.` }),
      el('p', { class: 'muted small', text: 'You can carry on; the result lands on Telegram.' }),
      el('a', { class: 'back center', href: '#/', text: 'See my plants →' }));
    startPolling(async (intake) => {
      if (intake.status === 'done') {
        mount(card, el('h2', { text: 'Health check updated' }),
          intake.summary ? el('p', { class: 'summary', text: intake.summary }) : null,
          el('p', { class: 'muted small', text: 'Refreshing the page in a moment…' }));
        setTimeout(() => renderPlant(plantId), 1600);
      } else {
        mount(card, el('h2', { text: intake.status === 'needs_info'
            ? 'Garden Keeper needs one more photo' : 'Could not work with those photos' }),
          intake.summary ? el('p', { class: 'summary', text: intake.summary }) : null,
          el('ul', { class: 'questions' }, (intake.questions || []).map((q) => el('li', { text: q }))));
      }
      setEnabled(true);                       // the upload is done; the analysis carries on in the background
    });
    setEnabled(true);
    return res;                               // truthy: the caller may now clear its queue
  } catch (err) {
    card.replaceChildren(el('h2', { text: 'That did not go through' }),
      el('p', { class: 'error', text: err.message }),
      el('p', { class: 'muted small', text: 'Nothing was saved — the photos are still here to try again.' }));
    setEnabled(true);
    return null;                              // falsy: keep the queue, keep the note
  }
}

function toast(message) {
  const box = el('div', { class: 'toast', text: message });
  document.body.append(box);
  setTimeout(() => box.classList.add('gone'), 2600);
  setTimeout(() => box.remove(), 3200);
}

// ── wiring ────────────────────────────────────────────────────────────────────
for (const [kind, id] of [['in', 'chip-in'], ['out', 'chip-out'], ['all', 'chip-all']]) {
  $(id).addEventListener('click', () => {
    const current = location.hash.replace(/^#\/?/, '');
    location.hash = current === kind ? '#/' : `#/${kind}`;
  });
}
$('add-plant').addEventListener('click', () => { location.hash = '#/add'; });
$('add-shortcut').addEventListener('click', () => { location.hash = '#/add'; });
$('list-retry').addEventListener('click', renderList);
$('again').addEventListener('click', resetForm);
$('btn-gallery').addEventListener('click', () => $('file-gallery').click());
$('file-gallery').addEventListener('change', (e) => { addFiles(e.target.files); e.target.value = ''; });
$('submit').addEventListener('click', submitNewPlant);

// Drag & drop (desktop convenience) — only meaningful on the capture form
document.addEventListener('dragover', (e) => e.preventDefault());
document.addEventListener('drop', (e) => {
  e.preventDefault();
  if (location.hash.replace(/^#\/?/, '').startsWith('add')) addFiles(e.dataTransfer && e.dataTransfer.files);
});

window.addEventListener('hashchange', route);
renderThumbs();
route();
