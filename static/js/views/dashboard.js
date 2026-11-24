import { h, api, qs, clear, fail, empty, accBar, pct, fmtDuration, fmtDate, createSession, KIND_LABEL, go } from "../lib.js";

export default async function (root) {
  const d = await api("/dashboard" + qs({ tz: new Date().getTimezoneOffset() }));
  const t = d.totals;
  clear(root);
  root.append(h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Dashboard"), h("p", {}, "O que estudar agora?"))));

  if (t.questions_total === 0) {
    root.append(h("div", { class: "card" }, empty("Seu banco de questões está vazio",
      "Importe um arquivo JSON com questões para começar a estudar.",
      h("a", { class: "btn primary", href: "#/importar" }, "Importar questões"))));
    return;
  }

  const s = d.suggestion;
  const startSuggestion = async () => {
    try {
      if (s.kind === "gaps") return go("#/lacunas");
      if (s.kind === "review") { const r = await api("/reviews/session", { method: "POST", body: { limit: 15 } }); return go(`#/sessao/${r.id}`); }
      await createSession({ kind: s.session_kind, filters: s.filters, limit: s.limit, order: "random" });
    } catch (e) { fail(e); }
  };
  root.append(h("div", { class: "card hero" },
    h("div", { class: "grow" }, h("div", { class: "muted small" }, "Sugestão de agora"), h("h2", {}, s.title), h("div", { class: "muted" }, s.reason)),
    s.kind === "import" ? h("a", { class: "btn primary lg", href: "#/importar" }, "Importar") : h("button", { class: "btn primary lg", onclick: startSuggestion }, "Começar"),
    h("a", { class: "btn ghost", href: "#/estudar" }, "Outras opções")));

  if (d.in_progress.length) {
    root.append(h("div", { class: "card sp" }, h("h2", {}, "Sessões em andamento"),
      h("div", { class: "list" }, d.in_progress.map((x) => h("div", { class: "li" },
        h("div", { class: "grow" }, h("div", { class: "trunc" }, x.title), h("div", { class: "muted small" }, `${x.answered}/${x.total} respondidas · ${fmtDate(x.started_at)}`)),
        h("a", { class: "btn sm primary", href: `#/sessao/${x.id}` }, "Continuar"))))));
  }

  const kpi = (v, l) => h("div", { class: "card kpi" }, h("div", { class: "v" }, v), h("div", { class: "l" }, l));
  root.append(h("div", { class: "grid g4 sp" },
    kpi(t.answered, "respostas registradas"),
    kpi(pct(t.accuracy), `aproveitamento (${t.correct} certas · ${t.wrong} erradas)`),
    kpi(`${t.questions_seen}/${t.questions_total}`, "questões já vistas"),
    kpi(fmtDuration(t.study_seconds), "tempo respondendo")));
  root.append(h("div", { class: "grid g2 sp" },
    h("a", { class: "card kpi", href: "#/revisoes", style: { color: "inherit", textDecoration: "none" } }, h("div", { class: `v ${t.reviews_due ? "warn" : ""}` }, t.reviews_due), h("div", { class: "l" }, "revisões pendentes")),
    h("a", { class: "card kpi", href: "#/lacunas", style: { color: "inherit", textDecoration: "none" } }, h("div", { class: `v ${t.open_gaps ? "warn" : ""}` }, t.open_gaps), h("div", { class: "l" }, "lacunas abertas para estudar"))));

  const weak = h("div", { class: "card" }, h("h2", {}, "Assuntos com mais dificuldade"));
  if (!d.weak_topics.length) weak.append(h("p", { class: "muted small" }, "Aparecem aqui assuntos com pelo menos 3 respostas registradas."));
  else weak.append(h("div", { class: "list" }, d.weak_topics.map((w) => h("div", { class: "li" },
    h("div", { class: "grow" }, h("div", { class: "trunc" }, w.name), accBar(w.accuracy)),
    h("div", { class: "small muted", style: { width: "92px", textAlign: "right" } }, `${pct(w.accuracy)} · ${w.n} resp.`),
    h("button", { class: "btn sm", onclick: () => createSession({ kind: "bateria", filters: { topic_id: w.id }, limit: 10 }).catch(fail) }, "Praticar")))));

  const prog = h("div", { class: "card" }, h("h2", {}, "Progresso por disciplina"),
    h("div", { class: "list" }, d.subject_progress.map((p) => h("div", { class: "li" },
      h("div", { class: "grow" }, h("div", { class: "trunc" }, p.name), h("div", { class: "bar" }, h("i", { style: { width: `${Math.round(100 * p.seen / p.total)}%` } }))),
      h("div", { class: "small muted", style: { textAlign: "right", minWidth: "120px" } }, `${p.seen}/${p.total} vistas`, h("br"), `acerto ${pct(p.accuracy)}`)))));
  root.append(h("div", { class: "grid g2 sp" }, weak, prog));

  const max = Math.max(1, ...d.activity.map((a) => a.n));
  const act = h("div", { class: "card" }, h("h2", {}, "Atividade nos últimos 14 dias"),
    h("div", { class: "spark" }, d.activity.map((a) => h("div", { class: a.n ? "" : "zero", title: `${a.date}: ${a.n} respostas, ${a.correct} acertos`, style: { height: `${a.n ? Math.max(6, 100 * a.n / max) : 3}%` } }))),
    h("div", { class: "spark-lbl" }, h("span", {}, d.activity[0].date.slice(5).split("-").reverse().join("/")), h("span", {}, "hoje")));
  const rec = h("div", { class: "card" }, h("h2", {}, "Últimas sessões"));
  if (!d.recent_sessions.length) rec.append(h("p", { class: "muted small" }, "Nenhuma sessão finalizada ainda."));
  else rec.append(h("div", { class: "list" }, d.recent_sessions.map((x) => h("div", { class: "li" },
    h("div", { class: "grow" }, h("div", { class: "trunc" }, x.title), h("div", { class: "muted small" }, `${KIND_LABEL[x.kind] || x.kind} · ${fmtDate(x.finished_at)} · ${fmtDuration(x.time_s)}`)),
    h("span", { class: `chip ${x.answered && x.correct / x.answered >= .7 ? "ok" : x.answered ? "warn" : ""}` }, `${x.correct}/${x.answered}`),
    h("a", { class: "btn sm", href: `#/sessao/${x.id}/resultado` }, "Ver")))));
  root.append(h("div", { class: "grid g2 sp" }, act, rec));

  if (t.fragile || t.wrong_last) {
    root.append(h("div", { class: "card sp row" },
      h("span", { class: "muted" }, "Para revisar:"),
      t.wrong_last ? h("button", { class: "btn sm", onclick: () => createSession({ kind: "bateria", filters: { status: "wrong" }, limit: 10 }).catch(fail) }, `${t.wrong_last} erradas na última vez`) : null,
      t.fragile ? h("button", { class: "btn sm", onclick: () => createSession({ kind: "bateria", filters: { status: "fragile" }, limit: 10 }).catch(fail) }, `${t.fragile} acertos frágeis`) : null));
  }
}
