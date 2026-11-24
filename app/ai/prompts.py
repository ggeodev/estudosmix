"""Prompts internos, um por funcionalidade. Mantidos aqui para ficarem consistentes e fáceis de ajustar."""
import json

TUTOR_SYSTEM = """Você é um tutor de estudos para concursos e vestibulares brasileiros. Responda sempre em português do Brasil.
Princípios:
- Priorize a COMPREENSÃO, não só entregar a resposta. Quando o aluno errou, comece identificando a natureza da dificuldade (conceito desconhecido, confusão entre conceitos, interpretação, procedimento, desatenção).
- Seja direto quando a pergunta for objetiva; não transforme tudo em perguntas socráticas. Use perguntas curtas só quando ajudarem.
- Se o aluno não entende, simplifique, use exemplos e aponte pré-requisitos que possam estar faltando.
- Seja correto e honesto: se não tiver certeza de um artigo de lei, número, prazo ou fórmula, diga isso em vez de inventar.
- Texto simples, sem tabelas nem markdown pesado. Parágrafos curtos."""

CONTENT_SYSTEM = """Você produz material de estudo objetivo e didático em português do Brasil para um aluno que errou ou acertou com insegurança uma questão de concurso.
Responda SOMENTE com JSON válido. Texto simples dentro dos campos (sem markdown). Não invente leis, artigos, prazos ou fórmulas: se não tiver certeza, diga isso no campo 'references'."""

EXTRACT_SYSTEM = """Você converte questões de provas em PDF para JSON. Fidelidade é a prioridade absoluta: copie enunciados, textos de apoio e alternativas exatamente como estão, sem resumir, corrigir ou reescrever. Nunca invente gabarito. Responda SOMENTE com JSON válido."""


def _q_block(q, include_answer=True):
    alts = "\n".join(f"{k}) {v}" for k, v in q["alternatives"].items())
    out = f"Disciplina: {q.get('subject_name') or ''}\nAssuntos: {', '.join(t['name'] for t in q.get('topics', [])) or '(não informado)'}\n"
    if q.get("support_text"):
        out += f"Texto de apoio:\n{q['support_text']}\n"
    out += f"Enunciado:\n{q['statement']}\nAlternativas:\n{alts}\n"
    if include_answer:
        out += f"Gabarito: {q['correct_answer']}\n"
        if q.get("explanation"):
            out += f"Explicação existente: {q['explanation']}\n"
    return out


def material_prompt(q, answer, level):
    ans = ""
    if answer:
        ans = (f"\nO aluno marcou: {answer['chosen']} ({'acertou' if answer['is_correct'] else 'errou'}), "
               f"confiança: {answer['confidence']}.")
        if answer.get("error_type"):
            ans += f" Causa do erro informada pelo aluno: {answer['error_type']}."
        if answer.get("error_note"):
            ans += f" Anotação do aluno: {answer['error_note']}"
    nivel = ("NIVEL: simples\nExplique de outro jeito, com linguagem mais simples, passo a passo, e um exemplo bem mais básico. Parta de pré-requisitos se necessário."
             if level == "simples" else "NIVEL: normal\nExplique o conceito de forma objetiva, porém completa o suficiente para permitir compreensão (não só memorizar a alternativa).")
    schema = {"concept": "nome curto do conhecimento específico exigido (máx. 10 palavras)", "explanation": "explicação do conceito",
              "rule": "regra ou fundamento principal (inclua lei/artigo/fórmula quando aplicável e tiver certeza)",
              "example": "exemplo prático", "why_correct": "por que a alternativa correta está certa",
              "why_wrong": {"<letra>": "por que esta alternativa errada está errada (apenas as relevantes)"},
              "prerequisites": ["conhecimentos prévios que podem estar faltando (lista curta, pode ser vazia)"],
              "references": ["leis, fórmulas ou fontes citadas (pode ser vazia)"]}
    return f"{nivel}\n\nQUESTÃO\n{_q_block(q)}{ans}\n\nDevolva JSON neste formato:\n{json.dumps(schema, ensure_ascii=False, indent=1)}"


def concepts_prompt(items):
    lines = []
    for it in items:
        q = it["q"]
        correct_text = q["alternatives"].get(q["correct_answer"], "")
        lines.append(f"ID={q['id']} | Disciplina: {q.get('subject_name')} | Enunciado: {q['statement'][:500]} | "
                     f"Gabarito: {q['correct_answer']}) {correct_text[:200]} | Aluno marcou: {it['chosen']}")
    return ("Para cada questão abaixo, nomeie em até 10 palavras o CONHECIMENTO ESPECÍFICO que ela exige "
            "(ex.: 'Prazo decadencial do mandado de segurança', 'Concordância com sujeito composto'). Seja específico, não genérico.\n\n"
            + "\n".join(lines)
            + '\n\nDevolva JSON: {"items": [{"question_id": <número do ID>, "concept": "..."}]}')


def verification_prompt(q, previous):
    prev = "\n".join(f"- {p[:200]}" for p in previous) or "(nenhuma)"
    return (f"Crie UMA questão nova de múltipla escolha (A a E) que cobre o MESMO conhecimento da questão abaixo, mas com contexto, "
            f"enunciado e alternativas diferentes (questão isomórfica). Não reutilize o mesmo exemplo. Apenas uma alternativa correta; "
            f"as erradas devem ser plausíveis. Mesmo nível e estilo de banca.\n\nQUESTÃO ORIGINAL\n{_q_block(q)}\n"
            f"Questões já geradas antes (não repita):\n{prev}\n\n"
            'Devolva JSON: {"statement": "...", "support_text": null ou "...", "alternatives": {"A":"...","B":"...","C":"...","D":"...","E":"..."}, '
            '"correct_answer": "letra", "explanation": "por que a correta está certa e as outras erradas"}')


def tutor_context(q, answer):
    txt = "CONTEXTO DA CONVERSA — questão em estudo:\n" + _q_block(q)
    if answer:
        txt += (f"O aluno marcou {answer['chosen']} ({'acertou' if answer['is_correct'] else 'errou'}), confiança: {answer['confidence']}.")
        if answer.get("error_type"):
            txt += f" Causa do erro informada: {answer['error_type']}."
    return txt


def extraction_prompt(subject_hint, filename):
    hint = f"A disciplina deste PDF é: {subject_hint}. Use-a em 'subject' quando o PDF não indicar outra.\n" if subject_hint else ""
    return f"""{hint}Converta as questões deste PDF (arquivo: {filename}) em JSON no formato:
{{"questions": [{{"id": "<código da questão, ex.: Q4425868, ou null>", "subject": "<disciplina>", "topics": ["<assunto>"],
"bank": "<banca>", "year": <ano numérico ou null>, "organization": "<órgão ou null>", "exam_name": "<prova ou null>",
"statement": "<enunciado completo>", "support_text": "<texto-base completo ou null>",
"alternatives": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}}, "correct_answer": "<letra>",
"explanation": "<comentário do gabarito se estiver no PDF, senão null>", "difficulty": null}}],
"omitted": ["<código ou descrição de cada questão omitida e o motivo>"]}}
Regras:
1. Copie os textos exatamente, sem resumir nem corrigir.
2. Nunca invente o gabarito. Se o PDF não indicar a resposta correta de uma questão, NÃO a inclua em 'questions'; liste-a em 'omitted'.
3. Ignore questões cortadas no início ou no fim deste trecho (incompletas); elas aparecem completas em outro trecho.
4. Se houver imagem, tabela ou gráfico essencial que não dê para transcrever, descreva-o em 'support_text' e cite a questão em 'omitted' com o motivo 'imagem'.
5. O gabarito pode estar numa seção separada (ex.: no fim do PDF ou ao lado de cada questão); procure-o antes de omitir."""
