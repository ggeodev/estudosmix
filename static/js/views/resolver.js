import { h, api, clear, fail, toast, confirmDialog, safeImgSrc, fmtClock, go, CONF, KIND_LABEL } from "../lib.js";

export default async function (root, id) {
  const [s, meta, settings] = await Promise.all([api(`/sessions/${id}`), api("/meta"), api("/settings")]);
  if (s.finished) { go(`#/sessao/${id}/resultado`); return; }

  const qs = s.questions;
  const each = s.reveal === "each";
  const ans = {};            // resposta salva no servidor, por questão
  const draft = {};          // escolha ainda não confirmada
  const spent = {};          // segundos acumulados por questão
  qs.forEach((q) => { if (q.answer) { ans[q.id] = q.answer; spent[q.id] = q.answer.time_s || 0; } spent[q.id] ||= 0; });
  let idx = Math.max(0, qs.findIndex((q) => !ans[q.id]));
  let t0 = Date.now();
  let finishing = false;

  const elapsed = (qid) => spent[qid] + (Date.now() - t0) / 1000;
  const bank = () => { spent[qs[idx].id] = elapsed(qs[idx].id); t0 = Date.now(); };
  const totalSpent = () => qs.reduce((a, q) => a + (q.id === qs[idx].id ? elapsed(q.id) : spent[q.id]), 0);
  const locked = (q) => each && !!ans[q.id];

  const timerEl = h("span", { class: "chip", title: "Tempo" });
  const tick = () => {
    const q = qs[idx];
    const parts = [];
    if (settings.show_timer) parts.push(fmtClock(elapsed(q.id)));
    if (s.timer_limit_s) {
      const left = s.timer_limit_s - totalSpent();
      parts.push(`restam ${fmtClock(left)}`);
      if (left <= 0 && !finishing) { toast("Tempo esgotado. Finalizando…", "info"); finish(true); }
    }
    timerEl.textContent = parts.join(" · ");
    timerEl.style.display = parts.length ? "" : "none";
  };
  const interval = setInterval(tick, 1000);

  async function finish(force = false) {
    if (finishing) return;
    const unanswered = qs.filter((q) => !ans[q.id]).length;
    if (!force && unanswered) {
      const ok = await confirmDialog(`Há ${unanswered} questão(ões) sem resposta. Finalizar mesmo assim?`, { confirmLabel: "Finalizar" });
      if (!ok) return;
    }
    finishing = true;
    try { await api(`/sessions/${id}/finish`, { method: "POST" }); go(`#/sessao/${id}/resultado`); }
    catch (e) { finishing = false; fail(e); }
  }

  async function confirm() {
    const q = qs[idx], d = draft[q.id] || {};
    const cur = ans[q.id];
    const chosen = d.chosen ?? cur?.chosen, confidence = d.confidence ?? cur?.confidence;
    if (!chosen || !confidence) return;
    const time_s = Math.floor(elapsed(q.id));
    try {
      const r = await api(`/sessions/${id}/answers`, { method: "POST", body: { question_id: q.id, chosen, confidence, time_s } });
      ans[q.id] = { id: r.answer_id, chosen, confidence, time_s, ...(each ? { is_correct: r.is_correct, correct_answer: r.correct_answer, explanation: r.explanation } : {}) };
      delete draft[q.id];
      draw();
    } catch (e) { fail(e); }
  }

  function go_to(i) {
    if (i < 0 || i >= qs.length || i === idx) return;
    bank(); idx = i; draw();
  }

  function draw() {
    const q = qs[idx], a = ans[q.id], d = draft[q.id] || {};
    const chosen = d.chosen ?? a?.chosen, confidence = d.confidence ?? a?.confidence;
    const lock = locked(q);
    const dirty = !!(d.chosen || d.confidence);
    const answeredCount = qs.filter((x) => ans[x.id]).length;

    const alt = ([L, T]) => {
      let cls = "alt";
      if (lock && a) {
        if (L === a.correct_answer) cls += " right";
        else if (L === a.chosen) cls += " wrong";
      } else if (chosen === L) cls += " sel";
      return h("button", { class: cls, "aria-disabled": lock ? "true" : "false", "aria-pressed": chosen === L ? "true" : "false",
        onclick: () => { if (lock) return; draft[q.id] = { ...d, chosen: L }; draw(); } },
        h("span", { class: "L" }, L), h("span", { class: "T" }, T));
    };
    const seg = h("div", { class: "seg", role: "group", "aria-label": "Nível de confiança" },
      Object.entries(CONF).map(([k, label], i) => h("button", { class: confidence === k ? "on" : "", disabled: lock,
        onclick: () => { draft[q.id] = { ...d, confidence: k }; draw(); } }, `${label} `, h("span", { class: "kbd" }, i + 1))));

    const ready = !!chosen && !!confidence;
    const confirmBtn = lock ? null : h("button", { class: "btn primary lg", disabled: !ready || (!!a && !dirty), onclick: confirm },
      a ? "Atualizar resposta" : "Confirmar resposta");

    const children = [
      h("div", { class: "solve-top" },
        h("button", { class: "btn ghost sm", onclick: () => go("#/dashboard"), title: "O progresso fica salvo" }, "← Sair"),
        h("div", { class: "grow", style: { minWidth: 0 } }, h("div", { class: "trunc small muted" }, `${KIND_LABEL[s.kind] || s.kind} · ${s.title}`),
          h("div", { class: "bar" }, h("i", { style: { width: `${100 * answeredCount / qs.length}%` } }))),
        h("span", { class: "muted small" }, `${idx + 1}/${qs.length}`), timerEl,
        h("button", { class: "btn ghost sm", title: "Marcar questão", onclick: async () => { const r = await api(`/questions/${q.id}/flag`, { method: "POST" }).catch(fail); if (r) { q.flagged = r.flagged; draw(); } } }, q.flagged ? "⚑ Marcada" : "⚐ Marcar")),
      h("div", { class: "card" },
        h("div", { class: "qmeta" }, h("span", { class: "chip" }, q.subject_name), q.bank ? h("span", { class: "chip" }, q.bank) : null, q.year ? h("span", { class: "chip" }, q.year) : null, q.exam_name ? h("span", { class: "chip" }, q.exam_name) : null),
        q.support_text ? h("div", { class: "support" }, q.support_text) : null,
        q.images.map((im) => safeImgSrc(im.src) ? h("img", { class: "qimg", src: im.src, alt: im.caption || "Imagem da questão" }) : null),
        h("div", { class: "statement" }, q.statement),
        h("div", { class: "alts", role: "group", "aria-label": "Alternativas" }, Object.entries(q.alternatives).map(alt)),
        h("div", { class: "row" }, h("span", { class: "muted small" }, "Confiança:"), seg),
        h("div", { class: "row sp" }, confirmBtn,
          !each && a && !dirty ? h("span", { class: "chip ok" }, "✓ resposta registrada") : null,
          !each && a ? h("span", { class: "muted small" }, "O gabarito aparece ao finalizar. Você pode alterar a resposta até lá.") : null),
        lock && a ? feedback(q, a) : null),
      h("div", { class: "row sp" },
        h("button", { class: "btn", disabled: idx === 0, onclick: () => go_to(idx - 1) }, "← Anterior"),
        h("button", { class: "btn", disabled: idx === qs.length - 1, onclick: () => go_to(idx + 1) }, "Próxima →"),
        h("span", { class: "right" }),
        h("button", { class: `btn ${answeredCount === qs.length ? "primary" : ""}`, onclick: () => finish() }, "Finalizar sessão")),
      h("div", { class: "qnav" }, qs.map((x, i) => {
        const done = ans[x.id];
        const cls = [done ? "done" : "", i === idx ? "cur" : "", each && done ? (done.is_correct ? "okk" : "badd") : ""].join(" ");
        return h("button", { class: cls, "aria-label": `Questão ${i + 1}`, onclick: () => go_to(i) }, i + 1);
      })),
    ];
    clear(root).append(...children);
    tick();
  }

  function feedback(q, a) {
    const box = h("div", { class: `feedback ${a.is_correct ? "ok" : "bad"}` },
      h("h3", { class: a.is_correct ? "ok" : "bad" }, a.is_correct ? "Resposta correta" : `Resposta incorreta — gabarito: ${a.correct_answer}`));
    if (a.is_correct && a.confidence !== "certeza") box.append(h("p", { class: "small", style: { margin: "0 0 6px" } }, a.confidence === "chute" ? "Você acertou, mas marcou que chutou: este conhecimento ainda é frágil." : "Você acertou com dúvida: vale reforçar este ponto."));
    if (a.explanation) box.append(h("p", { class: "expl" }, a.explanation));
    else box.append(h("p", { class: "muted small" }, "Esta questão não tem explicação cadastrada."));
    if (!a.is_correct) {
      const note = h("input", { placeholder: "Quer anotar o que aconteceu? (opcional)", value: a.error_note || "", style: { width: "100%" } });
      const save = () => api(`/answers/${a.id}`, { method: "PATCH", body: { error_type: a.error_type, error_note: note.value } }).catch(fail);
      note.onblur = () => { a.error_note = note.value; save(); };
      const chips = h("div", { class: "row", style: { gap: "6px" } }, Object.entries(meta.error_types).map(([k, label]) =>
        h("button", { class: `btn sm ${a.error_type === k ? "primary" : "ghost"}`, onclick: async () => {
          a.error_type = a.error_type === k ? null : k; a.error_note = note.value; await save(); draw();
        } }, label)));
      box.append(h("div", { class: "sp stack" }, h("div", { class: "small muted" }, "Por que você acha que errou? (opcional)"), chips, note));
    }
    if (idx < qs.length - 1) box.append(h("div", { class: "row sp" }, h("button", { class: "btn primary", onclick: () => go_to(idx + 1) }, "Próxima questão →")));
    return box;
  }

  const onKey = (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || document.querySelector(".overlay")) return;
    const q = qs[idx];
    const key = e.key.toUpperCase();
    if (!locked(q) && q.alternatives[key]) { draft[q.id] = { ...(draft[q.id] || {}), chosen: key }; draw(); }
    else if (!locked(q) && ["1", "2", "3"].includes(e.key)) { draft[q.id] = { ...(draft[q.id] || {}), confidence: Object.keys(CONF)[Number(e.key) - 1] }; draw(); }
    else if (e.key === "Enter") { const btn = root.querySelector(".btn.primary.lg"); if (btn && !btn.disabled) confirm(); else if (locked(q)) go_to(idx + 1); }
    else if (e.key === "ArrowRight") go_to(idx + 1);
    else if (e.key === "ArrowLeft") go_to(idx - 1);
  };
  document.addEventListener("keydown", onKey);
  const onLeave = () => { bank(); };  // tempo da questão atual já é enviado ao confirmar
  draw();
  return () => { clearInterval(interval); document.removeEventListener("keydown", onKey); onLeave(); };
}
