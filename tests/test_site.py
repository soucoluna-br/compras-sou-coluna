"""Testes de ponta a ponta do site num Chromium de verdade, com o servidor da Cloudflare rodando
localmente (wrangler pages dev + banco D1 local zerado). Também confere a versão offline.

Uso:
  python3 build.py
  python3 tests/test_site.py                    # CHROMIUM_PATH=/caminho/do/chromium se precisar
  python3 tests/test_site.py --telas pasta/     # também salva capturas de tela (celular e computador)
"""
import os, re, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from servidor_local import CHAVE, ROOT, Servidor

TELAS = Path(sys.argv[sys.argv.index("--telas") + 1]) if "--telas" in sys.argv else None
passou = 0


def ok(cond, msg):
    global passou
    if not cond:
        raise AssertionError("FALHOU: " + msg)
    passou += 1
    print("ok:", msg)


def novo_contexto(browser, **kw):
    ctx = browser.new_context(permissions=["clipboard-read", "clipboard-write"], **kw)
    ctx.erros = []
    def vigiar(page):
        page.on("pageerror", lambda e: ctx.erros.append(f"{page.url}: {e}"))
        page.on("response", lambda r: r.status >= 400 and "/api/" not in r.url and "127.0.0.1" in r.url
                and ctx.erros.append(f"{r.status} {r.url}"))
    ctx.on("page", vigiar)
    return ctx


def api(page, caminho):
    return page.evaluate("async c => (await fetch('/api/' + c)).json()", caminho)


def pronto(page):
    page.wait_for_function("document.body.classList.contains('pronto')")


def card(page, item):
    return page.locator(f'.card[data-id="{item}"]')


def esperar_salvo(page):
    page.wait_for_function("document.getElementById('sync').textContent==='Tudo salvo'", timeout=15000)


def ver(page, view):
    page.locator(f'[data-view="{view}"]').wait_for()


def entrar(page, base, email, senha):
    page.goto(base + "/")
    ver(page, "entrar")
    page.fill("#e-mail", email); page.fill("#e-senha", senha)
    page.click("#f-entrar button[type=submit]")


def sem_rolagem_lateral(page):
    return page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


def tela(page, nome):
    if TELAS:
        TELAS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(TELAS / f"{nome}.png"))


def main():
    with Servidor() as srv, sync_playwright() as p:
        B = srv.base
        exe = os.environ.get("CHROMIUM_PATH")
        browser = p.chromium.launch(**({"executable_path": exe} if exe else {}))
        ctx = novo_contexto(browser, viewport={"width": 1366, "height": 900})
        pg = ctx.new_page()

        # ---------- franqueadora cria a conta com a chave e cadastra unidades ----------
        pg.goto(B + "/")
        ver(pg, "entrar")
        tela(pg, "login-computador")
        pg.click('[data-view="entrar"] [data-ir="criar"]')
        pg.fill("#c-codigo", CHAVE); pg.fill("#c-nome", "Franqueadora"); pg.fill("#c-mail", "adm@soucoluna.test"); pg.fill("#c-senha", "senha-adm-123")
        pg.click("#f-criar button[type=submit]")
        pg.wait_for_url("**/painel")
        pg.locator(".vazio").wait_for()
        ok("Nenhuma unidade" in pg.inner_text(".vazio"), "franqueadora entra com a chave e vê o painel vazio")
        pg.click(".vazio button")
        pg.fill("#u-nome", "Sou Coluna Florianópolis"); pg.fill("#u-cidade", "Florianópolis"); pg.fill("#u-inaug", "2027-02-01")
        pg.click("#f-unidade button[type=submit]")
        pg.locator("#d-convite[open]").wait_for()
        cod_a = pg.inner_text("#dc-codigo")
        ok(re.fullmatch(r"[0-9A-F]{5}-[0-9A-F]{5}", cod_a) is not None, "nova unidade abre o convite com o código")
        pg.click("#b-copiar-msg")
        msg = pg.evaluate("navigator.clipboard.readText()")
        ok(cod_a in msg and f"{B}/?codigo={cod_a}" in msg, "mensagem de convite copiada com link e código")
        tela(pg, "painel-convite")
        pg.click("#d-convite [data-fechar]")
        pg.click("#b-nova"); pg.fill("#u-nome", "Sou Coluna Curitiba"); pg.fill("#u-cidade", "Curitiba")
        pg.click("#f-unidade button[type=submit]")
        pg.locator("#d-convite[open]").wait_for()
        cod_b = pg.inner_text("#dc-codigo")
        pg.click("#d-convite [data-fechar]")
        ok(pg.locator(".un").count() == 2 and pg.inner_text("#k-n") == "2", "painel mostra as 2 unidades")
        UA = pg.locator(".un", has_text="Florianópolis").get_attribute("data-id")
        UB = pg.locator(".un", has_text="Curitiba").get_attribute("data-id")
        pg.click("[data-sair]"); pg.wait_for_url(B + "/")

        # ---------- franqueada entra pelo convite ----------
        pg.goto(B + "/?codigo=" + cod_a.lower().replace("-", ""))
        ver(pg, "criar")
        ok(pg.input_value("#c-codigo") == cod_a, "link de convite abre 'Criar conta' com o código formatado")
        pg.fill("#c-nome", "Ana"); pg.fill("#c-mail", "ana@unidade.test"); pg.fill("#c-senha", "123")
        pg.click("#f-criar button[type=submit]")
        ok("8 caracteres" in pg.inner_text("#f-criar .msg"), "senha curta é recusada")
        pg.fill("#c-senha", "senha-da-ana"); pg.click("#f-criar button[type=submit]")
        pg.wait_for_url(f"**/guia?u={UA}"); pronto(pg)
        ok(pg.input_value("#f-unit") == "Sou Coluna Florianópolis" and pg.locator("#f-unit").get_attribute("readonly") is not None,
           "guia abre na unidade do convite, com o nome travado")
        nav = pg.inner_text("#user-nav")
        ok("Sair" in nav and "Painel" not in nav, "franqueado vê 'Sair' e não vê o painel")
        ok(not pg.locator("#b-trocar").is_visible(), "com uma unidade só, não aparece 'Trocar unidade'")
        ok(not pg.locator(".hero-tag").is_visible() and not pg.locator("#b-backup").is_visible(), "itens só da versão offline ficam escondidos")
        ok(pg.inner_text("#foot-h") == "Seu progresso fica salvo na sua conta", "rodapé explica que salva na conta")

        prev = pg.evaluate("BYID['enxoval-geladeira'].prev")
        card(pg, "enxoval-geladeira").locator(".toggle").click()
        esperar_salvo(pg)
        itens = {i["item_id"]: i for i in api(pg, f"unidades/{UA}/compras")["itens"]}
        ok(itens["enxoval-geladeira"]["comprado"] and itens["enxoval-geladeira"]["valor_pago"] == prev, "marcar comprado grava no banco com o valor previsto")
        inp = card(pg, "enxoval-balde").locator(".money input")
        inp.fill("1.234,56"); inp.press("Enter")
        esperar_salvo(pg)
        itens = {i["item_id"]: i for i in api(pg, f"unidades/{UA}/compras")["itens"]}
        ok(itens["enxoval-balde"]["valor_pago"] == 1234.56 and itens["enxoval-balde"]["comprado"], "valor pago digitado grava no banco e marca como comprado")
        pg.fill("#f-resp", "Ana Souza")
        pg.wait_for_function(f"fetch('/api/unidades/{UA}/compras').then(r=>r.json()).then(j=>j.unidade.responsavel==='Ana Souza')", timeout=8000, polling=500)
        ok(True, "responsável digitado no guia vai para o banco")
        ok("sugestões" in pg.inner_text(".aviso"), "aviso de que quantidades e valores são sugestões")
        ok(card(pg, "enxoval-geladeira").locator(".price .l").inner_text().lower() == "valor estimado", "preço aparece como valor estimado")
        card(pg, "enxoval-geladeira").locator('[data-q="1"]').click()
        esperar_salvo(pg)
        ok(card(pg, "enxoval-geladeira").locator(".pv").inner_text() == "R$ 4.000" and pg.inner_text("#k-prev") == "R$ 304.638",
           "aumentar a quantidade recalcula o valor estimado do item e o total previsto")
        itens = {i["item_id"]: i for i in api(pg, f"unidades/{UA}/compras")["itens"]}
        ok(itens["enxoval-geladeira"]["quantidade"] == 2, "quantidade ajustada vai para o banco")
        pg.evaluate("scrollTo(0,0)")
        tela(pg, "guia-computador")

        pg.reload(); pronto(pg)
        ok("done" in card(pg, "enxoval-geladeira").get_attribute("class") and card(pg, "enxoval-balde").locator(".money input").input_value() == "1.234,56",
           "depois de recarregar, compras e valores continuam")
        ok(pg.inner_text("#k-items") == "2 de 130" and pg.input_value("#f-resp") == "Ana Souza", "andamento e responsável vêm do banco")
        ok(card(pg, "enxoval-geladeira").locator(".qtd input").input_value() == "2" and "Sugestão da rede: 1" in card(pg, "enxoval-geladeira").locator(".sug").inner_text(),
           "quantidade ajustada continua depois de recarregar, mostrando a sugestão original")

        # ---------- filtros, ordem e visualização ----------
        visiveis = lambda: pg.locator("#sections .card:visible").count()
        pg.click('#abas button[data-f="done"]')
        ok(visiveis() == 2 and pg.inner_text("#n-encontrados") == "2 itens encontrados", "aba Comprados mostra só os 2 comprados")
        pg.click('#abas button[data-f="todo"]')
        ok(visiveis() == 128 and not card(pg, "enxoval-geladeira").is_visible(), "aba Pendentes esconde os comprados")
        pg.click('#abas button[data-f="all"]')
        pg.check('#fl-etapa input[value="franqueadora"]')
        ok(visiveis() == 8, "filtro de etapa mostra só os itens da etapa")
        pg.check('#fl-supply input[value="homologado"]')
        n_h = pg.evaluate("ITEMS.filter(i=>i.sec==='franqueadora'&&i.supply==='homologado').length")
        ok(visiveis() == n_h, "filtros combinados (etapa + fornecimento)")
        pg.click("#b-limpar")
        ok(visiveis() == 130, "limpar filtros volta a mostrar tudo")
        pg.fill("#q", "geladeira")
        ok(visiveis() == 1, "busca encontra o item")
        pg.fill("#q", "")
        pg.select_option("#ordem", "maior")
        maior = pg.evaluate("[...ITEMS].sort((a,b)=>(b.prev||-1)-(a.prev||-1))[0].id")
        ok(pg.locator("#sections .card").first.get_attribute("data-id") == maior, "ordenar por maior valor põe o item mais caro primeiro")
        pg.click('#vis button[data-v="lista"]')
        ok("modo-lista" in pg.get_attribute("#sections", "class"), "visualização em lista")
        pg.reload(); pronto(pg)
        ok(pg.input_value("#ordem") == "maior" and "modo-lista" in pg.get_attribute("#sections", "class"), "ordem e visualização ficam lembradas")
        pg.select_option("#ordem", "etapa"); pg.click('#vis button[data-v="blocos"]')

        pg.goto(B + f"/guia?u={UB}")
        pg.wait_for_url("**/?escolher=1"); ver(pg, "escolher")
        ok(pg.locator("#lista a").count() == 1 and "Florianópolis" in pg.inner_text("#lista"), "franqueado não abre o guia de outra unidade")

        # ---------- queda de conexão ----------
        pg.goto(B + f"/guia?u={UA}"); pronto(pg)
        bloqueio = lambda rota: rota.abort() if rota.request.method == "POST" else rota.continue_()
        pg.route("**/api/unidades/*/compras", bloqueio)
        card(pg, "enxoval-calculadora").locator(".toggle").click()
        pg.wait_for_function("document.getElementById('sync').textContent.startsWith('Sem conexão')", timeout=6000)
        ok(True, "sem conexão: o guia avisa que não salvou")
        pg.unroute("**/api/unidades/*/compras", bloqueio)
        esperar_salvo(pg)
        ok(any(i["item_id"] == "enxoval-calculadora" for i in api(pg, f"unidades/{UA}/compras")["itens"]), "conexão volta: o guia reenvia sozinho")
        pg.click("#b-sair"); pg.wait_for_url(B + "/")

        # ---------- erros no login e no cadastro ----------
        ver(pg, "entrar")
        pg.click('[data-view="entrar"] [data-ir="criar"]')
        pg.fill("#c-codigo", "00000-00000"); pg.fill("#c-nome", "X"); pg.fill("#c-mail", "x@x.test"); pg.fill("#c-senha", "12345678")
        pg.click("#f-criar button[type=submit]")
        pg.wait_for_function("document.querySelector('#f-criar .msg').textContent.includes('Código não encontrado')")
        ok(True, "código inexistente é recusado")
        pg.fill("#c-codigo", cod_b); pg.fill("#c-mail", "ana@unidade.test")
        pg.click("#f-criar button[type=submit]")
        pg.wait_for_function("document.querySelector('#f-criar .msg').textContent.includes('já tem conta')")
        ok(True, "e-mail já cadastrado é avisado")
        entrar(pg, B, "adm@soucoluna.test", "errada")
        pg.wait_for_function("document.querySelector('#f-entrar .msg').textContent==='E-mail ou senha incorretos.'")
        ok(True, "senha errada mostra mensagem em português")

        # ---------- franqueadora acompanha ----------
        entrar(pg, B, "adm@soucoluna.test", "senha-adm-123")
        pg.wait_for_url("**/painel"); pg.locator(".un").first.wait_for()
        tela(pg, "painel-computador")
        ca = pg.locator(f'.un[data-id="{UA}"]')
        ok("3 de 130" in ca.inner_text() and "Ana Souza" in ca.inner_text() and "1 acesso" in ca.inner_text(), "painel mostra andamento, responsável e acessos")
        ok(pg.evaluate(f"UNIDADES.find(u=>u.id==='{UA}').st.prev") == 304638.4, "painel usa a quantidade ajustada pela unidade na previsão")
        ca.locator('[data-a="acessos"]').click()
        ok("ana@unidade.test" in pg.inner_text("#da-lista"), "janela de acessos lista a franqueada")
        pg.click("#da-lista [data-senha]")
        pg.wait_for_function("navigator.clipboard.readText().then(t=>t.includes('?redefinir='))")
        link_senha = re.search(r"https?://\S+\?redefinir=\S+", pg.evaluate("navigator.clipboard.readText()")).group(0)
        ok(link_senha.startswith(B + "/?redefinir="), "franqueadora copia um link de senha nova")
        rem = pg.locator("#da-lista [data-remover]"); rem.click(); rem.click()
        pg.wait_for_function("!document.querySelector('#da-lista [data-remover]')")
        pg.click("#d-acessos [data-fechar]")
        ok("Sem acesso ainda" in pg.locator(f'.un[data-id="{UA}"]').inner_text(), "remover acesso (com confirmação) sinaliza a unidade")
        pg.locator(f'.un[data-id="{UB}"] [data-a="convite"]').click()
        pg.click("#b-renovar"); pg.click("#b-renovar")
        pg.wait_for_function(f"document.getElementById('dc-codigo').textContent!=='{cod_b}'")
        novo_b = pg.inner_text("#dc-codigo")
        ok(novo_b != cod_b, "gerar novo código (com confirmação)")
        pg.click("#d-convite [data-fechar]")
        pg.click("#b-nova"); pg.fill("#u-nome", "Sou Coluna Joinville"); pg.click("#f-unidade button[type=submit]")
        pg.locator("#d-convite[open]").wait_for(); pg.click("#d-convite [data-fechar]")
        pg.locator(".un", has_text="Joinville").locator('[data-a="editar"]').click()
        pg.click("#b-excluir"); pg.click("#b-excluir")
        pg.wait_for_function("document.querySelectorAll('.un').length===2")
        ok(True, "excluir unidade (com confirmação)")
        pg.fill("#q", "curit")
        ok(pg.locator(".un").count() == 1, "busca filtra as unidades")
        pg.fill("#q", "")
        with pg.expect_download() as dl:
            pg.click("#b-csv")
        csv = Path(dl.value.path()).read_text(encoding="utf-8-sig").splitlines()
        ok(len(csv) == 3 and csv[0].startswith('"Unidade";"Cidade"'), "planilha exporta uma linha por unidade")
        pg.locator(f'.un[data-id="{UA}"] a', has_text="Abrir guia").click()
        pg.wait_for_url(f"**/guia?u={UA}"); pronto(pg)
        ok("Painel" in pg.inner_text("#user-nav") and pg.locator("#b-trocar").is_visible() and pg.inner_text("#k-items") == "3 de 130",
           "franqueadora abre o guia da unidade, com atalhos para o painel")
        pg.click("#b-sair"); pg.wait_for_url(B + "/")

        # ---------- link de senha nova + conta sem unidade ----------
        pg.goto(link_senha)
        ver(pg, "nova-senha")
        ok(pg.inner_text("#ns-email") == "ana@unidade.test", "link de senha mostra de quem é a conta")
        pg.fill("#n-senha", "senha-nova-ana"); pg.fill("#n-senha2", "outra"); pg.click("#f-senha button[type=submit]")
        ok("não são iguais" in pg.inner_text("#f-senha .msg"), "confirmação diferente é recusada")
        pg.fill("#n-senha2", "senha-nova-ana"); pg.click("#f-senha button[type=submit]")
        ver(pg, "codigo")
        ok(True, "senha nova salva; conta sem unidade pede o código")
        pg.fill("#k-codigo", novo_b.lower().replace("-", "")); pg.click("#f-codigo button[type=submit]")
        pg.wait_for_url(f"**/guia?u={UB}")
        ok(True, "com o código, a conta entra na outra unidade")
        pg.click("#b-sair"); pg.wait_for_url(B + "/")
        pg.goto(link_senha)
        ver(pg, "esqueci")
        ok("expirou" in pg.inner_text('[data-view="esqueci"]'), "link de senha usado não vale de novo")

        # ---------- franqueadora esqueceu a senha ----------
        pg.click('[data-view="esqueci"] summary')
        pg.fill("#k-mail", "adm@soucoluna.test"); pg.fill("#k-chave", CHAVE); pg.fill("#k-senha", "nova-senha-adm")
        pg.click("#f-chave button[type=submit]")
        pg.wait_for_url("**/painel")
        ok(True, "franqueadora troca a senha com a chave e entra")

        # ---------- franqueadora edita o catálogo ----------
        from PIL import Image
        foto = Path(srv.dados) / "foto-teste.png"; Image.new("RGB", (300, 200), (60, 154, 126)).save(foto)
        pg.click('.abas a[href="/catalogo"]'); pg.wait_for_url("**/catalogo"); pg.locator(".cat-row").first.wait_for()
        ok(pg.locator(".cat-row").count() == 130, "página do catálogo lista os 130 itens")
        tela(pg, "catalogo-computador")
        pg.fill("#q", "geladeira"); pg.locator('.cat-row[data-id="enxoval-geladeira"] [data-a="editar"]').click()
        pg.fill("#i-valor", "2.500,00"); pg.select_option("#i-forn", ""); pg.click("#f-item button[type=submit]")
        pg.wait_for_function("!document.getElementById('d-item').open")
        pg.wait_for_function("(document.querySelector('.cat-row[data-id=\"enxoval-geladeira\"]')||{}).innerText?.includes('Alterado')", timeout=10000)
        ok(True, "preço e fornecimento alterados ficam marcados como 'Alterado'")
        pg.fill("#q", "visita"); pg.locator('.cat-row[data-id="estoque-cartoes-de-visita"] [data-a="editar"]').click()
        pg.fill("#i-espec", "Verificar arte com a franqueadora"); pg.click("#f-item button[type=submit]")
        pg.wait_for_function("!document.getElementById('d-item').open")
        pg.wait_for_function("(document.querySelector('.cat-row[data-id=\"estoque-cartoes-de-visita\"]')||{}).innerText?.includes('Alterado')", timeout=10000)
        cv = next(i for i in pg.evaluate("fetch('/api/catalogo').then(r=>r.json())")["itens"] if i["id"] == "estoque-cartoes-de-visita")
        ok(cv["qtd"] == 1000 and cv["valor_unit"] == 0.2, f"editar só o texto não muda quantidade de 1.000 nem valor (ficou {cv['qtd']} × {cv['valor_unit']})")
        ok(pg.evaluate("[num('1.000'), num('1.900,50'), num('1.5'), num('0,20'), num('12.500')]") == [1000, 1900.5, 1.5, 0.2, 12500],
           "números digitados no padrão brasileiro (ponto de milhar, vírgula decimal)")
        pg.fill("#q", "coador"); pg.locator('.cat-row[data-id="enxoval-coador"] [data-a="editar"]').click()
        pg.set_input_files("#i-foto", str(foto)); pg.wait_for_selector("#foto-box img")
        pg.click("#f-item button[type=submit]"); pg.wait_for_function("!document.getElementById('d-item').open")
        pg.wait_for_selector('.cat-row[data-id="enxoval-coador"] .cat-foto img', timeout=10000)
        ok(True, "foto enviada aparece no catálogo")
        pg.fill("#q", ""); pg.click("#b-novo")
        pg.fill("#i-nome", "Bebedouro industrial"); pg.select_option("#i-etapa", "enxoval"); pg.fill("#i-cat", "Utensílios")
        pg.fill("#i-qtd", "2"); pg.fill("#i-valor", "300"); pg.select_option("#i-forn", "livre")
        pg.click("#f-item button[type=submit]"); pg.wait_for_function("!document.getElementById('d-item').open")
        pg.locator(".cat-row", has_text="Bebedouro industrial").wait_for(timeout=10000)
        ok(True, "item novo criado pelo painel")
        pg.fill("#q", "balde"); pg.locator('.cat-row[data-id="enxoval-balde"] [data-a="editar"]').click()
        pg.click("#b-remover"); pg.click("#b-remover"); pg.wait_for_function("!document.getElementById('d-item').open")
        pg.wait_for_function("!document.querySelector('.cat-row[data-id=\"enxoval-balde\"]')", timeout=10000)
        pg.fill("#q", ""); pg.select_option("#f-situ", "removido")
        ok(pg.locator('.cat-row[data-id="enxoval-balde"]').count() == 1, "item removido vai para o filtro 'Removidos'")
        pg.goto(B + f"/guia?u={UA}"); pronto(pg)
        ok(card(pg, "enxoval-geladeira").locator(".pv").inner_text() == "R$ 5.000" and card(pg, "enxoval-geladeira").locator(".bdg").count() == 0,
           "guia da unidade mostra o preço novo (com a quantidade dela) e sem o fornecimento")
        ok("/api/foto/enxoval-coador" in (card(pg, "enxoval-coador").locator(".media img").get_attribute("src") or ""), "guia mostra a foto enviada")
        ok(pg.locator('.card[data-id^="novo-bebedouro-industrial"]').count() == 1 and card(pg, "enxoval-balde").count() == 0,
           "guia mostra o item novo e esconde o removido")
        ok(pg.inner_text("#k-items") == "2 de 130", "andamento ignora o item removido e conta o novo")
        ok(not ctx.erros, "nenhum erro de JavaScript ou arquivo faltando: " + "; ".join(ctx.erros))
        ctx.close()

        # ---------- celular ----------
        ctx = novo_contexto(browser, viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        pg = ctx.new_page()
        pg.goto(B + "/"); ver(pg, "entrar")
        ok(sem_rolagem_lateral(pg), "celular: login sem rolagem lateral")
        tela(pg, "login-celular")
        entrar(pg, B, "adm@soucoluna.test", "nova-senha-adm")
        pg.wait_for_url("**/painel"); pg.locator(".un").first.wait_for()
        ok(sem_rolagem_lateral(pg), "celular: painel sem rolagem lateral")
        tela(pg, "painel-celular")
        pg.goto(B + f"/guia?u={UA}"); pronto(pg)
        ok(sem_rolagem_lateral(pg), "celular: guia sem rolagem lateral")
        tela(pg, "guia-celular")
        pg.click("#b-filtros"); pg.wait_for_timeout(300)
        ok(pg.locator("#filtros").is_visible() and pg.locator("#veu.on").is_visible(), "celular: filtros abrem numa gaveta")
        pg.click("#b-fechar-filtros")
        ok(not ctx.erros, "celular: nenhum erro de JavaScript")
        ctx.close()

        # ---------- versão offline ----------
        ctx = novo_contexto(browser, viewport={"width": 1366, "height": 900})
        pg = ctx.new_page()
        pg.goto((ROOT / "out/guia-compras-sou-coluna.html").as_uri())
        ok(pg.locator(".hero-tag").is_visible() and not pg.locator("#user-nav").is_visible() and not pg.locator("#b-trocar").is_visible(),
           "offline: sem login nem 'Trocar unidade'")
        ok(pg.locator("#b-backup").is_visible() and not pg.locator("#sync").is_visible(), "offline: backup visível, sem indicador de salvamento")
        card(pg, "enxoval-geladeira").locator(".toggle").click()
        pg.fill("#f-unit", "Unidade Teste")
        qi = card(pg, "enxoval-balde").locator(".qtd input"); qi.fill("3"); qi.press("Enter")
        ok(card(pg, "enxoval-balde").locator(".pv").inner_text() == "R$ 75", "offline: quantidade digitada recalcula o valor estimado")
        pg.reload()
        ok(card(pg, "enxoval-balde").locator(".qtd input").input_value() == "3", "offline: quantidade ajustada fica salva no navegador")
        card(pg, "enxoval-balde").locator('[data-q="reset"]').click()
        ok(card(pg, "enxoval-balde").locator(".qtd input").input_value() == "1" and card(pg, "enxoval-balde").locator(".pv").inner_text() == "R$ 25",
           "offline: 'voltar' devolve a quantidade sugerida")
        ok("done" in card(pg, "enxoval-geladeira").get_attribute("class") and pg.input_value("#f-unit") == "Unidade Teste",
           "offline: progresso continua salvo no navegador")
        ok(not ctx.erros, "offline: nenhum erro de JavaScript")
        ctx.close()
        browser.close()
    print(f"\nTODOS OS {passou} TESTES DO SITE PASSARAM")


if __name__ == "__main__":
    main()
