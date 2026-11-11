"""Testes de ponta a ponta do site (login, guia e painel) e da versão offline.

Roda num Chromium de verdade, com um Supabase de mentira (tests/site/fake-supabase.js),
então não precisa de conta no Supabase nem de internet.

Uso:
  python3 build.py
  python3 tests/test_site.py                    # CHROMIUM_PATH=/caminho/do/chromium se precisar
  python3 tests/test_site.py --telas pasta/     # também salva capturas de tela (celular e computador)
"""
import functools, http.server, json, os, re, sys, threading
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
FAKE = (ROOT / "tests/site/fake-supabase.js").read_text(encoding="utf-8")
TELAS = Path(sys.argv[sys.argv.index("--telas") + 1]) if "--telas" in sys.argv else None

ADM = "00000000-0000-4000-8000-0000000000ad"
UA = "aaaaaaaa-0000-4000-8000-000000000001"
UB = "bbbbbbbb-0000-4000-8000-000000000002"
SEED = {
    "users": [{"id": ADM, "email": "adm@soucoluna.test", "password": "senha-adm-123"}],
    "perfis": [{"user_id": ADM, "email": "adm@soucoluna.test", "nome": "Franqueadora", "franqueadora": True}],
    "unidades": [
        {"id": UA, "nome": "Sou Coluna Florianópolis", "cidade": "Florianópolis", "responsavel": None,
         "inauguracao": "2027-02-01", "codigo": "AAAAA-11111", "criado_em": "2026-11-01T10:00:00Z"},
        {"id": UB, "nome": "Sou Coluna Curitiba", "cidade": "Curitiba", "responsavel": "Bruno",
         "inauguracao": None, "codigo": "BBBBB-22222", "criado_em": "2026-11-02T10:00:00Z"},
    ],
    "membros": [], "compras": [], "log": [],
    "config": {"confirmarEmail": False, "falharEscrita": False},
}

passou = 0
def ok(cond, msg):
    global passou
    if not cond:
        raise AssertionError("FALHOU: " + msg)
    passou += 1
    print("ok:", msg)


class Quieto(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def servidor():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quieto, directory=str(SITE)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def novo_contexto(browser, base, configurado=True, seed=SEED, **kw):
    ctx = browser.new_context(permissions=["clipboard-read", "clipboard-write"], **kw)
    ctx.route(re.compile(r".*/vendor/supabase-[\d.]+\.js$"), lambda r: r.fulfill(body=FAKE, content_type="text/javascript"))
    if configurado:
        ctx.route(re.compile(r".*/config\.js$"), lambda r: r.fulfill(
            body='window.SC_CONFIG={url:"https://teste.supabase.co",anonKey:"chave-de-teste"};', content_type="text/javascript"))
    ctx.add_init_script(f"try{{if(!localStorage.getItem('__fakedb')) localStorage.setItem('__fakedb', {json.dumps(json.dumps(seed))});}}catch(e){{}}")
    erros = []
    ctx.on("page", lambda p: vigiar(p, erros))
    ctx.erros = erros
    return ctx


def vigiar(page, erros):
    page.on("pageerror", lambda e: erros.append(f"{page.url}: {e}"))
    page.on("response", lambda r: r.status >= 400 and "127.0.0.1" in r.url and erros.append(f"{r.status} {r.url}"))


def db(page):
    return page.evaluate("JSON.parse(localStorage.getItem('__fakedb'))")


def mexer_db(page, js):
    page.evaluate("(()=>{const d=JSON.parse(localStorage.getItem('__fakedb'));" + js + ";localStorage.setItem('__fakedb',JSON.stringify(d));})()")


def visivel(page, view):
    return page.locator(f'[data-view="{view}"]').is_visible()


def entrar(page, base, email, senha):
    page.goto(base + "/index.html")
    page.locator('[data-view="entrar"]').wait_for()
    page.fill("#e-mail", email); page.fill("#e-senha", senha)
    page.click("#f-entrar button[type=submit]")


def card(page, item):
    return page.locator(f'.card[data-id="{item}"]')


def esperar_salvo(page):
    page.wait_for_function("document.getElementById('sync').textContent==='Tudo salvo'", timeout=12000)


def sem_rolagem_lateral(page):
    return page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


def tela(page, nome):
    if TELAS:
        TELAS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(TELAS / f"{nome}.png"), full_page=False)


def main():
    srv, base = servidor()
    with sync_playwright() as p:
        exe = os.environ.get("CHROMIUM_PATH")
        browser = p.chromium.launch(**({"executable_path": exe} if exe else {}))

        # ---------- 1. site sem config.js preenchido ----------
        ctx = novo_contexto(browser, base, configurado=False)
        pg = ctx.new_page()
        pg.goto(base + "/index.html")
        ok(visivel(pg, "config"), "sem config.js: login avisa que o site não está configurado")
        pg.goto(base + "/guia.html")
        pg.locator(".falha").wait_for()
        ok("não configurado" in pg.inner_text(".falha"), "sem config.js: guia avisa em vez de quebrar")
        ctx.close()

        # ---------- 2. fluxo principal ----------
        ctx = novo_contexto(browser, base, viewport={"width": 1280, "height": 900})
        pg = ctx.new_page()

        entrar(pg, base, "adm@soucoluna.test", "errada")
        pg.locator("#f-entrar .msg").wait_for()
        ok(pg.inner_text("#f-entrar .msg") == "E-mail ou senha incorretos.", "senha errada mostra mensagem em português")

        entrar(pg, base, "adm@soucoluna.test", "senha-adm-123")
        pg.wait_for_url("**/painel.html")
        pg.locator(".row").first.wait_for()
        ok(pg.locator(".row").count() == 2, "franqueadora cai no painel e vê as 2 unidades")
        ok(pg.inner_text("#k-n") == "2", "KPI mostra 2 unidades")
        tela(pg, "painel-computador")

        pg.click("#b-nova")
        pg.fill("#u-nome", "Sou Coluna Joinville"); pg.fill("#u-cidade", "Joinville"); pg.fill("#u-inaug", "2027-05-10")
        pg.click("#f-unidade button[type=submit]")
        pg.locator("#d-convite[open]").wait_for()
        cod_j = pg.inner_text("#dc-codigo")
        ok(re.fullmatch(r"[0-9A-F]{5}-[0-9A-F]{5}", cod_j) is not None, "nova unidade abre o convite com o código")
        pg.click("#b-copiar-msg")
        msg = pg.evaluate("navigator.clipboard.readText()")
        ok(cod_j in msg and "/index.html?codigo=" + cod_j in msg, "mensagem de convite copiada com link e código")
        tela(pg, "painel-convite")
        pg.click("#d-convite [data-fechar]")
        ok(pg.locator(".row").count() == 3, "lista passa a ter 3 unidades")

        pg.click("[data-sair]")
        pg.wait_for_url("**/index.html")

        # franqueada entra pelo link de convite (código digitado de qualquer jeito)
        pg.goto(base + "/index.html?codigo=aaaaa11111")
        pg.locator('[data-view="criar"]').wait_for()
        ok(pg.input_value("#c-codigo") == "AAAAA-11111", "link de convite abre 'Criar conta' com o código formatado")
        pg.fill("#c-nome", "Ana"); pg.fill("#c-mail", "ana@unidade.test"); pg.fill("#c-senha", "123")
        pg.click("#f-criar button[type=submit]")
        ok("8 caracteres" in pg.inner_text("#f-criar .msg"), "senha curta é recusada")
        pg.fill("#c-senha", "senha-da-ana")
        pg.click("#f-criar button[type=submit]")
        pg.wait_for_url(f"**/guia.html?u={UA}")
        pg.wait_for_function("document.body.classList.contains('pronto')")
        ok(pg.input_value("#f-unit") == "Sou Coluna Florianópolis", "guia abre direto na unidade do convite")
        ok(pg.locator("#f-unit").get_attribute("readonly") is not None, "nome da unidade não é editável pelo franqueado")
        nav = pg.inner_text("#user-nav")
        ok("Sair" in nav and "Painel" not in nav, "franqueado vê 'Sair' e não vê o painel")
        ok(not pg.locator(".hero-tag").is_visible() and not pg.locator("#b-backup").is_visible(), "botões só da versão offline ficam escondidos")
        ok(pg.inner_text("#foot-h") == "Seu progresso fica salvo na sua conta", "rodapé explica que salva na conta")
        tela(pg, "guia-computador")

        prev_geladeira = pg.evaluate("BYID['enxoval-geladeira'].prev")
        card(pg, "enxoval-geladeira").locator(".toggle").click()
        esperar_salvo(pg)
        c = [x for x in db(pg)["compras"] if x["item_id"] == "enxoval-geladeira"]
        ok(len(c) == 1 and c[0]["comprado"] and c[0]["valor_pago"] == prev_geladeira and c[0]["unidade_id"] == UA,
           "marcar comprado grava no banco com o valor previsto")
        inp = card(pg, "enxoval-balde").locator(".money input")
        inp.fill("1.234,56"); inp.press("Enter")
        esperar_salvo(pg)
        c = [x for x in db(pg)["compras"] if x["item_id"] == "enxoval-balde"]
        ok(c and c[0]["valor_pago"] == 1234.56 and c[0]["comprado"], "valor pago digitado grava no banco e marca como comprado")
        pg.fill("#f-resp", "Ana Souza")
        pg.wait_for_function(f"JSON.parse(localStorage.getItem('__fakedb')).unidades.find(u=>u.id==='{UA}').responsavel==='Ana Souza'", timeout=5000)
        ok(True, "responsável digitado no guia vai para o banco")

        pg.reload(); pg.wait_for_function("document.body.classList.contains('pronto')")
        ok("done" in card(pg, "enxoval-geladeira").get_attribute("class"), "depois de recarregar, o item continua comprado")
        ok(card(pg, "enxoval-balde").locator(".money input").input_value() == "1.234,56", "depois de recarregar, o valor pago continua")
        ok(pg.inner_text("#k-items") == "2 de 130", "andamento recalculado a partir do banco")
        ok(pg.input_value("#f-resp") == "Ana Souza", "responsável carregado do banco")

        pg.goto(base + f"/guia.html?u={UB}")
        pg.wait_for_url("**/index.html?escolher=1")
        pg.locator('[data-view="escolher"]').wait_for()
        ok(pg.locator("#lista a").count() == 1 and "Florianópolis" in pg.inner_text("#lista"), "franqueado não abre o guia de outra unidade")

        # queda de conexão ao salvar
        pg.goto(base + f"/guia.html?u={UA}"); pg.wait_for_function("document.body.classList.contains('pronto')")
        mexer_db(pg, "d.config.falharEscrita=true")
        card(pg, "enxoval-calculadora").locator(".toggle").click()
        pg.wait_for_function("document.getElementById('sync').textContent.startsWith('Sem conexão')", timeout=5000)
        ok(True, "sem conexão: o guia avisa que não salvou")
        mexer_db(pg, "d.config.falharEscrita=false")
        esperar_salvo(pg)
        ok(any(x["item_id"] == "enxoval-calculadora" for x in db(pg)["compras"]), "conexão volta: o guia reenvia sozinho")
        pg.click("#b-sair"); pg.wait_for_url("**/index.html")

        # cadastro com código errado / e-mail repetido
        pg.locator('[data-view="entrar"]').wait_for()
        pg.click('[data-view="entrar"] [data-ir="criar"]')
        pg.fill("#c-codigo", "00000-00000"); pg.fill("#c-nome", "X"); pg.fill("#c-mail", "x@x.test"); pg.fill("#c-senha", "12345678")
        pg.click("#f-criar button[type=submit]")
        pg.wait_for_function("document.querySelector('#f-criar .msg').textContent.includes('Código não encontrado')")
        ok(True, "código inexistente é recusado antes de criar a conta")
        pg.fill("#c-codigo", "BBBBB-22222"); pg.fill("#c-mail", "ana@unidade.test")
        pg.click("#f-criar button[type=submit]")
        pg.wait_for_function("document.querySelector('#f-criar .msg').textContent.includes('já tem conta')")
        ok(True, "e-mail já cadastrado é avisado")

        # franqueadora acompanha
        entrar(pg, base, "adm@soucoluna.test", "senha-adm-123")
        pg.wait_for_url("**/painel.html"); pg.locator(".row").first.wait_for()
        row_a = pg.locator(f'.row[data-id="{UA}"]')
        ok("3 de 130" in row_a.inner_text() and "Ana Souza" in row_a.inner_text(), "painel mostra o andamento e o responsável da unidade")
        ok("1 acesso" in row_a.inner_text(), "painel mostra quantas pessoas acessam")
        row_a.locator('[data-a="acessos"]').click()
        ok("ana@unidade.test" in pg.inner_text("#da-lista"), "janela de acessos lista o e-mail da franqueada")
        b = pg.locator("#da-lista [data-remover]")
        b.click(); b.click()
        pg.wait_for_function("!document.querySelector('#da-lista [data-remover]')")
        ok(not [m for m in db(pg)["membros"] if m["unidade_id"] == UA], "franqueadora remove o acesso (com confirmação)")
        pg.click("#d-acessos [data-fechar]")
        ok("sem acesso ainda" in pg.locator(f'.row[data-id="{UA}"]').inner_text(), "unidade sem acesso fica sinalizada")

        pg.locator(f'.row[data-id="{UB}"] [data-a="convite"]').click()
        antigo = pg.inner_text("#dc-codigo")
        pg.click("#b-renovar"); pg.click("#b-renovar")
        pg.wait_for_function(f"document.getElementById('dc-codigo').textContent!=='{antigo}'")
        novo_b = pg.inner_text("#dc-codigo")
        ok(next(u for u in db(pg)["unidades"] if u["id"] == UB)["codigo"] == novo_b, "gerar novo código troca o código no banco")
        pg.click("#d-convite [data-fechar]")

        joinville = pg.locator(".row", has_text="Joinville")
        joinville.locator('[data-a="editar"]').click()
        pg.click("#b-excluir"); pg.click("#b-excluir")
        pg.wait_for_function("document.querySelectorAll('.row').length===2")
        ok(True, "excluir unidade (com confirmação) tira da lista")

        pg.fill("#q", "curit")
        ok(pg.locator(".row").count() == 1, "busca filtra as unidades")
        pg.fill("#q", "")
        with pg.expect_download() as dl:
            pg.click("#b-csv")
        csv = Path(dl.value.path()).read_text(encoding="utf-8-sig").splitlines()
        ok(len(csv) == 3 and csv[0].startswith('"Unidade";"Cidade"') and "Florianópolis" in "".join(csv), "planilha exporta uma linha por unidade")

        pg.locator(f'.row[data-id="{UA}"] a', has_text="Abrir guia").click()
        pg.wait_for_url(f"**/guia.html?u={UA}"); pg.wait_for_function("document.body.classList.contains('pronto')")
        ok("Painel" in pg.inner_text("#user-nav") and pg.inner_text("#k-items") == "3 de 130", "franqueadora abre o guia da unidade e volta pelo painel")
        pg.click("#b-sair"); pg.wait_for_url("**/index.html")

        # esqueci a senha + conta sem unidade + entrar com código
        pg.locator('[data-view="entrar"]').wait_for()
        pg.click('[data-ir="esqueci"]'); pg.fill("#r-mail", "ana@unidade.test"); pg.click("#f-esqueci button[type=submit]")
        pg.locator('[data-view="enviado"]').wait_for()
        ok(db(pg)["log"][-1]["redirect"].endswith("/index.html?nova-senha=1"), "esqueci a senha envia link que volta para a tela de nova senha")
        entrar(pg, base, "ana@unidade.test", "senha-da-ana")
        pg.locator('[data-view="codigo"]').wait_for()
        ok(True, "conta sem unidade pede o código")
        pg.goto(base + "/index.html?nova-senha=1")
        pg.locator('[data-view="nova-senha"]').wait_for()
        pg.fill("#n-senha", "nova-senha-ana"); pg.fill("#n-senha2", "outra-coisa"); pg.click("#f-senha button[type=submit]")
        ok("não são iguais" in pg.inner_text("#f-senha .msg"), "nova senha: confirmação diferente é recusada")
        pg.fill("#n-senha2", "nova-senha-ana"); pg.click("#f-senha button[type=submit]")
        pg.locator('[data-view="codigo"]').wait_for()
        ok(next(u for u in db(pg)["users"] if u["email"] == "ana@unidade.test")["password"] == "nova-senha-ana", "nova senha salva")
        pg.fill("#k-codigo", novo_b.lower().replace("-", ""))
        pg.click("#f-codigo button[type=submit]")
        pg.wait_for_url(f"**/guia.html?u={UB}")
        ok(True, "com o código, a conta entra na unidade e abre o guia")
        ok(not ctx.erros, "nenhum erro de JavaScript ou arquivo faltando: " + "; ".join(ctx.erros))
        ctx.close()

        # ---------- 3. confirmação de e-mail ligada ----------
        seed = json.loads(json.dumps(SEED)); seed["config"]["confirmarEmail"] = True
        ctx = novo_contexto(browser, base, seed=seed)
        pg = ctx.new_page()
        pg.goto(base + "/index.html?codigo=AAAAA-11111")
        pg.locator('[data-view="criar"]').wait_for()
        pg.fill("#c-nome", "Carla"); pg.fill("#c-mail", "carla@unidade.test"); pg.fill("#c-senha", "senha-carla")
        pg.click("#f-criar button[type=submit]")
        pg.locator('[data-view="confirme"]').wait_for()
        ok("carla@unidade.test" in pg.inner_text("#cf-email"), "com confirmação ligada, pede para abrir o e-mail")
        entrar(pg, base, "carla@unidade.test", "senha-carla")
        pg.wait_for_function("document.querySelector('#f-entrar .msg').textContent.includes('Confirme seu e-mail')")
        ok(True, "entrar antes de confirmar mostra o aviso certo")
        pg.goto("about:blank")   # o link do e-mail abre a página do zero
        pg.goto(base + "/index.html#error=access_denied&error_code=otp_expired")
        ok("expirou" in pg.inner_text("#f-entrar .msg"), "link de e-mail vencido mostra aviso amigável")
        ctx.close()

        # ---------- 4. celular ----------
        ctx = novo_contexto(browser, base, viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        pg = ctx.new_page()
        pg.goto(base + "/index.html"); pg.locator('[data-view="entrar"]').wait_for()
        ok(sem_rolagem_lateral(pg), "celular: login sem rolagem lateral")
        tela(pg, "login-celular")
        entrar(pg, base, "adm@soucoluna.test", "senha-adm-123")
        pg.wait_for_url("**/painel.html"); pg.locator(".row").first.wait_for()
        ok(sem_rolagem_lateral(pg), "celular: painel sem rolagem lateral")
        tela(pg, "painel-celular")
        pg.goto(base + f"/guia.html?u={UA}"); pg.wait_for_function("document.body.classList.contains('pronto')")
        ok(sem_rolagem_lateral(pg), "celular: guia sem rolagem lateral")
        tela(pg, "guia-celular")
        ok(not ctx.erros, "celular: nenhum erro de JavaScript")
        ctx.close()

        # ---------- 5. versão offline continua igual ----------
        ctx = browser.new_context()
        pg = ctx.new_page()
        erros = []; vigiar(pg, erros)
        pg.goto((ROOT / "out/guia-compras-sou-coluna.html").as_uri())
        ok(pg.locator(".hero-tag").is_visible() and not pg.locator("#user-nav").is_visible(), "offline: cabeçalho original, sem login")
        ok(pg.locator("#b-backup").is_visible() and not pg.locator("#sync").is_visible(), "offline: backup visível, sem indicador de salvamento")
        card(pg, "enxoval-geladeira").locator(".toggle").click()
        pg.fill("#f-unit", "Unidade Teste")
        pg.reload()
        ok("done" in card(pg, "enxoval-geladeira").get_attribute("class") and pg.input_value("#f-unit") == "Unidade Teste",
           "offline: progresso continua salvo no navegador")
        ok(not erros, "offline: nenhum erro de JavaScript")
        ctx.close()
        browser.close()
    srv.shutdown()
    print(f"\nTODOS OS {passou} TESTES DO SITE PASSARAM")


if __name__ == "__main__":
    main()
