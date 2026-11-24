import { h, api, clear, fail, empty, fmtDate, fmtDuration, pct, confirmDialog, KIND_LABEL } from "../lib.js";

export default async function (root) {
  const PER = 20;
  let offset = 0, all = [];
  clear(root);
  root.append(h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Histórico"), h("p", {}, "Todas as suas sessões de estudo."))));
  const box = h("div", { class: "card" }), more = h("div", { class: "row sp", style: { justifyContent: "center" } });
  root.append(box, more);

  async function load() {
    const batch = await api(`/sessions?limit=${PER}&offset=${offset}`);
    all = all.concat(batch); offset += batch.length;
    draw(batch.length === PER);
  }
  function draw(hasMore) {
    if (!all.length) { box.replaceChildren(empty("Nenhuma sessão ainda", "Suas sessões aparecem aqui.", h("a", { class: "btn primary", href: "#/estudar" }, "Estudar agora"))); more.replaceChildren(); return; }
    box.replaceChildren(h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Sessão"), h("th", {}, "Tipo"), h("th", {}, "Quando"), h("th", {}, "Resultado"), h("th", {}, "Tempo"), h("th", {}))),
      h("tbody", {}, all.map((x) => {
        const fin = !!x.finished_at;
        return h("tr", {},
          h("td", {}, h("div", { class: "trunc", style: { maxWidth: "280px" } }, x.title)),
          h("td", {}, KIND_LABEL[x.kind] || x.kind),
          h("td", { class: "muted" }, fmtDate(x.started_at)),
          h("td", {}, fin ? h("span", { class: "chip" }, `${x.correct}/${x.answered} · ${pct(x.answered ? Math.round(100 * x.correct / x.answered) : null)}`) : h("span", { class: "chip warn" }, `em andamento ${x.answered}/${x.total}`)),
          h("td", { class: "muted" }, fmtDuration(x.time_s)),
          h("td", { style: { whiteSpace: "nowrap", textAlign: "right" } },
            h("a", { class: "btn sm", href: fin ? `#/sessao/${x.id}/resultado` : `#/sessao/${x.id}` }, fin ? "Resultado" : "Continuar"), " ",
            h("button", { class: "btn sm ghost danger", title: "Excluir sessão e suas respostas", onclick: async () => {
              if (!(await confirmDialog("Excluir esta sessão e suas respostas? As estatísticas serão recalculadas.", { confirmLabel: "Excluir", danger: true }))) return;
              await api(`/sessions/${x.id}`, { method: "DELETE" }).catch(fail); all = all.filter((s) => s.id !== x.id); offset--; draw(hasMore);
            } }, "Excluir")));
      }))));
    more.replaceChildren(hasMore ? h("button", { class: "btn", onclick: () => load().catch(fail) }, "Carregar mais") : null);
  }
  await load();
}
