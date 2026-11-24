import { h, api, qs, clear, fail, toast, empty, aiBadge } from "../lib.js";

const KIND = { lacuna: ["Erro", "bad"], chute: ["Acerto por chute", "warn"], fragil: ["Acerto com dúvida", "warn"] };

export default async function (root) {
  const sess = new URLSearchParams((location.hash.split("?")[1] || "")).get("sessao");
  const [data, ai] = await Promise.all([api("/gaps" + qs({ session_id: sess })), api("/ai/status")]);
  const items = data.items;
  clear(root);
  root.append(h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Lacunas"), h("p", {}, sess ? "Lacunas desta sessão." : "Erros e acertos sem certeza que ainda não foram consolidados com estudo.")),
    h("span", { class: "right" }), sess ? h("a", { class: "btn ghost", href: "#/lacunas" }, "Ver todas") : null));
  if (!items.length) {
    root.append(h("div", { class: "card" }, empty("Nenhuma lacuna aberta", "Responda questões (com a confiança marcada) para que o app identifique o que precisa de estudo.", h("a", { class: "btn primary", href: "#/estudar" }, "Estudar"))));
    return;
  }
  const unnamed = items.filter((i) => !i.concept).length;
  const head = h("div", { class: "row", style: { marginBottom: "14px" } },
    h("span", { class: "muted" }, `${items.length} lacuna(s)`),
    items.some((i) => i.confident_wrong) ? h("span", { class: "chip bad", title: "Erros marcados com 'Tenho certeza' podem indicar uma ideia equivocada" }, `${items.filter((i) => i.confident_wrong).length} erro(s) com certeza`) : null,
    h("span", { class: "right" }),
    unnamed && ai.configured ? h("button", { class: "btn", onclick: async (e) => {
      e.currentTarget.disabled = true; e.currentTarget.textContent = "Nomeando…";
      try { const r = await api("/gaps/name-concepts", { method: "POST", body: { question_ids: items.filter((i) => !i.concept).map((i) => i.question_id) } }); toast(`${r.named} lacuna(s) nomeada(s).`, "success"); location.reload(); }
      catch (err) { fail(err); location.reload(); }
    } }, `✦ Nomear ${unnamed} lacuna(s) com IA`) : null,
    h("a", { class: "btn primary", href: `#/lacuna/${items[0].question_id}` }, "Estudar a primeira"));
  root.append(head);

  const groups = new Map();
  items.forEach((i) => { const k = i.topics[0]?.name || `(${i.subject_name} — sem assunto)`; (groups.get(k) || groups.set(k, []).get(k)).push(i); });
  for (const [name, list] of groups) {
    root.append(h("div", { class: "card", style: { marginBottom: "14px" } }, h("h2", {}, name, h("span", { class: "chip" }, list.length)),
      h("div", { class: "list" }, list.map((i) => h("div", { class: "li" },
        h("div", { class: "grow" }, h("div", {}, i.concept ? [i.concept, " ", aiBadge("✦ IA")] : h("span", { class: "trunc", style: { display: "block" } }, i.statement)),
          h("div", { class: "row small", style: { marginTop: "4px", gap: "6px" } },
            h("span", { class: `chip ${KIND[i.kind][1]}` }, KIND[i.kind][0]), i.confident_wrong ? h("span", { class: "chip bad" }, "com certeza") : null,
            i.studied ? h("span", { class: "chip" }, `estudada: ${i.studied.label}`) : null,
            i.error_type ? h("span", { class: "chip" }, i.error_type) : null)),
        h("a", { class: "btn sm primary", href: `#/lacuna/${i.question_id}` }, i.studied ? "Estudar de novo" : "Estudar"))))));
  }
}
