"""Provedor falso para testes e demonstração offline. Não chama nenhuma API."""
import hashlib
import itertools
import json
import re

from .base import Provider

_counter = itertools.count(1)


class FakeProvider(Provider):
    name = "fake"
    model = "fake-model"
    extraction_model = "fake-extraction"

    def generate(self, feature, system, contents, json_mode=False, model=None):
        prompt = contents[-1]["parts"][0]["text"]
        n = next(_counter)
        if feature == "material":
            simple = "NIVEL: simples" in prompt
            return json.dumps({
                "concept": "Conceito de teste",
                "explanation": f"[fake] Explicação {'simplificada ' if simple else ''}do conceito.",
                "rule": "[fake] Regra principal.",
                "example": f"[fake] Exemplo {'bem simples ' if simple else ''}prático.",
                "why_correct": "[fake] Por que a alternativa correta está certa.",
                "why_wrong": {"A": "[fake] errada"},
                "prerequisites": ["Pré-requisito de teste"],
                "references": ["Lei de teste"],
            })
        if feature == "concepts":
            ids = [int(i) for i in re.findall(r"ID=(\d+)", prompt)]
            return json.dumps({"items": [{"question_id": i, "concept": f"Conceito específico {i}"} for i in ids]})
        if feature == "verification":
            return json.dumps({
                "statement": f"[fake] Questão de verificação inédita número {n}?",
                "support_text": None,
                "alternatives": {"A": "opção a", "B": "opção b", "C": "opção c", "D": "opção d", "E": "opção e"},
                "correct_answer": "B",
                "explanation": "[fake] A alternativa B está correta.",
            })
        if feature == "tutor":
            return f"[fake tutor] Resposta {n} sobre: {prompt[-60:]}"
        return "ok"

    def generate_pdf(self, feature, system, prompt, pdf_bytes, model=None):
        h = hashlib.sha1(pdf_bytes).hexdigest()[:8]
        if b"BROKEN" in pdf_bytes:
            return "isto não é JSON"
        qs = [{
            "id": f"PDF-{h}-{i}", "subject": "Disciplina PDF", "topics": ["Assunto PDF"], "bank": "Banca PDF", "year": 2025,
            "statement": f"[fake] Questão {i} extraída do PDF {h}.",
            "alternatives": {"A": "a", "B": "b", "C": "c", "D": "d", "E": "e"}, "correct_answer": "C",
        } for i in (1, 2)]
        return json.dumps({"questions": qs, "omitted": [f"PDF-{h}-9 (sem gabarito)"]})
