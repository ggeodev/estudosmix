// Utilitários de UI. Conteúdo vindo de importações é SEMPRE inserido como texto (nunca innerHTML).
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k === "value" || k === "checked" || k === "disabled" || k === "selected") el[k] = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}
// O DOM nativo converte null/false em texto ("null"). Ignoramos esses valores em append/prepend/replaceChildren.
for (const fn of ["append", "prepend", "replaceChildren"]) {
  const native = Element.prototype[fn];
  Element.prototype[fn] = function (...nodes) { return native.apply(this, nodes.flat(Infinity).filter((n) => n !== null && n !== undefined && n !== false)); };
}
export const $ = (sel, root = document) => root.querySelector(sel);
export function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }

export class ApiError extends Error {
  constructor(message, status, data) { super(message); this.status = status; this.data = data; }
}
export async function api(path, { method = "GET", body } = {}) {
  let res;
  try {
    res = await fetch("/api" + path, {
      method,
      headers: body !== undefined ? { "Content-Type": "application/json" } : {},
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError("Não foi possível falar com o servidor. Ele está rodando?", 0);
  }
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { /* resposta não-JSON */ }
  if (!res.ok) throw new ApiError((data && data.error) || `Erro ${res.status}`, res.status, data);
  return data;
}
export const qs = (obj) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(obj || {})) if (v !== "" && v !== null && v !== undefined) p.set(k, v);
  const s = p.toString();
  return s ? "?" + s : "";
};

export function toast(msg, kind = "info", ms = 3500) {
  const t = h("div", { class: `toast ${kind}`, role: "status" }, msg);
  $("#toasts").append(t);
  setTimeout(() => t.remove(), ms);
}
export function fail(e) { console.error(e); toast(e.message || String(e), "error", 6000); }

export function modal({ title, body, actions = [], size = "", onClose }) {
  const overlay = h("div", { class: "overlay" });
  const close = () => { overlay.remove(); document.removeEventListener("keydown", onKey); onClose?.(); };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", onKey);
  overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(); });
  const footer = actions.length ? h("footer", {}, actions.map((a) =>
    h("button", { class: `btn ${a.class || ""}`, onclick: async (e) => {
      const btn = e.currentTarget; btn.disabled = true;
      try { const keep = await a.onClick?.(close); if (keep !== false && a.close !== false) close(); }
      catch (err) { fail(err); }
      finally { btn.disabled = false; }
    } }, a.label))) : null;
  overlay.append(h("div", { class: `modal ${size}`, role: "dialog", "aria-modal": "true" },
    h("header", {}, h("h2", {}, title), h("button", { class: "btn ghost sm", onclick: close, "aria-label": "Fechar" }, "✕")),
    h("div", { class: "body" }, body), footer));
  document.body.append(overlay);
  return close;
}
export function confirmDialog(message, { confirmLabel = "Confirmar", danger = false } = {}) {
  return new Promise((resolve) => {
    let done = false;
    const finish = (v) => { if (!done) { done = true; resolve(v); } };
    modal({ title: "Confirmar", size: "sm", onClose: () => finish(false), body: h("p", { style: { margin: 0 } }, message), actions: [
      { label: "Cancelar", class: "ghost", onClick: () => finish(false) },
      { label: confirmLabel, class: danger ? "primary danger" : "primary", onClick: () => finish(true) },
    ] });
  });
}
export function formModal({ title, fields, submitLabel = "Salvar", onSubmit }) {
  const inputs = {};
  const body = h("div", { class: "stack" }, fields.map((f) => {
    let input;
    if (f.options) {
      input = h("select", {}, f.options.map((o) => h("option", { value: o.value ?? "", selected: String(o.value ?? "") === String(f.value ?? "") }, o.label)));
    } else input = h("input", { type: f.type || "text", value: f.value ?? "", placeholder: f.placeholder || "" });
    inputs[f.name] = input;
    return h("label", { class: "field" }, f.label, input);
  }));
  const submit = async (close) => {
    const vals = {}; for (const f of fields) vals[f.name] = inputs[f.name].value;
    await onSubmit(vals);
  };
  modal({ title, body, size: "sm", actions: [{ label: "Cancelar", class: "ghost" }, { label: submitLabel, class: "primary", onClick: submit }] });
  body.addEventListener("keydown", (e) => { if (e.key === "Enter") e.target.closest(".modal")?.querySelector(".btn.primary")?.click(); });
  setTimeout(() => Object.values(inputs)[0]?.focus(), 30);
}

export const CONF = { certeza: "Tenho certeza", duvida: "Tenho dúvidas", chute: "Chutei" };
export const CONF_SHORT = { certeza: "certeza", duvida: "dúvida", chute: "chute" };
export const KIND_LABEL = { bateria: "Bateria", diagnostico: "Diagnóstico", simulado: "Simulado", misto: "Misto", avulsa: "Avulsa", revisao: "Revisão", verificacao: "Verificação" };
export const aiBadge = (text = "✦ Gerado por IA") => h("span", { class: "chip ai", title: "Conteúdo gerado por inteligência artificial; pode conter erros" }, text);
export function daysLabel(n) { return n === 1 ? "amanhã" : `em ${n} dias`; }
export const pct = (v) => (v === null || v === undefined ? "—" : `${v}%`);
export function fmtDuration(s) {
  s = Math.round(s || 0);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}min ${String(s % 60).padStart(2, "0")}s`;
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}min`;
}
export function fmtClock(s) { s = Math.max(0, Math.round(s)); return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; }
export function fmtDate(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}
export function accBar(value) {
  const cls = value === null ? "" : value < 50 ? "low" : value < 75 ? "mid" : "";
  return h("div", { class: `bar acc ${cls}`, title: pct(value) }, h("i", { style: { width: `${value ?? 0}%` } }));
}
export function empty(title, text, ...actions) {
  return h("div", { class: "empty" }, h("h3", {}, title), h("p", {}, text), h("div", { class: "row", style: { justifyContent: "center" } }, actions));
}
export function safeImgSrc(src) {
  return typeof src === "string" && /^(data:image\/|https?:\/\/)/i.test(src) ? src : null;
}
export const go = (hash) => { location.hash = hash; };

export async function createSession(body) {
  const { id } = await api("/sessions", { method: "POST", body });
  go(`#/sessao/${id}`);
}
