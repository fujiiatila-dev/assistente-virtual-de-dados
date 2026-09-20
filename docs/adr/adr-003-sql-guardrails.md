# ADR-003: Guardrails e execução segura de SQL

- **Status:** Aceito
- **Data:** 2026-09-20
- **Desafio:** Técnico 1 — Assistente Virtual de Dados

## Contexto

O LLM gera SQL a partir de linguagem natural. Mesmo com um modelo competente, há riscos:
statements destrutivos (DROP/DELETE/UPDATE), consultas acidentalmente caras (cross join
gigante, SELECT * em tabelas grandes), múltiplos statements injetados via `;` e vazamento
de dados além do necessário para responder. Como o banco será exposto a um agente, a
segurança não pode depender só do prompt.

Alternativas consideradas:

1. **Confiar no prompt apenas** — frágil; prompt injection via dados do próprio banco
   (ex.: nome de cliente malicioso) pode induzir SQL malicioso.
2. **Usuário de banco somente-leitura** — SQLite não tem permissões por usuário; no
   máximo modo de abertura `mode=ro` (bloqueia escrita, não bloqueia custo).
3. **Camada de validação determinística antes da execução** — parser de SQL +
   regras + limites, independentes do LLM.

## Decisão

Implementar **três camadas de defesa**:

1. **Conexão somente-leitura:** abertura do SQLite com URI `file:...?mode=ro` — o SQLite
   recusa qualquer operação de escrita no nível do motor, independentemente do SQL gerado.
2. **Validador determinístico (pré-execução):** parser (sqlglot) que rejeita:
   - statements que não sejam `SELECT`/`WITH` (whitelist);
   - múltiplos statements (split por `;`);
   - funções e pragmas não permitidas (blocklist: `load_extension`, `PRAGMA`, `ATTACH`);
   - cross joins sem conditions explícitas detectáveis estaticamente quando possível.
3. **Borda de custo:** `LIMIT` obrigatório quando ausente (injeção de `LIMIT 200` default),
   e enforcement de `max_query_rows`/`query_timeout` no executor.

## Consequências

**Positivas**
- Bloqueio de escrita garantido pelo motor, não pelo prompt.
- Custo por pergunta delimitado; sem risco de tabela cartesiamente gigante na demo.
- Regras auditáveis e testáveis sem chamar LLM (testes unitários puros).

**Negativas / Riscos**
- Falsos positivos do validador (SQL válido demais para as regras) — mitigado por
  whitelist estreita: o validador só precisa aceitar SELECT analítico.
- `mode=ro` + validador não evita 100% dos cenários de custo (subqueries correlacionadas);
  timeout como rede de segurança final.
