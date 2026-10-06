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

        check(not errors, f"нет ошибок в консоли {errors[:3]}")
        await browser.close()
    srv.shutdown()
    print("E2E=PASS" if not failures else "E2E=FAIL")
    return 0 if not failures else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--chromium", default=None)
    raise SystemExit(asyncio.run(main(ap.parse_args().chromium)))
