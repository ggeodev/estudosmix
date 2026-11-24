import base64
import time

import requests

from .base import AIError, Provider

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(self, api_key, model, extraction_model):
        self.api_key = api_key
        self.model = model
        self.extraction_model = extraction_model

    def _post(self, model, body):
        url = f"{BASE_URL}/{model}:generateContent"
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        r = None
        for attempt in range(3):
            try:
                r = requests.post(url, headers=headers, json=body, timeout=240)
            except requests.Timeout:
                raise AIError("A IA demorou demais para responder. Tente novamente.", "timeout", 504)
            except requests.RequestException:
                raise AIError("Não foi possível conectar à API do Gemini. Verifique sua internet.", "network", 503)
            if r.status_code in (429, 500, 503) and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            break
        if r.status_code != 200:
            try:
                detail = r.json().get("error", {}).get("message", "")
            except ValueError:
                detail = r.text[:200]
            s = r.status_code
            if s == 429:
                raise AIError("Limite de requisições da API atingido. Aguarde um pouco e tente de novo (ou verifique sua cota).", "rate_limit", 429)
            if s in (401, 403) or "API key" in detail:
                raise AIError("A chave de API foi recusada. Confira a chave em Configurações → IA.", "auth", 502)
            if s == 404:
                raise AIError(f"Modelo '{model}' não encontrado. Troque o nome do modelo em Configurações → IA. ({detail[:120]})", "model", 502)
            raise AIError(f"Erro da API do Gemini ({s}): {detail[:200]}", "error", 502)
        data = r.json()
        cands = data.get("candidates") or []
        if not cands:
            reason = (data.get("promptFeedback") or {}).get("blockReason")
            raise AIError(f"A IA não devolveu resposta{f' (bloqueio: {reason})' if reason else ''}.", "bad_output")
        parts = (cands[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if cands[0].get("finishReason") == "MAX_TOKENS":
            raise AIError("A resposta da IA foi cortada por ser longa demais.", "truncated")
        if not text.strip():
            raise AIError("A IA devolveu uma resposta vazia.", "bad_output")
        return text

    # Obs.: modelos recentes não aceitam 'temperature'/'top_p'; por isso não enviamos esses parâmetros.
    def generate(self, feature, system, contents, json_mode=False, model=None):
        body = {"contents": contents}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if json_mode:
            body["generationConfig"] = {"responseMimeType": "application/json"}
        return self._post(model or self.model, body)

    def generate_pdf(self, feature, system, prompt, pdf_bytes, model=None):
        body = {
            "contents": [{"role": "user", "parts": [
                {"inlineData": {"mimeType": "application/pdf", "data": base64.b64encode(pdf_bytes).decode()}},
                {"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        return self._post(model or self.extraction_model, body)
