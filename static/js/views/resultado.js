import { h, api, clear, fail, toast, empty, pct, fmtDuration, accBar, CONF, CONF_SHORT, KIND_LABEL, createSession, safeImgSrc, aiBadge } from "../lib.js";

export default async function (root, id) {
  const [r, meta] = await Promise.all([api(`/sessions/${id}/results`).catch(async (e) => {
    if (e.status === 409) { location.hash = `#/sessao/${id}`; return null; } throw e;
  }), api("/meta")]);
  if (!r) return;
  const S = r.summary, s = r.session;
  clear(root);
  root.append(h("div", { class: "page-head" },
    h("div", {}, h("h1", {}, s.title), h("p", {}, `${KIND_LABEL[s.kind] || s.kind} · ${fmtDuration(S.duration_s)}`)),
    h("span", { class: "right" }), h("a", { class: "btn", href: "#/historico" }, "Histórico"), h("a", { class: "btn primary", href: "#/estudar" }, "Nova sessão")));

  const kpi = (v, l, cls = "") => h("div", { class: "card kpi" }, h("div", { class: `v ${cls}` }, v), h("div", { class: "l" }, l));
  root.append(h("div", { class: "grid g4" },
    kpi(pct(S.accuracy), `aproveitamento (${S.correct}/${S.answered})`, S.accuracy >= 70 ? "ok" : S.accuracy < 50 ? "bad" : "warn"),
    kpi(S.wrong, "erros"), kpi(S.fragile_correct, "acertos com dúvida ou chute"), kpi(S.confident_wrong, "erros com “certeza”")));
  if (S.unanswered) root.append(h("p", { class: "muted small" }, `${S.unanswered} questão(ões) ficaram sem resposta e não entram nas estatísticas.`));

  // confiança x resultado
  const M = r.confidence_matrix;
  const matrix = h("div", { class: "matrix" }, h("div", { class: "h" }, "Confiança"), h("div", { class: "h" }, "Acertos"), h("div", { class: "h" }, "Erros"),
    Object.keys(CONF).flatMap((k) => [h("div", {}, CONF[k]), h("div", { class: M[k].correct ? "ok" : "muted" }, M[k].correct), h("div", { class: M[k].wrong ? "bad" : "muted" }, M[k].wrong)]));
  const topics = h("div", { class: "card" }, h("h2", {}, "Por assunto nesta sessão"),
    r.by_topic.length ? h("div", { class: "list" }, r.by_topic.map((t) => h("div", { class: "li" }, h("div", { class: "grow" }, h("div", { class: "trunc" }, t.name), accBar(Math.round(100 * t.correct / t.n))), h("span", { class: "small muted" }, `${t.correct}/${t.n}`)))) : h("p", { class: "muted small" }, "Sem respostas."));
  root.append(h("div", { class: "grid g2 sp" }, h("div", { class: "card" }, h("h2", {}, "Confiança × resultado"), matrix, h("p", { class: "muted small", style: { marginBottom: 0 } }, "Acerto com dúvida ou chute pode ser conhecimento frágil; erro com certeza pode indicar uma ideia equivocada.")), topics));

  // diagnóstico da sessão (lacunas)
  const diag = h("div", { class: "card sp" });
  root.append(diag);
  const drawDiag = async () => {
    let an, ai;
    try { [an, ai] = await Promise.all([api(`/sessions/${id}/analysis`), api("/ai/status")]); } catch { return; }
    const col = (title, cls, list) => h("div", {}, h("h3", { class: cls, style: { marginBottom: "6px" } }, `${title} (${list.length})`),
      list.length ? h("ul", { style: { margin: 0, paddingLeft: "18px" } }, list.map((i) => h("li", {}, i.label, i.concept ? [" ", aiBadge("✦")] : null))) : h("span", { class: "muted small" }, "—"));
    const need = an.gaps.length + an.fragile.length + an.guessed.length;
    diag.replaceChildren(h("h2", {}, "Diagnóstico desta sessão"),
      an.small_sample ? h("p", { class: "muted small", style: { marginTop: 0 } }, `Amostra pequena (${an.total_answered} resposta(s)): é uma sondagem inicial, não um diagnóstico definitivo.`) : null,
      h("div", { class: "grid g2" }, col("Conhecimento demonstrado", "ok", an.demonstrated), col("Lacunas (erros)", "bad", an.gaps), col("Conhecimento frágil (acerto com dúvida)", "warn", an.fragile), col("Acertos por chute", "warn", an.guessed)),
      h("div", { class: "row sp" },
        need ? h("a", { class: "btn primary", href: `#/lacunas?sessao=${id}` }, `Estudar as ${need} lacuna(s)`) : h("span", { class: "ok" }, "Nenhuma lacuna nesta sessão."),
        an.unnamed && ai.configured ? h("button", { class: "btn", onclick: async (e) => { e.currentTarget.disabled = true; e.currentTarget.textContent = "Nomeando…"; await api("/gaps/name-concepts", { method: "POST", body: { session_id: Number(id) } }).catch(fail); drawDiag(); } }, `✦ Nomear lacunas com IA (${an.unnamed})`) : null),
      an.unnamed && !ai.configured ? h("p", { class: "muted small" }, "Sem IA, os itens aparecem pelo assunto. Configure a chave em Configurações → IA para nomear o conhecimento específico de cada lacuna.") : null);
  };
  drawDiag();

  // ações
  const wrongIds = r.items.filter((i) => i.answer && !i.answer.is_correct).map((i) => i.question_id);
  const fragileIds = r.items.filter((i) => i.answer && i.answer.is_correct && i.answer.confidence !== "certeza").map((i) => i.question_id);
  const redo = [...new Set([...wrongIds, ...fragileIds])];
  if (redo.length) root.append(h("div", { class: "row sp" }, h("button", { class: "btn primary", onclick: () => createSession({ kind: "bateria", question_ids: redo, title: `Refazer: ${s.title}` }).catch(fail) }, `Refazer ${redo.length} questão(ões) erradas ou frágeis`)));

  // questões
  const list = h("div", { class: "stack" });
  r.items.forEach((it) => {
    const a = it.answer;
    const head = h("div", { class: "row" }, h("b", {}, `Questão ${it.position}`), h("span", { class: "chip" }, it.subject_name),
      a ? h("span", { class: `chip ${a.is_correct ? "ok" : "bad"}` }, a.is_correct ? "acertou" : "errou") : h("span", { class: "chip" }, "sem resposta"),
      a ? h("span", { class: `chip ${a.confidence === "certeza" ? "" : "warn"}` }, CONF_SHORT[a.confidence]) : null,
      a ? h("span", { class: "muted small" }, fmtDuration(a.time_s)) : null,
      it.topics.map((t) => h("span", { class: "chip" }, t.name)));
    const det = h("details", { class: "card" }, h("summary", { style: { cursor: "pointer", listStyle: "none" } }, head,
      h("div", { class: "trunc muted small", style: { marginTop: "6px" } }, it.statement)));
    const body = h("div", { class: "stack sp" },
      it.support_text ? h("div", { class: "support" }, it.support_text) : null,
      h("div", { class: "statement", style: { fontSize: "15.5px" } }, it.statement),
      h("div", { class: "alts", style: { margin: 0 } }, Object.entries(it.alternatives).map(([L, T]) => {
        const cls = L === it.correct_answer ? "right" : (a && L === a.chosen ? "wrong" : "");
        return h("div", { class: `alt ${cls}`, "aria-disabled": "true" }, h("span", { class: "L" }, L), h("span", { class: "T" }, T));
      })),
      it.explanation ? h("div", {}, h("h3", {}, "Explicação"), h("p", { class: "expl" }, it.explanation)) : h("p", { class: "muted small" }, "Sem explicação cadastrada."));
    if (a && !a.is_correct) {
      const note = h("input", { placeholder: "Anotação opcional", value: a.error_note || "", style: { width: "100%" } });
      const save = () => api(`/answers/${a.id}`, { method: "PATCH", body: { error_type: a.error_type, error_note: note.value } }).catch(fail);
      note.onblur = () => { a.error_note = note.value; save(); };
      const chipBox = h("div", { class: "row", style: { gap: "6px" } });
      const draw = () => chipBox.replaceChildren(...Object.entries(meta.error_types).map(([k, label]) =>
        h("button", { class: `btn sm ${a.error_type === k ? "primary" : "ghost"}`, onclick: async () => { a.error_type = a.error_type === k ? null : k; a.error_note = note.value; await save(); draw(); } }, label)));
      draw();
      body.append(h("div", { class: "stack" }, h("div", { class: "small muted" }, "Causa do erro:"), chipBox, note));
    }
    if (a) body.append(h("div", { class: "row" }, h("a", { class: "btn sm", href: `#/tutor?q=${it.question_id}` }, "✦ Perguntar ao tutor"), !a.is_correct || a.confidence !== "certeza" ? h("a", { class: "btn sm", href: `#/lacuna/${it.question_id}` }, "Estudar esta lacuna") : null));
    det.append(body);
    list.append(det);
  });
  root.append(h("h2", { class: "sp", style: { marginBottom: "10px" } }, "Questões"), list);
}
