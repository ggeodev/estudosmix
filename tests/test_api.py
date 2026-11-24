import json
import os
import tempfile
import unittest
from pathlib import Path

from app import create_app

SAMPLE = json.loads((Path(__file__).resolve().parent.parent / "samples" / "exemplo.json").read_text(encoding="utf-8"))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "t.db")
        self.app = create_app({"DATABASE_PATH": self.db_path, "TESTING": True})
        self.c = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def import_sample(self, data=None, exam_id=None):
        r = self.c.post("/api/imports/commit", json={"data": data or SAMPLE, "filename": "exemplo.json", "exam_id": exam_id})
        self.assertEqual(r.status_code, 201, r.json)
        return r.json

    def new_session(self, **body):
        r = self.c.post("/api/sessions", json=body)
        self.assertEqual(r.status_code, 201, r.json)
        return r.json["id"]


class ImportTests(Base):
    def test_preview_and_commit(self):
        prev = self.c.post("/api/imports/preview", json={"data": SAMPLE}).json
        self.assertEqual(prev["counts"], {"valid": 7, "invalid": 0, "duplicate": 0, "total": 7})
        self.assertEqual(self.c.get("/api/questions/count").json["total"], 0)  # prévia não grava
        res = self.import_sample()
        self.assertEqual(res["imported"], 7)
        tax = self.c.get("/api/taxonomy").json
        self.assertEqual({s["name"] for s in tax["subjects"]}, {"Língua Portuguesa", "Matemática", "Direito Constitucional", "Tecnologia da Informação"})
        names = {t["name"] for t in tax["topics"]}
        self.assertIn("Mandado de segurança", names)
        ms = next(t for t in tax["topics"] if t["name"] == "Mandado de segurança")
        parent = next(t for t in tax["topics"] if t["id"] == ms["parent_id"])
        self.assertEqual(parent["name"], "Remédios constitucionais")

    def test_duplicates_blocked(self):
        self.import_sample()
        prev = self.c.post("/api/imports/preview", json={"data": SAMPLE}).json
        self.assertEqual(prev["counts"]["duplicate"], 7)
        r = self.c.post("/api/imports/commit", json={"data": SAMPLE})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.c.get("/api/questions/count").json["total"], 7)

    def test_duplicate_by_text_without_id_and_within_file(self):
        self.import_sample()
        q = {k: v for k, v in SAMPLE["questions"][0].items() if k != "id"}
        data = {"metadata": {}, "questions": [q, dict(q), {**SAMPLE["questions"][3], "id": "DEMO-004"}]}
        prev = self.c.post("/api/imports/preview", json={"data": data}).json
        self.assertEqual([i["status"] for i in prev["items"]], ["duplicate", "duplicate", "duplicate"])
        fresh = {"metadata": {"subject": "X"}, "questions": [
            {"statement": "Nova?", "alternatives": {"A": "a", "B": "b"}, "correct_answer": "A"},
            {"statement": "Nova?", "alternatives": {"A": "a", "B": "b"}, "correct_answer": "A"}]}
        prev = self.c.post("/api/imports/preview", json={"data": fresh}).json
        self.assertEqual([i["status"] for i in prev["items"]], ["valid", "duplicate"])

    def test_validation_errors_are_reported(self):
        bad = {"metadata": {}, "questions": [
            {"statement": "", "alternatives": {"A": "x", "B": "y"}, "correct_answer": "A", "subject": "S"},
            {"statement": "ok", "alternatives": {"A": "x", "B": "y"}, "correct_answer": "D", "subject": "S"},
            {"statement": "ok", "alternatives": {"A": "x"}, "correct_answer": "A", "subject": "S"},
            {"statement": "ok", "alternatives": {"A": "x", "B": "y"}, "correct_answer": "A"},
            "não é objeto",
            {"statement": "bom", "alternatives": ["x", "y", "z"], "correct_answer": "b", "subject": "S", "year": "abc", "campo_novo": 1},
        ]}
        prev = self.c.post("/api/imports/preview", json={"data": bad}).json
        self.assertEqual(prev["counts"], {"valid": 1, "invalid": 5, "duplicate": 0, "total": 6})
        self.assertTrue(all(i["errors"] for i in prev["items"][:5]))
        warn = " ".join(prev["items"][5]["warnings"])
        self.assertIn("Ano inválido", warn)
        self.assertIn("campo_novo", warn)
        self.import_sample(bad)
        q = self.c.get("/api/questions?per_page=5").json["items"][0]
        full = self.c.get(f"/api/questions/{q['id']}").json
        self.assertEqual(full["extra"]["campo_novo"], 1)  # nada descartado
        self.assertEqual(full["extra"]["year"], "abc")
        self.assertEqual(full["alternatives"], {"A": "x", "B": "y", "C": "z"})

    def test_invalid_file_structure(self):
        r = self.c.post("/api/imports/preview", json={"data": {"foo": 1}})
        self.assertEqual(r.status_code, 400)

    def test_import_into_exam_and_delete_import(self):
        eid = self.c.post("/api/exams", json={"name": "Banco do Brasil"}).json["id"]
        res = self.import_sample(exam_id=eid)
        subs = self.c.get("/api/taxonomy").json["subjects"]
        self.assertTrue(all(s["exam_id"] == eid for s in subs))
        d = self.c.delete(f"/api/imports/{res['import_id']}").json
        self.assertEqual(d["removed_questions"], 7)
        self.assertEqual(self.c.get("/api/questions/count").json["total"], 0)

    def test_question_list_hides_answer(self):
        self.import_sample()
        item = self.c.get("/api/questions").json["items"][0]
        self.assertNotIn("correct_answer", item)
        self.assertNotIn("explanation", item)
        self.assertIn("correct_answer", self.c.get(f"/api/questions/{item['id']}").json)


class TaxonomyTests(Base):
    def test_crud_and_rules(self):
        eid = self.c.post("/api/exams", json={"name": "Concurso X"}).json["id"]
        sid = self.c.post("/api/subjects", json={"name": "Matemática", "exam_id": eid}).json["id"]
        t1 = self.c.post("/api/topics", json={"name": "Juros", "subject_id": sid}).json["id"]
        t2 = self.c.post("/api/topics", json={"name": "Compostos", "subject_id": sid, "parent_id": t1}).json["id"]
        self.assertEqual(self.c.patch(f"/api/topics/{t1}", json={"parent_id": t2}).status_code, 400)  # ciclo
        self.assertEqual(self.c.patch(f"/api/topics/{t2}", json={"name": "Juros compostos"}).status_code, 200)
        self.assertEqual(self.c.post("/api/topics", json={"name": "  ", "subject_id": sid}).status_code, 400)
        self.c.patch(f"/api/subjects/{sid}", json={"exam_id": None})
        self.assertIsNone(self.c.get("/api/taxonomy").json["subjects"][0]["exam_id"])
        self.c.delete(f"/api/topics/{t1}")  # remove subassunto junto
        self.assertEqual(self.c.get("/api/taxonomy").json["topics"], [])

    def test_cannot_delete_subject_with_questions_and_topic_assignment(self):
        self.import_sample()
        tax = self.c.get("/api/taxonomy").json
        mat = next(s for s in tax["subjects"] if s["name"] == "Matemática")
        r = self.c.delete(f"/api/subjects/{mat['id']}")
        self.assertEqual(r.status_code, 409)
        qs = self.c.get(f"/api/questions?subject_id={mat['id']}").json["items"]
        new_t = self.c.post("/api/topics", json={"name": "Razão", "subject_id": mat["id"]}).json["id"]
        port = next(s for s in tax["subjects"] if s["name"] == "Língua Portuguesa")
        t_port = self.c.post("/api/topics", json={"name": "Fonética", "subject_id": port["id"]}).json["id"]
        res = self.c.post("/api/questions/bulk-topics", json={"question_ids": [q["id"] for q in qs], "add_topic_ids": [new_t, t_port]}).json
        self.assertEqual(res["skipped_other_subject"], len(qs))  # assunto de outra disciplina é recusado
        got = self.c.get(f"/api/questions?topic_id={new_t}").json
        self.assertEqual(got["total"], len(qs))


class SessionTests(Base):
    def setUp(self):
        super().setUp()
        self.import_sample()

    def correct_of(self, qid):
        return self.c.get(f"/api/questions/{qid}").json["correct_answer"]

    def test_immediate_feedback_flow(self):
        sid = self.new_session(kind="bateria", limit=3)
        s = self.c.get(f"/api/sessions/{sid}").json
        self.assertEqual(len(s["questions"]), 3)
        self.assertNotIn("correct_answer", s["questions"][0])
        q = s["questions"][0]
        right = self.correct_of(q["id"])
        wrong = next(k for k in q["alternatives"] if k != right)
        r = self.c.post(f"/api/sessions/{sid}/answers", json={"question_id": q["id"], "chosen": wrong, "confidence": "certeza", "time_s": 20}).json
        self.assertFalse(r["is_correct"])
        self.assertEqual(r["correct_answer"], right)
        again = self.c.post(f"/api/sessions/{sid}/answers", json={"question_id": q["id"], "chosen": right, "confidence": "certeza"})
        self.assertEqual(again.status_code, 409)  # sem trocar após ver o gabarito
        self.assertEqual(self.c.patch(f"/api/answers/{r['answer_id']}", json={"error_type": "confusao", "error_note": "troquei fazer/haver"}).status_code, 200)
        self.assertEqual(self.c.patch(f"/api/answers/{r['answer_id']}", json={"error_type": "inventado"}).status_code, 400)
        res = self.c.post(f"/api/sessions/{sid}/finish").json
        self.assertEqual(res["summary"]["answered"], 1)
        self.assertEqual(res["summary"]["unanswered"], 2)
        self.assertEqual(res["summary"]["confident_wrong"], 1)
        self.assertEqual(res["confidence_matrix"]["certeza"]["wrong"], 1)
        self.assertEqual(res["items"][0]["answer"]["error_type"], "confusao")
        self.assertEqual(self.c.post(f"/api/sessions/{sid}/answers", json={"question_id": q["id"], "chosen": right, "confidence": "certeza"}).status_code, 409)

    def test_end_reveal_hides_until_finish(self):
        sid = self.new_session(kind="diagnostico", limit=2)
        qs = self.c.get(f"/api/sessions/{sid}").json["questions"]
        q = qs[0]
        right = self.correct_of(q["id"])
        r = self.c.post(f"/api/sessions/{sid}/answers", json={"question_id": q["id"], "chosen": right, "confidence": "chute", "time_s": 5}).json
        self.assertNotIn("is_correct", r)
        self.assertNotIn("correct_answer", r)
        self.assertEqual(self.c.get(f"/api/sessions/{sid}/results").status_code, 409)
        self.assertEqual(self.c.patch(f"/api/answers/{r['answer_id']}", json={"error_type": "outro"}).status_code, 409)
        other = next(k for k in q["alternatives"] if k != right)  # pode mudar antes de finalizar
        self.c.post(f"/api/sessions/{sid}/answers", json={"question_id": q["id"], "chosen": other, "confidence": "duvida"})
        got = self.c.get(f"/api/sessions/{sid}").json["questions"][0]["answer"]
        self.assertIsNone(got["is_correct"])
        self.assertNotIn("correct_answer", got)
        res = self.c.post(f"/api/sessions/{sid}/finish").json
        self.assertEqual(res["summary"]["wrong"], 1)

    def test_validation_of_answer(self):
        sid = self.new_session(kind="bateria", limit=1)
        q = self.c.get(f"/api/sessions/{sid}").json["questions"][0]
        post = lambda **b: self.c.post(f"/api/sessions/{sid}/answers", json=b).status_code
        self.assertEqual(post(question_id=q["id"], chosen="Z", confidence="certeza"), 400)
        self.assertEqual(post(question_id=q["id"], chosen="A", confidence="talvez"), 400)
        self.assertEqual(post(question_id=99999, chosen="A", confidence="certeza"), 404)

    def test_filters_and_empty_session(self):
        r = self.c.post("/api/sessions", json={"kind": "bateria", "filters": {"bank": "Inexistente"}})
        self.assertEqual(r.status_code, 400)
        sid = self.new_session(kind="bateria", limit=1)
        q = self.c.get(f"/api/sessions/{sid}").json["questions"][0]
        a = self.c.post(f"/api/sessions/{sid}/answers", json={"question_id": q["id"], "chosen": self.correct_of(q["id"]), "confidence": "chute"}).json
        self.c.post(f"/api/sessions/{sid}/finish")
        self.assertEqual(self.c.get("/api/questions/count?status=unseen").json["total"], 6)
        self.assertEqual(self.c.get("/api/questions/count?status=fragile").json["total"], 1)  # acerto com chute
        self.assertEqual(self.c.get("/api/questions/count?status=correct").json["total"], 1)
        self.assertEqual(self.c.get("/api/questions/count?status=wrong").json["total"], 0)
        self.assertEqual(self.c.get("/api/questions/count?status=xx").status_code, 400)
        self.assertEqual(self.c.post(f"/api/questions/{q['id']}/flag").json["flagged"], True)
        self.assertEqual(self.c.get("/api/questions/count?status=flagged").json["total"], 1)

    def test_mixed_and_stats_and_dashboard(self):
        sid = self.new_session(kind="misto", limit=6)
        qs = self.c.get(f"/api/sessions/{sid}").json["questions"]
        self.assertEqual(len({q["subject_id"] for q in qs[:4]}), 4)  # intercala disciplinas
        for i, q in enumerate(qs):
            right = self.correct_of(q["id"])
            pick = right if i % 2 == 0 else next(k for k in q["alternatives"] if k != right)
            self.c.post(f"/api/sessions/{sid}/answers", json={"question_id": q["id"], "chosen": pick, "confidence": "certeza" if i % 2 == 0 else "duvida", "time_s": 10})
        self.c.post(f"/api/sessions/{sid}/finish")
        st = self.c.get("/api/stats").json
        self.assertEqual(st["overall"]["answered"], 6)
        self.assertEqual(st["overall"]["correct"], 3)
        self.assertEqual(st["overall"]["accuracy"], 50)
        self.assertEqual(sum(r["n"] for r in st["by_subject"]), 6)
        self.assertEqual(st["facts"]["errors_without_cause"], 3)
        self.assertEqual(st["novelty"][0]["name"], "new")
        d = self.c.get("/api/dashboard?tz=180").json
        self.assertEqual(d["totals"]["answered"], 6)
        self.assertEqual(d["totals"]["study_seconds"], 60)
        self.assertEqual(d["totals"]["sessions_finished"], 1)
        self.assertEqual(d["suggestion"]["kind"], "gaps")  # há erros ainda sem estudo
        self.assertEqual(sum(day["n"] for day in d["activity"]), 6)
        # segunda sessão repete questões -> contam como 'repeated'
        sid2 = self.new_session(kind="bateria", question_ids=[qs[0]["id"]])
        self.c.post(f"/api/sessions/{sid2}/answers", json={"question_id": qs[0]["id"], "chosen": self.correct_of(qs[0]["id"]), "confidence": "certeza"})
        st = self.c.get("/api/stats?days=7").json
        self.assertEqual({r["name"]: r["n"] for r in st["novelty"]}, {"new": 6, "repeated": 1})


class SystemTests(Base):
    def test_persistence_across_restart(self):
        self.import_sample()
        sid = self.new_session(kind="bateria", limit=1)
        q = self.c.get(f"/api/sessions/{sid}").json["questions"][0]
        self.c.post(f"/api/sessions/{sid}/answers", json={"question_id": q["id"], "chosen": "A", "confidence": "chute", "time_s": 7})
        self.c.post(f"/api/sessions/{sid}/finish")
        self.c.put("/api/settings", json={"theme": "light"})
        app2 = create_app({"DATABASE_PATH": self.db_path, "TESTING": True})  # "reabrir o aplicativo"
        c2 = app2.test_client()
        self.assertEqual(c2.get("/api/questions/count").json["total"], 7)
        self.assertEqual(c2.get("/api/dashboard").json["totals"]["answered"], 1)
        self.assertEqual(c2.get("/api/settings").json["theme"], "light")
        self.assertEqual(len(c2.get("/api/sessions").json), 1)

    def test_settings_validation_backup_static(self):
        self.assertEqual(self.c.put("/api/settings", json={"theme": "neon"}).status_code, 400)
        self.assertEqual(self.c.put("/api/settings", json={"foo": 1}).status_code, 400)
        r = self.c.get("/api/backup")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data.startswith(b"SQLite format 3"))
        self.assertEqual(self.c.get("/api/nada").status_code, 404)
        self.assertEqual(self.c.get("/files/exemplo.json").status_code, 200)
        self.assertEqual(self.c.get("/files/app.py").status_code, 404)


if __name__ == "__main__":
    unittest.main()
