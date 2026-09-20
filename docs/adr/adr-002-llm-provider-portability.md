# ADR-002: Provedor LLM via OpenRouter com portabilidade

- **Status:** Aceito
- **Data:** 2026-09-20
- **Desafio:** Técnico 1 — Assistente Virtual de Dados

## Contexto

O agente depende de um LLM com bom desempenho em text-to-SQL e tool calling. A avaliação
não especifica provedor; o avaliador precisa conseguir executar o projeto com a própria
chave. Custo e latência importam: cada pergunta dispara múltiplas chamadas (geração,
correção, formatação).

Alternativas consideradas:

1. **OpenAI direto** — referência em tool calling, mas acopla o projeto a um fornecedor.
2. **Anthropic direto** — forte em raciocínio, mesmo acoplamento.
3. **Google (Gemini) via OpenRouter** — Gemini 2.5 Flash tem excelente custo/benefício
   para SQL estruturado; OpenRouter expõe uma API compatível com OpenAI que abstrai o
   fornecedor.
4. **Modelos locais (Ollama)** — custo zero por chamada, mas qualidade em text-to-SQL
   complexo e setup extra do avaliador pioram a experiência de execução.

## Decisão

- Acesso ao LLM **exclusivamente via OpenRouter** (endpoint compatível com a API OpenAI),
  usando `langchain-openai` apontado para `base_url` configurável.
- Modelo padrão: `google/gemini-2.5-flash`. Troca por variável de ambiente
  `OPENROUTER_MODEL`, sem alteração de código.
- Nenhum código importa SDK específico de provedor; apenas o client compatível com OpenAI.
- Chave em `OPENROUTER_API_KEY` (arquivo `.env` fora do versionamento; fornecer `.env.example`).

## Consequências

**Positivas**
- O avaliador roda com qualquer modelo disponível no OpenRouter (ou trocando `base_url`
  para qualquer endpoint compatível com OpenAI, inclusive locais).
- Custo por execução de demo na casa de centavos com Gemini Flash.
- Uma única integração a manter.

**Negativas / Riscos**
- Intermediário a mais no caminho (latência e disponibilidade do OpenRouter) — aceitável
  para escopo de avaliação.
- Diferenças sutis de tool calling entre modelos exigem teste com o modelo padrão;
  o README lista modelos validados.
