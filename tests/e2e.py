"""Teste ponta a ponta no navegador (opcional; requer `pip install playwright` + chromium).
Uso: python3 tests/e2e.py [pasta_para_screenshots]"""
import os, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else None
PORT = 5057
tmp = tempfile.mkdtemp()
env = {**os.environ, "ESTUDOS_DB": f"{tmp}/e2e.db", "ESTUDOS_PORT": str(PORT), "AI_PROVIDER": "fake", "ESTUDOS_ENV": f"{tmp}/.env"}
srv = subprocess.Popen([sys.executable, "run.py"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
time.sleep(1.5)
BASE = f"http://127.0.0.1:{PORT}"
errors = []

def shot(page, name):
    if SHOTS:
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=False)

try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1280, "height": 860})
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.goto(BASE)
        page.wait_for_selector("text=Seu banco de questões está vazio")
        print("1. dashboard vazio OK"); shot(page, "01-dashboard-vazio")

        # importação pela UI
        page.click("#nav >> text=Importar questões")
        page.set_input_files("input[type=file]", str(ROOT / "samples" / "exemplo.json"))
        page.wait_for_selector("text=Importar 7 questão(ões)")
        shot(page, "02-previa")
        page.click("text=Importar 7 questão(ões)")
        page.wait_for_selector("text=Importação concluída")
        print("2. importação OK")

        # banco
        page.click("#nav >> text=Banco de questões")
        page.wait_for_selector("text=7 questão(ões)")
        page.select_option("label:has-text('Disciplina') select", label="Matemática")
        page.wait_for_selector("text=2 questão(ões)")
        shot(page, "03-banco")
        page.click("tbody tr >> nth=0")
        page.wait_for_selector(".modal .alt.right")
        shot(page, "04-detalhe")
        page.keyboard.press("Escape")
        print("3. banco/filtro/detalhe OK")

        # sessão com feedback imediato (usa teclado)
        page.click("#nav >> text=Estudar")
        page.wait_for_selector("text=Iniciar sessão")
        page.fill("input[type=number]", "3")
        page.click("text=Iniciar sessão")
        page.wait_for_selector(".statement")
        page.keyboard.press("a"); page.keyboard.press("1")
        shot(page, "05-resolver")
        page.keyboard.press("Enter")
        page.wait_for_selector(".feedback")
        shot(page, "06-feedback")
        page.click("text=Próxima questão")
        page.click(".alt >> nth=1"); page.click("text=Chutei"); page.click("text=Confirmar resposta")
        page.wait_for_selector(".feedback")
        page.click("text=Finalizar sessão")
        page.click(".modal button.primary")
        page.wait_for_selector("text=Confiança × resultado")
        shot(page, "07-resultado")
        print("4. sessão feedback imediato + resultado OK")

        # diagnóstico (gabarito só no final)
        page.click("#nav >> text=Estudar")
        page.click("text=Diagnóstico de assunto")
        page.fill("input[type=number]", "2")
        page.click("text=Iniciar sessão")
        page.wait_for_selector(".statement")
        page.click(".alt >> nth=0"); page.click("text=Tenho dúvidas"); page.click("text=Confirmar resposta")
        page.wait_for_selector("text=resposta registrada")
        assert page.locator(".feedback").count() == 0, "gabarito vazou antes do fim"
        page.click("text=Próxima →")
        page.click(".alt >> nth=2"); page.click("text=Tenho certeza"); page.click("text=Confirmar resposta")
        page.click("text=Finalizar sessão")
        page.wait_for_selector("text=Confiança × resultado")
        print("5. diagnóstico sem vazar gabarito OK")

        # retomar sessão
        page.click("#nav >> text=Estudar"); page.click("text=Iniciar sessão")
        page.wait_for_selector(".statement"); page.click("text=← Sair")
        page.wait_for_selector("text=Sessões em andamento"); page.click("text=Continuar >> nth=0")
        page.wait_for_selector(".statement")
        print("6. retomar sessão OK")

        page.click("text=← Sair")
        page.wait_for_selector(".kpi"); shot(page, "08-dashboard")
        page.click("#nav >> text=Estatísticas"); page.wait_for_selector("text=Confiança × acerto"); shot(page, "09-estatisticas")
        page.click("#nav >> text=Histórico"); page.wait_for_selector("text=Resultado >> nth=0")
        page.click("#nav >> text=Disciplinas"); page.wait_for_selector("text=Mandado de segurança"); shot(page, "10-disciplinas")
        page.click("#nav >> text=Configurações"); page.select_option("select", "light"); page.wait_for_function("document.documentElement.dataset.theme==='light'"); shot(page, "11-config-claro")
        page.reload(); page.wait_for_selector("text=Configurações")
        assert page.evaluate("document.documentElement.dataset.theme") == "light"
        print("7. dashboard/estatísticas/histórico/disciplinas/config + tema persistente OK")

        # ---------- FASE 2 (com provedor de IA falso) ----------
        page.click("#nav >> text=Lacunas"); page.wait_for_selector("text=lacuna(s)")
        shot(page, "12-lacunas")
        page.click("text=✦ Nomear >> nth=0"); page.wait_for_selector("text=Conceito específico")
        page.click("a:has-text('Estudar') >> nth=-1") if False else page.click(".li a.btn.primary >> nth=0")
        page.wait_for_selector("text=Lacuna identificada")
        page.click("text=Gerar explicação com IA"); page.wait_for_selector("text=Conceito")
        assert page.locator(".chip.ai").count() >= 1, "falta selo de IA"
        shot(page, "13-explicacao")
        page.click("text=Explicar de outro jeito"); page.wait_for_selector("text=versão mais simples")
        page.click("text=Ver exemplo"); page.wait_for_selector("text=Exemplo prático")
        page.click("text=Fazer questão de verificação"); page.click("text=Questão inédita")
        page.wait_for_selector("text=Questão de verificação")
        page.click(".alt >> nth=1"); page.click("text=Tenho certeza"); page.click("text=Confirmar resposta")
        page.wait_for_selector(".feedback"); shot(page, "14-resultado-verificacao")
        page.click("text=Perguntar ao tutor"); page.fill("textarea", "Não entendi o conceito"); page.keyboard.press("Control+Enter")
        page.wait_for_selector("text=[fake tutor]")
        print("8. lacunas → explicação → exemplo → verificação → resultado + tutor OK")

        page.click("#nav >> text=Revisões"); page.wait_for_selector("text=Como as revisões são agendadas"); shot(page, "15-revisoes")
        page.click("#nav >> text=Tutor IA"); page.wait_for_selector("h1:has-text(\"Tutor IA\")"); page.wait_for_selector("text=Nenhuma mensagem ainda")
        page.click("#nav >> text=Dashboard"); page.wait_for_selector("text=lacunas abertas para estudar"); shot(page, "16-dashboard-fase2")
        # resultado de sessão mostra diagnóstico
        page.click("#nav >> text=Histórico"); page.click("a.btn:has-text(\"Resultado\") >> nth=0")
        try:
            page.wait_for_selector("text=Diagnóstico desta sessão", timeout=6000)
        except Exception:
            print("DEBUG url:", page.url); print("DEBUG view:", page.inner_text("#view")[:600]); print("DEBUG errors:", errors); raise
        shot(page, "17-diagnostico")
        print("9. revisões/tutor/dashboard/diagnóstico OK")

        # PDF com IA
        from pypdf import PdfWriter
        w = PdfWriter(); [w.add_blank_page(200, 200) for _ in range(2)]
        w.write(f"{tmp}/prova1.pdf")
        page.click("#nav >> text=Importar questões"); page.click(".tabs >> text=PDFs com IA")
        page.set_input_files("input[type=file][accept*='pdf']", f"{tmp}/prova1.pdf")
        page.wait_for_selector("text=2 questão(ões) extraída(s)", timeout=20000); shot(page, "18-pdf")
        page.click("text=Selecionar todos os prontos"); page.click("text=Revisar e importar")
        page.wait_for_selector("text=Importar 2 questão(ões)"); page.click("text=Importar 2 questão(ões)")
        page.wait_for_selector("text=Importação concluída")
        print("10. PDF → IA → prévia → importação OK")

        page.click("#nav >> text=Configurações"); page.wait_for_selector("text=Inteligência artificial")
        page.click("text=Testar conexão"); page.wait_for_selector("text=Conexão OK"); shot(page, "19-config-ia")
        print("11. configurações de IA OK")
        b.close()
finally:
    srv.terminate()

real = [e for e in errors if "favicon" not in e]
print("\nErros de console:", real or "nenhum")
sys.exit(1 if real else 0)
