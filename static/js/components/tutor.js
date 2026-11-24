import { h, api, fail, aiBadge, fmtDate } from "../lib.js";

/** Painel de conversa com o tutor de IA. thread: "free" ou "q:<id>". */
export async function createTutor({ thread, placeholder = "Pergunte algo sobre este assunto…" }) {
  const hist = await api(`/tutor/history?thread=${encodeURIComponent(thread)}`);
  const list = h("div", { class: "chat", "aria-live": "polite" });
  const add = (role, text) => { const m = h("div", { class: `msg ${role}` }, text); list.append(m); list.scrollTop = list.scrollHeight; return m; };
  hist.forEach((m) => add(m.role, m.content));
  if (!hist.length) list.append(h("p", { class: "muted small", style: { margin: 0 } }, "Nenhuma mensagem ainda."));
  const input = h("textarea", { rows: 2, placeholder, style: { flex: 1, resize: "vertical" } });
  const send = h("button", { class: "btn primary" }, "Enviar");
  const submit = async () => {
    const text = input.value.trim(); if (!text) return;
    if (!hist.length && list.querySelector("p")) list.replaceChildren();
    add("user", text); input.value = ""; send.disabled = input.disabled = true;
    const wait = add("model", "Pensando…");
    try { const r = await api("/tutor/chat", { method: "POST", body: { thread, message: text } }); wait.textContent = r.reply; hist.push(1); }
    catch (e) { wait.remove(); fail(e); }
    finally { send.disabled = input.disabled = false; input.focus(); list.scrollTop = list.scrollHeight; }
  };
  send.onclick = submit;
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit(); });
  const clearBtn = h("button", { class: "btn ghost sm", onclick: async () => { await api(`/tutor/history?thread=${encodeURIComponent(thread)}`, { method: "DELETE" }).catch(fail); list.replaceChildren(h("p", { class: "muted small", style: { margin: 0 } }, "Conversa limpa.")); hist.length = 0; } }, "Limpar conversa");
  return h("div", { class: "stack" },
    h("div", { class: "row" }, aiBadge("✦ Tutor de IA"), h("span", { class: "muted small" }, "Respostas geradas por IA podem conter erros; confira leis, prazos e fórmulas."), h("span", { class: "right" }), clearBtn),
    list, h("div", { class: "row", style: { alignItems: "flex-end" } }, input, send), h("span", { class: "muted small" }, "Ctrl+Enter envia."));
}
