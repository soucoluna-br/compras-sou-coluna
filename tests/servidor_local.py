"""Sobe o site localmente (wrangler pages dev + banco D1 local, zerado) para os testes.

Precisa do wrangler instalado em ferramentas/:  cd ferramentas && npm ci
GUIA_TMP=pasta (opcional) define onde ficam os dados temporários do teste.
"""
import json, os, shutil, signal, socket, subprocess, tempfile, time, urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WRANGLER = ROOT / "ferramentas/node_modules/.bin/wrangler"
CHAVE = "chave-da-franqueadora-de-teste"


def porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Servidor:
    def __enter__(self):
        if not WRANGLER.exists():
            raise SystemExit("wrangler não encontrado. Rode: cd ferramentas && npm ci")
        self.dados = tempfile.mkdtemp(prefix="guia-d1-", dir=os.environ.get("GUIA_TMP"))
        self.porta = porta_livre()
        self.base = f"http://127.0.0.1:{self.porta}"
        self.log = open(Path(self.dados) / "wrangler.log", "w")
        self.proc = subprocess.Popen(
            [str(WRANGLER), "pages", "dev", "site", "--ip", "127.0.0.1", "--port", str(self.porta),
             "--d1", "DB=banco-local", "--binding", f"CODIGO_FRANQUEADORA={CHAVE}",
             "--compatibility-date", "2026-10-01", "--persist-to", self.dados],
            cwd=ROOT, stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)
        for _ in range(120):
            try:
                urllib.request.build_opener(urllib.request.ProxyHandler({})).open(self.base + "/", timeout=2)
                return self
            except Exception:
                if self.proc.poll() is not None:
                    raise SystemExit("wrangler parou:\n" + (Path(self.dados) / "wrangler.log").read_text())
                time.sleep(0.5)
        raise SystemExit("wrangler não subiu a tempo")

    def __exit__(self, *a):
        # encerra o wrangler e o workerd que ele abre (mesmo grupo de processos)
        try:
            os.killpg(self.proc.pid, signal.SIGTERM)
            self.proc.wait(10)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.log.close()
        shutil.rmtree(self.dados, ignore_errors=True)

    def sql(self, comando):
        """Consulta direto no banco local (para conferir o que foi gravado)."""
        out = subprocess.run(
            [str(WRANGLER), "d1", "execute", "DB", "--local", "--persist-to", self.dados, "--json", "--command", comando],
            cwd=ROOT / "tests/banco-local", capture_output=True, text=True, check=True).stdout
        return json.loads(out)[0]["results"]

    def exportar(self, saida, tabelas):
        """Roda o mesmo "wrangler d1 export" do backup automático, no banco local."""
        pasta = Path(tempfile.mkdtemp(prefix="guia-export-", dir=os.environ.get("GUIA_TMP")))
        shutil.copy(ROOT / "tests/banco-local/wrangler.toml", pasta)
        (pasta / ".wrangler").mkdir()
        (pasta / ".wrangler/state").symlink_to(self.dados)   # o export local não aceita --persist-to
        cmd = [str(WRANGLER), "d1", "export", "DB", "--local", "--output", str(saida)]
        for t in tabelas:
            cmd += ["--table", t]
        subprocess.run(cmd, cwd=pasta, check=True, capture_output=True)
        shutil.rmtree(pasta, ignore_errors=True)


class Cliente:
    """Um "navegador" simples com cookies, para chamar a API como um usuário."""

    def __init__(self, base, origem=True):
        self.base, self.jar, self.origem = base, CookieJar(), origem
        self.op = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(self.jar))

    def req(self, metodo, caminho, dados=None, headers=None):
        h = {"Accept": "application/json"}
        corpo = None
        if dados is not None:
            corpo = json.dumps(dados).encode()
            h["Content-Type"] = "application/json"
            if self.origem:
                h["Origin"] = self.base
        h.update(headers or {})
        r = urllib.request.Request(self.base + "/api/" + caminho, data=corpo, headers=h, method=metodo)
        try:
            with self.op.open(r) as resp:
                return resp.status, json.loads(resp.read() or b"null"), resp.headers
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null"), e.headers

    def get(self, caminho):
        return self.req("GET", caminho)

    def post(self, caminho, dados=None, headers=None):
        return self.req("POST", caminho, {} if dados is None else dados, headers)
