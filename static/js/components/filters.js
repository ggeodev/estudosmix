import { h, api } from "../lib.js";

export const STATUS_OPTIONS = [
  ["", "Todas"], ["unseen", "Inéditas"], ["answered", "Já respondidas"], ["wrong", "Erradas na última vez"],
  ["fragile", "Acertos frágeis (dúvida/chute)"], ["correct", "Certas na última vez"], ["flagged", "Marcadas"],
];

export function topicOptions(topics, subjectId) {
  const list = topics.filter((t) => String(t.subject_id) === String(subjectId));
  const out = [];
  const walk = (parent, depth) => {
    list.filter((t) => (t.parent_id ?? null) === parent).forEach((t) => {
      out.push({ value: t.id, label: `${"— ".repeat(depth)}${t.name}` });
      walk(t.id, depth + 1);
    });
  };
  walk(null, 0);
  return out;
}

/** Barra de filtros reutilizada no banco de questões e na tela de estudo. */
export async function createFilters({ initial = {}, onChange, search = true, fields } = {}) {
  const [tax, facets] = await Promise.all([api("/taxonomy"), api("/questions/facets")]);
  const state = { ...initial };
  const show = (f) => !fields || fields.includes(f);
  const root = h("div", { class: "filters" });
  const controls = {};

  const set = (key, value) => {
    state[key] = value;
    if (key === "subject_id") { state.topic_id = ""; renderTopic(); }
    onChange?.({ ...state });
  };
  const select = (key, label, options) => {
    const el = h("select", { onchange: (e) => set(key, e.target.value) },
      h("option", { value: "" }, "Todos"),
      options.map((o) => h("option", { value: o.value, selected: String(state[key] ?? "") === String(o.value) }, o.label)));
    controls[key] = el;
    return h("label", { class: "field" }, label, el);
  };
  const topicWrap = h("div");
  function renderTopic() {
    topicWrap.replaceChildren(select("topic_id", "Assunto",
      state.subject_id ? topicOptions(tax.topics, state.subject_id) : []));
    topicWrap.firstChild.querySelector("select").disabled = !state.subject_id;
  }

  if (show("exam_id") && tax.exams.length) root.append(select("exam_id", "Concurso", tax.exams.map((e) => ({ value: e.id, label: e.name }))));
  if (show("subject_id")) root.append(select("subject_id", "Disciplina", tax.subjects.map((s) => ({ value: s.id, label: s.name }))));
  if (show("topic_id")) { renderTopic(); root.append(topicWrap); }
  if (show("bank")) root.append(select("bank", "Banca", facets.bank.map((v) => ({ value: v, label: v }))));
  if (show("year")) root.append(select("year", "Ano", [...facets.year].reverse().map((v) => ({ value: v, label: v }))));
  if (show("exam_name")) root.append(select("exam_name", "Prova", facets.exam_name.map((v) => ({ value: v, label: v }))));
  if (show("difficulty")) root.append(select("difficulty", "Dificuldade", facets.difficulty.map((v) => ({ value: v, label: v }))));
  if (show("status")) {
    const el = h("select", { onchange: (e) => set("status", e.target.value) },
      STATUS_OPTIONS.map(([v, l]) => h("option", { value: v, selected: (state.status || "") === v }, l)));
    root.append(h("label", { class: "field" }, "Situação", el));
  }
  if (search && show("q")) {
    let timer;
    root.append(h("label", { class: "field" }, "Buscar no texto",
      h("input", { type: "search", value: state.q || "", placeholder: "palavra ou ID…", oninput: (e) => {
        clearTimeout(timer); const v = e.target.value; timer = setTimeout(() => set("q", v), 300);
      } })));
  }
  return { el: root, get: () => ({ ...state }), tax, facets };
}
