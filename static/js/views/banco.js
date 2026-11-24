import { h, api, qs, clear, fail, toast, empty, modal, formModal, createSession, safeImgSrc, CONF_SHORT, fmtDate } from "../lib.js";
import { createFilters, topicOptions } from "../components/filters.js";

const PER = 25;

export default async function (root) {
  const total0 = (await api("/questions/count")).total;
  clear(root);
  root.append(h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Banco de questões"), h("p", {}, "Explore, filtre e organize suas questões."))));
  if (!total0) {
    root.append(h("div", { class: "card" }, empty("Nenhuma questão importada", "Importe um arquivo JSON para começar.", h("a", { class: "btn primary", href: "#/importar" }, "Importar questões"))));
    return;
  }
  let page = 1, data = null;
  const selected = new Set();
  const filters = await createFilters({ onChange: () => { page = 1; load(); } });
  const listBox = h("div"), pager = h("div", { class: "row sp" }), bar = h("div", { class: "row", style: { margin: "14px 0" } });
  root.append(h("div", { class: "card" }, filters.el), bar, h("div", { class: "card", style: { padding: 0 } }, listBox), pager);

  function renderBar() {
    bar.replaceChildren(
      h("span", { class: "muted" }, `${data.total} questão(ões)`),
      h("span", { class: "right" }),
      selected.size ? h("button", { class: "btn", onclick: bulkAssign }, `Atribuir assunto (${selected.size})`) : null,
      h("button", { class: "btn primary", disabled: !data.total, onclick: () => practice() }, `Resolver filtradas`));
  }
  function practice() {
    let n = Math.min(10, data.total);
    const input = h("input", { type: "number", min: 1, max: data.total, value: n });
    modal({ title: "Resolver questões filtradas", size: "sm",
      body: h("div", { class: "stack" }, h("p", { class: "muted", style: { margin: 0 } }, `${data.total} questão(ões) correspondem aos filtros.`), h("label", { class: "field" }, "Quantas questões?", input)),
      actions: [{ label: "Cancelar", class: "ghost" }, { label: "Iniciar", class: "primary", onClick: () => createSession({ kind: "bateria", filters: filters.get(), limit: Number(input.value) || null }) }] });
  }
  function bulkAssign() {
    const tax = filters.tax;
    const subjects = tax.subjects;
    const subSel = h("select", {}, subjects.map((s) => h("option", { value: s.id, selected: String(s.id) === String(filters.get().subject_id) }, s.name)));
    const topSel = h("select", {});
    const fill = () => topSel.replaceChildren(...topicOptions(tax.topics, subSel.value).map((o) => h("option", { value: o.value }, o.label)));
    subSel.onchange = fill; fill();
    modal({ title: `Atribuir assunto a ${selected.size} questão(ões)`, size: "sm",
      body: h("div", { class: "stack" }, h("p", { class: "muted small", style: { margin: 0 } }, "Só questões da disciplina escolhida recebem o assunto."),
        h("label", { class: "field" }, "Disciplina", subSel), h("label", { class: "field" }, "Assunto", topSel)),
      actions: [{ label: "Cancelar", class: "ghost" }, { label: "Atribuir", class: "primary", onClick: async () => {
        if (!topSel.value) throw new Error("Crie um assunto nesta disciplina primeiro (página Disciplinas).");
        const r = await api("/questions/bulk-topics", { method: "POST", body: { question_ids: [...selected], add_topic_ids: [Number(topSel.value)] } });
        toast(r.skipped_other_subject ? `${r.updated - r.skipped_other_subject} atribuída(s); ${r.skipped_other_subject} ignorada(s) por serem de outra disciplina.` : "Assunto atribuído.", "success");
        selected.clear(); load();
      } }] });
  }

  function renderList() {
    if (!data.items.length) { listBox.replaceChildren(empty("Nada encontrado", "Nenhuma questão corresponde aos filtros.")); return; }
    const status = (q) => q.attempts === 0 ? h("span", { class: "chip" }, "inédita")
      : q.last_correct ? h("span", { class: `chip ${q.last_confidence === "certeza" ? "ok" : "warn"}` }, `certa · ${CONF_SHORT[q.last_confidence]}`)
      : h("span", { class: "chip bad" }, "errada");
    listBox.replaceChildren(h("table", {},
      h("thead", {}, h("tr", {}, h("th", { style: { width: "32px" } }, h("input", { type: "checkbox", title: "Selecionar página", checked: data.items.every((q) => selected.has(q.id)), onchange: (e) => { data.items.forEach((q) => e.target.checked ? selected.add(q.id) : selected.delete(q.id)); renderList(); renderBar(); } })), h("th", {}, "Questão"), h("th", {}, "Situação"), h("th", {}))),
      h("tbody", {}, data.items.map((q) => h("tr", { class: "click", onclick: (e) => { if (!e.target.closest("button,input,a")) openDetail(q.id); } },
        h("td", {}, h("input", { type: "checkbox", checked: selected.has(q.id), onchange: (e) => { e.target.checked ? selected.add(q.id) : selected.delete(q.id); renderBar(); } })),
        h("td", {}, h("div", { class: "trunc", style: { maxWidth: "640px", whiteSpace: "normal", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" } }, q.statement),
          h("div", { class: "row small muted", style: { marginTop: "4px", gap: "6px" } }, h("span", {}, q.subject_name), q.topics.map((t) => h("span", { class: "chip" }, t.name)), q.bank ? h("span", {}, `· ${q.bank}`) : null, q.year ? h("span", {}, `· ${q.year}`) : null, q.flagged ? h("span", { class: "warn" }, "⚑") : null)),
        h("td", {}, status(q)),
        h("td", { style: { whiteSpace: "nowrap" } }, h("button", { class: "btn sm", onclick: () => createSession({ kind: "avulsa", question_ids: [q.id] }).catch(fail) }, "Resolver")))))));
  }
  function renderPager() {
    const pages = Math.max(1, Math.ceil(data.total / PER));
    pager.replaceChildren(h("button", { class: "btn sm", disabled: page <= 1, onclick: () => { page--; load(); } }, "← Anterior"), h("span", { class: "muted" }, `Página ${page} de ${pages}`), h("button", { class: "btn sm", disabled: page >= pages, onclick: () => { page++; load(); } }, "Próxima →"));
  }
  async function load() {
    try { data = await api("/questions" + qs({ ...filters.get(), page, per_page: PER })); }
    catch (e) { fail(e); return; }
    renderBar(); renderList(); renderPager();
  }

  async function openDetail(id) {
    const q = await api(`/questions/${id}`).catch(fail); if (!q) return;
    const tax = filters.tax;
    const body = h("div", { class: "stack" });
    const draw = (q) => {
      const free = topicOptions(tax.topics, q.subject_id).filter((o) => !q.topics.some((t) => t.id === o.value));
      const addSel = h("select", {}, h("option", { value: "" }, "Adicionar assunto…"), free.map((o) => h("option", { value: o.value }, o.label)));
      addSel.onchange = async () => { if (addSel.value) { await api(`/questions/${q.id}`, { method: "PATCH", body: { add_topic_ids: [Number(addSel.value)] } }).catch(fail); refresh(); } };
      body.replaceChildren(
        h("div", { class: "row small muted" }, h("span", {}, q.subject_name), q.external_id ? h("span", {}, `· ${q.external_id}`) : null, q.bank ? h("span", {}, `· ${q.bank}`) : null, q.year ? h("span", {}, `· ${q.year}`) : null, q.exam_name ? h("span", {}, `· ${q.exam_name}`) : null, q.difficulty ? h("span", {}, `· ${q.difficulty}`) : null),
        q.support_text ? h("div", { class: "support" }, q.support_text) : null,
        h("div", { class: "statement", style: { fontSize: "15.5px" } }, q.statement),
        q.images.map((im) => safeImgSrc(im.src) ? h("img", { class: "qimg", src: im.src, alt: im.caption || "Imagem da questão" }) : null),
        h("div", { class: "alts", style: { margin: "4px 0" } }, Object.entries(q.alternatives).map(([L, T]) => h("div", { class: `alt ${L === q.correct_answer ? "right" : ""}`, "aria-disabled": "true" }, h("span", { class: "L" }, L), h("span", { class: "T" }, T)))),
        q.explanation ? h("div", {}, h("h3", {}, "Explicação"), h("p", { class: "expl" }, q.explanation)) : h("p", { class: "muted small" }, "Esta questão não tem explicação."),
        h("div", {}, h("h3", { style: { marginBottom: "8px" } }, "Assuntos"), h("div", { class: "row" },
          q.topics.map((t) => h("span", { class: "chip" }, t.name, h("button", { title: "Remover", onclick: async () => { await api(`/questions/${q.id}`, { method: "PATCH", body: { remove_topic_ids: [t.id] } }).catch(fail); refresh(); } }, "✕"))),
          q.topics.length ? null : h("span", { class: "muted small" }, "nenhum"), addSel)),
        q.history.length ? h("div", {}, h("h3", { style: { marginBottom: "6px" } }, "Seu histórico nesta questão"),
          h("div", { class: "list" }, q.history.map((a) => h("div", { class: "li small" }, h("span", { class: `chip ${a.is_correct ? "ok" : "bad"}` }, a.is_correct ? "acertou" : "errou"), h("span", {}, `marcou ${a.chosen} · ${CONF_SHORT[a.confidence]}`), h("span", { class: "muted right" }, fmtDate(a.answered_at)))))) : null);
    };
    const refresh = async () => { draw(await api(`/questions/${id}`)); load(); };
    draw(q);
    modal({ title: `Questão ${q.external_id || "#" + q.id}`, body, actions: [
      { label: "Marcar/desmarcar ⚑", class: "ghost", close: false, onClick: async () => { const r = await api(`/questions/${id}/flag`, { method: "POST" }); toast(r.flagged ? "Questão marcada." : "Marcação removida.", "success", 1800); load(); return false; } },
      { label: "Resolver", class: "primary", onClick: () => createSession({ kind: "avulsa", question_ids: [id] }) }] });
  }
  load();
}
