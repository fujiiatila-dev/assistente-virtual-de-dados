# Assistente Virtual de Dados — Desafio 1

Repositório dedicado à implementação do Desafio Técnico 1: um assistente que
responde perguntas de negócio em linguagem natural consultando um SQLite em modo
somente leitura, com descoberta dinâmica de schema, autocorreção de SQL e visualização
no Streamlit.

## Estado do projeto

Este commit contém o bootstrap seguro e o plano de implementação. O código de produto
será desenvolvido seguindo `openspec/changes/implement-data-assistant/tasks.md`.
Consulte [`PROMPT_IMPLEMENTADOR.md`](PROMPT_IMPLEMENTADOR.md) para a instrução
autocontida do modelo executor e [`HANDOFF.md`](HANDOFF.md) para o contrato de entrega.

## Regras de desenvolvimento

- O root deste diretório é um repositório Git independente, com `main` como branch
  permanente.
- Cada task deve ser executada em uma branch `feat/tN-nome` ou `fix/tN-nome`, validada,
  commitada com Conventional Commits e mergeada em `main` antes da próxima task.
- Credenciais locais ficam em `.env`; somente `.env.example` é versionado.
- O anexo oficial não é versionado. Durante o desenvolvimento local, ele fica um nível
  acima deste diretório, em `../anexo_desafio_1.db`.
- O Desafio 2 é apenas material de referência em `docs/desafio-2-pipeline/` e não será
  implementado neste repositório.

## Documentação de planejamento

- `openspec/`: proposta, especificação, design e tasks.
- `docs/adr/`: decisões arquiteturais aceitas, incluindo frontend, temas e exportação.
- `HANDOFF.md`: critérios de aceite e regras operacionais.

## Próximo passo

Executar T0a e T0b, validar o dataset oficial em modo somente leitura e só então
começar o scaffolding de T1.
