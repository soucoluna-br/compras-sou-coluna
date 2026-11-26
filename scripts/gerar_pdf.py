"""Gera os PDFs a partir do HTML do build.py:
  out/Guia-de-Compras-Sou-Coluna.pdf  (guia completo, com cards, linhas para valor pago e data)
  out/Lista-de-Compras-Sou-Coluna.pdf (lista compacta de poucas páginas, com caixa de marcação)
Requer: pip install playwright && playwright install chromium
Uso: python3 scripts/gerar_pdf.py
"""
import asyncio, os
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
SRC = (ROOT / "out/guia-compras-sou-coluna.html").as_uri() + "?blank"
DEST = ROOT / "out/Guia-de-Compras-Sou-Coluna.pdf"
LISTA = ROOT / "out/lista-compras-sou-coluna.html"
DEST_LISTA = ROOT / "out/Lista-de-Compras-Sou-Coluna.pdf"
RODAPE = ('<div style="width:100%;font-family:Inter,sans-serif;font-size:7px;color:#9A938E;padding:0 9mm;display:flex;justify-content:space-between">'
          '<span>Sou Coluna · Lista de compras para abertura de unidade</span>'
          '<span>Página <span class="pageNumber"></span> de <span class="totalPages"></span></span></div>')

async def main():
    async with async_playwright() as p:
        # CHROMIUM_PATH (opcional): usa um Chromium já instalado em vez do baixado pelo Playwright
        exe = os.environ.get("CHROMIUM_PATH")
        b = await p.chromium.launch(**({"executable_path": exe} if exe else {}))
        pg = await b.new_page()
        await pg.goto(SRC); await pg.wait_for_timeout(800)
        await pg.emulate_media(media="print")
        await pg.pdf(path=str(DEST), prefer_css_page_size=True, print_background=True)
        print("ok:", DEST)
        if LISTA.exists():
            await pg.goto(LISTA.as_uri()); await pg.wait_for_timeout(500)
            await pg.pdf(path=str(DEST_LISTA), prefer_css_page_size=True, print_background=True,
                         display_header_footer=True, header_template="<span></span>", footer_template=RODAPE)
            print("ok:", DEST_LISTA)
        await b.close()

asyncio.run(main())
