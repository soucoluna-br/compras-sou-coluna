"""Gera o PDF de impressão a partir de out/guia-compras-sou-coluna.html.
Requer: pip install playwright && playwright install chromium
Uso: python3 scripts/gerar_pdf.py
"""
import asyncio, os
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / "out/guia-compras-sou-coluna.html").as_uri() + "?blank"
DEST = ROOT / "out/Guia-de-Compras-Sou-Coluna.pdf"

async def main():
    async with async_playwright() as p:
        # CHROMIUM_PATH (opcional): usa um Chromium já instalado em vez do baixado pelo Playwright
        exe = os.environ.get("CHROMIUM_PATH")
        b = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
        pg = await b.new_page()
        await pg.goto(SRC); await pg.wait_for_timeout(800)
        await pg.emulate_media(media="print")
        await pg.pdf(path=str(DEST), prefer_css_page_size=True, print_background=True)
        await b.close()
    print("ok:", DEST)

asyncio.run(main())
