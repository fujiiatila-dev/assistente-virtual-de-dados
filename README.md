# Assistente Virtual de Dados — Desafio 1

Repositório dedicado à implementação do Desafio Técnico 1: um assistente que
responde perguntas de negócio em linguagem natural consultando um SQLite em modo
somente leitura, com descoberta dinâmica de schema, autocorreção de SQL e visualização
no Streamlit.

## Estado do projeto

Este commit contém o bootstrap seguro e o plano de implementação. O código de produto
será desenvolvido a partir do desafio e seus critérios de aceite. O material interno de
planejamento e execução é mantido fora do repositório oficial.

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

## Próximo passo

Executar T0a e T0b, validar o dataset oficial em modo somente leitura e só então
começar o scaffolding de T1.

## Validar o anexo local

O banco oficial permanece fora do repositório. Valide sua cópia sem alterá-la:

```powershell
python scripts/validate_dataset.py --db ..\anexo_desafio_1.db
```
