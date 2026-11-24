import { h, api, clear, fail, toast, empty, formModal, confirmDialog } from "../lib.js";
import { topicOptions } from "../components/filters.js";

export default async function (root) {
  async function load() {
    const tax = await api("/taxonomy");
    draw(tax);
  }
  const reload = () => load().catch(fail);
  const act = (label, fn, cls = "") => h("button", { class: `btn sm ghost ${cls}`, onclick: (e) => { e.stopPropagation(); fn(); } }, label);

  function draw(tax) {
    clear(root);
    root.append(h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Disciplinas e assuntos"), h("p", {}, "Concurso → disciplina → assunto → subassunto. Uma questão pode ter vários assuntos.")),
      h("span", { class: "right" }),
      h("button", { class: "btn", onclick: newExam }, "Novo concurso/prova"),
      h("button", { class: "btn primary", onclick: () => newSubject(tax) }, "Nova disciplina")));

    const groups = [...tax.exams.map((e) => ({ exam: e, subjects: tax.subjects.filter((s) => s.exam_id === e.id) })),
      { exam: null, subjects: tax.subjects.filter((s) => !s.exam_id) }];
    if (!tax.subjects.length && !tax.exams.length) {
      root.append(h("div", { class: "card" }, empty("Nada por aqui ainda", "Crie uma disciplina ou importe questões: disciplinas e assuntos são criados automaticamente na importação.", h("a", { class: "btn", href: "#/importar" }, "Importar questões"))));
      return;
    }
    for (const g of groups) {
      if (!g.exam && !g.subjects.length) continue;
      const card = h("div", { class: "card", style: { marginBottom: "16px" } });
      card.append(h("div", { class: "row", style: { marginBottom: "10px" } },
        h("h2", { style: { margin: 0 } }, g.exam ? g.exam.name : "Sem concurso"), h("span", { class: "chip" }, `${g.subjects.length} disciplina(s)`), h("span", { class: "right" }),
        g.exam ? [act("Renomear", () => renameExam(g.exam)), act("Excluir", () => delExam(g.exam), "danger")] : null));
      if (!g.subjects.length) card.append(h("p", { class: "muted small" }, "Nenhuma disciplina neste concurso."));
      const ul = h("ul", { style: { listStyle: "none", margin: 0, padding: 0 } });
      g.subjects.forEach((s) => ul.append(h("li", {}, subjectNode(s, tax))));
      card.append(h("div", { class: "tree" }, ul));
      root.append(card);
    }
  }

  function subjectNode(s, tax) {
    const topics = tax.topics.filter((t) => t.subject_id === s.id);
    const wrap = h("div");
    wrap.append(h("div", { class: "node sub" }, h("span", {}, s.name), h("span", { class: "chip" }, `${s.question_count} questões`),
      h("span", { class: "acts" }, act("+ assunto", () => newTopic(s, null)), act("Editar", () => editSubject(s, tax)), act("Excluir", () => delSubject(s), "danger"))));
    const build = (parent) => {
      const kids = topics.filter((t) => (t.parent_id ?? null) === parent);
      if (!kids.length) return null;
      return h("ul", {}, kids.map((t) => h("li", {}, h("div", { class: "node" }, h("span", {}, t.name), h("span", { class: "muted small" }, `${t.question_count}`),
        h("span", { class: "acts" }, act("+ subassunto", () => newTopic(s, t.id)), act("Editar", () => editTopic(t, tax)), act("Excluir", () => delTopic(t), "danger"))), build(t.id))));
    };
    wrap.append(build(null));
    return wrap;
  }

  const newExam = () => formModal({ title: "Novo concurso/prova", fields: [{ name: "name", label: "Nome", placeholder: "ex.: Banco do Brasil" }], onSubmit: async (v) => { await api("/exams", { method: "POST", body: v }); reload(); } });
  const renameExam = (e) => formModal({ title: "Renomear concurso", fields: [{ name: "name", label: "Nome", value: e.name }], onSubmit: async (v) => { await api(`/exams/${e.id}`, { method: "PATCH", body: v }); reload(); } });
  const delExam = async (e) => { if (await confirmDialog(`Excluir “${e.name}”? As disciplinas ficam sem concurso; nada mais é apagado.`, { confirmLabel: "Excluir", danger: true })) { await api(`/exams/${e.id}`, { method: "DELETE" }).catch(fail); reload(); } };
  const examOpts = (tax) => [{ value: "", label: "Sem concurso" }, ...tax.exams.map((e) => ({ value: e.id, label: e.name }))];
  const newSubject = (tax) => formModal({ title: "Nova disciplina", fields: [{ name: "name", label: "Nome", placeholder: "ex.: Língua Portuguesa" }, { name: "exam_id", label: "Concurso", options: examOpts(tax) }],
    onSubmit: async (v) => { await api("/subjects", { method: "POST", body: { name: v.name, exam_id: v.exam_id || null } }); reload(); } });
  const editSubject = (s, tax) => formModal({ title: "Editar disciplina", fields: [{ name: "name", label: "Nome", value: s.name }, { name: "exam_id", label: "Concurso", options: examOpts(tax), value: s.exam_id ?? "" }],
    onSubmit: async (v) => { await api(`/subjects/${s.id}`, { method: "PATCH", body: { name: v.name, exam_id: v.exam_id || null } }); reload(); } });
  const delSubject = async (s) => { if (await confirmDialog(`Excluir a disciplina “${s.name}” e seus assuntos?`, { confirmLabel: "Excluir", danger: true })) { await api(`/subjects/${s.id}`, { method: "DELETE" }).catch(fail); reload(); } };
  const newTopic = (s, parent) => formModal({ title: parent ? "Novo subassunto" : `Novo assunto em ${s.name}`, fields: [{ name: "name", label: "Nome" }],
    onSubmit: async (v) => { await api("/topics", { method: "POST", body: { name: v.name, subject_id: s.id, parent_id: parent } }); reload(); } });
  const editTopic = (t, tax) => {
    const blocked = new Set(descendantIds(tax.topics, t.id));
    const opts = [{ value: "", label: "(raiz da disciplina)" }, ...topicOptions(tax.topics, t.subject_id).filter((o) => !blocked.has(o.value))];
    formModal({ title: "Editar assunto", fields: [{ name: "name", label: "Nome", value: t.name }, { name: "parent_id", label: "Dentro de", options: opts, value: t.parent_id ?? "" }],
      onSubmit: async (v) => { await api(`/topics/${t.id}`, { method: "PATCH", body: { name: v.name, parent_id: v.parent_id || null } }); reload(); } });
  };
  const delTopic = async (t) => { if (await confirmDialog(`Excluir o assunto “${t.name}” e seus subassuntos? As questões continuam existindo, apenas perdem esse vínculo.`, { confirmLabel: "Excluir", danger: true })) { await api(`/topics/${t.id}`, { method: "DELETE" }).catch(fail); reload(); } };

  function descendantIds(topics, id) {
    const out = [id];
    topics.filter((t) => t.parent_id === id).forEach((c) => out.push(...descendantIds(topics, c.id)));
    return out;
  }
  await load();
}
