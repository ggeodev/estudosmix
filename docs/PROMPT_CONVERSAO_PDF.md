# Prompt para converter um PDF de questões em JSON

Envie o PDF para a IA de sua preferência junto com o texto abaixo (copie tudo a partir da linha de baixo).

---

Você vai converter as questões deste PDF para um arquivo JSON. Responda **somente com JSON válido**, sem comentários
e sem blocos de markdown.

Formato:

{
  "metadata": { "source": "QConcursos", "subject": "<disciplina>", "exam": "<nome da prova, se houver>", "created_at": "<AAAA-MM-DD>" },
  "questions": [
    {
      "id": "<código da questão, ex.: Q4425868; null se não houver>",
      "subject": "<disciplina>",
      "topics": ["<assunto>", "<outro assunto, se houver>"],
      "bank": "<banca>",
      "year": <ano como número ou null>,
      "organization": "<órgão ou null>",
      "exam_name": "<nome da prova ou null>",
      "statement": "<enunciado completo>",
      "support_text": "<texto-base completo ou null>",
      "alternatives": { "A": "...", "B": "...", "C": "...", "D": "...", "E": "..." },
      "correct_answer": "<letra do gabarito>",
      "explanation": "<comentário do gabarito, se estiver no PDF; senão null>",
      "difficulty": null,
      "images": []
    }
  ]
}

Regras:
1. Copie enunciados, textos de apoio e alternativas **exatamente** como estão, sem resumir nem corrigir.
2. Não invente o gabarito. Se o PDF não indicar a resposta correta de uma questão, não inclua essa questão e liste os
   códigos omitidos em `metadata.omitted`.
3. Se uma questão tiver imagem, tabela ou gráfico que não possa ser transcrito em texto, descreva o conteúdo em
   `support_text` e registre o código da questão em `metadata.notes`. Nunca descarte informação sem avisar.
4. Use o campo `topics` para o assunto/subassunto indicado no PDF (ex.: "Sintaxe > Concordância verbal").
5. Se houver muitas questões, divida em partes de até ~40 questões e mantenha o mesmo formato em cada parte.
