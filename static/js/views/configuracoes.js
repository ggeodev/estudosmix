import { h, api, clear, fail, toast, fmtDuration } from "../lib.js";

export default async function (root) {
  const [settings, info, ai] = await Promise.all([api("/settings"), api("/system/info"), api("/ai/status")]);
  clear(root);
  const save = async (patch) => { try { Object.assign(settings, await api("/settings", { method: "PUT", body: patch })); } catch (e) { fail(e); } };
  const theme = h("select", { onchange: async (e) => { await save({ theme: e.target.value }); document.documentElement.dataset.theme = settings.theme; localStorage.setItem("theme", settings.theme); toast("Tema aplicado.", "success", 1500); } },
    [["dark", "Escuro"], ["light", "Claro"]].map(([v, l]) => h("option", { value: v, selected: settings.theme === v }, l)));
  const timer = h("input", { type: "checkbox", checked: !!settings.show_timer, onchange: (e) => save({ show_timer: e.target.checked }) });
  const mb = (info.database_bytes / 1024 / 1024).toFixed(2);

  root.append(h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Configurações"))),
    h("div", { class: "card" }, h("h2", {}, "Aparência e estudo"), h("div", { class: "stack" },
      h("label", { class: "field", style: { maxWidth: "240px" } }, "Tema", theme),
      h("label", { class: "row" }, timer, "Mostrar cronômetro por questão durante a resolução"))),
    h("div", { class: "card sp" }, h("h2", {}, "Seus dados"),
      h("p", { class: "muted", style: { marginTop: 0 } }, `${info.questions} questões · ${info.answers} respostas · ${info.sessions} sessões · banco com ${mb} MB`),
      h("p", { class: "small muted" }, `Arquivo do banco: ${info.database_path}`),
      h("div", { class: "row" }, h("a", { class: "btn primary", href: "/api/backup" }, "Baixar backup (.db)")),
      h("p", { class: "small muted" }, "O backup é uma cópia completa e consistente do banco SQLite. Para restaurar, feche o aplicativo e substitua o arquivo indicado acima pelo backup.")),
    aiCard());

  function aiCard() {
    const key = h("input", { type: "password", placeholder: ai.configured ? "•••••••• (já configurada; cole outra para trocar)" : "Cole sua chave de API do Gemini", autocomplete: "off", style: { width: "100%" } });
    const model = h("input", { value: ai.model, style: { width: "100%" } });
    const xmodel = h("input", { value: ai.extraction_model, style: { width: "100%" } });
    const result = h("p", { class: "small", style: { margin: 0 } });
    const u = ai.usage;
    return h("div", { class: "card sp" }, h("h2", {}, "Inteligência artificial (Gemini)", h("span", { class: `chip ${ai.configured ? "ok" : "warn"}` }, ai.configured ? "configurada" : "não configurada")),
      h("p", { class: "muted small", style: { marginTop: 0 } }, "A chave fica só no arquivo .env do seu computador e é usada apenas pelo servidor local; ela nunca é enviada ao navegador nem exibida de novo. Gere a sua em aistudio.google.com."),
      h("div", { class: "stack" },
        h("label", { class: "field" }, "Chave de API", key),
        h("div", { class: "grid g2" }, h("label", { class: "field" }, "Modelo (tutor, explicações, questões)", model), h("label", { class: "field" }, "Modelo para converter PDFs", xmodel)),
        h("div", { class: "row" },
          h("button", { class: "btn primary", onclick: async () => {
            try { await api("/ai/config", { method: "PUT", body: { api_key: key.value, model: model.value, extraction_model: xmodel.value } }); toast("Configuração salva.", "success"); location.reload(); } catch (e) { fail(e); }
          } }, "Salvar"),
          h("button", { class: "btn", onclick: async (e) => {
            const btn = e.currentTarget; btn.disabled = true; result.className = "small muted"; result.textContent = "Testando…";
            try { const r = await api("/ai/test", { method: "POST" }); result.className = "small ok"; result.textContent = `Conexão OK com o modelo ${r.model}.`; }
            catch (err) { result.className = "small bad"; result.textContent = err.message; }
            finally { btn.disabled = false; }
          } }, "Testar conexão"), result),
        h("p", { class: "muted small", style: { margin: 0 } }, `Chamadas de IA feitas: ${u.calls} (${u.failed} com erro).${u.by_feature.length ? " " + u.by_feature.map((f) => `${f.feature}: ${f.n}`).join(" · ") : ""}`),
        u.last_error ? h("p", { class: "small warn", style: { margin: 0 } }, `Último erro: ${u.last_error.error}`) : null,
        h("p", { class: "muted small", style: { margin: 0 } }, "Modelos são aposentados com frequência; se aparecer “modelo não encontrado”, troque o nome acima por um modelo atual. Veja custos e limites em ai.google.dev/pricing.")));
  }
}
