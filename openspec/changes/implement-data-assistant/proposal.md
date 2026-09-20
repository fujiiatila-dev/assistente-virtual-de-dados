# Proposal: implement-data-assistant

## Why

A diretoria precisa de respostas rápidas de negócio sem depender de um engenheiro para
escrever SQL a cada pergunta. Este change implementa o **Desafio Técnico 1**: um
Assistente Virtual de Dados que responde perguntas em linguagem natural consultando o
anexo SQLite fornecido, descobrindo o schema, gerando SQL, corrigindo os próprios erros
e apresentando o resultado com a visualização mais apropriada, com transparência das
etapas executadas.

O change entrega o produto mínimo avaliável: motor LangGraph + frontend Streamlit + os
5 exemplos de pergunta do enunciado funcionando end-to-end, com testes e README.

## Scope

**Incluído:**
- Pacote Python `data_assistant` com o grafo LangGraph (interpretar → schema → gerar →
  validar → executar → corrigir/refinar → formatar).
- Guardrails de SQL (ADR-003): conexão somente-leitura, validador sqlglot, LIMIT obrigatório.
- Descoberta dinâmica de schema com amostragem de valores categóricos (ADR-004).
- Loop de auto-correção com orçamento limitado (ADR-005).
- Contrato de saída JSON com bloco de visualização e fallback (ADR-006).
- App Streamlit com chat, painel de raciocínio e renderização (ADR-007).
- Frontend com linguagem Material 3, tema `System`/`Light`/`Dark`, alternância de
  visualizações e exportação CSV/PNG conforme o tipo de resultado.
- Testes pytest (nós do grafo com executor mockado, validador, contrato de saída e
  contrato do dataset fornecido).
- README em português + versão em inglês.
- Validação local do `anexo_desafio_1.db` sem versionar o binário.
- Implementação isolada no repositório Git `assistente-virtual-dados-desafio-1/`, com
  branches de task e merge controlado em `main`.
- Configuração por `.env` na raiz do repositório, com `.env.example` versionado e nenhum
  segredo no histórico.

**Não incluído (Non-goals):**
- API HTTP dedicada (motor é importável; extração de API fica como melhoria).
- Suporte a bancos não-SQLite.
- Memória entre sessões / autenticação de usuários.
- Desafio Técnico 2 (documentado separadamente para a entrevista).
- Criação de dados sintéticos para substituir o anexo oficial; fixtures mínimos de teste
  continuam permitidos dentro dos testes.

## Approach

Grafo LangGraph com estado tipado (`TypedDict`), nós como funções puras testáveis e
arestas condicionais dedicadas. LLM via OpenRouter (compatível com OpenAI) com modelo
trocável por env var. SQLite aberto em `mode=ro`, com o caminho recebido por configuração
e schema sempre descoberto em runtime. Contrato de saída versionado em Pydantic para o
frontend consumir com segurança. Detalhes em `design.md`; decisões em
`docs/adr/adr-001..007`.
