import { $, clear, h, fail, api } from "./lib.js";

const NAV = [
  ["#/dashboard", "Dashboard"], ["#/estudar", "Estudar"], ["#/lacunas", "Lacunas"], ["#/revisoes", "Revisões"], ["#/banco", "Banco de questões"],
  ["#/historico", "Histórico"], ["#/disciplinas", "Disciplinas"], ["#/estatisticas", "Estatísticas"], ["#/tutor", "Tutor IA"],
  ["#/importar", "Importar questões"], ["#/configuracoes", "Configurações"],
];
const ROUTES = [
  [/^#\/dashboard$/, () => import("./views/dashboard.js")],
  [/^#\/estudar$/, () => import("./views/estudar.js")],
  [/^#\/banco$/, () => import("./views/banco.js")],
  [/^#\/historico$/, () => import("./views/historico.js")],
  [/^#\/disciplinas$/, () => import("./views/disciplinas.js")],
  [/^#\/estatisticas$/, () => import("./views/estatisticas.js")],
  [/^#\/importar$/, () => import("./views/importar.js")],
  [/^#\/configuracoes$/, () => import("./views/configuracoes.js")],
  [/^#\/lacunas(\?.*)?$/, () => import("./views/lacunas.js")],
  [/^#\/lacuna\/(\d+)$/, () => import("./views/estudo.js")],
  [/^#\/revisoes$/, () => import("./views/revisoes.js")],
  [/^#\/tutor(\?.*)?$/, () => import("./views/tutor.js")],
  [/^#\/sessao\/(\d+)$/, () => import("./views/resolver.js"), true],
  [/^#\/sessao\/(\d+)\/resultado$/, () => import("./views/resultado.js")],
];

let cleanup = null;
async function render() {
  const hash = location.hash || "#/dashboard";
  if (cleanup) { try { cleanup(); } catch {} cleanup = null; }
  const view = $("#view");
  const match = ROUTES.map(([re, loader, focus]) => [re.exec(hash), loader, focus]).find(([m]) => m);
  document.body.classList.toggle("focus", !!(match && match[2]));
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active", hash.startsWith(a.getAttribute("href")) || (a.getAttribute("href") === "#/lacunas" && hash.startsWith("#/lacuna/"))));
  if (!match) { location.hash = "#/dashboard"; return; }
  clear(view).append(h("p", { class: "muted" }, "Carregando…"));
  try {
    const mod = await match[1]();
    const out = await mod.default(view, ...match[0].slice(1));
    if (typeof out === "function") cleanup = out;
    window.scrollTo(0, 0);
  } catch (e) {
    fail(e);
    clear(view).append(h("div", { class: "card" }, h("h2", {}, "Algo deu errado"), h("p", { class: "muted" }, e.message)));
  }
}

async function init() {
  $("#nav").append(...NAV.map(([href, label]) => h("a", { href }, label)));
  try {
    const s = await api("/settings");
    document.documentElement.dataset.theme = s.theme;
    localStorage.setItem("theme", s.theme);
  } catch { /* usa o tema local */ }
  window.addEventListener("hashchange", render);
  render();
}
init();
