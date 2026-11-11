/* Sou Coluna · Guia de Compras — conversa com a API do site (/api, Cloudflare Pages Functions + D1).
   Usado por index.html (login), guia.html (checklist da unidade) e painel.html (franqueadora). */
(function () {
  // Chama a API. Erros viram exceções com .code (ex.: "credenciais", "codigo_invalido") e .status.
  async function api(caminho, dados) {
    const opts = { method: dados === undefined ? "GET" : "POST", headers: {}, credentials: "same-origin" };
    if (dados !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(dados); }
    let r;
    try { r = await fetch("/api/" + caminho, opts); }
    catch (e) { const er = new Error("rede"); er.code = "rede"; throw er; }
    let corpo = null;
    try { corpo = await r.json(); } catch (e) { /* resposta sem JSON */ }
    if (!r.ok) {
      const er = new Error((corpo && corpo.erro) || "http_" + r.status);
      er.code = (corpo && corpo.erro) || (r.status === 404 ? "sem_api" : "http_" + r.status);
      er.status = r.status;
      er.sessaoExpirada = r.status === 401;
      throw er;
    }
    return corpo;
  }

  // Usuário logado ({email, nome, franqueadora, unidades}) ou null.
  async function eu() {
    try { return await api("eu"); }
    catch (e) { if (e.status === 401) return null; throw e; }
  }

  // Carrega o guia de uma unidade. Sem login ou sem unidade, redireciona e devolve null.
  async function abrirGuia() {
    const quem = await eu();
    if (!quem) { location.replace("/"); return null; }
    const pedida = new URLSearchParams(location.search).get("u");
    const u = pedida ? quem.unidades.find((x) => x.id === pedida) : quem.unidades.length === 1 && !quem.franqueadora ? quem.unidades[0] : null;
    if (!u) { location.replace(quem.franqueadora ? "/painel" : "/?escolher=1"); return null; }
    const [r, catalogo] = await Promise.all([api("unidades/" + encodeURIComponent(u.id) + "/compras"), api("catalogo")]);
    const itens = {};
    r.itens.forEach((x) => { itens[x.item_id] = { done: !!x.comprado, paid: x.valor_pago, qty: x.quantidade == null ? null : x.quantidade }; });
    return { unidade: r.unidade, itens, catalogo, email: quem.email, franqueadora: quem.franqueadora, varias: quem.unidades.length > 1 };
  }

  // Junta o catálogo do guia (data.py) com as alterações da franqueadora (GET /api/catalogo).
  // Itens editados mudam de lugar/dados mas mantêm o id (o progresso das unidades continua valendo);
  // removidos somem; criados no painel entram na etapa/categoria escolhida. Itens em ordem alfabética.
  function aplicarAjustes(base, imagens, aj) {
    const secs = base.map((s) => ({ id: s.id, title: s.title, short: s.short, desc: s.desc,
      cats: s.cats.map((c) => ({ name: c.name, key: c.key, items: c.items.map((i) => ({ ...i })) })) }));
    const imgs = { ...imagens };
    const lugar = {};
    secs.forEach((s) => s.cats.forEach((c) => c.items.forEach((i) => { lugar[i.id] = { c, i }; })));
    const linhas = (aj && aj.itens) || [];
    for (const r of linhas) { const o = lugar[r.id]; if (o) o.c.items = o.c.items.filter((x) => x.id !== r.id); }
    for (const r of linhas) {
      if (r.removido) { delete imgs[r.id]; continue; }
      const sec = secs.find((s) => s.id === r.etapa);
      if (!sec || !r.nome) continue;
      let cat = sec.cats.find((c) => c.name.toLowerCase() === String(r.categoria || "").toLowerCase());
      if (!cat) { cat = { name: r.categoria, key: r.icone || "utensilio", items: [] }; sec.cats.push(cat); }
      cat.items.push({ id: r.id, name: r.nome, spec: r.especificacao || null, qty: r.qtd, unit: r.valor_unit == null ? null : r.valor_unit,
        uom: r.unidade_medida || null, supply: r.fornecimento || null, supplier: r.fornecedor || null, note: r.observacao || null });
    }
    for (const f of (aj && aj.fotos) || []) {
      if (f.removida) delete imgs[f.item_id];
      else if (f.tem_foto) imgs[f.item_id] = { src: "/api/foto/" + encodeURIComponent(f.item_id) + "?v=" + f.versao, fit: f.ajuste === "cover" ? "cover" : "contain" };
      else if (imgs[f.item_id]) imgs[f.item_id] = { ...imgs[f.item_id], fit: f.ajuste === "cover" ? "cover" : "contain" };
    }
    secs.forEach((s) => {
      s.cats = s.cats.filter((c) => c.items.length);
      s.cats.forEach((c) => c.items.sort((a, b) => a.name.localeCompare(b.name, "pt-BR")));
    });
    return { sections: secs, images: imgs };
  }

  const salvarCompras = (unidadeId, linhas) => api("unidades/" + encodeURIComponent(unidadeId) + "/compras", { linhas });
  const definirResponsavel = (unidadeId, nome) => api("unidades/" + encodeURIComponent(unidadeId) + "/responsavel", { nome: nome || "" });

  async function sair() {
    try { await api("sair", {}); } catch (e) { /* sai mesmo assim */ }
    location.replace("/");
  }

  function mensagemErro(e) {
    const c = (e && e.code) || "";
    return ({
      credenciais: "E-mail ou senha incorretos.",
      email_existe: "Este e-mail já tem conta. Use “Entrar”.",
      email_invalido: "Informe um e-mail válido.",
      senha_curta: "A senha precisa ter pelo menos 8 caracteres.",
      codigo_invalido: "Código não encontrado. Confira com a franqueadora.",
      chave_invalida: "E-mail ou chave da franqueadora incorretos.",
      foto_invalida: "Foto inválida ou grande demais. Use uma imagem JPG, PNG ou WebP.",
      link_invalido: "Este link de senha expirou ou já foi usado. Peça um novo à franqueadora.",
      limite: "Muitas tentativas seguidas. Aguarde alguns minutos e tente de novo.",
      sem_acesso: "Sua conta não tem acesso a isso.",
      login: "Sua sessão terminou. Entre de novo.",
      dados: "Confira os dados informados.",
      sem_banco: "O banco de dados ainda não foi ligado ao site (veja o README).",
      sem_api: "O site está sem a parte do servidor. Ele precisa rodar na Cloudflare (ou com wrangler pages dev).",
      rede: "Sem conexão com o servidor. Verifique a internet.",
    })[c] || "Algo deu errado. Tente de novo em instantes.";
  }

  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  window.SC = { api, eu, abrirGuia, aplicarAjustes, salvarCompras, definirResponsavel, sair, mensagemErro, esc };
})();
