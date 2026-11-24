import { h, api, clear, fail } from "../lib.js";
import { createTutor } from "../components/tutor.js";

export default async function (root) {
  const q = new URLSearchParams(location.hash.split("?")[1] || "").get("q");
  const [gaps, ai] = await Promise.all([api("/gaps"), api("/ai/status")]);
  let thread = q ? `q:${q}` : "free";
  clear(root);
  const box = h("div", { class: "card" });
  const options = [{ value: "free", label: "Conversa livre" }, ...gaps.items.slice(0, 40).map((g) => ({ value: `q:${g.question_id}`, label: `Questão: ${g.concept || g.statement.slice(0, 70)}` }))];
  if (q && !options.some((o) => o.value === thread)) options.push({ value: thread, label: `Questão #${q}` });
  const sel = h("select", { onchange: (e) => { thread = e.target.value; load(); } }, options.map((o) => h("option", { value: o.value, selected: o.value === thread }, o.label)));
  root.append(h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Tutor IA"), h("p", {}, "Tire dúvidas sobre um assunto ou sobre uma questão que você errou."))),
    !ai.configured ? h("div", { class: "card", style: { marginBottom: "14px" } }, h("b", {}, "A IA ainda não está configurada. "), h("a", { href: "#/configuracoes" }, "Informe sua chave de API"), ".") : null,
    h("label", { class: "field", style: { maxWidth: "520px", marginBottom: "14px" } }, "Assunto da conversa", sel), box);
  async function load() {
    try { box.replaceChildren(await createTutor({ thread })); } catch (e) { box.replaceChildren(h("p", { class: "muted" }, e.message)); }
  }
  await load();
}
