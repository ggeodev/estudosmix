import io
import os
import sqlite3
import tempfile
import unittest

from pypdf import PdfWriter

import app.config as appconfig
from test_api import SAMPLE, Base
from app.services import pdf_import


def make_pdf(pages=2, title=None):
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(200, 200)
    if title:
        w.add_metadata({"/Title": title})
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


class P2(Base):
    def setUp(self):
        self._old = os.environ.get("AI_PROVIDER")
        os.environ["AI_PROVIDER"] = "fake"
        super().setUp()
        self.app.config["PDF_WORKER"] = False
        self.import_sample()

    def tearDown(self):
        if self._old is None:
            os.environ.pop("AI_PROVIDER", None)
        else:
            os.environ["AI_PROVIDER"] = self._old
        super().tearDown()

    def raw(self, sql, params=()):
        conn = sqlite3.connect(self.db_path)
        conn.execute(sql, params)
        conn.commit()
        conn.close()

    def qids(self, **filters):
        return [q["id"] for q in self.c.get("/api/questions?per_page=50" + "".join(f"&{k}={v}" for k, v in filters.items())).json["items"]]

    def answer(self, sid, qid, right, conf="certeza", t=5):
        correct = self.c.get(f"/api/questions/{qid}").json["correct_answer"]
        q = self.c.get(f"/api/questions/{qid}").json
        pick = correct if right else next(k for k in q["alternatives"] if k != correct)
        return self.c.post(f"/api/sessions/{sid}/answers", json={"question_id": qid, "chosen": pick, "confidence": conf, "time_s": t}).json

    def wrong_in_session(self, qid, conf="certeza"):
        sid = self.new_session(kind="bateria", question_ids=[qid])
        self.answer(sid, qid, False, conf)
        self.c.post(f"/api/sessions/{sid}/finish")
        return sid


class ReviewTests(P2):
    def test_schedule_rules(self):
        q = self.qids()[0]
        for right, conf, days, reason in [(False, "certeza", 1, "errou"), (True, "chute", 2, "chute"), (True, "duvida", 3, "duvida"),
                                          (True, "certeza", 3, "consolidando")]:
            sid = self.new_session(kind="bateria", question_ids=[q])
            self.answer(sid, q, right, conf)
            row = sqlite3.connect(self.db_path).execute("SELECT interval_days, reason FROM reviews WHERE question_id=?", (q,)).fetchone()
            self.assertEqual(row, (days, reason), (right, conf))
        for _ in range(3):  # acertos seguidos com certeza ampliam o intervalo (escada 3,7,16,35)
            sid = self.new_session(kind="bateria", question_ids=[q])
            self.answer(sid, q, True, "certeza")
        row = sqlite3.connect(self.db_path).execute("SELECT interval_days, streak, reason FROM reviews WHERE question_id=?", (q,)).fetchone()
        self.assertEqual(row, (35, 4, "consolidando"))  # 1 acerto + 3 seguidos = 4º degrau da escada

    def test_change_of_answer_is_idempotent_and_delete_recomputes(self):
        q = self.qids()[0]
        sid = self.new_session(kind="diagnostico", question_ids=[q])
        self.answer(sid, q, False, "certeza")
        self.answer(sid, q, True, "certeza")  # troca de resposta antes de finalizar
        row = sqlite3.connect(self.db_path).execute("SELECT interval_days, streak FROM reviews WHERE question_id=?", (q,)).fetchone()
        self.assertEqual(row, (3, 1))
        self.c.delete(f"/api/sessions/{sid}")
        self.assertEqual(sqlite3.connect(self.db_path).execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 0)

    def test_due_list_and_review_session(self):
        a, b = self.qids()[:2]
        self.wrong_in_session(a)
        self.wrong_in_session(b, "chute")
        self.assertEqual(self.c.get("/api/reviews").json["due_count"], 0)  # só vencem no futuro
        self.assertEqual(self.c.post("/api/reviews/session", json={}).status_code, 400)
        self.raw("UPDATE reviews SET due_at = '2020-01-01T00:00:00Z'")
        ov = self.c.get("/api/reviews").json
        self.assertEqual(ov["due_count"], 2)
        self.assertEqual(ov["due"][0]["reason"], "errou")  # prioridade: erro antes de chute
        d = self.c.get("/api/dashboard").json
        self.assertEqual(d["suggestion"]["kind"], "review")
        self.assertEqual(d["totals"]["reviews_due"], 2)
        sid = self.c.post("/api/reviews/session", json={"limit": 5}).json["id"]
        s = self.c.get(f"/api/sessions/{sid}").json
        self.assertEqual((s["kind"], len(s["questions"])), ("revisao", 2))


class StudyTests(P2):
    def test_gaps_hide_unrevealed_diagnostic(self):
        q = self.qids()[0]
        sid = self.new_session(kind="diagnostico", question_ids=[q])
        self.answer(sid, q, False)
        self.assertEqual(self.c.get("/api/gaps").json["items"], [])  # gabarito ainda não revelado
        self.assertEqual(self.c.get(f"/api/study/{q}").status_code, 409)
        self.assertEqual(self.c.post(f"/api/study/{q}/material", json={}).status_code, 409)
        self.assertEqual(self.c.post("/api/tutor/chat", json={"thread": f"q:{q}", "message": "oi"}).status_code, 409)
        self.c.post(f"/api/sessions/{sid}/finish")
        items = self.c.get("/api/gaps").json["items"]
        self.assertEqual([(i["question_id"], i["kind"], i["confident_wrong"]) for i in items], [(q, "lacuna", True)])

    def test_gap_kinds_order_and_analysis(self):
        a, b, c, d = self.qids()[:4]
        sid = self.new_session(kind="diagnostico", question_ids=[a, b, c, d])
        self.answer(sid, a, True, "certeza")
        self.answer(sid, b, True, "chute")
        self.answer(sid, c, True, "duvida")
        self.answer(sid, d, False, "duvida")
        self.c.post(f"/api/sessions/{sid}/finish")
        kinds = [(i["question_id"], i["kind"]) for i in self.c.get("/api/gaps").json["items"]]
        self.assertEqual(kinds, [(d, "lacuna"), (b, "chute"), (c, "fragil")])  # acerto com certeza não é lacuna
        an = self.c.get(f"/api/sessions/{sid}/analysis").json
        self.assertEqual([len(an[k]) for k in ("demonstrated", "gaps", "fragile", "guessed")], [1, 1, 1, 1])
        self.assertTrue(an["small_sample"])
        self.assertEqual(an["unnamed"], 3)
        self.assertEqual(self.c.post("/api/gaps/name-concepts", json={"session_id": sid}).json["named"], 3)
        self.assertEqual(self.c.get(f"/api/sessions/{sid}/analysis").json["unnamed"], 0)
        self.assertTrue(self.c.get(f"/api/sessions/{sid}/analysis").json["gaps"][0]["label"].startswith("Conceito específico"))

    def test_material_cached_and_levels(self):
        q = self.qids()[0]
        self.wrong_in_session(q)
        m = self.c.post(f"/api/study/{q}/material", json={}).json
        self.assertFalse(m["cached"])
        self.assertIn("Explicação do conceito", m["material"]["explanation"])
        self.assertTrue(self.c.post(f"/api/study/{q}/material", json={}).json["cached"])  # sem nova chamada de IA
        calls = self.c.get("/api/ai/status").json["usage"]["calls"]
        self.c.post(f"/api/study/{q}/material", json={})
        self.assertEqual(self.c.get("/api/ai/status").json["usage"]["calls"], calls)
        simple = self.c.post(f"/api/study/{q}/material", json={"level": "simples"}).json
        self.assertIn("simplificada", simple["material"]["explanation"])
        self.assertEqual(self.c.post(f"/api/study/{q}/material", json={"level": "x"}).status_code, 400)
        st = self.c.get(f"/api/study/{q}").json
        self.assertEqual(set(st["materials"]), {"normal", "simples"})
        self.assertEqual(st["last_answer"]["is_correct"], 0)

    def test_verification_existing_then_ai_and_record(self):
        mat = [q["id"] for q in self.c.get("/api/questions?topic_id=" + str(self.topic_id("Porcentagem"))).json["items"]]
        self.assertEqual(len(mat), 2)  # DEMO-004 e DEMO-005 compartilham "Porcentagem"
        origin = mat[0]
        self.wrong_in_session(origin)
        v = self.c.post(f"/api/study/{origin}/verification", json={}).json
        self.assertEqual((v["source"], v["question_id"]), ("existing", mat[1]))  # prefere questão inédita do banco
        sid = v["session_id"]
        self.answer(sid, v["question_id"], True, "certeza")
        rec = self.c.post(f"/api/study/{origin}/record", json={"session_id": sid}).json
        self.assertEqual(rec["outcome"], "correct_confident")
        self.assertIsNotNone(rec["review_original"])
        self.assertEqual(self.c.post(f"/api/study/{origin}/record", json={"session_id": sid}).status_code, 409)
        self.assertEqual(self.c.get("/api/gaps").json["items"], [])  # lacuna consolidada some da lista
        self.assertEqual(self.c.get("/api/study/records").json[0]["outcome"], "correct_confident")
        # sem inéditas: modo existing falha, auto cai para IA
        self.assertEqual(self.c.post(f"/api/study/{origin}/verification", json={"mode": "existing"}).status_code, 404)
        v2 = self.c.post(f"/api/study/{origin}/verification", json={}).json
        self.assertEqual(v2["source"], "ai")
        gen = self.c.get(f"/api/questions/{v2['question_id']}").json
        self.assertEqual(gen["bank"], "Gerada por IA")
        self.assertTrue(gen["extra"]["ai_generated"])
        self.assertEqual(gen["extra"]["derived_from"], origin)
        self.assertEqual([t["name"] for t in gen["topics"]], ["Porcentagem"])

    def test_verification_wrong_keeps_gap_open(self):
        origin = self.qids()[0]
        self.wrong_in_session(origin)
        v = self.c.post(f"/api/study/{origin}/verification", json={"mode": "ai"}).json
        self.answer(v["session_id"], v["question_id"], True, "chute")
        rec = self.c.post(f"/api/study/{origin}/record", json={"session_id": v["session_id"]}).json
        self.assertEqual(rec["outcome"], "correct_fragile")
        gap = next(g for g in self.c.get("/api/gaps").json["items"] if g["question_id"] == origin)
        self.assertEqual(gap["studied"]["outcome"], "correct_fragile")

    def topic_id(self, name):
        return next(t["id"] for t in self.c.get("/api/taxonomy").json["topics"] if t["name"] == name)


class TutorAndAITests(P2):
    def test_tutor_threads(self):
        q = self.qids()[0]
        self.wrong_in_session(q)
        r = self.c.post("/api/tutor/chat", json={"thread": f"q:{q}", "message": "Não entendi, pode explicar?"}).json
        self.assertTrue(r["reply"].startswith("[fake tutor]"))
        r2 = self.c.post("/api/tutor/chat", json={"thread": f"q:{q}", "message": "E se fosse plural?"}).json
        h = self.c.get(f"/api/tutor/history?thread=q:{q}").json
        self.assertEqual([m["role"] for m in h], ["user", "model", "user", "model"])
        self.assertEqual(self.c.post("/api/tutor/chat", json={"thread": "free", "message": "   "}).status_code, 400)
        self.assertEqual(self.c.post("/api/tutor/chat", json={"thread": "../x", "message": "oi"}).status_code, 400)
        self.assertEqual(self.c.get("/api/tutor/threads").json[0]["thread"], f"q:{q}")
        self.c.delete(f"/api/tutor/history?thread=q:{q}")
        self.assertEqual(self.c.get(f"/api/tutor/history?thread=q:{q}").json, [])

    def test_not_configured_and_key_never_exposed(self):
        os.environ["AI_PROVIDER"] = "gemini"
        saved = os.environ.pop("GEMINI_API_KEY", None)
        env = os.path.join(self.tmp.name, ".env")
        old_path = appconfig.ENV_PATH
        appconfig.ENV_PATH = type(old_path)(env)
        try:
            r = self.c.post("/api/tutor/chat", json={"thread": "free", "message": "oi"})
            self.assertEqual((r.status_code, r.json["kind"]), (400, "not_configured"))
            self.assertFalse(self.c.get("/api/ai/status").json["configured"])
            self.assertEqual(self.c.put("/api/ai/config", json={"api_key": "curta"}).status_code, 400)
            secret = "AIzaSy" + "x" * 30
            r = self.c.put("/api/ai/config", json={"api_key": secret, "model": "gemini-3.5-flash-lite"})
            self.assertEqual(r.status_code, 200)
            self.assertNotIn(secret, r.get_data(as_text=True))
            self.assertTrue(r.json["configured"])
            self.assertIn(secret, open(env).read())
            self.assertNotIn(secret, self.c.get("/api/ai/status").get_data(as_text=True))
        finally:
            appconfig.ENV_PATH = old_path
            os.environ.pop("GEMINI_API_KEY", None)
            if saved:
                os.environ["GEMINI_API_KEY"] = saved

    def test_ai_error_is_reported_and_logged(self):
        from app.ai import gemini
        import requests
        os.environ["AI_PROVIDER"] = "gemini"
        os.environ["GEMINI_API_KEY"] = "k" * 30

        class R:
            def __init__(s, code, body):
                s.status_code, s._b, s.text = code, body, ""
            def json(s):
                return s._b
        orig = requests.post
        try:
            requests.post = lambda *a, **k: R(404, {"error": {"message": "model not found"}})
            r = self.c.post("/api/ai/test")
            self.assertEqual((r.status_code, r.json["kind"]), (502, "model"))
            self.assertIn("Modelo", r.json["error"])
            requests.post = lambda *a, **k: R(403, {"error": {"message": "API key not valid"}})
            self.assertEqual(self.c.post("/api/ai/test").json["kind"], "auth")
            sent = {}
            def ok(url, headers=None, json=None, timeout=None):
                sent.update(url=url, headers=headers, body=json)
                return R(200, {"candidates": [{"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}]})
            requests.post = ok
            self.assertTrue(self.c.post("/api/ai/test").json["ok"])
            self.assertIn("gemini-3.5-flash-lite:generateContent", sent["url"])
            self.assertEqual(sent["headers"]["x-goog-api-key"], "k" * 30)  # chave vai no header, nunca na URL
            self.assertNotIn("temperature", str(sent["body"]))  # modelos novos não aceitam
        finally:
            requests.post = orig
            os.environ["AI_PROVIDER"] = "fake"
            os.environ.pop("GEMINI_API_KEY", None)
        u = self.c.get("/api/ai/status").json["usage"]
        self.assertEqual((u["calls"], u["failed"]), (3, 2))


class PdfTests(P2):
    def upload(self, name, data, **form):
        return self.c.post("/api/pdf-jobs", data={"files": (io.BytesIO(data), name), **form}, content_type="multipart/form-data")

    def test_pdf_flow_to_import(self):
        r = self.upload("grande.pdf", make_pdf(15), subject="Matemática")
        self.assertEqual(r.status_code, 201)
        self.upload("pequeno.pdf", make_pdf(2))
        self.upload("quebrado.pdf", make_pdf(2, title="BROKEN"))
        self.assertEqual(self.upload("x.pdf", b"nao e pdf").status_code, 400)
        pdf_import.process_all(self.app)
        jobs = {j["filename"]: j for j in self.c.get("/api/pdf-jobs").json}
        self.assertEqual(jobs["grande.pdf"]["status"], "done")
        self.assertEqual(jobs["grande.pdf"]["chunks_total"], 3)  # 15 páginas, trechos de 6 com 1 de sobreposição
        self.assertGreaterEqual(jobs["grande.pdf"]["n_questions"], 2)
        self.assertEqual(jobs["grande.pdf"]["n_omitted"], 3)
        self.assertEqual(jobs["pequeno.pdf"]["n_questions"], 2)
        self.assertEqual(jobs["quebrado.pdf"]["status"], "error")
        self.assertIn("JSON", jobs["quebrado.pdf"]["error"])
        ids = [jobs["grande.pdf"]["id"], jobs["pequeno.pdf"]["id"]]
        payload = self.c.post("/api/pdf-jobs/combine", json={"job_ids": ids}).json
        self.assertEqual(payload["questions"][0]["source_pdf"], "grande.pdf")
        self.assertEqual(self.c.post("/api/pdf-jobs/combine", json={"job_ids": [jobs["quebrado.pdf"]["id"]]}).status_code, 409)
        prev = self.c.post("/api/imports/preview", json={"data": payload}).json
        self.assertEqual(prev["counts"]["invalid"], 0)
        self.assertIn("Matemática", prev["subjects"] + ["Matemática"])
        res = self.c.post("/api/imports/commit", json={"data": payload, "filename": "pdfs", "pdf_job_ids": ids}).json
        self.assertEqual(res["imported"], len(payload["questions"]))
        self.assertTrue(all(j["imported_at"] for j in self.c.get("/api/pdf-jobs").json if j["id"] in ids))
        q = self.c.get(f"/api/questions?q=PDF-&per_page=1").json["items"][0]
        self.assertEqual(self.c.get(f"/api/questions/{q['id']}").json["extra"]["source_pdf"], "grande.pdf")
        # retry / delete
        bad = jobs["quebrado.pdf"]["id"]
        self.assertEqual(self.c.post(f"/api/pdf-jobs/{bad}/retry").status_code, 200)
        self.assertEqual(self.c.delete(f"/api/pdf-jobs/{bad}").status_code, 200)
        self.assertEqual(self.c.post(f"/api/pdf-jobs/{bad}/retry").status_code, 404)


if __name__ == "__main__":
    unittest.main()
