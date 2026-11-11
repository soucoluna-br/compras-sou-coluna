/* Sou Coluna · Guia de Compras — conexão com o Supabase (login e banco).
   Usado por index.html (login), guia.html (checklist da unidade) e painel.html (franqueadora). */
(function () {
  const cfg = window.SC_CONFIG || {};
  const configurado = !!(cfg.url && cfg.anonKey && !/SEU-PROJETO|COLE-AQUI/.test(cfg.url + cfg.anonKey));
  const sb = configurado && window.supabase ? window.supabase.createClient(cfg.url, cfg.anonKey) : null;

  function cliente() {
    if (!sb) throw new Error("config");
    return sb;
  }

  // Erros do banco viram exceções; sessão vencida é sinalizada para a página pedir login de novo.
  function checar(res) {
    if (res.error) {
      const e = new Error(res.error.message || "erro");
      e.code = res.error.code;
      e.sessaoExpirada = res.error.code === "PGRST301" || res.error.code === "42501" || res.status === 401;
      throw e;
    }
    return res.data;
  }

  async function sessao() {
    const { data, error } = await cliente().auth.getSession();
    if (error) throw error;
    return data.session;
  }

  async function perfil(userId) {
    return checar(await cliente().from("perfis").select("user_id,email,nome,franqueadora").eq("user_id", userId).maybeSingle());
  }

  // Franqueado: só as unidades dele. Franqueadora: todas (as regras do banco decidem).
  async function unidades() {
    return checar(await cliente().from("unidades").select("*").order("nome")) || [];
  }

  // Busca tudo, de 1000 em 1000 (limite padrão do Supabase por consulta).
  async function todos(consulta) {
    const saida = [];
    for (let i = 0; ; i += 1000) {
      const lote = checar(await consulta().range(i, i + 999)) || [];
      saida.push(...lote);
      if (lote.length < 1000) return saida;
    }
  }

  // Carrega o guia de uma unidade. Sem login ou sem unidade, redireciona e devolve null.
  async function abrirGuia() {
    const s = await sessao();
    if (!s) { location.replace("index.html"); return null; }
    const [p, us] = await Promise.all([perfil(s.user.id), unidades()]);
    const pedida = new URLSearchParams(location.search).get("u");
    const u = pedida ? us.find((x) => x.id === pedida) : us.length === 1 ? us[0] : null;
    if (!u) { location.replace(p && p.franqueadora ? "painel.html" : "index.html?escolher=1"); return null; }
    const linhas = await todos(() => cliente().from("compras").select("item_id,comprado,valor_pago").eq("unidade_id", u.id));
    const itens = {};
    linhas.forEach((r) => { itens[r.item_id] = { done: !!r.comprado, paid: r.valor_pago == null ? null : Number(r.valor_pago) }; });
    return { unidade: u, itens, email: s.user.email, franqueadora: !!(p && p.franqueadora), varias: us.length > 1 };
  }

  async function salvarCompras(unidadeId, linhas) {
    checar(await cliente().from("compras").upsert(
      linhas.map((l) => ({ unidade_id: unidadeId, item_id: l.item_id, comprado: l.comprado, valor_pago: l.valor_pago })),
      { onConflict: "unidade_id,item_id" }));
  }

  async function definirResponsavel(unidadeId, nome) {
    checar(await cliente().rpc("definir_responsavel", { unidade: unidadeId, nome: nome || "" }));
  }

  async function sair() {
    try { await cliente().auth.signOut(); } catch (e) { /* sai mesmo assim */ }
    location.replace("index.html");
  }

  // Mensagens do Supabase Auth em português.
  function mensagemErro(e) {
    const c = (e && (e.code || "")) + " " + ((e && e.message) || "");
    if (/config/.test(c)) return "O site ainda não foi configurado (config.js).";
    if (/invalid_credentials|Invalid login credentials/i.test(c)) return "E-mail ou senha incorretos.";
    if (/email_not_confirmed|Email not confirmed/i.test(c)) return "Confirme seu e-mail pelo link que enviamos antes de entrar.";
    if (/user_already_exists|already registered/i.test(c)) return "Este e-mail já tem conta. Use “Entrar”.";
    if (/weak_password|Password should be/i.test(c)) return "A senha precisa ter pelo menos 8 caracteres.";
    if (/rate_limit|rate limit|too many/i.test(c)) return "Muitas tentativas seguidas. Aguarde um minuto e tente de novo.";
    if (/same_password|should be different/i.test(c)) return "A nova senha precisa ser diferente da anterior.";
    if (/codigo_invalido/.test(c)) return "Código não encontrado. Confira com a franqueadora.";
    if (/Failed to fetch|NetworkError|network/i.test(c)) return "Sem conexão com o servidor. Verifique a internet.";
    return "Algo deu errado. Tente de novo em instantes.";
  }

  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  window.SC = { sb, configurado, cliente, checar, sessao, perfil, unidades, todos, abrirGuia, salvarCompras, definirResponsavel, sair, mensagemErro, esc };
})();
