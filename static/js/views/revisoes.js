import { h, api, clear, fail, empty, fmtDate, daysLabel, createSession } from "../lib.js";

export default async function (root) {
  const [ov, recs] = await Promise.all([api("/reviews"), api("/study/records")]);
  clear(root);
  root.append(h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Revisões"), h("p", {}, "O app traz de volta o que você errou ou acertou sem certeza."))));
  if (!ov.tracked) {
    root.append(h("div", { class: "card" }, empty("Nada para revisar ainda", "Depois que você responder questões, elas passam a ser agendadas aqui.", h("a", { class: "btn primary", href: "#/estudar" }, "Estudar"))));
    return;
  }
  const n = h("input", { type: "number", min: 1, value: Math.min(15, Math.max(1, ov.due_count)), style: { width: "80px" } });
  root.append(h("div", { class: "card hero" },
    h("div", { class: "grow" }, h("div", { class: "muted small" }, "Pendentes agora"), h("h2", {}, ov.due_count ? `${ov.due_count} questão(ões) para revisar` : "Nenhuma revisão pendente"),
      h("div", { class: "muted" }, ov.due_count ? "Erros e dúvidas vêm primeiro; as disciplinas são intercaladas na sessão." : `${ov.tracked} questão(ões) em acompanhamento.`)),
    ov.due_count ? h("div", { class: "row" }, h("label", { class: "field" }, "Quantas?", n), h("button", { class: "btn primary lg", onclick: async () => {
      try { const r = await api("/reviews/session", { method: "POST", body: { limit: Number(n.value) || 15 } }); location.hash = `#/sessao/${r.id}`; } catch (e) { fail(e); }
    } }, "Iniciar revisão")) : null));

  const due = h("div", { class: "card" }, h("h2", {}, "Pendentes"));
  if (!ov.due_count) due.append(h("p", { class: "muted small" }, "Nada vencido."));
  else due.append(h("div", { class: "row", style: { marginBottom: "8px" } }, ov.by_subject.map((s) => h("span", { class: "chip" }, `${s.name}: ${s.n}`))),
    h("div", { class: "list" }, ov.due.slice(0, 12).map((r) => h("div", { class: "li" }, h("div", { class: "grow" }, h("div", { class: "trunc" }, r.statement), h("div", { class: "muted small" }, r.subject_name)), h("span", { class: `chip ${r.reason === "errou" ? "bad" : r.reason === "consolidando" ? "" : "warn"}` }, r.reason_label)))));
  const up = h("div", { class: "card" }, h("h2", {}, "Próximos dias"));
  if (!ov.upcoming.length) up.append(h("p", { class: "muted small" }, "Nenhuma revisão agendada para os próximos dias."));
  else up.append(h("div", { class: "list" }, ov.upcoming.map((u) => h("div", { class: "li" }, h("div", { class: "grow" }, new Date(u.date + "T12:00:00").toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit" })), h("span", { class: "chip" }, `${u.n} questão(ões)`)))));
  root.append(h("div", { class: "grid g2 sp" }, due, up));

  const R = ov.rules;
  root.append(h("div", { class: "card sp" }, h("h2", {}, "Estudos de lacunas recentes"),
    recs.length ? h("div", { class: "list" }, recs.map((r) => h("div", { class: "li" }, h("div", { class: "grow" }, h("div", { class: "trunc" }, r.concept || r.statement), h("div", { class: "muted small" }, `${r.subject_name} · ${fmtDate(r.created_at)}`)),
      h("span", { class: `chip ${r.outcome === "correct_confident" ? "ok" : r.outcome === "wrong" ? "bad" : "warn"}` }, r.outcome_label)))) : h("p", { class: "muted small" }, "Quando você concluir o ciclo de estudo de uma lacuna, o resultado fica registrado aqui.")),
    h("details", { class: "card sp" }, h("summary", { style: { cursor: "pointer", fontWeight: 600 } }, "Como as revisões são agendadas"),
      h("p", { class: "muted" }, "Regras iniciais, simples e transparentes. São hipóteses de design, não valores cientificamente ideais; serão ajustadas conforme seus dados reais."),
      h("ul", { style: { paddingLeft: "18px" } },
        h("li", {}, `Errou: volta em ${R.wrong_days} dia.`), h("li", {}, `Acertou chutando: ${R.guess_days} dias.`), h("li", {}, `Acertou com dúvida: ${R.doubt_days} dias.`),
        h("li", {}, `Acertou com certeza: o intervalo cresce a cada acerto seguido (${R.ladder.join(" → ")} dias).`),
        h("li", {}, `Desempenho inconsistente (acertos e erros nas últimas 3 respostas): no máximo ${R.inconsistent_max_days} dias.`))));
}
