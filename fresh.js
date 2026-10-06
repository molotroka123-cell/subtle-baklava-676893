/* Свежесть данных витрины: показывает, когда компьютер владельца последний раз прислал снимок.
 * Если снимок старше 26 часов — витрина говорит об этом прямо (автообновление с ПК не работает или компьютер выключен). */
export function describeFreshness(iso, now = Date.now()) {
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return { text: 'время снимка неизвестно', stale: true, hours: null };
  const h = Math.max(0, (now - t) / 36e5);
  const ago = h < 1 ? `${Math.max(1, Math.round(h * 60))} мин назад` : h < 48 ? `${Math.round(h)} ч назад` : `${Math.round(h / 24)} дн назад`;
  const stale = h > 26;
  return { text: `данные обновлены ${ago}${stale ? ' — компьютер давно не присылал снимок' : ''}`, stale, hours: h };
}
