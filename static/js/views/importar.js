import { h, api, clear, fail, toast, empty, confirmDialog, fmtDate, $ } from "../lib.js";

export default async function (root) {
  const [exams, imports] = await Promise.all([api("/taxonomy").then((t) => t.exams), api("/imports")]);
  let payload = null, filename = null, report = null, filter = "all", tab = "json", pdfJobIds = [], poll = null;
  const examSel = h("select", {}, h("option", { value: "" }, "Sem concurso"), exams.map((e) => h("option", { value: e.id }, e.name)));

  clear(root);
  root.append(h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "Importar questões"), h("p", {}, "Envie um arquivo JSON, confira a prévia e confirme."))));
  const stage = h("div");
  root.append(stage);

  function jsonPanel() {
    const input = h("input", { type: "file", accept: ".json,application/json", style: { display: "none" }, onchange: (e) => e.target.files[0] && readFile(e.target.files[0]) });
    const drop = h("div", { class: "dropzone" }, h("p", { style: { marginTop: 0 } }, "Arraste o arquivo .json aqui ou"), h("button", { class: "btn primary", onclick: () => input.click() }, "Escolher arquivo"), input);
    drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
    drop.addEventListener("dragleave", () => drop.classList.remove("over"));
    drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); if (e.dataTransfer.files[0]) readFile(e.dataTransfer.files[0]); });
    return h("div", { class: "card" }, h("div", { class: "row", style: { marginBottom: "12px" } }, h("label", { class: "field" }, "Agrupar disciplinas novas em", examSel)), drop,
        h("div", { class: "row sp small" }, h("span", { class: "muted" }, "Precisa de ajuda com o formato?"),
          h("a", { href: "/files/FORMATO_IMPORTACAO.md" }, "Documentação do formato"), h("a", { href: "/files/PROMPT_CONVERSAO_PDF.md" }, "Prompt para converter PDFs com IA"), h("a", { href: "/files/exemplo.json" }, "Arquivo de exemplo (questões fictícias)")));
  }

  function pickScreen() {
    clearInterval(poll);
    const tabs = h("div", { class: "tabs", style: { marginBottom: "14px" } },
      [["json", "Arquivo JSON"], ["pdf", "PDFs com IA"]].map(([k, l]) => h("button", { class: tab === k ? "on" : "", onclick: () => { tab = k; pickScreen(); } }, l)));
    stage.replaceChildren(tabs, tab === "json" ? jsonPanel() : pdfPanel(), historyCard());
  }

  function pdfPanel() {
    const box = h("div", { class: "stack" });
    const jobsBox = h("div", { class: "card sp" });
    const subject = h("input", { placeholder: "ex.: Língua Portuguesa (opcional)" });
    const input = h("input", { type: "file", accept: ".pdf,application/pdf", multiple: true, style: { display: "none" }, onchange: (e) => upload([...e.target.files]) });
    const drop = h("div", { class: "dropzone" }, h("p", { style: { marginTop: 0 } }, "Arraste seus PDFs aqui (pode ser vários de uma vez) ou"), h("button", { class: "btn primary", onclick: () => input.click() }, "Escolher PDFs"), input);
    drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
    drop.addEventListener("dragleave", () => drop.classList.remove("over"));
    drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); upload([...e.dataTransfer.files].filter((f) => /\.pdf$/i.test(f.name))); });
    const aiWarn = h("div");
    api("/ai/status").then((a) => { if (!a.configured) aiWarn.append(h("p", { class: "warn" }, "A IA não está configurada. ", h("a", { href: "#/configuracoes" }, "Informe sua chave de API"), " para converter PDFs.")); });

    async function upload(files) {
      if (!files.length) return;
      let ok = 0;
      for (const f of files) {
        const fd = new FormData(); fd.append("files", f); fd.append("subject", subject.value);
        try {
          const res = await fetch("/api/pdf-jobs", { method: "POST", body: fd });
          const data = await res.json().catch(() => ({}));
          if (!res.ok) throw new Error(data.error || `Erro ${res.status}`);
          ok++;
        } catch (e) { toast(`${f.name}: ${e.message}`, "error", 6000); }
      }
      if (ok) toast(`${ok} PDF(s) enviado(s). A conversão acontece em segundo plano.`, "success");
      refresh();
    }
    const sel = new Set();
    async function refresh() {
      let jobs;
      try { jobs = await api("/pdf-jobs"); } catch (e) { return; }
      const active = jobs.some((j) => ["queued", "processing"].includes(j.status));
      clearInterval(poll); if (active) poll = setInterval(refresh, 3000);
      if (!jobs.length) { jobsBox.replaceChildren(h("p", { class: "muted small", style: { margin: 0 } }, "Nenhum PDF enviado ainda.")); return; }
      const ready = jobs.filter((j) => j.status === "done" && !j.imported_at);
      const label = { queued: "na fila", processing: "convertendo", done: "pronto", error: "erro" };
      jobsBox.replaceChildren(h("h2", {}, "PDFs enviados"),
        h("div", { class: "list" }, jobs.map((j) => h("div", { class: "li" },
          j.status === "done" && !j.imported_at ? h("input", { type: "checkbox", checked: sel.has(j.id), onchange: (e) => { e.target.checked ? sel.add(j.id) : sel.delete(j.id); refresh(); } }) : h("span", { style: { width: "13px" } }),
          h("div", { class: "grow" }, h("div", { class: "trunc" }, j.filename),
            h("div", { class: "muted small" }, j.status === "processing" ? `trecho ${j.chunks_done}/${j.chunks_total}` : j.status === "done" ? `${j.n_questions} questão(ões) extraída(s)${j.n_omitted ? ` · ${j.n_omitted} omitida(s) (ex.: sem gabarito)` : ""}${j.imported_at ? " · já importado" : ""}` : j.error || ""),
            j.warnings?.length ? h("div", { class: "warn small" }, j.warnings[0]) : null),
          h("span", { class: `chip ${j.status === "done" ? "ok" : j.status === "error" ? "bad" : "warn"}` }, label[j.status]),
          j.status === "error" ? h("button", { class: "btn sm", onclick: async () => { await api(`/pdf-jobs/${j.id}/retry`, { method: "POST" }).catch(fail); refresh(); } }, "Tentar de novo") : null,
          h("button", { class: "btn sm ghost danger", onclick: async () => { await api(`/pdf-jobs/${j.id}`, { method: "DELETE" }).catch(fail); sel.delete(j.id); refresh(); } }, "Remover")))),
        h("div", { class: "row sp" },
          h("button", { class: "btn primary", disabled: !sel.size, onclick: async () => {
            try {
              payload = await api("/pdf-jobs/combine", { method: "POST", body: { job_ids: [...sel] } });
              pdfJobIds = [...sel]; filename = `${sel.size} PDF(s) convertido(s) por IA`;
              report = await api("/imports/preview", { method: "POST", body: { data: payload } }); filter = "all"; previewScreen();
            } catch (e) { fail(e); }
          } }, `Revisar e importar ${sel.size || ""} selecionado(s)`),
          ready.length ? h("button", { class: "btn ghost", onclick: () => { ready.forEach((j) => sel.add(j.id)); refresh(); } }, `Selecionar todos os prontos (${ready.length})`) : null));
    }
    box.append(h("div", { class: "card" }, aiWarn,
      h("p", { style: { marginTop: 0 } }, "A IA lê cada PDF e extrai as questões. Nada entra no banco direto: você confere tudo na mesma prévia da importação JSON."),
      h("label", { class: "field", style: { maxWidth: "420px", marginBottom: "12px" } }, "Disciplina dos PDFs deste envio", subject), drop,
      h("p", { class: "muted small", style: { marginBottom: 0 } }, "Cada PDF usa várias chamadas da API do Gemini (custo). Confira por amostragem: a IA pode errar a transcrição, e questões sem gabarito no PDF são omitidas, nunca inventadas.")),
      jobsBox);
    refresh();
    return box;
  }

  async function readFile(file) {
    try {
      const text = await file.text();
      payload = JSON.parse(text); filename = file.name;
    } catch (e) { toast(`Não foi possível ler "${file.name}" como JSON: ${e.message}`, "error", 7000); return; }
    try { report = await api("/imports/preview", { method: "POST", body: { data: payload } }); filter = "all"; previewScreen(); }
    catch (e) { fail(e); }
  }

  function previewScreen() {
    const c = report.counts;
    const stat = (v, l, cls = "") => h("div", { class: "card kpi" }, h("div", { class: `v ${cls}` }, v), h("div", { class: "l" }, l));
    const rows = h("tbody");
    const tabs = h("div", { class: "tabs" });
    const draw = () => {
      tabs.replaceChildren(...[["all", `Todas (${c.total})`], ["valid", `Válidas (${c.valid})`], ["duplicate", `Duplicadas (${c.duplicate})`], ["invalid", `Inválidas (${c.invalid})`]]
        .map(([k, l]) => h("button", { class: filter === k ? "on" : "", onclick: () => { filter = k; draw(); } }, l)));
      const items = report.items.filter((i) => filter === "all" || i.status === filter).slice(0, 300);
      rows.replaceChildren(...items.map((i) => h("tr", {},
        h("td", { class: "muted" }, i.index), h("td", {}, i.id || "—"), h("td", {}, i.subject || "—"),
        h("td", {}, h("div", { class: "trunc", style: { maxWidth: "340px" } }, i.preview || "(sem enunciado)")),
        h("td", {}, h("span", { class: `chip ${i.status === "valid" ? "ok" : i.status === "invalid" ? "bad" : "warn"}` }, { valid: "válida", invalid: "inválida", duplicate: "duplicada" }[i.status])),
        h("td", { class: "small" }, i.errors.map((m) => h("div", { class: "bad" }, m)), i.reason ? h("div", { class: "warn" }, i.reason) : null, i.warnings.map((m) => h("div", { class: "muted" }, m))))));
      if (report.items.filter((i) => filter === "all" || i.status === filter).length > 300) rows.append(h("tr", {}, h("td", { colspan: 6, class: "muted" }, "Mostrando as 300 primeiras linhas deste filtro.")));
    };
    draw();
    const commit = async (e) => {
      const btn = e.currentTarget; btn.disabled = true;
      try {
        const res = await api("/imports/commit", { method: "POST", body: { data: payload, filename, exam_id: examSel.value ? Number(examSel.value) : null, pdf_job_ids: pdfJobIds } });
        stage.replaceChildren(h("div", { class: "card" }, h("h2", {}, "Importação concluída"),
          h("p", {}, `${res.imported} questão(ões) importada(s). ${res.duplicates} duplicada(s) e ${res.invalid} inválida(s) foram puladas.`),
          h("div", { class: "row" }, h("a", { class: "btn primary", href: "#/banco" }, "Ver banco de questões"), h("a", { class: "btn", href: "#/estudar" }, "Estudar"), h("button", { class: "btn ghost", onclick: () => { payload = report = null; reload(); } }, "Importar outro arquivo"))));
      } catch (err) { btn.disabled = false; fail(err); }
    };
    stage.replaceChildren(
      h("div", { class: "card" }, h("div", { class: "row" }, h("b", {}, filename), report.metadata?.source ? h("span", { class: "chip" }, `fonte: ${report.metadata.source}`) : null)),
      h("div", { class: "grid g4 sp" }, stat(c.total, "no arquivo"), stat(c.valid, "válidas", "ok"), stat(c.duplicate, "duplicadas (serão puladas)", c.duplicate ? "warn" : ""), stat(c.invalid, "inválidas (não serão importadas)", c.invalid ? "bad" : "")),
      report.subjects.length ? h("p", { class: "muted small" }, `Disciplinas: ${report.subjects.join(", ")}${report.topics.length ? ` · ${report.topics.length} assunto(s) detectado(s)` : ""}. Os que não existirem serão criados.`) : null,
      h("div", { class: "card sp", style: { padding: 0, overflow: "auto" } }, h("div", { style: { padding: "12px" } }, tabs),
        h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "#"), h("th", {}, "ID"), h("th", {}, "Disciplina"), h("th", {}, "Enunciado"), h("th", {}, "Status"), h("th", {}, "Detalhes"))), rows)),
      h("div", { class: "row sp" }, h("button", { class: "btn primary lg", disabled: !c.valid, onclick: commit }, `Importar ${c.valid} questão(ões)`),
        h("button", { class: "btn ghost", onclick: () => { payload = report = null; pdfJobIds = []; pickScreen(); } }, "Cancelar")));
  }

  function historyCard() {
    if (!imports.length) return h("div");
    return h("div", { class: "card sp" }, h("h2", {}, "Importações anteriores"), h("div", { class: "list" }, imports.map((i) => h("div", { class: "li" },
      h("div", { class: "grow" }, h("div", { class: "trunc" }, i.filename || "(sem nome)"), h("div", { class: "muted small" }, `${fmtDate(i.created_at)} · ${i.imported} importadas · ${i.duplicates} duplicadas · ${i.invalid} inválidas · ${i.current_questions} ainda no banco`)),
      h("button", { class: "btn sm ghost danger", onclick: async () => {
        if (!(await confirmDialog(`Excluir as ${i.current_questions} questões desta importação? Respostas e histórico dessas questões também serão apagados.`, { confirmLabel: "Excluir", danger: true }))) return;
        await api(`/imports/${i.id}`, { method: "DELETE" }).catch(fail); reload();
      } }, "Excluir questões")))));
  }
  const reload = () => import("./importar.js").then((m) => m.default(root));
  pickScreen();
  return () => clearInterval(poll);
}
