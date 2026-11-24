# Formato de importação de questões (JSON)

O aplicativo importa arquivos `.json` neste formato. Antes de gravar, ele mostra uma prévia com as questões
válidas, inválidas e duplicadas. Nada é descartado silenciosamente: campos desconhecidos são guardados em `extra`.

## Estrutura

```json
{
  "metadata": {
    "source": "QConcursos",
    "subject": "Língua Portuguesa",
    "bank": "VUNESP",
    "exam": "Nome da prova",
    "created_at": "2026-11-23"
  },
  "questions": [
    {
      "id": "Q4425868",
      "subject": "Língua Portuguesa",
      "topics": ["Sintaxe", "Concordância verbal"],
      "bank": "VUNESP",
      "year": 2026,
      "organization": "Órgão do concurso",
      "exam_name": "Nome da prova",
      "statement": "Enunciado...",
      "support_text": null,
      "alternatives": { "A": "...", "B": "...", "C": "...", "D": "...", "E": "..." },
      "correct_answer": "C",
      "explanation": null,
      "difficulty": null,
      "images": []
    }
  ]
}
```

## Campos

| Campo | Obrigatório | Observações |
|---|---|---|
| `statement` | **sim** | Enunciado completo. |
| `alternatives` | **sim** | Objeto `{"A": "...", "B": "..."}` com pelo menos 2 alternativas (letras A–J). Uma lista simples também é aceita (vira A, B, C…). |
| `correct_answer` | **sim** | Letra do gabarito; precisa existir em `alternatives`. |
| `subject` | **sim**\* | Disciplina. \*Pode vir só em `metadata.subject`, valendo para todas as questões do arquivo. |
| `id` | não | ID original (ex.: `Q4425868`). Usado para detectar duplicadas. Sem ID, a duplicidade é detectada pelo texto. |
| `topics` | não | Lista de assuntos. Uma questão pode ter vários. Use `"Assunto > Subassunto"` para criar hierarquia. |
| `bank`, `year`, `organization`, `exam_name` | não | Banca, ano, órgão e nome da prova. `year` deve ser número. |
| `support_text` | não | Texto-base, quando existir. |
| `explanation` | não | Comentário/justificativa do gabarito. |
| `difficulty` | não | Texto livre (ex.: `fácil`, `média`, `difícil`). |
| `images` | não | Lista de `{"src": "...", "caption": "..."}`. `src` pode ser `data:image/...;base64,...` ou URL `https://`. Uma lista de strings também é aceita. |

Qualquer outro campo é preservado em `extra`.

## Regras de duplicidade

Uma questão é considerada duplicada se (a) o `id` já existe no banco, (b) o texto (enunciado + texto de apoio +
alternativas) é idêntico a uma questão existente, ou (c) aparece repetida no mesmo arquivo. Duplicadas são puladas.

## Disciplinas e assuntos

Disciplinas e assuntos que não existirem são criados na importação. Você pode escolher um **Concurso** na tela de
importação para agrupar as disciplinas criadas.
