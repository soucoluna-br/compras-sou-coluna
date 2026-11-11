/* Supabase de mentira, só para os testes do site (tests/test_site.py).
   Substitui site/vendor/supabase-*.js no navegador de teste. Guarda o "banco" no localStorage
   (para sobreviver às trocas de página) e imita as regras de acesso de supabase/schema.sql. */
(function () {
  const DBK = "__fakedb", SK = "__fakesession";
  const load = () => JSON.parse(localStorage.getItem(DBK));
  const save = (db) => localStorage.setItem(DBK, JSON.stringify(db));
  const sess = () => JSON.parse(localStorage.getItem(SK) || "null");
  const uuid = () => "xxxxxxxx-xxxx-4xxx-8xxx-xxxxxxxxxxxx".replace(/x/g, () => ((Math.random() * 16) | 0).toString(16));
  const hex = (n) => Array.from({ length: n }, () => ((Math.random() * 16) | 0).toString(16)).join("").toUpperCase();
  const codigo = () => hex(5) + "-" + hex(5);
  const now = () => new Date().toISOString();
  const err = (message, code) => ({ data: null, error: { message, code } });
  const rls = (t) => err(`new row violates row-level security policy for table "${t}"`, "42501");

  function ctx(db) {
    const s = sess(), uid = s && s.user.id;
    const admin = !!(uid && db.perfis.find((p) => p.user_id === uid && p.franqueadora));
    const membro = (u) => !!(uid && db.membros.find((m) => m.user_id === uid && m.unidade_id === u));
    return { uid, admin, membro };
  }
  function visiveis(db, t, c) {
    const rows = db[t];
    if (t === "perfis") return rows.filter((r) => r.user_id === c.uid || c.admin);
    if (t === "unidades") return rows.filter((r) => c.admin || c.membro(r.id));
    if (t === "membros") return rows.filter((r) => r.user_id === c.uid || c.admin);
    if (t === "compras") return rows.filter((r) => c.admin || c.membro(r.unidade_id));
    return [];
  }

  class Q {
    constructor(t) { this.t = t; this.op = "select"; this.cols = "*"; this.f = []; this.o = []; this.r = null; this.one = null; this.ret = false; }
    select(cols) { if (this.op === "select") this.cols = cols || "*"; else this.ret = true; return this; }
    insert(p) { this.op = "insert"; this.p = p; return this; }
    update(p) { this.op = "update"; this.p = p; return this; }
    upsert(p, o) { this.op = "upsert"; this.p = p; this.opts = o || {}; return this; }
    delete() { this.op = "delete"; return this; }
    eq(c, v) { this.f.push([c, v]); return this; }
    order(c, o) { this.o.push([c, o && o.ascending === false ? -1 : 1]); return this; }
    range(a, b) { this.r = [a, b]; return this; }
    single() { this.one = "single"; return this; }
    maybeSingle() { this.one = "maybe"; return this; }
    then(ok, ko) { return new Promise((r) => setTimeout(r, 15)).then(() => this.exec()).then(ok, ko); }
    match(row) { return this.f.every(([c, v]) => row[c] === v); }
    exec() {
      const db = load(), c = ctx(db);
      if (!c.uid) return err(`permission denied for table ${this.t}`, "42501");
      if (db.config.falharEscrita && this.op !== "select") return err("TypeError: Failed to fetch", "");
      let out;
      if (this.op === "select") {
        out = visiveis(db, this.t, c).filter((r) => this.match(r)).map((r) => ({ ...r }));
        if (this.t === "membros" && this.cols.includes("perfis(")) out.forEach((m) => {
          const p = db.perfis.find((x) => x.user_id === m.user_id); m.perfis = p ? { email: p.email, nome: p.nome } : null; });
        for (const [col, dir] of this.o.slice().reverse()) out.sort((a, b) => (a[col] > b[col] ? dir : a[col] < b[col] ? -dir : 0));
        if (this.r) out = out.slice(this.r[0], this.r[1] + 1);
      } else if (this.op === "insert") {
        if (this.t !== "unidades" || !c.admin) return rls(this.t);
        const rows = (Array.isArray(this.p) ? this.p : [this.p]).map((p) => ({ id: uuid(), codigo: codigo(), criado_em: now(), cidade: null, responsavel: null, inauguracao: null, ...p }));
        db.unidades.push(...rows); save(db); out = rows;
      } else if (this.op === "update") {
        const alvo = visiveis(db, this.t, c).filter((r) => this.match(r));
        if (this.t === "unidades" && !c.admin) out = [];
        else if (this.t === "perfis" && Object.keys(this.p).some((k) => k !== "nome")) return err("permission denied for table perfis", "42501");
        else { alvo.forEach((r) => Object.assign(db[this.t].find((x) => x === r || JSON.stringify(x) === JSON.stringify(r)), this.p)); save(db); out = alvo; }
      } else if (this.op === "upsert") {
        if (this.t !== "compras") return rls(this.t);
        const rows = Array.isArray(this.p) ? this.p : [this.p];
        if (!rows.every((r) => c.admin || c.membro(r.unidade_id))) return rls("compras");
        rows.forEach((r) => {
          const ex = db.compras.find((x) => x.unidade_id === r.unidade_id && x.item_id === r.item_id);
          const v = { ...r, atualizado_em: now(), atualizado_por: c.uid };
          if (ex) Object.assign(ex, v); else db.compras.push({ comprado: false, valor_pago: null, ...v });
        });
        save(db); out = rows;
      } else if (this.op === "delete") {
        if (!["unidades", "membros"].includes(this.t) || !c.admin) { out = []; }
        else {
          const sai = db[this.t].filter((r) => this.match(r));
          db[this.t] = db[this.t].filter((r) => !sai.includes(r));
          if (this.t === "unidades") sai.forEach((u) => {
            db.compras = db.compras.filter((x) => x.unidade_id !== u.id);
            db.membros = db.membros.filter((x) => x.unidade_id !== u.id); });
          save(db); out = sai;
        }
      }
      if (this.one) {
        if (out.length > 1 || (this.one === "single" && out.length === 0)) return err("JSON object requested, multiple (or no) rows returned", "PGRST116");
        return { data: out[0] || null, error: null };
      }
      return { data: this.op === "select" || this.ret ? out : null, error: null, status: 200 };
    }
  }

  function rpc(nome, a) {
    return new Promise((r) => setTimeout(r, 15)).then(() => {
      const db = load(), c = ctx(db);
      const porCodigo = (k) => db.unidades.find((u) => u.codigo === String(k || "").trim().toUpperCase());
      if (nome === "codigo_valido") return { data: !!porCodigo(a.codigo), error: null };
      if (!c.uid) return err(`permission denied for function ${nome}`, "42501");
      if (nome === "entrar_com_codigo") {
        const u = porCodigo(a.codigo); if (!u) return err("codigo_invalido", "P0001");
        if (!db.membros.find((m) => m.user_id === c.uid && m.unidade_id === u.id)) db.membros.push({ user_id: c.uid, unidade_id: u.id, criado_em: now() });
        save(db); return { data: u.id, error: null };
      }
      if (nome === "definir_responsavel") {
        if (!(c.membro(a.unidade) || c.admin)) return err("sem acesso a esta unidade", "P0001");
        db.unidades.find((u) => u.id === a.unidade).responsavel = (a.nome || "").trim() || null; save(db); return { data: null, error: null };
      }
      if (nome === "renovar_codigo") {
        if (!c.admin) return err("apenas a franqueadora", "P0001");
        const u = db.unidades.find((x) => x.id === a.unidade); u.codigo = codigo(); save(db); return { data: u.codigo, error: null };
      }
      return err("função desconhecida " + nome, "PGRST202");
    });
  }

  const auth = {
    async getSession() { return { data: { session: sess() }, error: null }; },
    onAuthStateChange() { return { data: { subscription: { unsubscribe() {} } } }; },
    async signInWithPassword({ email, password }) {
      const db = load(), u = db.users.find((x) => x.email === email.toLowerCase());
      if (!u || u.password !== password) return { data: {}, error: { code: "invalid_credentials", message: "Invalid login credentials" } };
      if (u.naoConfirmado) return { data: {}, error: { code: "email_not_confirmed", message: "Email not confirmed" } };
      const s = { access_token: "fake", user: { id: u.id, email: u.email } };
      localStorage.setItem(SK, JSON.stringify(s)); return { data: { session: s, user: s.user }, error: null };
    },
    async signUp({ email, password, options }) {
      const db = load(); email = email.toLowerCase();
      if (db.users.find((x) => x.email === email)) {
        return db.config.confirmarEmail ? { data: { user: { identities: [] }, session: null }, error: null }
          : { data: {}, error: { code: "user_already_exists", message: "User already registered" } };
      }
      const id = uuid(), meta = (options && options.data) || {};
      db.users.push({ id, email, password, naoConfirmado: !!db.config.confirmarEmail });
      db.perfis.push({ user_id: id, email, nome: meta.nome || null, franqueadora: false });
      const u = db.unidades.find((x) => x.codigo === String(meta.codigo || "").toUpperCase());
      if (u) db.membros.push({ user_id: id, unidade_id: u.id, criado_em: now() });
      db.log.push({ signUp: email, redirect: options && options.emailRedirectTo });
      save(db);
      if (db.config.confirmarEmail) return { data: { user: { id, identities: [{}] }, session: null }, error: null };
      const s = { access_token: "fake", user: { id, email } };
      localStorage.setItem(SK, JSON.stringify(s)); return { data: { user: s.user, session: s }, error: null };
    },
    async signOut() { localStorage.removeItem(SK); return { error: null }; },
    async resetPasswordForEmail(email, o) { const db = load(); db.log.push({ reset: email, redirect: o && o.redirectTo }); save(db); return { data: {}, error: null }; },
    async updateUser({ password }) {
      const db = load(), s = sess(); if (!s) return { data: {}, error: { message: "Auth session missing!" } };
      db.users.find((u) => u.id === s.user.id).password = password; save(db); return { data: { user: s.user }, error: null };
    },
  };

  window.supabase = { createClient: () => ({ auth, from: (t) => new Q(t), rpc }) };
})();
