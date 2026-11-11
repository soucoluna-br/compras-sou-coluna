/* Sou Coluna · Guia de Compras — API do site (Cloudflare Pages Functions + banco D1).
 *
 * Tudo que o site lê ou grava passa por aqui, em /api/... Quem pode ver o quê:
 *   franqueado   só as unidades de que é membro (entrou com o código da unidade) e as compras delas
 *   franqueadora tudo (conta criada com a chave CODIGO_FRANQUEADORA, configurada como segredo na Cloudflare)
 *
 * Configuração na Cloudflare (Pages → Settings):
 *   Bindings:  D1 database com o nome DB
 *   Secrets:   CODIGO_FRANQUEADORA (mínimo 12 caracteres) — vira a "chave" para criar contas da franqueadora
 *
 * As tabelas são criadas sozinhas no primeiro acesso (CREATE TABLE IF NOT EXISTS).
 */

// ---------- banco ----------
// Uma instrução por item (o D1 executa em lote). Senhas, sessões e links ficam em tabelas separadas
// para o backup automático (GitHub) poder deixá-las de fora.
const SCHEMA = [
  `CREATE TABLE IF NOT EXISTS usuarios (id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, nome TEXT, franqueadora INTEGER NOT NULL DEFAULT 0, criado_em TEXT NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS unidades (id TEXT PRIMARY KEY, nome TEXT NOT NULL, cidade TEXT, responsavel TEXT, inauguracao TEXT, codigo TEXT NOT NULL UNIQUE, criado_em TEXT NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS membros (user_id TEXT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE, unidade_id TEXT NOT NULL REFERENCES unidades(id) ON DELETE CASCADE, criado_em TEXT NOT NULL, PRIMARY KEY (user_id, unidade_id))`,
  `CREATE INDEX IF NOT EXISTS membros_unidade ON membros(unidade_id)`,
  `CREATE TABLE IF NOT EXISTS compras (unidade_id TEXT NOT NULL REFERENCES unidades(id) ON DELETE CASCADE, item_id TEXT NOT NULL, comprado INTEGER NOT NULL DEFAULT 0, valor_centavos INTEGER, quantidade REAL, atualizado_em TEXT NOT NULL, atualizado_por TEXT, PRIMARY KEY (unidade_id, item_id))`,
  `CREATE TABLE IF NOT EXISTS senhas (user_id TEXT PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE, hash TEXT NOT NULL, atualizado_em TEXT NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS sessoes (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE, expira_em TEXT NOT NULL)`,
  `CREATE INDEX IF NOT EXISTS sessoes_usuario ON sessoes(user_id)`,
  `CREATE TABLE IF NOT EXISTS links_senha (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE, expira_em TEXT NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS tentativas (chave TEXT PRIMARY KEY, n INTEGER NOT NULL, ate INTEGER NOT NULL)`,
  // catálogo editável pela franqueadora: só os itens alterados, criados ou removidos (o resto vem de data.py)
  `CREATE TABLE IF NOT EXISTS catalogo (id TEXT PRIMARY KEY, dados TEXT NOT NULL, removido INTEGER NOT NULL DEFAULT 0, atualizado_em TEXT NOT NULL, atualizado_por TEXT)`,
  `CREATE TABLE IF NOT EXISTS catalogo_fotos (item_id TEXT PRIMARY KEY, base64 TEXT, tipo TEXT, ajuste TEXT NOT NULL DEFAULT 'contain', removida INTEGER NOT NULL DEFAULT 0, versao INTEGER NOT NULL, atualizado_em TEXT NOT NULL)`,
];
let schemaPronto = false;

// ---------- parâmetros ----------
const ITERACOES = 25000;  // PBKDF2-SHA256: ~6 ms, cabe nos 10 ms de CPU do plano gratuito. Fica gravado em cada hash;
                         // se aumentar (plano pago), as senhas são refeitas sozinhas no próximo login.
const SESSAO_DIAS = 30;
const LINK_SENHA_DIAS = 7;
const COOKIE = "sc";

// ---------- utilidades ----------
class Erro extends Error {
  constructor(status, codigo) { super(codigo); this.status = status; this.codigo = codigo; }
}
const agoraIso = () => new Date().toISOString();
const emDias = (d) => new Date(Date.now() + d * 864e5).toISOString();
const enc = new TextEncoder();
const b64u = (bytes) => btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const deb64u = (s) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (s.length % 4)) % 4)), (c) => c.charCodeAt(0));
const aleatorio = (n = 32) => b64u(crypto.getRandomValues(new Uint8Array(n)));
const hex = (n) => Array.from(crypto.getRandomValues(new Uint8Array(n)), (b) => (b % 16).toString(16)).join("").toUpperCase();
const novoCodigo = () => hex(5) + "-" + hex(5);
const uuid = () => crypto.randomUUID();
async function sha256(s) { return b64u(await crypto.subtle.digest("SHA-256", enc.encode(s))); }
function iguais(a, b) {
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a[i] ^ b[i];
  return d === 0;
}
const iguaisTexto = (a, b) => iguais(enc.encode(String(a)), enc.encode(String(b)));
// chave da franqueadora: ignora maiúsculas e pontuação/espaços nas pontas (ex.: o ponto final de uma frase copiada)
const normChave = (s) => String(s || "").trim().replace(/^[^0-9A-Za-z]+|[^0-9A-Za-z]+$/g, "").toLowerCase();
const chaveConfere = (digitada, chave) => !!chave && chave.length >= 12 && iguaisTexto(normChave(digitada), normChave(chave));

function json(obj, status = 200, extra = {}) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", ...extra },
  });
}

// ---------- senhas ----------
async function pbkdf2(senha, sal, iter) {
  const chave = await crypto.subtle.importKey("raw", enc.encode(senha), "PBKDF2", false, ["deriveBits"]);
  return new Uint8Array(await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt: sal, iterations: iter }, chave, 256));
}
async function gerarHash(senha) {
  const sal = crypto.getRandomValues(new Uint8Array(16));
  return `pbkdf2$${ITERACOES}$${b64u(sal)}$${b64u(await pbkdf2(senha, sal, ITERACOES))}`;
}
async function conferirSenha(senha, guardado) {
  const [alg, it, sal, h] = String(guardado || "").split("$");
  if (alg !== "pbkdf2" || !sal || !h) { await pbkdf2(senha, new Uint8Array(16), ITERACOES); return { ok: false }; }
  const ok = iguais(await pbkdf2(senha, deb64u(sal), Number(it)), deb64u(h));
  return { ok, refazer: ok && Number(it) < ITERACOES };
}

// ---------- validação de entrada ----------
function texto(v, max, obrigatorio) {
  const s = v == null ? "" : String(v).trim();
  if (obrigatorio && !s) throw new Erro(400, "dados");
  if (s.length > max) throw new Erro(400, "dados");
  return s || null;
}
function email(v) {
  const s = String(v || "").trim().toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s) || s.length > 200) throw new Erro(400, "email_invalido");
  return s;
}
function senhaNova(v) {
  const s = String(v || "");
  if (s.length < 8) throw new Erro(400, "senha_curta");
  if (s.length > 200) throw new Erro(400, "dados");
  return s;
}
function data(v) {
  if (v == null || v === "") return null;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(v))) throw new Erro(400, "dados");
  return String(v);
}
// aceita "7f3a9c0d41", "7F3A9 C0D41" etc. → "7F3A9-C0D41"
function normCodigo(v) {
  const c = String(v || "").toUpperCase().replace(/[^0-9A-Z]/g, "");
  return c.length === 10 ? c.slice(0, 5) + "-" + c.slice(5) : c;
}

// ---------- proteção contra tentativas em massa ----------
async function limitar(env, chave, max, segundos) {
  const agora = Math.floor(Date.now() / 1000);
  const r = await env.DB.prepare(
    `INSERT INTO tentativas (chave, n, ate) VALUES (?1, 1, ?2)
     ON CONFLICT(chave) DO UPDATE SET
       n = CASE WHEN tentativas.ate < ?3 THEN 1 ELSE tentativas.n + 1 END,
       ate = CASE WHEN tentativas.ate < ?3 THEN ?2 ELSE tentativas.ate END
     RETURNING n`).bind(chave, agora + segundos, agora).first();
  if (r.n > max) throw new Erro(429, "limite");
}

// ---------- sessão ----------
function lerCookie(request, nome) {
  const m = (request.headers.get("Cookie") || "").match(new RegExp("(?:^|;\\s*)" + nome + "=([^;]+)"));
  return m ? m[1] : null;
}
function cookieSessao(url, token, maxAge) {
  return `${COOKIE}=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${maxAge}` + (url.protocol === "https:" ? "; Secure" : "");
}
async function criarSessao(env, url, userId) {
  const token = aleatorio(32);
  await env.DB.prepare("INSERT INTO sessoes (token_hash, user_id, expira_em) VALUES (?1, ?2, ?3)")
    .bind(await sha256(token), userId, emDias(SESSAO_DIAS)).run();
  return cookieSessao(url, token, SESSAO_DIAS * 86400);
}
async function usuarioDaSessao(env, request) {
  const token = lerCookie(request, COOKIE);
  if (!token) return null;
  const th = await sha256(token);
  const u = await env.DB.prepare(
    `SELECT u.id, u.email, u.nome, u.franqueadora, s.expira_em, s.token_hash FROM sessoes s JOIN usuarios u ON u.id = s.user_id
     WHERE s.token_hash = ?1 AND s.expira_em > ?2`).bind(th, agoraIso()).first();
  if (!u) return null;
  // sessão em uso é renovada quando passa da metade da validade
  if (u.expira_em < emDias(SESSAO_DIAS / 2)) {
    await env.DB.prepare("UPDATE sessoes SET expira_em = ?1 WHERE token_hash = ?2").bind(emDias(SESSAO_DIAS), th).run();
  }
  return { id: u.id, email: u.email, nome: u.nome, franqueadora: !!u.franqueadora, tokenHash: th };
}
async function exigirSessao(c) {
  const u = await usuarioDaSessao(c.env, c.request);
  if (!u) throw new Erro(401, "login");
  return u;
}
function exigirFranqueadora(u) {
  if (!u.franqueadora) throw new Erro(403, "sem_acesso");
}
async function exigirUnidade(c, u, unidadeId) {
  const un = await c.env.DB.prepare("SELECT id, nome, cidade, responsavel, inauguracao, codigo FROM unidades WHERE id = ?1").bind(unidadeId).first();
  if (u.franqueadora) { if (!un) throw new Erro(404, "nao_encontrado"); return un; }
  const m = un && await c.env.DB.prepare("SELECT 1 FROM membros WHERE user_id = ?1 AND unidade_id = ?2").bind(u.id, unidadeId).first();
  if (!m) throw new Erro(403, "sem_acesso");
  delete un.codigo;
  return un;
}
async function unidadesDoUsuario(env, u) {
  const q = u.franqueadora
    ? env.DB.prepare("SELECT id, nome, cidade FROM unidades ORDER BY nome COLLATE NOCASE")
    : env.DB.prepare(`SELECT un.id, un.nome, un.cidade FROM unidades un JOIN membros m ON m.unidade_id = un.id
                      WHERE m.user_id = ?1 ORDER BY un.nome COLLATE NOCASE`).bind(u.id);
  return (await q.all()).results;
}
async function definirSenha(env, userId, senha) {
  await env.DB.batch([
    env.DB.prepare(`INSERT INTO senhas (user_id, hash, atualizado_em) VALUES (?1, ?2, ?3)
                    ON CONFLICT(user_id) DO UPDATE SET hash = excluded.hash, atualizado_em = excluded.atualizado_em`)
      .bind(userId, await gerarHash(senha), agoraIso()),
    env.DB.prepare("DELETE FROM sessoes WHERE user_id = ?1").bind(userId),      // sai de todos os aparelhos
    env.DB.prepare("DELETE FROM links_senha WHERE user_id = ?1").bind(userId),
  ]);
}
const ip = (request) => request.headers.get("CF-Connecting-IP") || "local";

// ---------- rotas ----------
const ROTAS = [];
const rota = (metodo, padrao, fn) => ROTAS.push({ metodo, re: new RegExp("^" + padrao.replace(/:(\w+)/g, "(?<$1>[^/]+)") + "$"), fn });

// Quem sou eu + unidades que posso abrir (401 se não estiver logado)
rota("GET", "/eu", async (c) => {
  const u = await exigirSessao(c);
  return json({ email: u.email, nome: u.nome, franqueadora: u.franqueadora, unidades: await unidadesDoUsuario(c.env, u) });
});

rota("POST", "/entrar", async (c) => {
  const e = email(c.body.email), senha = String(c.body.senha || "");
  await limitar(c.env, "entrar-ip:" + ip(c.request), 30, 900);
  await limitar(c.env, "entrar:" + e, 10, 900);
  const u = await c.env.DB.prepare("SELECT u.id, s.hash FROM usuarios u LEFT JOIN senhas s ON s.user_id = u.id WHERE u.email = ?1").bind(e).first();
  const r = await conferirSenha(senha, u && u.hash);
  if (!u || !r.ok) throw new Erro(401, "credenciais");
  if (r.refazer) await c.env.DB.prepare("UPDATE senhas SET hash = ?1 WHERE user_id = ?2").bind(await gerarHash(senha), u.id).run();
  return json({ ok: true }, 200, { "Set-Cookie": await criarSessao(c.env, c.url, u.id) });
});

// Criar conta: com o código de uma unidade (franqueado) ou com a chave da franqueadora
rota("POST", "/cadastrar", async (c) => {
  const bruto = String(c.body.codigo || "").trim();
  const nome = texto(c.body.nome, 120, true), e = email(c.body.email), senha = senhaNova(c.body.senha);
  await limitar(c.env, "cadastro-ip:" + ip(c.request), 15, 3600);
  const chave = c.env.CODIGO_FRANQUEADORA;
  const ehFranqueadora = chaveConfere(bruto, chave);
  let unidade = null;
  if (!ehFranqueadora) {
    unidade = await c.env.DB.prepare("SELECT id FROM unidades WHERE codigo = ?1").bind(normCodigo(bruto)).first();
    if (!unidade) throw new Erro(400, "codigo_invalido");
  }
  if (await c.env.DB.prepare("SELECT 1 FROM usuarios WHERE email = ?1").bind(e).first()) throw new Erro(409, "email_existe");
  const id = uuid(), agora = agoraIso();
  const ops = [
    c.env.DB.prepare("INSERT INTO usuarios (id, email, nome, franqueadora, criado_em) VALUES (?1, ?2, ?3, ?4, ?5)").bind(id, e, nome, ehFranqueadora ? 1 : 0, agora),
    c.env.DB.prepare("INSERT INTO senhas (user_id, hash, atualizado_em) VALUES (?1, ?2, ?3)").bind(id, await gerarHash(senha), agora),
  ];
  if (unidade) ops.push(c.env.DB.prepare("INSERT INTO membros (user_id, unidade_id, criado_em) VALUES (?1, ?2, ?3)").bind(id, unidade.id, agora));
  await c.env.DB.batch(ops);
  return json({ ok: true }, 201, { "Set-Cookie": await criarSessao(c.env, c.url, id) });
});

// Já logado: entrar em (mais) uma unidade com o código
rota("POST", "/entrar-com-codigo", async (c) => {
  const u = await exigirSessao(c);
  await limitar(c.env, "codigo-ip:" + ip(c.request), 30, 3600);
  const un = await c.env.DB.prepare("SELECT id FROM unidades WHERE codigo = ?1").bind(normCodigo(c.body.codigo)).first();
  if (!un) throw new Erro(400, "codigo_invalido");
  await c.env.DB.prepare("INSERT INTO membros (user_id, unidade_id, criado_em) VALUES (?1, ?2, ?3) ON CONFLICT DO NOTHING").bind(u.id, un.id, agoraIso()).run();
  return json({ unidade_id: un.id });
});

rota("POST", "/sair", async (c) => {
  const token = lerCookie(c.request, COOKIE);
  if (token) await c.env.DB.prepare("DELETE FROM sessoes WHERE token_hash = ?1").bind(await sha256(token)).run();
  return json({ ok: true }, 200, { "Set-Cookie": cookieSessao(c.url, "", 0) });
});

// Link de senha nova (gerado pela franqueadora no painel)
async function linkValido(env, token) {
  const r = await env.DB.prepare(`SELECT l.user_id, u.email FROM links_senha l JOIN usuarios u ON u.id = l.user_id
                                  WHERE l.token_hash = ?1 AND l.expira_em > ?2`).bind(await sha256(String(token || "")), agoraIso()).first();
  if (!r) throw new Erro(400, "link_invalido");
  return r;
}
rota("GET", "/redefinir", async (c) => {
  await limitar(c.env, "link-ip:" + ip(c.request), 30, 3600);
  const r = await linkValido(c.env, c.url.searchParams.get("token"));
  return json({ email: r.email });
});
rota("POST", "/redefinir", async (c) => {
  const senha = senhaNova(c.body.senha);
  await limitar(c.env, "link-ip:" + ip(c.request), 30, 3600);
  const r = await linkValido(c.env, c.body.token);
  await definirSenha(c.env, r.user_id, senha);
  return json({ ok: true }, 200, { "Set-Cookie": await criarSessao(c.env, c.url, r.user_id) });
});
// Franqueadora que esqueceu a senha: usa a chave da franqueadora
rota("POST", "/redefinir-com-chave", async (c) => {
  const e = email(c.body.email), senha = senhaNova(c.body.senha);
  await limitar(c.env, "chave-ip:" + ip(c.request), 5, 3600);
  const chave = c.env.CODIGO_FRANQUEADORA;
  const u = await c.env.DB.prepare("SELECT id FROM usuarios WHERE email = ?1 AND franqueadora = 1").bind(e).first();
  if (!chaveConfere(c.body.chave, chave) || !u) throw new Erro(401, "chave_invalida");
  await definirSenha(c.env, u.id, senha);
  return json({ ok: true }, 200, { "Set-Cookie": await criarSessao(c.env, c.url, u.id) });
});

// ---------- guia de uma unidade ----------
rota("GET", "/unidades/:id/compras", async (c) => {
  const u = await exigirSessao(c);
  const un = await exigirUnidade(c, u, c.p.id);
  const itens = (await c.env.DB.prepare("SELECT item_id, comprado, valor_centavos, quantidade FROM compras WHERE unidade_id = ?1").bind(un.id).all()).results;
  return json({
    unidade: { id: un.id, nome: un.nome, cidade: un.cidade, responsavel: un.responsavel, inauguracao: un.inauguracao },
    itens: itens.map((r) => ({ item_id: r.item_id, comprado: !!r.comprado, valor_pago: r.valor_centavos == null ? null : r.valor_centavos / 100,
      quantidade: r.quantidade })),
  });
});
rota("POST", "/unidades/:id/compras", async (c) => {
  const u = await exigirSessao(c);
  const un = await exigirUnidade(c, u, c.p.id);
  const linhas = c.body.linhas;
  if (!Array.isArray(linhas) || !linhas.length || linhas.length > 200) throw new Erro(400, "dados");
  const agora = agoraIso();
  const st = c.env.DB.prepare(
    `INSERT INTO compras (unidade_id, item_id, comprado, valor_centavos, quantidade, atualizado_em, atualizado_por) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)
     ON CONFLICT(unidade_id, item_id) DO UPDATE SET comprado = excluded.comprado, valor_centavos = excluded.valor_centavos,
       quantidade = excluded.quantidade, atualizado_em = excluded.atualizado_em, atualizado_por = excluded.atualizado_por`);
  await c.env.DB.batch(linhas.map((l) => {
    const item = String((l && l.item_id) || "");
    if (!/^[a-z0-9-]{1,120}$/.test(item)) throw new Erro(400, "dados");
    const v = l.valor_pago;
    if (v != null && !(typeof v === "number" && isFinite(v) && v >= 0 && v < 1e9)) throw new Erro(400, "dados");
    const q = l.quantidade;   // null = usa a quantidade sugerida no guia
    if (q != null && !(typeof q === "number" && isFinite(q) && q >= 0 && q <= 100000)) throw new Erro(400, "dados");
    return st.bind(un.id, item, l.comprado ? 1 : 0, v == null ? null : Math.round(v * 100), q == null ? null : Math.round(q * 100) / 100, agora, u.id);
  }));
  return json({ ok: true });
});
rota("POST", "/unidades/:id/responsavel", async (c) => {
  const u = await exigirSessao(c);
  const un = await exigirUnidade(c, u, c.p.id);
  await c.env.DB.prepare("UPDATE unidades SET responsavel = ?1 WHERE id = ?2").bind(texto(c.body.nome, 120), un.id).run();
  return json({ ok: true });
});

// ---------- painel da franqueadora ----------
rota("GET", "/painel", async (c) => {
  const u = await exigirSessao(c); exigirFranqueadora(u);
  const [un, co, me] = await c.env.DB.batch([
    c.env.DB.prepare("SELECT id, nome, cidade, responsavel, inauguracao, codigo, criado_em FROM unidades ORDER BY nome COLLATE NOCASE"),
    c.env.DB.prepare("SELECT unidade_id, item_id, comprado, valor_centavos, quantidade, atualizado_em FROM compras"),
    c.env.DB.prepare(`SELECT m.unidade_id, m.user_id, m.criado_em, u.email, u.nome FROM membros m JOIN usuarios u ON u.id = m.user_id
                      ORDER BY m.criado_em`),
  ]);
  return json({
    unidades: un.results,
    compras: co.results.map((r) => ({ unidade_id: r.unidade_id, item_id: r.item_id, comprado: !!r.comprado,
      valor_pago: r.valor_centavos == null ? null : r.valor_centavos / 100, quantidade: r.quantidade, atualizado_em: r.atualizado_em })),
    membros: me.results,
  });
});
function camposUnidade(b) {
  return { nome: texto(b.nome, 120, true), cidade: texto(b.cidade, 120), responsavel: texto(b.responsavel, 120), inauguracao: data(b.inauguracao) };
}
rota("POST", "/unidades", async (c) => {
  const u = await exigirSessao(c); exigirFranqueadora(u);
  const d = camposUnidade(c.body), id = uuid();
  for (let i = 0; ; i++) {
    try {
      await c.env.DB.prepare("INSERT INTO unidades (id, nome, cidade, responsavel, inauguracao, codigo, criado_em) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)")
        .bind(id, d.nome, d.cidade, d.responsavel, d.inauguracao, novoCodigo(), agoraIso()).run();
      break;
    } catch (e) { if (i >= 3 || !/UNIQUE/i.test(String(e))) throw e; }   // código repetido (raríssimo): tenta outro
  }
  return json(await c.env.DB.prepare("SELECT * FROM unidades WHERE id = ?1").bind(id).first(), 201);
});
rota("POST", "/unidades/:id", async (c) => {
  const u = await exigirSessao(c); exigirFranqueadora(u);
  const d = camposUnidade(c.body);
  const r = await c.env.DB.prepare("UPDATE unidades SET nome = ?1, cidade = ?2, responsavel = ?3, inauguracao = ?4 WHERE id = ?5")
    .bind(d.nome, d.cidade, d.responsavel, d.inauguracao, c.p.id).run();
  if (!r.meta.changes) throw new Erro(404, "nao_encontrado");
  return json({ ok: true });
});
rota("POST", "/unidades/:id/excluir", async (c) => {
  const u = await exigirSessao(c); exigirFranqueadora(u);
  await c.env.DB.batch([
    c.env.DB.prepare("DELETE FROM compras WHERE unidade_id = ?1").bind(c.p.id),
    c.env.DB.prepare("DELETE FROM membros WHERE unidade_id = ?1").bind(c.p.id),
    c.env.DB.prepare("DELETE FROM unidades WHERE id = ?1").bind(c.p.id),
  ]);
  return json({ ok: true });
});
rota("POST", "/unidades/:id/renovar-codigo", async (c) => {
  const u = await exigirSessao(c); exigirFranqueadora(u);
  const codigo = novoCodigo();
  const r = await c.env.DB.prepare("UPDATE unidades SET codigo = ?1 WHERE id = ?2").bind(codigo, c.p.id).run();
  if (!r.meta.changes) throw new Erro(404, "nao_encontrado");
  return json({ codigo });
});
rota("POST", "/unidades/:id/membros/:uid/remover", async (c) => {
  const u = await exigirSessao(c); exigirFranqueadora(u);
  await c.env.DB.prepare("DELETE FROM membros WHERE unidade_id = ?1 AND user_id = ?2").bind(c.p.id, c.p.uid).run();
  return json({ ok: true });
});
rota("POST", "/usuarios/:uid/link-senha", async (c) => {
  const u = await exigirSessao(c); exigirFranqueadora(u);
  const alvo = await c.env.DB.prepare("SELECT id, email FROM usuarios WHERE id = ?1").bind(c.p.uid).first();
  if (!alvo) throw new Erro(404, "nao_encontrado");
  const token = aleatorio(24), expira = emDias(LINK_SENHA_DIAS);
  await c.env.DB.prepare("INSERT INTO links_senha (token_hash, user_id, expira_em) VALUES (?1, ?2, ?3)").bind(await sha256(token), alvo.id, expira).run();
  return json({ token, email: alvo.email, expira_em: expira });
});

// ---------- catálogo (franqueadora edita; todos leem) ----------
const ETAPAS = ["obra", "enxoval", "franqueadora", "estoque"];
const ICONES = ["projeto", "obra", "marcenaria", "clima", "clinico", "apoio", "movel", "eletro", "utensilio", "escritorio",
  "uniforme", "info", "servico", "expo", "venda", "atendimento", "copa", "papel", "higiene"];
const FORNECIMENTOS = ["homologado", "marca", "livre"];
const idItem = (v) => { const s = String(v || ""); if (!/^[a-z0-9-]{1,120}$/.test(s)) throw new Erro(400, "dados"); return s; };
function numero(v, min, max, obrigatorio) {
  if (v == null || v === "") { if (obrigatorio) throw new Erro(400, "dados"); return null; }
  const n = Number(v);
  if (!isFinite(n) || n < min || n > max) throw new Erro(400, "dados");
  return Math.round(n * 100) / 100;
}
function camposItem(b) {
  const etapa = String(b.etapa || "");
  if (!ETAPAS.includes(etapa)) throw new Erro(400, "dados");
  const fornecimento = b.fornecimento || null;
  if (fornecimento && !FORNECIMENTOS.includes(fornecimento)) throw new Erro(400, "dados");
  const icone = ICONES.includes(b.icone) ? b.icone : "utensilio";
  return {
    etapa, categoria: texto(b.categoria, 80, true), icone,
    nome: texto(b.nome, 160, true), especificacao: texto(b.especificacao, 300), observacao: texto(b.observacao, 400),
    qtd: numero(b.qtd, 0, 100000, true), valor_unit: numero(b.valor_unit, 0, 1e8, false),   // valor vazio = recorrente/a definir
    fornecimento, fornecedor: texto(b.fornecedor, 120), unidade_medida: texto(b.unidade_medida, 20),
  };
}
async function salvarItem(env, u, id, dados, removido) {
  await env.DB.prepare(`INSERT INTO catalogo (id, dados, removido, atualizado_em, atualizado_por) VALUES (?1, ?2, ?3, ?4, ?5)
     ON CONFLICT(id) DO UPDATE SET dados = excluded.dados, removido = excluded.removido, atualizado_em = excluded.atualizado_em,
       atualizado_por = excluded.atualizado_por`).bind(id, JSON.stringify(dados), removido ? 1 : 0, agoraIso(), u.id).run();
}
// Público (sem login): as páginas do guia já são públicas; assim o build do PDF também consegue ler.
rota("GET", "/catalogo", async (c) => {
  const [it, fo] = await c.env.DB.batch([
    c.env.DB.prepare("SELECT id, dados, removido, atualizado_em FROM catalogo ORDER BY id"),
    c.env.DB.prepare("SELECT item_id, base64 IS NOT NULL AS tem_foto, ajuste, removida, versao FROM catalogo_fotos ORDER BY item_id"),
  ]);
  return json({
    itens: it.results.map((r) => ({ id: r.id, removido: !!r.removido, atualizado_em: r.atualizado_em, ...JSON.parse(r.dados) })),
    fotos: fo.results.map((r) => ({ item_id: r.item_id, tem_foto: !!r.tem_foto, ajuste: r.ajuste, removida: !!r.removida, versao: r.versao })),
  });
});
rota("GET", "/foto/:id", async (c) => {
  const r = await c.env.DB.prepare("SELECT base64, tipo, versao FROM catalogo_fotos WHERE item_id = ?1 AND removida = 0 AND base64 IS NOT NULL")
    .bind(idItem(c.p.id)).first();
  if (!r) throw new Erro(404, "nao_encontrado");
  return new Response(deb64u(r.base64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")), {
    headers: { "Content-Type": r.tipo, "Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff" },
  });
});
rota("POST", "/catalogo/novo", async (c) => {
  const u = await exigirSessao(c); exigirFranqueadora(u);
  const d = camposItem(c.body);
  const id = "novo-" + (d.nome.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || "item")
    + "-" + hex(4).toLowerCase();
  await salvarItem(c.env, u, id, d, false);
  return json({ id }, 201);
});
rota("POST", "/catalogo/:id", async (c) => {
  const u = await exigirSessao(c); exigirFranqueadora(u);
  await salvarItem(c.env, u, idItem(c.p.id), camposItem(c.body), false);
  return json({ ok: true });
});
rota("POST", "/catalogo/:id/remover", async (c) => {
  const u = await exigirSessao(c); exigirFranqueadora(u);
  const id = idItem(c.p.id);
  const atual = await c.env.DB.prepare("SELECT dados FROM catalogo WHERE id = ?1").bind(id).first();
  await salvarItem(c.env, u, id, atual ? JSON.parse(atual.dados) : {}, true);
  return json({ ok: true });
});
// Volta o item ao original do guia (desfaz edição, remoção e foto). Item criado no painel é apagado.
rota("POST", "/catalogo/:id/restaurar", async (c) => {
  const u = await exigirSessao(c); exigirFranqueadora(u);
  const id = idItem(c.p.id);
  await c.env.DB.batch([
    c.env.DB.prepare("DELETE FROM catalogo WHERE id = ?1").bind(id),
    c.env.DB.prepare("DELETE FROM catalogo_fotos WHERE item_id = ?1").bind(id),
  ]);
  return json({ ok: true });
});
const TIPOS_FOTO = { "image/webp": "UklGR", "image/jpeg": "/9j/", "image/png": "iVBOR" };
rota("POST", "/catalogo/:id/foto", async (c) => {
  const u = await exigirSessao(c); exigirFranqueadora(u);
  const id = idItem(c.p.id), b = c.body;
  const ajuste = b.ajuste === "cover" ? "cover" : "contain";
  if (b.remover) {
    await c.env.DB.prepare(`INSERT INTO catalogo_fotos (item_id, base64, tipo, ajuste, removida, versao, atualizado_em) VALUES (?1, NULL, NULL, ?2, 1, ?3, ?4)
       ON CONFLICT(item_id) DO UPDATE SET base64 = NULL, tipo = NULL, removida = 1, versao = excluded.versao, atualizado_em = excluded.atualizado_em`)
      .bind(id, ajuste, Date.now(), agoraIso()).run();
    return json({ ok: true });
  }
  if (b.base64 == null) {   // só muda o enquadramento (vale para a foto atual, nova ou original)
    await c.env.DB.prepare(`INSERT INTO catalogo_fotos (item_id, base64, tipo, ajuste, removida, versao, atualizado_em) VALUES (?1, NULL, NULL, ?2, 0, ?3, ?4)
       ON CONFLICT(item_id) DO UPDATE SET ajuste = excluded.ajuste, versao = excluded.versao, atualizado_em = excluded.atualizado_em`)
      .bind(id, ajuste, Date.now(), agoraIso()).run();
    return json({ ok: true });
  }
  const tipo = String(b.tipo || ""), dados = String(b.base64 || "");
  if (!TIPOS_FOTO[tipo] || !dados.startsWith(TIPOS_FOTO[tipo]) || dados.length > 1400000 || !/^[A-Za-z0-9+/=]+$/.test(dados)) throw new Erro(400, "foto_invalida");
  const versao = Date.now();
  await c.env.DB.prepare(`INSERT INTO catalogo_fotos (item_id, base64, tipo, ajuste, removida, versao, atualizado_em) VALUES (?1, ?2, ?3, ?4, 0, ?5, ?6)
     ON CONFLICT(item_id) DO UPDATE SET base64 = excluded.base64, tipo = excluded.tipo, ajuste = excluded.ajuste, removida = 0,
       versao = excluded.versao, atualizado_em = excluded.atualizado_em`).bind(id, dados, tipo, ajuste, versao, agoraIso()).run();
  return json({ ok: true, versao });
});
rota("POST", "/catalogo/:id/foto/restaurar", async (c) => {
  const u = await exigirSessao(c); exigirFranqueadora(u);
  await c.env.DB.prepare("DELETE FROM catalogo_fotos WHERE item_id = ?1").bind(idItem(c.p.id)).run();
  return json({ ok: true });
});

// ---------- entrada ----------
export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  try {
    if (!env.DB) throw new Erro(500, "sem_banco");
    if (!schemaPronto) {
      await env.DB.batch(SCHEMA.map((s) => env.DB.prepare(s)));
      // migração: quantidade ajustada pela unidade (coluna criada depois da primeira versão do banco)
      const cols = (await env.DB.prepare("PRAGMA table_info(compras)").all()).results.map((c) => c.name);
      if (!cols.includes("quantidade")) await env.DB.prepare("ALTER TABLE compras ADD COLUMN quantidade REAL").run();
      schemaPronto = true;
    }

    const caminho = "/" + [].concat(context.params.rota || []).join("/");
    const metodo = request.method === "HEAD" ? "GET" : request.method;
    let body = {};
    if (metodo === "POST") {
      // só aceita chamadas do próprio site (bloqueia formulários de outros sites)
      const origem = request.headers.get("Origin");
      if (origem && origem !== url.origin) throw new Erro(403, "origem");
      if (!(request.headers.get("Content-Type") || "").includes("application/json")) throw new Erro(415, "dados");
      try { body = (await request.json()) || {}; } catch (e) { throw new Erro(400, "dados"); }
      if (typeof body !== "object" || Array.isArray(body)) throw new Erro(400, "dados");
    }
    let achouCaminho = false;
    for (const r of ROTAS) {
      const m = caminho.match(r.re);
      if (!m) continue;
      achouCaminho = true;
      if (r.metodo !== metodo) continue;
      const resp = await r.fn({ request, env, url, body, p: m.groups || {} });
      // faxina ocasional de sessões, links e contadores vencidos
      if (Math.random() < 0.02) {
        const agora = agoraIso();
        context.waitUntil(env.DB.batch([
          env.DB.prepare("DELETE FROM sessoes WHERE expira_em < ?1").bind(agora),
          env.DB.prepare("DELETE FROM links_senha WHERE expira_em < ?1").bind(agora),
          env.DB.prepare("DELETE FROM tentativas WHERE ate < ?1").bind(Math.floor(Date.now() / 1000) - 86400),
        ]).catch(() => {}));
      }
      return resp;
    }
    throw achouCaminho ? new Erro(405, "metodo") : new Erro(404, "nao_encontrado");
  } catch (e) {
    if (e instanceof Erro) return json({ erro: e.codigo }, e.status);
    console.error(e && e.stack || e);
    return json({ erro: "interno" }, 500);
  }
}
