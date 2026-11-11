// Configuração do Supabase (Supabase → Project Settings → API).
// A "anon key" é pública por natureza: quem protege os dados são as regras de acesso do banco
// (supabase/schema.sql). Nunca coloque aqui a "service_role key".
window.SC_CONFIG = {
  url: "https://SEU-PROJETO.supabase.co",
  anonKey: "COLE-AQUI-A-ANON-KEY",
};
