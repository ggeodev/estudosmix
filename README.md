# Estudos — app pessoal de estudos por questões

Aplicativo web local para estudar com questões de concursos e provas. Roda no seu computador, grava tudo em um
arquivo SQLite e abre no navegador.

## Como executar

Requisitos: **Python 3.10+** (nada de Node, build ou Docker). Dependências: Flask, requests, pypdf.

```bash
cd estudos
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python3 run.py
```

Abra **http://127.0.0.1:5000**. Para fechar, `Ctrl+C` no terminal. Ao abrir de novo, seus dados continuam lá.

Variáveis opcionais: `ESTUDOS_DB` (caminho do banco, padrão `data/estudos.db`), `ESTUDOS_PORT`, `ESTUDOS_HOST`.
O servidor escuta só em `127.0.0.1` (apenas o seu computador).

## Importar seu primeiro conjunto de questões

1. Baixe o PDF de questões (ex.: QConcursos).
2. Envie o PDF para uma IA junto com o texto de `docs/PROMPT_CONVERSAO_PDF.md` (também disponível na tela
   *Importar questões*). Salve a resposta como `.json`.
3. No app: **Importar questões** → escolha o arquivo → confira a prévia (válidas / duplicadas / inválidas) → **Importar**.

O formato está documentado em `docs/FORMATO_IMPORTACAO.md`. Para testar sem PDF, importe `samples/exemplo.json`
(7 questões **fictícias de demonstração**, identificadas como EXEMPLO; apague-as depois em *Importar questões →
Importações anteriores → Excluir questões*).

## Configurar o Gemini (tutor, explicações, questões e PDFs)

1. Gere uma chave em https://aistudio.google.com (Get API key).
2. No app: **Configurações → Inteligência artificial**, cole a chave, **Salvar** e **Testar conexão**.
   (Alternativa: copie `.env.example` para `.env` e preencha `GEMINI_API_KEY`.)

A chave fica só no `.env` local (arquivo protegido e ignorado pelo git), é usada apenas pelo servidor e nunca volta ao navegador.
**Não cole a chave em chats nem a envie a ninguém.**

Modelos padrão: `gemini-3.5-flash-lite` (tutor/explicações/questões, econômico) e `gemini-3.5-flash` (conversão de PDFs, onde a
fidelidade importa mais). Os nomes são editáveis em Configurações porque o Google aposenta modelos com frequência
(o `gemini-2.5-flash` sai do ar em 01/12/2026). Confira preços e cota gratuita em https://ai.google.dev/pricing. O app conta as
chamadas feitas (Configurações → IA) e evita repetir chamadas: explicações ficam em cache.

> A comunicação real com a API do Gemini foi escrita seguindo a documentação, mas **só foi testada com um provedor simulado e
> respostas HTTP simuladas** (o ambiente de desenvolvimento não tinha internet). Use **Testar conexão** primeiro; se algo falhar,
> a mensagem de erro diz o que ajustar (chave, modelo ou limite de requisições).

## Converter PDFs de questões dentro do app

**Importar questões → PDFs com IA.** Envie vários PDFs de uma vez; a conversão roda em segundo plano (cada PDF é dividido em
trechos de 6 páginas com 1 de sobreposição). Ao terminar, selecione os prontos e confira tudo na mesma **prévia** da importação
JSON. Nada entra no banco sem sua confirmação. Questões sem gabarito no PDF são omitidas (nunca inventadas) e listadas; a origem de
cada questão fica guardada em `extra.source_pdf`. Alternativa: converter fora do app com `docs/PROMPT_CONVERSAO_PDF.md`.

## Estado das funcionalidades

**Fase 1 (MVP) — implementada e testada**: importação JSON, organização por concurso/disciplina/assunto, banco com filtros,
sessões (bateria, diagnóstico, misto, simulado, avulsa), confiança, causa do erro, resultados, histórico, dashboard, estatísticas,
tema claro/escuro, backup.

**Fase 2 (estudo reverso) — implementada**
- Diagnóstico da sessão (demonstrado / lacuna / frágil / chute) e tela **Lacunas** (erros com “certeza” em destaque); nome do
  conhecimento específico de cada lacuna via IA (1 chamada para várias).
- **Estudo direcionado**: lacuna → explicação → exemplo → questão de verificação → resultado → próxima etapa, com explicação
  alternativa mais simples, pré-requisitos sugeridos e tutor na própria tela. Tudo gerado por IA é rotulado “✦ Gerado por IA”.
- **Verificação** com questão inédita do banco (mesma disciplina/assunto) ou questão isomórfica gerada por IA (banca “Gerada por IA”).
- **Revisões** com regras simples e visíveis na tela (hipóteses iniciais, ajustáveis em `app/services/reviews.py`).
- **Tutor IA** (conversa livre ou por questão, com histórico) e **conversor de PDF com IA**.

**Ainda NÃO implementado**: Fase 3 (revisão adaptativa baseada em dados, detecção formal de pré-requisitos, estatísticas avançadas) e
Fase 4 (exportações extras, restauração de backup pela interface).

## Estrutura

```
run.py                 inicia o servidor
app/db.py              única camada que fala com o banco (troca SQLite→PostgreSQL começa aqui)
app/migrations/*.sql   esquema versionado (aplicado automaticamente)
app/services/          regras de negócio (importação, questões, sessões, estatísticas, assuntos)
app/routes/            API JSON (/api/...)
static/                frontend (JS modular sem build): views/, components/, lib.js
tests/test_api.py, test_phase2.py   28 testes (API, revisões, estudo, tutor, IA simulada, PDF)  →  python3 -m unittest discover -s tests
app/ai/                camada de IA (provedor Gemini + provedor falso para testes; troca de provedor = novo arquivo aqui)
tests/e2e.py           teste no navegador, Fases 1 e 2 (opcional, requer playwright)
```

## Migrar para PostgreSQL no futuro

Todo SQL passa por `app/db.py` e `app/services/`. A migração exige: trocar o driver/conexão em `db.py`,
adaptar os placeholders (`?` → `%s`) e ajustar `AUTOINCREMENT` nas migrações. As regras de negócio e o frontend não mudam.
