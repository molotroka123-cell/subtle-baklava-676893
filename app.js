import { createScene } from './tree-scene.js';

/* Витрина развития Bossman. Данные — data/*.json, их собирает scripts/sync_bossman.py (без ИИ, пути и секреты вырезаны).
   Весь текст из данных попадает на страницу только через textContent: разметки из данных нет. */

const COLORS = { reported: '#5dff8f', code: '#4fa8ff', branch: '#ffb547', prepared: '#ffd166', idea: '#b98bff', blocked: '#ff5470', recorded: '#c9d4e5', mixed: '#ffe8a3' };
const ORDER = ['reported', 'code', 'branch', 'prepared', 'idea', 'blocked', 'recorded', 'mixed'];
const KIND = { feat: ['Новое', '#5dff8f'], fix: ['Исправление', '#ffb547'], docs: ['Документы', '#8bc5ff'], test: ['Тесты', '#b98bff'], chore: ['Служебное', '#c9d4e5'], refactor: ['Рефакторинг', '#7dd3fc'], perf: ['Скорость', '#f0abfc'], ci: ['CI', '#fde68a'], build: ['Сборка', '#fde68a'], other: ['Другое', '#a3b2cf'] };
const reduced = !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
const $ = (s, r = document) => r.querySelector(s);
const fmtDay = (d) => new Date(d + 'T12:00:00').toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
const plural = (n, a, b, c) => { const m = n % 10, k = n % 100; return m === 1 && k !== 11 ? a : m >= 2 && m <= 4 && (k < 12 || k > 14) ? b : c; };

function h(spec, props, ...kids) {
  const m = spec.match(/^([a-z0-9]+)((?:[.#][\w-]+)*)$/i);
  const el = document.createElement(m ? m[1] : 'div');
  for (const part of (m ? m[2] : '').match(/[.#][\w-]+/g) || []) part[0] === '.' ? el.classList.add(part.slice(1)) : (el.id = part.slice(1));
  if (props && typeof props === 'object' && !(props instanceof Node) && !Array.isArray(props)) {
    for (const [k, v] of Object.entries(props)) {
      if (v == null || v === false) continue;
      if (k === 'style') for (const [sk, sv] of Object.entries(v)) el.style.setProperty(sk, sv);
      else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
      else if (k === 'text') el.textContent = v;
      else if (k === 'class') String(v).split(/\s+/).filter(Boolean).forEach((c) => el.classList.add(c));
      else el.setAttribute(k, v === true ? '' : v);
    }
  } else if (props != null) kids.unshift(props);
  for (const k of kids.flat()) if (k != null && k !== false) el.append(k instanceof Node ? k : document.createTextNode(String(k)));
  return el;
}

async function getJSON(path) {
  const r = await fetch(path, { cache: 'no-cache' });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

/* ---------------------------------------------------------------- reveal / счётчики */
const io = new IntersectionObserver((entries) => {
  for (const e of entries) {
    if (!e.isIntersecting) continue;
    e.target.classList.add('in');
    const b = e.target.querySelector('b[data-to]');
    if (b) countUp(b);
    io.unobserve(e.target);
  }
}, { threshold: 0.12, rootMargin: '0px 0px -6% 0px' });
function observeReveal(root = document) { root.querySelectorAll('.reveal:not(.in)').forEach((el) => (reduced ? el.classList.add('in') : io.observe(el))); }
function countUp(b) {
  const to = Number(b.dataset.to), t0 = performance.now(), dur = 1400;
  if (reduced) { b.textContent = String(to); return; }
  (function step(now) { const k = Math.min(1, (now - t0) / dur); b.textContent = String(Math.round(to * (1 - Math.pow(1 - k, 3)))); if (k < 1) requestAnimationFrame(step); })(t0);
}

/* ---------------------------------------------------------------- данные */
const [meta, tree, timeline, articleIndex] = await Promise.all([
  getJSON('./data/meta.json'), getJSON('./data/tree.json'), getJSON('./data/timeline.json'), getJSON('./data/articles/index.json')]);
const nodes = tree.nodes;
const byId = new Map(nodes.map((n) => [n.id, n]));
const kidsOf = new Map();
nodes.forEach((n) => { if (!kidsOf.has(n.parent)) kidsOf.set(n.parent, []); kidsOf.get(n.parent).push(n); });
const legend = meta.status_legend;
const statusLabel = (s) => (legend[s] && legend[s].label) || s;
const zones = (kidsOf.get('bossman') || []);
const zoneOf = (id) => { let n = byId.get(id), g = 0; while (n && n.parent !== 'bossman' && n.parent && g++ < 14) n = byId.get(n.parent); return n; };

function descendants(id) {
  const out = []; const st = [...(kidsOf.get(id) || [])];
  while (st.length) { const x = st.pop(); out.push(x); st.push(...(kidsOf.get(x.id) || [])); }
  return out;
}

/* ---------------------------------------------------------------- hero */
const words = $('#h1').textContent.trim().split(/\s+/);
$('#h1').replaceChildren(...words.map((w, i) => h('span.w', { style: { '--i': i }, text: w })));

const commits = timeline.items.length;
const counterDefs = [
  [meta.counts.nodes, 'узлов на карте'], [meta.counts.articles, 'статей'], [meta.counts.zones, 'направлений'],
  [commits, `изменений за ${Math.max(1, Object.keys(timeline.per_day).length)} ${plural(Object.keys(timeline.per_day).length, 'день', 'дня', 'дней')}`]];
const counters = $('#counters');
counterDefs.forEach(([n, label], i) => counters.append(h('div.counter.reveal', { style: { '--d': `${300 + i * 90}ms` } }, h('b', { 'data-to': n, text: reduced ? String(n) : '0' }), h('span', label))));

/* ---------------------------------------------------------------- дерево */
const counts = {};
nodes.forEach((n) => { if (n.id !== 'bossman') counts[n.status] = (counts[n.status] || 0) + 1; });
const statusNames = Object.fromEntries(ORDER.map((s) => [s, statusLabel(s)]));
const scene = createScene({
  nodes, colors: COLORS, labels: { _status: statusNames },
  onPick: (n) => openArticle(n.id),
});
$('#scene').replaceWith(scene.el);
$('#zoomIn').addEventListener('click', () => scene.zoomBy(1.6));
$('#zoomOut').addEventListener('click', () => scene.zoomBy(1 / 1.6));
$('#zoomReset').addEventListener('click', () => scene.zoomReset());
$('#treeHint').textContent = `${scene.leaves} ${plural(scene.leaves, 'лист', 'листа', 'листьев')} · нажмите на лист или на название ветви`;

const lg = $('#legend');
let activeFilter = null;
ORDER.filter((s) => counts[s]).forEach((s) => {
  const b = h('button.lg', { type: 'button', style: { '--c': COLORS[s] }, 'aria-pressed': 'false', title: legend[s] ? legend[s].about : '' }, h('i'), statusLabel(s), h('b', String(counts[s])));
  b.addEventListener('click', () => {
    activeFilter = activeFilter === s ? null : s;
    lg.querySelectorAll('.lg').forEach((x) => { x.classList.remove('on'); x.setAttribute('aria-pressed', 'false'); });
    if (activeFilter) { b.classList.add('on'); b.setAttribute('aria-pressed', 'true'); }
    scene.filter(activeFilter);
  });
  lg.append(b);
});
// на телефоне открываем дерево по центру (ствол), чтобы листать вбок в обе стороны
requestAnimationFrame(() => { const sc = $('#treeScroll'); sc.scrollLeft = (sc.scrollWidth - sc.clientWidth) / 2; });

/* ---------------------------------------------------------------- пульс */
const total = ORDER.reduce((n, s) => n + (counts[s] || 0), 0);
$('#pulseSub').textContent = `Снимок ${new Date(meta.generated_at).toLocaleString('ru-RU', { dateStyle: 'long', timeStyle: 'short' })}. Карта от ${meta.source.map_as_of || '—'}, коммит ${meta.source.head}.`;
$('#stack').replaceChildren(...ORDER.filter((s) => counts[s]).map((s, i) => h('i', { style: { '--c': COLORS[s], '--n': counts[s], '--i': i }, title: `${statusLabel(s)}: ${counts[s]}` })));
$('#stackLegend').replaceChildren(...ORDER.filter((s) => counts[s]).map((s) => h('li', { style: { '--c': COLORS[s] } }, h('i'), statusLabel(s), h('b', `${counts[s]}`))));

(function spark() {
  const days = [], today = new Date();
  for (let i = 29; i >= 0; i--) { const d = new Date(today); d.setDate(d.getDate() - i); days.push(d.toISOString().slice(0, 10)); }
  const vals = days.map((d) => timeline.per_day[d] || 0), max = Math.max(1, ...vals);
  $('#spark').replaceChildren(...vals.map((v, i) => h('i', { style: { '--h': `${Math.max(4, Math.round((v / max) * 100))}%`, '--i': i }, 'data-n': v, title: `${fmtDay(days[i])}: ${v}` })));
  const sum = vals.reduce((a, b) => a + b, 0);
  $('#sparkNote').textContent = `${sum} ${plural(sum, 'изменение', 'изменения', 'изменений')} в видимой ленте за 30 дней. Это активность разработки, а не качество.`;
})();

(function live() {
  const L = meta.live || {}, box = $('#live');
  if (L.state === 'live') {
    box.replaceChildren(h('span.badge.live', 'ПОДКЛЮЧЕНО К BOSSMAN'),
      h('div.live-grid', h('div', h('b', String(L.improved)), h('span', 'улучшено Bossman')), h('div', h('b', String(L.applied)), h('span', 'применено')), h('div', h('b', String(L.verified)), h('span', 'проверено независимо'))),
      h('p.muted', `Задач по зонам: ${L.jobs_total}, завершено: ${L.jobs_completed}, с ошибкой: ${L.jobs_failed}. Улучшение засчитывается только после независимой проверки.`));
  } else {
    box.replaceChildren(h('span.badge', 'СНИМОК ИЗ GIT'),
      h('p.muted', 'Живые счётчики самоулучшения подключаются запуском парсера на компьютере владельца с ключом --live. Пока не подключено — витрина ничего не утверждает о самоулучшении.'),
      h('p.muted', 'Правило: засчитывается только цепочка «нашёл → исправил в изолированной копии → независимая проверка прошла».'));
  }
})();

$('#ladder').replaceChildren(...meta.ladder.map((s) => h('li', { class: s.reached ? 'reached' : '' }, h('b', s.title), h('span', s.about), h('em', s.reached ? 'ДОСТИГНУТО' : 'НЕ ДОКАЗАНО'))));

/* ---------------------------------------------------------------- лента */
let kindFilter = 'all', shown = 40;
const kinds = Object.entries(timeline.kinds).sort((a, b) => b[1] - a[1]);
const chips = $('#tlChips');
function chipRow() {
  chips.replaceChildren(...[['all', 'Всё', timeline.items.length], ...kinds.map(([k, n]) => [k, (KIND[k] || KIND.other)[0], n])].map(([k, label, n]) => {
    const b = h('button.chip', { type: 'button', class: k === kindFilter ? 'on' : '' }, label, h('b', String(n)));
    b.addEventListener('click', () => { kindFilter = k; shown = 40; chipRow(); renderTimeline(); });
    return b;
  }));
}
function renderTimeline() {
  const rows = timeline.items.filter((r) => kindFilter === 'all' || r.kind === kindFilter);
  const out = []; let day = '';
  rows.slice(0, shown).forEach((r, i) => {
    if (r.day !== day) { day = r.day; out.push(h('li.day', fmtDay(day).toUpperCase())); }
    const [kl, kc] = KIND[r.kind] || KIND.other;
    out.push(h('li.it.reveal', { style: { '--d': `${Math.min(i, 8) * 40}ms` } }, h('span.k', { style: { '--c': kc }, text: kl }), h('p', r.title), h('code', r.sha)));
  });
  $('#tl').replaceChildren(...out);
  observeReveal($('#tl'));
  const more = $('#tlMore');
  more.hidden = rows.length <= shown;
  more.textContent = `Показать ещё (${Math.min(40, rows.length - shown)} из ${rows.length - shown})`;
}
$('#tlMore').addEventListener('click', () => { shown += 40; renderTimeline(); });
$('#tlSub').textContent = `${timeline.items.length} последних изменений во всех ветках разработки. Заголовки — как их написали разработчики; пути и ключи скрыты.`;
chipRow(); renderTimeline();

/* ---------------------------------------------------------------- зоны */
const zoneGrid = $('#zoneGrid');
zones.forEach((z, i) => {
  const ds = descendants(z.id), c = {};
  ds.forEach((d) => { c[d.status] = (c[d.status] || 0) + 1; });
  const card = h('button.zone.reveal', { type: 'button', style: { '--d': `${(i % 4) * 70}ms` } },
    h('h3', z.label), h('p', z.short && !/^Раскрой ветку/.test(z.short) ? z.short : `Элементов внутри: ${ds.length}.`),
    h('div.mini', ORDER.filter((s) => c[s]).map((s) => h('i', { style: { '--c': COLORS[s], '--n': c[s] } }))),
    h('span.meta', `${ds.length} ${plural(ds.length, 'элемент', 'элемента', 'элементов')} · открыть статью →`));
  card.addEventListener('click', () => openArticle(z.id));
  zoneGrid.append(card);
});

/* ---------------------------------------------------------------- для ИИ */
const promptText = `Прочитай ${location.origin}/ai/bossman-development.md — это полное описание развития Bossman (зоны, статьи, уровни доказательства). Объясни простыми словами, что в Bossman уже есть, чего не хватает и с чего начать. Не считай «код написан» доказательством работы.`;
$('#promptText').textContent = promptText;
$('#copyPrompt').addEventListener('click', async (e) => copyText(promptText, e.currentTarget, 'Скопировано'));
$('#footMeta').textContent = `Снимок ${meta.generated_at} · коммит ${meta.source.head} · режим ${meta.source.mode === 'live+git' ? 'живые данные + git' : 'снимок из git'} · карта от ${meta.source.map_as_of || '—'}.`;

async function copyText(text, btn, okLabel) {
  const old = btn.textContent;
  try { await navigator.clipboard.writeText(text); btn.textContent = okLabel; btn.classList.add('ok'); }
  catch { const t = h('textarea', { style: { position: 'fixed', opacity: '0' } }); t.value = text; document.body.append(t); t.select(); try { document.execCommand('copy'); btn.textContent = okLabel; btn.classList.add('ok'); } catch { btn.textContent = 'Не удалось'; } t.remove(); }
  setTimeout(() => { btn.textContent = old; btn.classList.remove('ok'); }, 1600);
}

/* ---------------------------------------------------------------- reveal / счётчики / подсветка */
observeReveal();
['#cardStatus', '#cardActivity'].forEach((s) => { const el = $(s); const o = new IntersectionObserver((es) => { if (es[0].isIntersecting) { el.classList.add('in'); o.disconnect(); } }, { threshold: 0.3 }); o.observe(el); });

document.addEventListener('pointermove', (e) => {
  const c = e.target.closest && e.target.closest('.card,.zone');
  if (!c) return;
  const r = c.getBoundingClientRect();
  c.style.setProperty('--mx', `${e.clientX - r.left}px`); c.style.setProperty('--my', `${e.clientY - r.top}px`);
}, { passive: true });

const bar = $('#progress');
addEventListener('scroll', () => { const d = document.documentElement; bar.style.transform = `scaleX(${d.scrollTop / Math.max(1, d.scrollHeight - d.clientHeight)})`; }, { passive: true });
const navLinks = [...document.querySelectorAll('.nav a')];
const secObs = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) navLinks.forEach((a) => a.classList.toggle('on', a.getAttribute('href') === `#${e.target.id}`)); }), { rootMargin: '-45% 0px -50% 0px' });
['tree', 'pulse', 'timeline', 'zones', 'ai'].forEach((id) => secObs.observe($(`#${id}`)));

/* ---------------------------------------------------------------- читалка */
const reader = $('#reader'), rBody = $('#readerBody'), rScroll = $('#readerScroll');
const zoneCache = new Map();
let current = null, lastFocus = null, secIO = null;

function loadZone(zone) {
  if (!zoneCache.has(zone)) zoneCache.set(zone, getJSON(`./data/articles/${zone}.json`).catch((e) => { zoneCache.delete(zone); throw e; }));
  return zoneCache.get(zone);
}
async function getArticle(id) {
  const zone = articleIndex[id];
  if (!zone) return null;
  return (await loadZone(zone))[id] || null;
}

function dedupe(a) {
  const sum = (a.summary || '').replace(/…$/, '').trim();
  const first = a.sections[0];
  if (!sum || !first || first.h !== 'Что это' || !first.p) return a.sections;
  const rest = first.p.filter((t) => !t.startsWith(sum));
  if (rest.length === first.p.length) return a.sections;
  return rest.length ? [{ ...first, p: rest }, ...a.sections.slice(1)] : a.sections.slice(1);
}

function sectionEl(sec, i) {
  const body = [h('h2', h('span', String(i + 1).padStart(2, '0')), sec.h)];
  (sec.p || []).forEach((t) => body.push(h('p', t)));
  if (sec.list) body.push(h('ul.items', sec.list.map((it) => h('li', h('b', it.t), it.d ? h('span', it.d) : null))));
  if (sec.link) body.push(h('p', h('a.ext', { href: sec.link, target: '_blank', rel: 'noopener noreferrer', text: sec.link })));
  if (sec.note) body.push(h('p.note', sec.note));
  return h('section.rv', body);
}

function renderArticle(a) {
  const c = COLORS[a.status] || '#c9d4e5';
  const sibs = a.siblings || [];
  const side = [h('dl.facts', a.facts.map(([k, v]) => h('div', h('dt', k), h('dd', v))))];
  if (a.children && a.children.length) {
    side.push(h('div.kids', h('h3', `Внутри · ${a.children_total}`), h('div.kid-list', a.children.map((k) =>
      h('button.kid', { type: 'button', style: { '--c': COLORS[k.status] || '#c9d4e5' }, onclick: () => openArticle(k.id) }, h('i'), h('span', k.label))))));
  }
  const nav = [];
  if (sibs.length) {
    const same = (kidsOf.get((byId.get(a.id) || {}).parent) || []);
    const pos = same.findIndex((n) => n.id === a.id);
    const prev = same[pos - 1], next = same[pos + 1];
    if (prev) nav.push(h('button.prev', { type: 'button', onclick: () => openArticle(prev.id) }, h('small', '← ПРЕДЫДУЩАЯ'), h('b', prev.label)));
    else nav.push(h('span'));
    if (next) nav.push(h('button.next', { type: 'button', onclick: () => openArticle(next.id) }, h('small', 'СЛЕДУЮЩАЯ →'), h('b', next.label)));
  }
  rBody.replaceChildren(
    h('header.a-hero', h('span.a-chip', { style: { '--c': c } }, h('i'), a.status_label.toUpperCase()), h('h1#readerTitle', a.title), h('p.a-sum', a.summary || '')),
    h('div.a-grid', h('div.a-main', dedupe(a).map(sectionEl)), h('aside.a-side', side)),
    nav.length ? h('div.a-nav', nav) : null);
  const crumbs = $('#crumbs');
  crumbs.replaceChildren(...a.crumbs.flatMap((cr, i) => [i ? h('span', '›') : null, h('button', { type: 'button', onclick: () => openArticle(cr.id), text: cr.label })]).filter(Boolean), ...(a.crumbs.length ? [h('span', '›')] : []), h('span', { text: a.title }));
  if (secIO) secIO.disconnect();
  secIO = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('in'); secIO.unobserve(e.target); } }), { root: rScroll, threshold: 0.08 });
  rBody.querySelectorAll('section.rv').forEach((s) => (reduced ? s.classList.add('in') : secIO.observe(s)));
  rScroll.scrollTop = 0;
  scene.select(a.id);
}

async function showArticle(id) {
  let art;
  try { art = await getArticle(id); } catch { art = null; }
  if (!art) {
    const n = byId.get(id);
    art = { id, title: n ? n.label : 'Статья не найдена', status: n ? n.status : 'code', status_label: n ? statusLabel(n.status) : '', summary: n ? n.short : 'Не удалось загрузить статью. Проверьте соединение и обновите страницу.', crumbs: [], facts: [], sections: [], children: [], siblings: [] };
  }
  current = art;
  if (reader.hidden) { lastFocus = document.activeElement; reader.hidden = false; reader.classList.remove('closing'); document.documentElement.style.overflow = 'hidden'; }
  renderArticle(art);
  document.title = `${art.title} — Bossman`;
  $('#readerClose').focus({ preventScroll: true });
}
function openArticle(id, push = true) {
  if (push) history.pushState({ n: id }, '', `#/n/${encodeURIComponent(id)}`);
  return showArticle(id);
}
function hideReader() {
  if (reader.hidden) return;
  reader.classList.add('closing');
  setTimeout(() => { reader.hidden = true; reader.classList.remove('closing'); document.documentElement.style.overflow = ''; document.title = 'Bossman — дерево развития'; scene.select(null); if (lastFocus && lastFocus.focus) lastFocus.focus({ preventScroll: true }); }, reduced ? 0 : 260);
}
function closeReader() {
  history.replaceState(null, '', location.pathname + location.search + '#tree');
  hideReader();
}
$('#readerClose').addEventListener('click', closeReader);
reader.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { e.stopPropagation(); closeReader(); return; }
  if (e.key !== 'Tab') return;
  const f = [...reader.querySelectorAll('button,a[href]')].filter((x) => x.offsetParent !== null);
  if (!f.length) return;
  const first = f[0], last = f[f.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); } else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
});
rScroll.addEventListener('scroll', () => { $('#readProgress').style.transform = `scaleX(${rScroll.scrollTop / Math.max(1, rScroll.scrollHeight - rScroll.clientHeight)})`; }, { passive: true });
$('#copyLink').addEventListener('click', (e) => copyText(location.href, e.currentTarget, 'Скопировано'));
$('#copyMd').addEventListener('click', (e) => {
  const a = current; if (!a) return;
  const md = [`## ${a.title}`, `*Уровень доказательства: ${a.status_label}* · id: \`${a.id}\``, ''];
  a.sections.forEach((s) => { md.push(`### ${s.h}`, ...(s.p || [])); (s.list || []).forEach((it) => md.push(`- ${it.t}${it.d ? ' — ' + it.d : ''}`)); md.push(''); });
  md.push('Факты: ' + a.facts.map(([k, v]) => `${k}: ${v}`).join('; '));
  copyText(md.join('\n') + '\n', e.currentTarget, 'Скопировано');
});

function route() {
  const m = location.hash.match(/^#\/n\/(.+)$/);
  if (m) { const id = decodeURIComponent(m[1]); if (!current || current.id !== id || reader.hidden) showArticle(id); } else hideReader();
}
addEventListener('popstate', route);
addEventListener('hashchange', route);
if (location.hash.startsWith('#/n/')) route();

/* ---------------------------------------------------------------- поиск */
const palette = $('#palette'), q = $('#q'), qList = $('#qList');
const zoneName = new Map(nodes.map((n) => [n.id, (zoneOf(n.id) || {}).label || '']));
const haystack = nodes.filter((n) => n.id !== 'bossman').map((n) => ({ n, a: n.label.toLowerCase(), b: (n.short || '').toLowerCase() }));
let sel = 0, results = [];
function search(text) {
  const t = text.trim().toLowerCase();
  if (!t) return zones.map((z) => ({ n: z }));
  const parts = t.split(/\s+/);
  const scored = [];
  for (const row of haystack) {
    if (!parts.every((p) => row.a.includes(p) || row.b.includes(p))) continue;
    scored.push({ n: row.n, s: (row.a.startsWith(parts[0]) ? 0 : row.a.includes(parts[0]) ? 1 : 2) + (kidsOf.has(row.n.id) ? -0.5 : 0) });
  }
  return scored.sort((x, y) => x.s - y.s).slice(0, 40);
}
function renderResults() {
  results = search(q.value);
  sel = Math.min(sel, Math.max(0, results.length - 1));
  qList.replaceChildren(...(results.length ? results.map((r, i) => h('li', { role: 'option', class: i === sel ? 'sel' : '', style: { '--c': COLORS[r.n.status] || '#c9d4e5' }, onclick: () => pick(i), onmousemove: () => { sel = i; mark(); } }, h('i'), h('span', r.n.label), h('small', zoneName.get(r.n.id) || ''))) : [h('li', 'Ничего не найдено')]));
}
function mark() { [...qList.children].forEach((li, i) => li.classList.toggle('sel', i === sel)); const el = qList.children[sel]; if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest' }); }
function pick(i) { const r = results[i]; if (!r) return; closePalette(); openArticle(r.n.id); }
function openPalette() { palette.hidden = false; q.value = ''; sel = 0; renderResults(); q.focus(); }
function closePalette() { palette.hidden = true; }
q.addEventListener('input', () => { sel = 0; renderResults(); });
q.addEventListener('keydown', (e) => {
  if (e.key === 'ArrowDown') { e.preventDefault(); sel = Math.min(results.length - 1, sel + 1); mark(); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); sel = Math.max(0, sel - 1); mark(); }
  else if (e.key === 'Enter') { e.preventDefault(); pick(sel); }
  else if (e.key === 'Escape') { e.stopPropagation(); closePalette(); }
});
palette.addEventListener('mousedown', (e) => { if (e.target === palette) closePalette(); });
$('#searchBtn').addEventListener('click', openPalette);
$('#searchBtn2').addEventListener('click', openPalette);
addEventListener('keydown', (e) => {
  const typing = /^(input|textarea|select)$/i.test(document.activeElement && document.activeElement.tagName);
  if ((e.key === '/' && !typing) || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k')) { e.preventDefault(); openPalette(); }
  else if (e.key === 'Escape' && !palette.hidden) closePalette();
});

/* для автоматических проверок: тот же путь, что клик по листу */
window.__bossman = { open: (id) => openArticle(id), where: (id) => scene.where(id), zoom: () => scene.zoom, zoomTo: (id, k) => scene.zoomTo(id, k), leaves: scene.leaves, nodes: nodes.length };
