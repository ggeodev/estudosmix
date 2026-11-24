import { h, api, clear, fail, toast, aiBadge, safeImgSrc, CONF, daysLabel, go } from "../lib.js";
import { createTutor } from "../components/tutor.js";

const STEPS = ["Lacuna", "Explicação", "Exemplo", "Verificação", "Resultado"];
const ERR = { desconhecimento: "Desconhecimento do conteúdo", incompleto: "Conhecimento incompleto", interpretacao: "Interpretação do enunciado", confusao: "Confusão entre conceitos", procedimento: "Procedimento/cálculo", desatencao: "Desatenção", outro: "Outro motivo" };

export default async function (root, qid) {
  const st = await api(`/study/${qid}`);
  const q = st.question, la = st.last_answer;
  const mats = { normal: st.materials.normal || null, simples: st.materials.simples || null };
  let step = 0, level = "normal", busy = false, tutor = null;
  let ver = null;        // { sid, source, q, chosen, conf, fb }
  let outcome = null;

  const withBusy = async (fn) => { if (busy) return; busy = true; draw(); try { await fn(); } catch (e) { fail(e); } finally { busy = false; draw(); } };
  const loadMaterial = (lv, force = false) => withBusy(async () => {
    const r = await api(`/study/${qid}/material`, { method: "POST", body: { level: lv, force } });
    mats[lv] = r.material; level = lv;
  });

  const alts = (qq, { correct, chosen } = {}) => h("div", { class: "alts", style: { margin: "10px 0" } }, Object.entries(qq.alternatives).map(([L, T]) =>
    h("div", { class: `alt ${correct && L === correct ? "right" : chosen && L === chosen && L !== correct ? "wrong" : ""}`, "aria-disabled": "true" }, h("span", { class: "L" }, L), h("span", { class: "T" }, T))));
  const sec = (title, text) => text ? h("div", { class: "sec" }, h("h3", {}, title), h("p", {}, text)) : null;

  function panelLacuna() {
    const have = mats.normal;
    return [
      h("h2", {}, "Lacuna identificada"),
      h("p", { class: "muted" }, la ? `Você marcou ${la.chosen} (${la.is_correct ? "acertou" : "errou"}) com a confiança “${CONF[la.confidence]}”.` : "Você ainda não respondeu esta questão."),
      q.support_text ? h("div", { class: "support" }, q.support_text) : null,
      h("div", { class: "statement", style: { fontSize: "15.5px" } }, q.statement),
      alts(q, { correct: q.correct_answer, chosen: la?.chosen }),
      q.explanation ? sec("Explicação da própria questão", q.explanation) : null,
      !st.ai.configured ? h("p", { class: "warn" }, "A IA não está configurada: ", h("a", { href: "#/configuracoes" }, "informe sua chave"), " para gerar o material de estudo.") : null,
      h("div", { class: "row sp" }, h("button", { class: "btn primary", disabled: busy || !st.ai.configured, onclick: async () => { if (!have) await loadMaterial("normal"); step = 1; draw(); } },
        busy ? "Gerando explicação…" : have ? "Ver explicação" : "✦ Gerar explicação com IA"), h("a", { class: "btn ghost", href: "#/lacunas" }, "Deixar para depois")),
    ];
  }
  function panelExplicacao() {
    const m = mats[level] || mats.normal;
    return [
      h("div", { class: "row" }, h("h2", {}, level === "simples" ? "Explicação (versão mais simples)" : "Explicação"), aiBadge()),
      sec("Conhecimento exigido", m.concept), sec("Conceito", m.explanation), sec("Regra / fundamento", m.rule), sec("Por que a alternativa correta está certa", m.why_correct),
      m.why_wrong && Object.keys(m.why_wrong).length ? h("div", { class: "sec" }, h("h3", {}, "Por que as erradas estão erradas"), Object.entries(m.why_wrong).map(([k, v]) => h("p", {}, `${k}) ${v}`))) : null,
      m.prerequisites?.length ? h("div", { class: "sec" }, h("h3", {}, "Pode ajudar rever antes (sugestão da IA)"), h("ul", { style: { margin: 0, paddingLeft: "18px" } }, m.prerequisites.map((p) => h("li", {}, p)))) : null,
      m.references?.length ? sec("Referências citadas (confira nas fontes oficiais)", m.references.join("; ")) : null,
      h("div", { class: "row sp" },
        h("button", { class: "btn primary", onclick: () => { step = 2; draw(); } }, "Ver exemplo →"),
        level === "normal" ? h("button", { class: "btn", disabled: busy, onclick: async () => { if (!mats.simples) await loadMaterial("simples"); else level = "simples"; draw(); } }, busy ? "Gerando…" : "Explicar de outro jeito") : h("button", { class: "btn", onclick: () => { level = "normal"; draw(); } }, "Voltar à versão normal"),
        h("button", { class: "btn ghost", onclick: () => { step = 0; draw(); } }, "← Lacuna")),
    ];
  }
  function panelExemplo() {
    const m = mats[level] || mats.normal;
    return [h("div", { class: "row" }, h("h2", {}, "Exemplo prático"), aiBadge()), sec("", m.example),
      h("div", { class: "row sp" }, h("button", { class: "btn primary", onclick: () => { step = 3; ver = null; draw(); } }, "Fazer questão de verificação →"), h("button", { class: "btn ghost", onclick: () => { step = 1; draw(); } }, "← Explicação"))];
  }
  async function startVerification(mode) {
    await withBusy(async () => {
      const r = await api(`/study/${qid}/verification`, { method: "POST", body: { mode } });
      const s = await api(`/sessions/${r.session_id}`);
      ver = { sid: r.session_id, source: r.source, q: s.questions[0], chosen: null, conf: null, fb: null };
    });
  }
  function panelVerificacao() {
    if (!ver) return [
      h("h2", {}, "Verificação da aprendizagem"),
      h("p", { class: "muted" }, "Responda uma questão nova sobre o mesmo conhecimento, sem consultar o material. A questão original não é repetida."),
      h("div", { class: "row sp" },
        h("button", { class: "btn primary", disabled: busy, onclick: () => startVerification("auto") }, busy ? "Preparando…" : "Questão inédita (do banco; ou gerada por IA se não houver)"),
        h("button", { class: "btn", disabled: busy || !st.ai.configured, onclick: () => startVerification("ai") }, "✦ Gerar uma nova com IA")),
      h("button", { class: "btn ghost sm", onclick: () => { step = 2; draw(); } }, "← Voltar")];
    const vq = ver.q;
    const done = !!ver.fb;
    return [
      h("div", { class: "row" }, h("h2", {}, "Questão de verificação"), ver.source === "ai" || vq.bank === "Gerada por IA" ? aiBadge("✦ Questão gerada por IA — o gabarito pode conter erros") : h("span", { class: "chip" }, "do seu banco")),
      vq.support_text ? h("div", { class: "support" }, vq.support_text) : null,
      h("div", { class: "statement", style: { fontSize: "15.5px" } }, vq.statement),
      done ? alts(vq, { correct: ver.fb.correct_answer, chosen: ver.chosen }) : h("div", { class: "alts", style: { margin: "10px 0" } }, Object.entries(vq.alternatives).map(([L, T]) =>
        h("button", { class: `alt ${ver.chosen === L ? "sel" : ""}`, onclick: () => { ver.chosen = L; draw(); } }, h("span", { class: "L" }, L), h("span", { class: "T" }, T)))),
      done ? null : h("div", { class: "row" }, h("span", { class: "muted small" }, "Confiança:"), h("div", { class: "seg" }, Object.entries(CONF).map(([k, l]) => h("button", { class: ver.conf === k ? "on" : "", onclick: () => { ver.conf = k; draw(); } }, l)))),
      done ? null : h("div", { class: "row sp" }, h("button", { class: "btn primary lg", disabled: busy || !ver.chosen || !ver.conf, onclick: () => withBusy(async () => {
        ver.fb = await api(`/sessions/${ver.sid}/answers`, { method: "POST", body: { question_id: vq.id, chosen: ver.chosen, confidence: ver.conf, time_s: 0 } });
        outcome = await api(`/study/${qid}/record`, { method: "POST", body: { session_id: ver.sid } });
        step = 4;
      }) }, busy ? "Registrando…" : "Confirmar resposta")),
    ];
  }
  function panelResultado() {
    const ok = outcome.outcome === "correct_confident";
    const rv = outcome.review_original;
    const sched = rv ? `A questão original volta para revisão ${daysLabel(rv.interval_days)}.` : "";
    return [
      h("h2", {}, "Resultado"),
      h("div", { class: `feedback ${ver.fb.is_correct ? "ok" : "bad"}` }, h("h3", { class: ver.fb.is_correct ? "ok" : "bad" }, ver.fb.is_correct ? "Resposta correta" : `Resposta incorreta — gabarito: ${ver.fb.correct_answer}`),
        ver.fb.explanation ? h("p", { class: "expl" }, ver.fb.explanation) : null),
      alts(ver.q, { correct: ver.fb.correct_answer, chosen: ver.chosen }),
      h("p", {}, ok ? "Você acertou com certeza. Isso é um bom sinal, mas o conhecimento só se consolida se você acertar de novo em dias diferentes. " : outcome.outcome === "correct_fragile" ? "Você acertou, mas sem certeza: este conhecimento ainda está frágil. " : "Você errou de novo: vale ver o conteúdo de outro jeito antes de tentar outra vez. ", sched),
      ok ? h("div", { class: "row sp" }, outcome.next_gap_id ? h("a", { class: "btn primary", href: `#/lacuna/${outcome.next_gap_id}` }, `Próxima lacuna (${outcome.open_gaps} restantes)`) : null,
        h("a", { class: "btn", href: "#/lacunas" }, "Voltar às lacunas"), h("a", { class: "btn ghost", href: "#/dashboard" }, "Encerrar por hoje"))
        : h("div", { class: "row sp" },
          h("button", { class: "btn primary", disabled: busy, onclick: async () => { if (!mats.simples) await loadMaterial("simples"); else level = "simples"; step = 1; draw(); } }, "Explicação alternativa (mais simples)"),
          h("button", { class: "btn", disabled: busy, onclick: async () => { if (!mats.simples) await loadMaterial("simples"); else level = "simples"; step = 2; draw(); } }, "Exemplo mais simples"),
          h("button", { class: "btn", onclick: () => { ver = null; outcome = null; step = 3; draw(); } }, "Nova tentativa com outra questão"),
          h("a", { class: "btn ghost", href: "#/lacunas" }, "Deixar para depois")),
    ];
  }

  async function toggleTutor() {
    if (tutor) { tutor = null; draw(); return; }
    tutor = await createTutor({ thread: `q:${qid}`, placeholder: "Pergunte sobre esta questão ou conceito…" }).catch((e) => { fail(e); return null; });
    draw();
  }

  function draw() {
    const panels = [panelLacuna, panelExplicacao, panelExemplo, panelVerificacao, panelResultado];
    clear(root).append(
      h("div", { class: "page-head" }, h("div", {}, h("h1", {}, st.concept || "Estudo direcionado"), h("div", { class: "row small muted", style: { marginTop: "4px" } }, h("span", { class: "chip" }, q.subject_name), q.topics.map((t) => h("span", { class: "chip" }, t.name)))),
        h("span", { class: "right" }), h("a", { class: "btn ghost", href: "#/lacunas" }, "← Lacunas")),
      h("div", { class: "steps" }, STEPS.map((s, i) => h("span", { class: i === step ? "on" : i < step ? "done" : "" }, `${i + 1}. ${s}`))),
      h("div", { class: "card" }, panels[step]()),
      step !== 3 || !ver || ver.fb ? h("div", { class: "row sp" }, h("button", { class: "btn", onclick: toggleTutor }, tutor ? "Fechar tutor" : "✦ Perguntar ao tutor"), h("span", { class: "muted small" }, step === 3 ? "" : "")) : null,
      tutor ? h("div", { class: "card sp" }, tutor) : null);
  }
  draw();
}
