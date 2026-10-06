/* Живое дерево развития Bossman — Canvas 2D (оригинальная реализация для облачной витрины).
 *
 * Мир 1600×900 масштабируется по ширине контейнера. Слои за кадр:
 *   небо (заранее) → звёзды → озеро с бликами → ствол из светящихся волокон → кроны зон (ветер качает всю зону,
 *   листья мерцают) → подписи зон → светлячки и падающая звезда → кольцо выбора.
 * Ветка = зона карты, лист = узел карты. Цвет листа — уровень доказательства (не PASS).
 * При открытии дерево вырастает: сначала ствол, затем зоны по очереди, листья распускаются по мере роста ветви.
 * prefers-reduced-motion: один статичный кадр, перерисовка только на наведение/выбор.
 */
const W = 1600, H = 900, TX = 800, TY = 600, BASE_Y = 812, GROUND = 786;
const TAU = Math.PI * 2;
const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const easeOut = (t) => 1 - Math.pow(1 - t, 3);
const easeBack = (t) => { const c = 1.7; return 1 + (c + 1) * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2); };

function rng(seed) {
  let x = 2166136261;
  for (const ch of String(seed)) x = Math.imul(x ^ ch.charCodeAt(0), 16777619);
  return () => { x ^= x << 13; x ^= x >>> 17; x ^= x << 5; return ((x >>> 0) % 1000003) / 1000003; };
}

function bez(p, t) {
  const u = 1 - t;
  return [u * u * u * p[0][0] + 3 * u * u * t * p[1][0] + 3 * u * t * t * p[2][0] + t * t * t * p[3][0],
    u * u * u * p[0][1] + 3 * u * u * t * p[1][1] + 3 * u * t * t * p[2][1] + t * t * t * p[3][1]];
}

function rgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function sprite(hex, size = 64) {
  const c = document.createElement('canvas');
  c.width = c.height = size;
  const g = c.getContext('2d');
  const [r, gg, b] = rgb(hex);
  const grd = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  grd.addColorStop(0, `rgba(${r},${gg},${b},.95)`);
  grd.addColorStop(0.28, `rgba(${r},${gg},${b},.42)`);
  grd.addColorStop(1, `rgba(${r},${gg},${b},0)`);
  g.fillStyle = grd;
  g.fillRect(0, 0, size, size);
  return c;
}

function rot(px, py, ox, oy, a) {
  const s = Math.sin(a), c = Math.cos(a), dx = px - ox, dy = py - oy;
  return [ox + dx * c - dy * s, oy + dx * s + dy * c];
}

function buildModel(nodes) {
  const kids = new Map();
  nodes.forEach((n) => { if (!kids.has(n.parent)) kids.set(n.parent, []); kids.get(n.parent).push(n); });
  const zones = (kids.get('bossman') || []).slice();
  const count = zones.length || 1;
  const model = [];
  const tangent = (p, t) => { const a = bez(p, Math.max(0, t - 0.01)), c = bez(p, Math.min(1, t + 0.01)); const dx = c[0] - a[0], dy = c[1] - a[1], l = Math.hypot(dx, dy) || 1; return [dx / l, dy / l]; };
  zones.forEach((zone, zi) => {
    const r = rng(zone.id);
    const a = Math.PI * (0.955 - 0.91 * (zi / Math.max(1, count - 1)));    // слева направо по дуге
    const side = Math.cos(a), lift = Math.sin(a);
    const reach = 520 + 80 * lift;
    const end = [TX + 690 * side * (0.9 + 0.1 * lift) + (r() - 0.5) * 50, Math.max(130, TY - 40 - 440 * lift + (r() - 0.5) * 40)];
    const start = [TX + side * 10, TY + 38 - 46 * lift];
    const bend = (r() - 0.5) * 110;
    const p = [start,
      [start[0] + side * reach * 0.22, start[1] - 110 - 50 * lift + bend * 0.35],
      [start[0] + (end[0] - start[0]) * 0.58 + bend, start[1] + (end[1] - start[1]) * 0.8],
      end];
    const flat = [];
    const stack = [...(kids.get(zone.id) || [])];
    while (stack.length) { const x = stack.shift(); flat.push(x); stack.push(...(kids.get(x.id) || [])); }
    const nsub = Math.max(2, Math.min(11, Math.round(Math.sqrt(flat.length) / 1.5)));
    const subs = [];
    for (let k = 0; k < nsub; k++) {
      const ts = 0.2 + 0.7 * ((k + r() * 0.6) / nsub);
      const [bx, by] = bez(p, ts);
      const [tx, ty] = tangent(p, ts);
      const sgn = k % 2 ? 1 : -1;
      const ang = sgn * (0.5 + r() * 0.55);
      const dx = tx * Math.cos(ang) - ty * Math.sin(ang), dy = tx * Math.sin(ang) + ty * Math.cos(ang);
      const L = 70 + r() * 90 + Math.sqrt(flat.length) * 3.2;
      const px = -dy, py = dx, wob = (r() - 0.5) * 50;
      const q = [[bx, by], [bx + dx * L * 0.34, by + dy * L * 0.34 - 6], [bx + dx * L * 0.7 + px * wob, by + dy * L * 0.7 + py * wob - L * 0.1], [bx + dx * L, by + dy * L - L * 0.2]];
      subs.push({ q, ts, leaves: [] });
    }
    const leaves = flat.map((node, i) => {
      const lr = rng(node.id);
      const sb = subs[Math.floor(lr() * subs.length) % subs.length];
      const u = 0.32 + 0.68 * Math.pow(lr(), 0.75);
      const [bx, by] = bez(sb.q, u);
      const [tx, ty] = tangent(sb.q, u);
      const off = (lr() - 0.5) * (18 + Math.sqrt(flat.length) * 1.4);
      const l = { node, sb, u, bx, by, x: bx - ty * off, y: by + tx * off, ang: Math.atan2(ty, tx) + (off > 0 ? 0.8 : -0.8),
        size: node.status === 'mixed' ? 1.15 : 1, phase: lr() * TAU, i, tpos: sb.ts + 0.1 + u * 0.08 };
      sb.leaves.push(l);
      return l;
    });
    model.push({ zone, p, subs, leaves, delay: zi * 0.09, phase: r() * TAU, amp: 0.006 + r() * 0.004, end, side, order: zi, start });
  });
  return model;
}

export function createScene({ nodes, colors, labels = {}, onPick, onHover }) {
  const wrap = document.createElement('div');
  wrap.className = 'ts-scene';
  const canvas = document.createElement('canvas');
  canvas.className = 'ts-canvas';
  canvas.setAttribute('role', 'img');
  canvas.setAttribute('aria-label', 'Дерево развития Bossman: ветви — направления, листья — возможности. Полный список — ниже на странице.');
  canvas.tabIndex = 0;
  const tip = document.createElement('div');
  tip.className = 'ts-tip';
  tip.setAttribute('aria-hidden', 'true');
  wrap.append(canvas, tip);
  const ctx = canvas.getContext('2d');
  const model = buildModel(nodes);
  const reduced = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const sprites = Object.fromEntries(Object.entries(colors).map(([k, v]) => [k, sprite(v)]));
  const gold = sprite('#ffd27a');
  const white = sprite('#eaf2ff');

  const bg = document.createElement('canvas');
  bg.width = W; bg.height = H;
  (function paintSky() {
    const g = bg.getContext('2d');
    const sky = g.createLinearGradient(0, 0, 0, H);
    sky.addColorStop(0, '#070b1f'); sky.addColorStop(0.55, '#101a3d'); sky.addColorStop(1, '#1a2850');
    g.fillStyle = sky; g.fillRect(0, 0, W, H);
    const blob = (x, y, r, c) => { const q = g.createRadialGradient(x, y, 0, x, y, r); q.addColorStop(0, c); q.addColorStop(1, 'rgba(0,0,0,0)'); g.fillStyle = q; g.fillRect(x - r, y - r, r * 2, r * 2); };
    blob(300, 220, 420, 'rgba(70,90,200,.20)'); blob(1260, 160, 380, 'rgba(120,70,190,.16)'); blob(820, 520, 520, 'rgba(60,120,210,.14)');
    const moon = g.createRadialGradient(1330, 150, 4, 1330, 150, 90);
    moon.addColorStop(0, 'rgba(255,248,225,1)'); moon.addColorStop(0.18, 'rgba(255,244,214,.95)'); moon.addColorStop(0.2, 'rgba(255,240,200,.25)'); moon.addColorStop(1, 'rgba(255,240,200,0)');
    g.fillStyle = moon; g.fillRect(1230, 50, 200, 200);
    const range = (base, amp, seed, color) => {
      const q = rng(seed); g.fillStyle = color; g.beginPath(); g.moveTo(0, H);
      for (let x = 0; x <= W; x += 40) g.lineTo(x, base - amp * (0.5 + 0.5 * Math.sin(x * 0.004 + q() * 5)) - q() * 18);
      g.lineTo(W, H); g.closePath(); g.fill();
    };
    range(GROUND - 30, 90, 'm1', '#0d1634'); range(GROUND, 56, 'm2', '#0a1129');
    const lake = g.createLinearGradient(0, GROUND, 0, H);
    lake.addColorStop(0, '#0e1a3e'); lake.addColorStop(1, '#050816');
    g.fillStyle = lake; g.fillRect(0, GROUND, W, H - GROUND);
  })();

  const rs = rng('sky');
  const stars = Array.from({ length: 220 }, () => ({ x: rs() * W, y: rs() * GROUND * 0.9, r: rs() * 1.3 + 0.25, p: rs() * TAU, s: 0.6 + rs() * 1.6 }));
  const flies = Array.from({ length: 40 }, (_, i) => ({ x: TX + (rs() - 0.5) * 1400, y: 180 + rs() * 560, p: rs() * TAU, s: 0.3 + rs() * 0.7, k: i }));
  let state = { selected: null, filter: null, hover: null };
  let scale = 1, dpr = 1, raf = 0, shoot = null, last = performance.now(), start = last;
  const posed = new Map();                       // id -> [x, y] после ветра (для попаданий)
  const labelBoxes = [];
  const byId = new Map();
  model.forEach((m) => m.leaves.forEach((l) => byId.set(l.node.id, l)));
  model.forEach((m) => byId.set(m.zone.id, { node: m.zone, zone: m }));
  const growth = (t, delay) => reduced ? 1 : easeOut(clamp((t - 700 - delay * 1000) / 2300));

  function resize() {
    const w = Math.max(320, wrap.clientWidth || 1200);
    dpr = Math.min(2, window.devicePixelRatio || 1);
    scale = w / W;
    canvas.style.width = `${w}px`; canvas.style.height = `${Math.round(w * H / W)}px`;
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(w * H / W * dpr);
    if (reduced) draw(performance.now());
  }

  function trunk(t) {
    const g = clamp(reduced ? 1 : (t - 100) / 900);
    const e = easeOut(g);
    ctx.lineCap = 'round';
    const top = BASE_Y - (BASE_Y - (TY - 20)) * e;
    for (let k = 0; k < 13; k++) {
      const f = (k - 6) / 6;
      const sway = reduced ? 0 : Math.sin(t * 0.0006 + k) * 1.4;
      const tw = Math.sin(k * 1.7) * 14;
      ctx.beginPath();
      ctx.moveTo(TX + f * 74, BASE_Y + 6);
      ctx.bezierCurveTo(TX + f * 34 + tw + sway, BASE_Y - 70, TX + f * 16 - tw * 0.6 - sway, BASE_Y - 190 * e, TX + f * 5, top);
      ctx.strokeStyle = `rgba(${196 + (k % 4) * 8},${220 + (k % 3) * 6},255,${0.5 + 0.05 * (k % 3)})`;
      ctx.lineWidth = 7.5 - Math.abs(f) * 3.4;
      ctx.stroke();
    }
    ctx.globalAlpha = 0.55;
    ctx.drawImage(gold, TX - 170, BASE_Y - 230, 340, 340);
    ctx.globalAlpha = 1;
  }

  function leafCanvasPos(m, x, y, a) { return rot(x, y, TX, TY + 30, a); }

  function draw(t) {
    const dt = Math.min(64, t - last); last = t;
    ctx.setTransform(dpr * scale, 0, 0, dpr * scale, 0, 0);
    ctx.drawImage(bg, 0, 0);
    const elapsed = t - start;
    for (const s of stars) {
      ctx.globalAlpha = 0.25 + 0.6 * (0.5 + 0.5 * Math.sin(elapsed * 0.001 * s.s + s.p));
      ctx.fillStyle = '#dfe8ff'; ctx.beginPath(); ctx.arc(s.x, s.y, s.r, 0, TAU); ctx.fill();
    }
    ctx.globalAlpha = 1;
    // блики на озере
    for (let i = 0; i < 14; i++) {
      const y = GROUND + 10 + i * 9, w = 120 + 90 * Math.sin(i + elapsed * 0.0004 * (i % 3 + 1));
      ctx.fillStyle = `rgba(150,190,255,${0.05 + 0.02 * (i % 3)})`;
      ctx.fillRect(TX - w / 2 + Math.sin(elapsed * 0.0007 + i) * 20, y, w, 1.5);
    }
    trunk(elapsed);
    posed.clear(); labelBoxes.length = 0;
    const wind = reduced ? 0 : Math.sin(elapsed * 0.00031) * 0.6 + Math.sin(elapsed * 0.00073) * 0.4;
    for (const m of model) {
      const g = growth(elapsed, m.delay);
      if (g <= 0) continue;
      const a = reduced ? 0 : m.amp * (0.6 + 0.4 * wind) * Math.sin(elapsed * 0.0011 + m.phase) + m.amp * 0.35 * wind;
      ctx.save();
      ctx.translate(TX, TY + 30); ctx.rotate(a); ctx.translate(-TX, -(TY + 30));
      // ветка: сужается к кончику; рисуется до g
      const stroke = (pts, w0, w1, glow) => {
        if (pts.length < 2) return;
        ctx.lineCap = 'round';
        for (const [mul, al, col] of glow) {
          ctx.strokeStyle = `rgba(${col},${al})`;
          for (let i = 1; i < pts.length; i++) {
            ctx.lineWidth = Math.max(0.6, (w0 + (w1 - w0) * (i / pts.length)) * mul);
            ctx.beginPath(); ctx.moveTo(pts[i - 1][0], pts[i - 1][1]); ctx.lineTo(pts[i][0], pts[i][1]); ctx.stroke();
          }
        }
      };
      const mainPts = [];
      for (let k = 0; k <= 28 * g; k++) mainPts.push(bez(m.p, k / 28));
      const jeff = m.zone.id === 'jeff' ? 1.3 : 1;
      stroke(mainPts, 13 * jeff, 3.2, [[2.1, 0.14, '158,195,255'], [1, 0.92, '232,242,255'], [0.32, 0.6, '255,255,255']]);
      for (const sb of m.subs) {
        const gs = clamp((g - sb.ts) / 0.34);
        if (gs <= 0) continue;
        const sp = [];
        for (let k = 0; k <= 12 * gs; k++) sp.push(bez(sb.q, k / 12));
        stroke(sp, 3.8, 0.9, [[2.4, 0.1, '158,195,255'], [1, 0.78, '214,230,255']]);
      }
      for (const l of m.leaves) {
        const gs = clamp((g - l.sb.ts) / 0.34);
        if (gs < l.u * 0.92) continue;
        const bloom = reduced ? 1 : Math.max(0, easeBack(clamp((gs - l.u * 0.92) / 0.2 + (g >= 1 ? 1 : 0))));
        const dim = state.filter && l.node.status !== state.filter ? 0.16 : 1;
        ctx.strokeStyle = `rgba(190,212,255,${0.28 * dim * bloom})`; ctx.lineWidth = 0.9;
        ctx.beginPath(); ctx.moveTo(l.bx, l.by); ctx.lineTo(l.bx + (l.x - l.bx) * bloom, l.by + (l.y - l.by) * bloom); ctx.stroke();
        const tw = reduced ? 0.9 : 0.62 + 0.38 * Math.sin(elapsed * 0.0016 * (0.6 + (l.i % 5) * 0.12) + l.phase);
        const sprt = sprites[l.node.status] || sprites.code;
        const size = (22 + (l.node.status === 'reported' ? 8 : 0)) * l.size * Math.max(0.01, bloom);
        ctx.globalAlpha = clamp(tw * dim);
        ctx.drawImage(sprt, l.x - size / 2, l.y - size / 2, size, size);
        ctx.globalAlpha = clamp(0.95 * dim * bloom);
        ctx.fillStyle = colors[l.node.status] || '#4fa8ff';
        ctx.beginPath(); ctx.ellipse(l.x, l.y, 5 * bloom * l.size, 2.6 * bloom * l.size, l.ang, 0, TAU); ctx.fill();
        ctx.globalAlpha = 1;
        posed.set(l.node.id, leafCanvasPos(m, l.x, l.y, a));
      }
      ctx.restore();
      const [ex, ey] = leafCanvasPos(m, m.end[0], m.end[1], a);
      posed.set(m.zone.id, [ex, ey]);
      if (g > 0.85) {
        const text = labels[m.zone.id] || m.zone.label;
        const isJeff = m.zone.id === 'jeff';
        ctx.font = `600 ${isJeff ? 30 : 17}px Georgia, 'Times New Roman', serif`;
        const w = ctx.measureText(text).width;
        const x0 = Math.min(W - w - 10, Math.max(10, ex - w / 2)), y0 = Math.max(26, ey - (isJeff ? 26 : 16));
        ctx.globalAlpha = clamp((g - 0.85) / 0.15);
        ctx.lineWidth = 5; ctx.strokeStyle = 'rgba(6,10,30,.75)'; ctx.strokeText(text, x0, y0);
        ctx.shadowColor = 'rgba(150,190,255,.9)'; ctx.shadowBlur = 12;
        ctx.fillStyle = state.hover === m.zone.id || state.selected === m.zone.id ? '#fff3c4' : '#eef4ff';
        ctx.fillText(text, x0, y0);
        ctx.shadowBlur = 0; ctx.globalAlpha = 1;
        labelBoxes.push({ node: m.zone, x: x0 - 6, y: y0 - (isJeff ? 30 : 18), w: w + 12, h: isJeff ? 40 : 26, ex, ey });
      }
    }
    // светлячки, падающая звезда
    if (!reduced) {
      for (const f of flies) {
        const k = (elapsed * 0.00012 * f.s + f.p) % 1;
        ctx.globalAlpha = Math.sin(k * Math.PI) * 0.75;
        ctx.drawImage(gold, f.x + Math.sin(elapsed * 0.0005 * f.s + f.p) * 26, f.y - k * 90, 18, 18);
      }
      ctx.globalAlpha = 1;
      if (!shoot && Math.random() < dt / 9000) shoot = { x: 200 + Math.random() * 700, y: 60 + Math.random() * 120, age: 0 };
      if (shoot) {
        shoot.age += dt;
        const k = shoot.age / 900;
        ctx.strokeStyle = `rgba(255,255,255,${(1 - k) * 0.85})`; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(shoot.x + k * 420, shoot.y + k * 190); ctx.lineTo(shoot.x + k * 420 - 90, shoot.y + k * 190 - 40); ctx.stroke();
        if (k >= 1) shoot = null;
      }
    }
    // кольцо выбора
    const sel = state.selected && posed.get(state.selected);
    if (sel) {
      ctx.strokeStyle = 'rgba(255,255,255,.9)'; ctx.lineWidth = 2; ctx.setLineDash([4, 3]);
      ctx.lineDashOffset = -elapsed * 0.02; ctx.beginPath(); ctx.arc(sel[0], sel[1], 13 + Math.sin(elapsed * 0.004) * 1.5, 0, TAU); ctx.stroke(); ctx.setLineDash([]);
    }
    const hv = state.hover && state.hover !== state.selected && posed.get(state.hover);
    if (hv) { ctx.globalAlpha = 0.9; ctx.drawImage(white, hv[0] - 20, hv[1] - 20, 40, 40); ctx.globalAlpha = 1; }
  }

  function loop(now) {
    if (!wrap.isConnected) { cancelAnimationFrame(raf); ro.disconnect(); return; }
    if (!document.hidden) draw(now);
    raf = requestAnimationFrame(loop);
  }

  function hit(px, py) {
    let best = null, bd = 17 / Math.max(0.55, Math.min(1, scale * 1.3));
    for (const m of model) for (const l of m.leaves) {
      const p = posed.get(l.node.id);
      if (!p) continue;
      const d = Math.hypot(p[0] - px, p[1] - py);
      if (d < bd) { bd = d; best = { node: l.node, x: p[0], y: p[1] }; }
    }
    if (best) return best;
    for (const b of labelBoxes) if (px >= b.x && px <= b.x + b.w && py >= b.y && py <= b.y + b.h) return { node: b.node, x: b.ex, y: b.ey };
    return null;
  }

  const world = (e) => { const r = canvas.getBoundingClientRect(); return [(e.clientX - r.left) / scale, (e.clientY - r.top) / scale]; };
  function showTip(h) {
    if (!h) { tip.classList.remove('on'); return; }
    const sx = h.x * scale, sy = h.y * scale;
    tip.textContent = `${h.node.label}${labels._status ? ' · ' + (labels._status[h.node.status] || '') : ''}`;
    tip.style.transform = `translate(${Math.round(Math.min(sx + 14, wrap.clientWidth - 200))}px, ${Math.round(Math.max(6, sy - 40))}px)`;
    tip.classList.add('on');
  }
  canvas.addEventListener('pointermove', (e) => {
    if (e.pointerType === 'touch') return;
    const [x, y] = world(e);
    const h = hit(x, y);
    state.hover = h ? h.node.id : null;
    canvas.style.cursor = h ? 'pointer' : 'default';
    showTip(h);
    if (onHover) onHover(h && h.node);
    if (reduced) draw(performance.now());
  });
  canvas.addEventListener('pointerleave', () => { state.hover = null; showTip(null); if (reduced) draw(performance.now()); });
  canvas.addEventListener('click', (e) => {
    const [x, y] = world(e);
    const h = hit(x, y);
    if (h && onPick) onPick(h.node);
  });
  canvas.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    e.preventDefault();
    const first = model[0] && model[0].zone;
    if (first && onPick) onPick(first);
  });

  const ro = new ResizeObserver(() => resize());
  ro.observe(wrap);
  requestAnimationFrame(() => { resize(); start = performance.now(); if (reduced) draw(performance.now()); else raf = requestAnimationFrame(loop); });

  return {
    el: wrap,
    leaves: model.reduce((n, m) => n + m.leaves.length, 0),
    select(id) { state.selected = id; if (reduced) draw(performance.now()); },
    filter(status) { state.filter = status || null; if (reduced) draw(performance.now()); },
    /** Экранные координаты точки узла (для автоматических проверок: настоящий клик мышью). */
    where(id) { const p = posed.get(id); if (!p) return null; const r = canvas.getBoundingClientRect(); return { x: r.left + p[0] * scale, y: r.top + p[1] * scale }; },
    pick(id) { const l = byId.get(id); if (l && onPick) onPick(l.node); return !!l; },
    destroy() { ro.disconnect(); cancelAnimationFrame(raf); },
  };
}
