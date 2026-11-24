import { h, api, qs, clear, fail, toast, fmtDate, createSession, KIND_LABEL } from "../lib.js";
import { createFilters } from "../components/filters.js";

const KINDS = [
  ["bateria", "Bateria personalizada", "Escolha o recorte e responda. Gabarito logo após cada questão.", "each"],
  ["diagnostico", "Diagnóstico de assunto", "Sondagem inicial: o gabarito só aparece ao final. Poucas questões são só uma amostra, não um diagnóstico definitivo.", "end"],
  ["misto", "Assuntos mistos", "Intercala disciplinas e assuntos na mesma sessão.", "each"],
  ["simulado", "Simulado", "Estilo prova: gabarito só ao final, com limite de tempo opcional.", "end"],
];

export default async function (root) {
  const [inprog, count] = await Promise.all([api("/sessions?in_progress=1"), api("/questions/count")]);
  clear(root);
  root.append(h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Estudar"), h("p", {}, "Monte uma sessão a partir do seu banco de questões."))));
  if (count.total === 0) {
    root.append(h("div", { class: "card" }, h("div", { class: "empty" }, h("h3", {}, "Não há questões para estudar"), h("p", {}, "Importe questões primeiro."), h("a", { class: "btn primary", href: "#/importar" }, "Importar questões"))));
    return;
  }
  if (inprog.length) {
    root.append(h("div", { class: "card", style: { marginBottom: "16px" } }, h("h2", {}, "Continuar de onde parou"),
      h("div", { class: "list" }, inprog.map((x) => h("div", { class: "li" },
        h("div", { class: "grow" }, h("div", { class: "trunc" }, x.title), h("div", { class: "muted small" }, `${x.answered}/${x.total} · ${fmtDate(x.started_at)}`)),
        h("a", { class: "btn sm primary", href: `#/sessao/${x.id}` }, "Continuar"),
        h("button", { class: "btn sm ghost danger", onclick: async () => { await api(`/sessions/${x.id}`, { method: "DELETE" }).catch(fail); location.reload(); } }, "Descartar"))))));
  }

  let kind = "bateria", reveal = "each";
  const kindBox = h("div", { class: "grid g2" });
  const renderKinds = () => kindBox.replaceChildren(...KINDS.map(([k, t, d, r]) =>
    h("button", { class: `opt-card ${kind === k ? "on" : ""}`, onclick: () => { kind = k; reveal = r; renderKinds(); renderReveal(); renderTimer(); } }, h("b", {}, t), h("span", {}, d))));
  renderKinds();

  const countLbl = h("span", { class: "muted" });
  const filters = await createFilters({ onChange: () => refresh(), search: false, fields: ["subject_id", "topic_id", "bank", "year", "exam_name", "difficulty", "status"] });
  async function refresh() {
    try { const c = await api("/questions/count" + qs(filters.get())); countLbl.textContent = `${c.total} questão(ões) com esses filtros`; countLbl.dataset.n = c.total; }
    catch (e) { countLbl.textContent = e.message; }
  }
  refresh();

  const limit = h("input", { type: "number", min: 1, value: 10, style: { width: "100%" } });
  const order = h("select", {}, h("option", { value: "random" }, "Aleatória"), h("option", { value: "sequential" }, "Ordem de importação"));
  const revealSel = h("select", { onchange: (e) => { reveal = e.target.value; } });
  const renderReveal = () => revealSel.replaceChildren(
    h("option", { value: "each", selected: reveal === "each" }, "Após cada questão"),
    h("option", { value: "end", selected: reveal === "end" }, "Somente ao final da sessão"));
  renderReveal();
  const timer = h("input", { type: "number", min: 1, placeholder: "sem limite", style: { width: "100%" } });
  const timerWrap = h("label", { class: "field" }, "Limite de tempo (min)", timer);
  const renderTimer = () => { timerWrap.style.display = kind === "simulado" ? "" : "none"; };
  renderTimer();

  const start = async (e) => {
    const btn = e.currentTarget; btn.disabled = true;
    try {
      if (!Number(countLbl.dataset.n)) { toast("Nenhuma questão com esses filtros.", "error"); return; }
      await createSession({ kind, reveal, filters: filters.get(), limit: Number(limit.value) || null, order: order.value, timer_minutes: kind === "simulado" && timer.value ? Number(timer.value) : null });
    } catch (err) { fail(err); } finally { btn.disabled = false; }
  };

  root.append(
    h("div", { class: "card" }, h("h2", {}, "1. Tipo de sessão"), kindBox),
    h("div", { class: "card sp" }, h("h2", {}, "2. O que estudar"), filters.el, h("div", { class: "sp" }, countLbl)),
    h("div", { class: "card sp" }, h("h2", {}, "3. Ajustes"),
      h("div", { class: "filters" },
        h("label", { class: "field" }, "Quantidade de questões", limit),
        h("label", { class: "field" }, "Ordem", order),
        h("label", { class: "field" }, "Gabarito", revealSel), timerWrap)),
    h("div", { class: "row sp" }, h("button", { class: "btn primary lg", onclick: start }, "Iniciar sessão")));
}
