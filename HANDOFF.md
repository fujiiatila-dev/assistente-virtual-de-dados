# HANDOFF — Implementação do Desafio 1: Assistente Virtual de Dados

> **Este arquivo é um prompt de execução.** Cole-o (ou aponte o caminho dele) como
> instrução inicial para o modelo implementador. Ele é autocontido: todo o contexto
> necessário está no repositório.

---

Você é o modelo implementador deste projeto. Sua missão é **executar** a change OpenSpec
`implement-data-assistant` — o Desafio Técnico 1 do documento `ai_engineer_pl.pdf`:
um Assistente Virtual de Dados que responde perguntas de negócio em linguagem natural
consultando um banco SQLite, com descoberta dinâmica de schema, auto-correção de SQL e
visualização apropriada, num frontend Streamlit com transparência do raciocínio.

## Repositório e ciclo de desenvolvimento

- O root do projeto é `assistente-virtual-dados-desafio-1/`, dentro do workspace de
  planejamento. Trabalhe exclusivamente dentro desse diretório e trate-o como um
  repositório Git independente.
- A branch permanente é `main`. Nunca implemente diretamente nela.
- Para cada task, crie uma branch curta a partir de `main`, usando `feat/tN-nome` para
  funcionalidade ou `fix/tN-nome` para correção. Exemplo: `feat/t2-schema-discovery`.
- Execute a task, rode o comando de verificação indicado, faça commit convencional e
  somente então faça merge fast-forward ou merge normal da branch em `main`. Depois,
  remova a branch local já integrada. Se um merge exigir resolução manual, registre o
  motivo e valide novamente a suite antes de concluir.
- Nunca faça `git reset --hard`, `git checkout --` ou operações destrutivas para
  descartar trabalho existente. Preserve mudanças não relacionadas e pare para revisão
  humana se houver conflito de escopo.
- O arquivo `.env` na raiz é reservado para credenciais locais e configurações privadas.
  Ele é ignorado pelo Git. Versione somente `.env.example`, sem valores secretos.
- `*.db`, WAL/journal SQLite, logs, CSV/PNG exportados, caches, ambientes virtuais,
  relatórios de ferramentas e qualquer token/chave também devem ser ignorados. Antes de
  cada merge, confirme que não há segredo, banco ou artefato rastreado e que nenhum deles
  entrou no histórico.

## Fontes de verdade (leia nesta ordem)

1. `openspec/config.yaml` — contexto do projeto, stack e regras.
2. `openspec/changes/implement-data-assistant/proposal.md` — escopo e non-goals.
3. `openspec/changes/implement-data-assistant/specs/data-assistant/spec.md` — requisitos
   e cenários (o critério de aceite).
4. `openspec/changes/implement-data-assistant/design.md` — arquitetura, `AgentState`,
   contrato Pydantic e diagrama do ciclo de correção.
5. `openspec/changes/implement-data-assistant/tasks.md` — **seu plano de trabalho**.
6. `docs/adr/adr-001` a `adr-008` — as decisões que você DEVE seguir (não redecidir).
7. `PROMPT_IMPLEMENTADOR.md` — versão autocontida deste handoff, para referência
   operacional do modelo executor.

## Regras de execução

1. **Siga `tasks.md` em ordem (T0a/T0b → T15).** Cada task tem um comando de
   verificação — rode-o e só avance se passar. T0a e T0b são pré-requisitos do
   bootstrap e devem ser concluídas antes de T1.
2. **Fidelidade aos ADRs:** as decisões arquiteturais já foram tomadas. Se encontrar um
   motivo objetivo para desviar, PARE, registre a proposta de desvio num arquivo
   `docs/notes/deviations.md` (o quê, por quê, impacto) e siga a decisão do ADR até
   revisão humana.
3. **Proibições absolutas:**
   - NENHUMA query SQL hardcoded contra o schema do banco (descoberta dinâmica é requisito).
   - NENHUM segredo em código ou versionado (`.env` fora do git; só `.env.example`).
   - NENHUM `print` para logging — use `logging` estruturado.
   - NENHUMA dependência fora do `pyproject.toml`.
4. **Fronteira LLM:** o comportamento dependente de LLM fica isolado em `llm.py` e
   `prompts.py`. Nós do grafo e arestas condicionais são testáveis com mocks — os testes
   unitários NÃO chamam API externa (só os marcados `@pytest.mark.llm`, que skipam sem
   `OPENROUTER_API_KEY`).
5. **Commits:** conventional commits, um ou mais por task concluída, sempre após o
   comando de verificação passar.
6. **Não implemente o Desafio 2** e não toque em `docs/desafio-2-pipeline/` —
   é material de entrevista, não escopo de código.
7. **Banco de dados:** o anexo oficial `anexo_desafio_1.db` está disponível localmente
   um nível acima do root do projeto, em `../anexo_desafio_1.db`, para integração, mas
   NÃO deve ser versionado. O `DB_PATH` é configurável e o app deve aceitar também um
   SQLite compatível. A task T0b cria `scripts/validate_dataset.py` para
   validar o arquivo em modo somente leitura, incluindo tabelas, colunas mínimas, chaves
   estrangeiras, contagens e intervalo de datas. Testes unitários usam fixtures temporários;
   não é necessário criar uma base sintética permanente.
8. **Idioma:** README em português (`README.md`) + tradução em inglês (`README.en.md`);
   código, identificadores e commits em inglês.
9. **Escopo:** implemente somente o Desafio 1. Não altere nem transforme o material em
   `docs/desafio-2-pipeline/`; ele é referência de entrevista e não faz parte do app.

## Critérios de aceite (do spec)

- As 5 perguntas de exemplo do enunciado funcionam end-to-end no Streamlit.
- A integração local reconhece as colunas extras existentes no anexo sem schema fixo.
- O contrato de aceitação do anexo confirma: 33 clientes distintos que interagiram com
  WhatsApp em 2024; médias por categoria; 19/18/14 reclamações não resolvidas por canal
  usando `tipo_contato = 'Reclamação'`; e série mensal de reclamações de 2024-07 a
  2025-07.
- SQL de escrita/múltiplos statements é rejeitado pelo validador; conexão em `mode=ro`.
- Erro de SQL entra no loop de correção (máx. 3 tentativas; orçamento de 6 queries) e,
  esgotado, produz resposta honesta — nunca stack trace cru.
- Visualização segue o contrato (line/bar/table/metric) com fallback para table, permite
  trocar o tipo sem nova consulta e apresenta estados `status`, `warnings` e
  `available_types`.
- A interface segue Material 3 por meio dos componentes do Streamlit, é `pt-BR`, usa
  tema `System` como padrão e oferece `Light`/`Dark`; tabela pode ser exportada como
  CSV e PNG, e os demais visuais como PNG.
- Painel de raciocínio mostra nós executados, queries e resultados intermediários.
- `python scripts/validate_dataset.py --db ..\anexo_desafio_1.db`, `uv run pytest`,
  `uv run ruff check .` e `uv run mypy src/` passam sem erro.
- `openspec validate --changes` continua passando (não edite os artefatos da change,
  exceto marcando tasks com `- [x]` conforme conclui).
- O histórico Git permanece limpo: nenhum `.env`, banco, chave, token, CSV, PNG ou
  relatório local deve ser rastreado ou commitado.

## Definição de pronto

Todas as tasks de `tasks.md` marcadas com `- [x]`, critérios acima atendidos e um
parágrafo final em `HANDOFF.md` (seção "Resultado da execução") relatando: tasks
concluídas, desvios registrados (se houver), cobertura dos testes, commits/merges
realizados e como reproduzir a execução. O estado final deve estar em `main`, com as
branches de task já integradas e removidas.
