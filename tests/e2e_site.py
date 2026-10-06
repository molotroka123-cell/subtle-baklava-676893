"""Браузерная проверка витрины (Playwright + Chromium). Запуск:  python tests/e2e_site.py [--chromium /opt/pw-browsers/chromium]

Сайт поднимается локально (python -m http.server). Проверяется настоящий путь пользователя: клик по ветви дерева,
статья, Esc, поиск, прямая ссылка, телефон без горизонтальной прокрутки, отсутствие ошибок в консоли.
"""
import argparse
import asyncio
import functools
import http.server
import socketserver
import threading
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent


def serve() -> tuple[socketserver.TCPServer, int]:
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a, **k):
            pass

    handler = functools.partial(Quiet, directory=str(ROOT))
    srv = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


async def main(chromium: str | None) -> int:
    srv, port = serve()
    base = f"http://127.0.0.1:{port}/index.html"
    failures: list[str] = []

    def check(ok: bool, what: str) -> None:
        print(("PASS " if ok else "FAIL ") + what)
        if not ok:
            failures.append(what)

    async with async_playwright() as p:
        browser = await p.chromium.launch(**({"executable_path": chromium} if chromium else {}), args=["--no-sandbox"])
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "ERR_" not in m.text else None)
        await page.route("**/fonts.googleapis.com/**", lambda r: r.abort())
        await page.goto(base)
        await page.wait_for_function("window.__bossman && window.__bossman.leaves > 100")
        info = await page.evaluate("({n: window.__bossman.nodes, l: window.__bossman.leaves})")
        check(info["n"] > 100 and info["l"] > 100, f"дерево построено: узлов {info['n']}, листьев {info['l']}")

        await page.evaluate("document.querySelector('#tree').scrollIntoView()")
        await page.wait_for_timeout(5200)                                  # дерево выросло
        await page.wait_for_timeout(2500)
        draw = await page.evaluate("""async () => { const t = await (await fetch('data/tree.json')).json();
          const leaves = t.nodes.filter(n => n.parent !== '' && n.parent !== 'bossman');
          const miss = leaves.filter(n => !window.__bossman.where(n.id)).map(n => n.id);
          return { leaves: leaves.length, miss }; }""")
        check(not draw["miss"], f"каждый лист нарисован и нажимаем: {draw['leaves'] - len(draw['miss'])} из {draw['leaves']}")
        box = await page.locator("#scene canvas, .ts-canvas").first.bounding_box()
        # настоящий клик мышью по листу дерева (координаты листа берём у сцены)
        pt = await page.evaluate("window.__bossman.where('cap-0')")
        check(pt is not None, "лист cap-0 найден на сцене")
        await page.mouse.move(pt["x"], pt["y"])
        await page.mouse.click(pt["x"], pt["y"])
        await page.wait_for_selector("#reader:not([hidden])")
        check((await page.inner_text("#readerTitle")).strip() == "Диалог и ответы", "клик мышью по листу открывает его статью")
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)
        await page.evaluate("window.__bossman.open('jeff')")
        await page.wait_for_selector("#reader:not([hidden])")
        check((await page.inner_text("#readerTitle")).startswith("Jeff"), "статья зоны открывается")
        sections = await page.locator("#readerBody section").count()
        check(sections >= 5, f"в статье зоны {sections} разделов")
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)
        check(not await page.is_visible("#reader"), "Esc закрывает статью")
        check(box is not None and box["width"] > 600, "canvas дерева имеет размер")

        await page.keyboard.press("/")
        await page.keyboard.type("discovery")
        await page.wait_for_timeout(300)
        results = await page.locator("#qList li").all_inner_texts()
        check(any("discovery.py" in r for r in results), "поиск находит discovery.py")
        await page.keyboard.press("Enter")
        await page.wait_for_selector("#reader:not([hidden])")
        heads = await page.locator("#readerBody h2").all_inner_texts()
        check(any("ОСНОВНЫЕ ФУНКЦИИ" in h.upper() for h in heads), "статья модуля содержит функции")
        body_text = await page.inner_text("#readerBody")
        check("C:\\" not in body_text and "/home/" not in body_text, "в статье нет локальных путей")


        # --- приближение дерева ---
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(600)
        await page.evaluate("document.querySelector('#tree').scrollIntoView()")
        await page.wait_for_timeout(400)
        check(await page.evaluate("window.__bossman.zoom()") == 1, "дерево открыто целиком (zoom=1)")
        await page.click("#zoomIn")
        await page.click("#zoomIn")
        z1 = await page.evaluate("window.__bossman.zoom()")
        check(z1 > 2, f"кнопка + приближает ({z1:.2f})")
        await page.evaluate("window.__bossman.zoomTo('cap-0', 3)")
        pt = await page.evaluate("window.__bossman.where('cap-0')")
        cb = await page.locator(".ts-canvas").first.bounding_box()
        check(cb["x"] < pt["x"] < cb["x"] + cb["width"] and cb["y"] < pt["y"] < cb["y"] + cb["height"], "после приближения лист виден на холсте")
        await page.mouse.click(pt["x"], pt["y"])
        await page.wait_for_selector("#reader:not([hidden])")
        check((await page.inner_text("#readerTitle")).strip() == "Диалог и ответы", "клик по листу в приближенном дереве открывает ту же статью")
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)
        await page.click("#zoomReset")
        check(await page.evaluate("window.__bossman.zoom()") == 1, "⤢ возвращает дерево целиком")
        cx, cy = cb["x"] + cb["width"] / 2, cb["y"] + cb["height"] / 2
        sx, sy = cb["x"] + 30, cb["y"] + 30                                      # пустое небо
        await page.mouse.dblclick(sx, sy)
        zd = await page.evaluate("window.__bossman.zoom()")
        await page.mouse.dblclick(sx, sy)
        check(zd > 2 and await page.evaluate("window.__bossman.zoom()") == 1, f"двойной клик по пустому месту приближает ({zd:.2f}) и возвращает")
        await page.mouse.move(cx, cy)
        await page.keyboard.down("Control")
        await page.mouse.wheel(0, -500)
        await page.keyboard.up("Control")
        check(await page.evaluate("window.__bossman.zoom()") > 1.5, "Ctrl+колесо приближает")
        await page.click("#zoomReset")
        await page.evaluate("""() => { const c = document.querySelector('.ts-canvas'), r = c.getBoundingClientRect();
          const mk = (t, id, x, y) => c.dispatchEvent(new PointerEvent(t, { pointerId: id, pointerType: 'touch', clientX: x, clientY: y, bubbles: true, isPrimary: id === 1 }));
          const x = r.left + r.width / 2, y = r.top + r.height / 2;
          mk('pointerdown', 1, x - 40, y); mk('pointerdown', 2, x + 40, y);
          mk('pointermove', 1, x - 120, y); mk('pointermove', 2, x + 120, y);
          mk('pointerup', 1, x - 120, y); mk('pointerup', 2, x + 120, y); }""")
        zp = await page.evaluate("window.__bossman.zoom()")
        check(2.5 < zp <= 3.2, f"щипок двумя пальцами приближает пропорционально ({zp:.2f}, ждали ≈3)")
        await page.click("#zoomReset")
        await page.mouse.click(cb["x"] + 8, cb["y"] + 8)
        await page.wait_for_timeout(300)
        check(not await page.is_visible("#reader"), "контроль: клик по пустому небу ничего не открывает")


        fr = await page.evaluate("""async () => { const m = await import('./fresh.js'); const t0 = Date.parse('2026-10-06T12:00:00Z');
          return [m.describeFreshness('2026-10-06T10:00:00Z', t0), m.describeFreshness('2026-10-05T04:00:00Z', t0), m.describeFreshness('мусор', t0), m.describeFreshness('2026-10-06T11:40:00Z', t0)]; }""")
        check(fr[0]["text"] == "данные обновлены 2 ч назад" and not fr[0]["stale"], "свежесть: 2 часа назад — нормально")
        check(fr[1]["stale"] and "давно не присылал" in fr[1]["text"], "свежесть: 32 часа — красная строка")
        check(fr[2]["stale"] and fr[3]["text"] == "данные обновлены 20 мин назад", "свежесть: мусорная дата — тревога; минуты считаются")
        check(len((await page.inner_text("#fresh")).strip()) > 10, "на странице есть строка свежести данных")

        page2 = await ctx.new_page()
        await page2.route("**/fonts.googleapis.com/**", lambda r: r.abort())
        await page2.goto(base + "#/n/jeff")
        await page2.wait_for_selector("#reader:not([hidden])")
        check(True, "прямая ссылка #/n/<id> открывает статью")

        mobile = await browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        mp = await mobile.new_page()
        await mp.route("**/fonts.googleapis.com/**", lambda r: r.abort())
        await mp.goto(base)
        await mp.wait_for_function("window.__bossman")
        await mp.wait_for_timeout(1500)
        width = await mp.evaluate("document.documentElement.scrollWidth")
        check(width <= 392, f"телефон: нет горизонтальной прокрутки страницы ({width}px)")


        await mp.evaluate("document.querySelector('#tree').scrollIntoView()")
        await mp.wait_for_timeout(5500)
        await mp.tap("#zoomIn")
        await mp.tap("#zoomIn")
        check(await mp.evaluate("window.__bossman.zoom()") > 2, "телефон: кнопка + приближает пальцем")
        await mp.evaluate("window.__bossman.zoomTo('cap-0', 3)")
        await mp.evaluate("(() => { const s = document.querySelector('#treeScroll'); s.scrollLeft = (s.scrollWidth - s.clientWidth) / 2; })()")
        mpt = await mp.evaluate("window.__bossman.where('cap-0')")
        await mp.touchscreen.tap(mpt["x"], mpt["y"])
        await mp.wait_for_selector("#reader:not([hidden])")
        check((await mp.inner_text("#readerTitle")).strip() == "Диалог и ответы", "телефон: тап по листу в приближенном дереве открывает статью")

        check(not errors, f"нет ошибок в консоли {errors[:3]}")
        await browser.close()
    srv.shutdown()
    print("E2E=PASS" if not failures else "E2E=FAIL")
    return 0 if not failures else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--chromium", default=None)
    raise SystemExit(asyncio.run(main(ap.parse_args().chromium)))
