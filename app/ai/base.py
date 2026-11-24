class AIError(Exception):
    """Erro de IA com mensagem amigável. kind: not_configured|auth|rate_limit|network|timeout|model|truncated|bad_output|error"""

    def __init__(self, message, kind="error", status=502):
        super().__init__(message)
        self.message = message
        self.kind = kind
        self.status = status


class Provider:
    name = "base"
    model = ""
    extraction_model = ""

    def generate(self, feature, system, contents, json_mode=False, model=None):
        """contents: lista [{'role': 'user'|'model', 'parts': [{'text': ...}]}]. Retorna texto."""
        raise NotImplementedError

    def generate_pdf(self, feature, system, prompt, pdf_bytes, model=None):
        raise NotImplementedError
