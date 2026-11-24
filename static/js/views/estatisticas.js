import { h, api, qs, clear, empty, accBar, pct, fmtDuration, CONF } from "../lib.js";

export default async function (root) {
  let days = "";
  const box = h("div");
  clear(root);
  const sel = h("select", { onchange: (e) => { days = e.target.value; load(); } },
    [["", "Todo o período"], ["7", "Últimos 7 dias"], ["30", "Últimos 30 dias"], ["90", "Últimos 90 dias"]].map(([v, l]) => h("option", { value: v }, l)));
  root.append(h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Estatísticas"), h("p", {}, "Números para decidir o que estudar, não só para enfeitar.")), h("span", { class: "right" }), sel), box);

  async function load() {
    const s = await api("/stats" + qs({ days, tz: new Date().getTimezoneOffset() }));
    if (!s.overall.answered) { box.replaceChildren(h("div", { class: "card" }, empty("Sem respostas no período", "Resolva algumas questões para ver suas estatísticas.", h("a", { class: "btn primary", href: "#/estudar" }, "Estudar")))); return; }
    const table = (title, rows, { nameKey = "name", extra, hint } = {}) => h("div", { class: "card" }, h("h2", {}, title), hint ? h("p", { class: "muted small", style: { marginTop: 0 } }, hint) : null,
      rows.length ? h("div", { class: "list" }, rows.map((r) => h("div", { class: "li" },
        h("div", { class: "grow" }, h("div", { class: "trunc" }, r[nameKey], extra ? h("span", { class: "muted small" }, ` · ${r[extra]}`) : null), accBar(r.accuracy)),
        h("div", { class: "small muted", style: { minWidth: "96px", textAlign: "right" } }, `${pct(r.accuracy)} · ${r.c}/${r.n}`)))) : h("p", { class: "muted small" }, "Sem dados."));
    const kpi = (v, l) => h("div", { class: "card kpi" }, h("div", { class: "v" }, v), h("div", { class: "l" }, l));
    const f = s.facts;
    const conf = s.by_confidence.map((r) => ({ ...r, name: CONF[r.name] || r.name }));
    const max = Math.max(1, ...s.daily.map((d) => d.n));
    const nov = s.novelty.map((r) => ({ ...r, name: r.name === "new" ? "Questões inéditas" : "Questões repetidas (outra sessão)" }));

    box.replaceChildren(
      h("div", { class: "grid g4" }, kpi(s.overall.answered, "respostas"), kpi(pct(s.overall.accuracy), "aproveitamento"), kpi(fmtDuration(s.overall.study_seconds), "tempo respondendo"),
        kpi(f.errors_without_cause, "erros sem causa registrada")),
      h("div", { class: "card sp" }, h("h2", {}, "Pontos de atenção (fatos do período)"), h("ul", { style: { margin: 0, paddingLeft: "18px" } },
        h("li", {}, `${f.confident_wrong} erro(s) com “Tenho certeza”: candidatos a ideias equivocadas.`),
        h("li", {}, `${f.guess_correct} acerto(s) marcado(s) como chute: não contam como domínio.`))),
      h("div", { class: "grid g2 sp" }, table("Por disciplina", s.by_subject), table("Confiança × acerto", conf, { hint: "Se “Tenho certeza” não acerta bem mais que “Chutei”, sua percepção do que sabe está descalibrada." })),
      h("div", { class: "grid g2 sp" }, table("Por assunto (piores primeiro)", s.by_topic.slice(0, 15), { extra: "subject" }), h("div", { class: "stack" }, table("Por banca", s.by_bank), table("Inéditas × repetidas", nov))),
      h("div", { class: "grid g2 sp" },
        h("div", { class: "card" }, h("h2", {}, "Causas de erro registradas"), s.by_error_type.length ? h("div", { class: "list" }, s.by_error_type.map((r) => h("div", { class: "li" }, h("div", { class: "grow" }, s.error_labels[r.name] || r.name), h("span", { class: "chip" }, r.n)))) : h("p", { class: "muted small" }, "Ao errar, você pode marcar a causa na própria questão. Elas aparecem aqui.")),
        table("Por prova", s.by_exam)),
      h("div", { class: "card sp" }, h("h2", {}, `Respostas por dia (${s.daily.length} dias)`),
        h("div", { class: "spark" }, s.daily.map((d) => h("div", { class: d.n ? "" : "zero", title: `${d.date}: ${d.n} respostas, ${d.correct} acertos`, style: { height: `${d.n ? Math.max(6, 100 * d.n / max) : 3}%` } }))),
        h("div", { class: "spark-lbl" }, h("span", {}, s.daily[0].date.slice(5).split("-").reverse().join("/")), h("span", {}, "hoje"))));
  }
  await load();
}
