# Assistente Virtual de Dados — Desafio 1

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB)
![uv](https://img.shields.io/badge/deps-uv-5C4EE5)

Assistente em linguagem natural para perguntas de negócio sobre um SQLite. O produto
descobre o schema em runtime, gera e corrige SQL com LangGraph, executa somente leitura e
apresenta resultados auditáveis em Streamlit.

[English version](README.en.md)

## Avaliação online

O endereço público da demonstração é **https://avaliacao.nalk.com.br**. O acesso será
livre, sem login ou e-mail, assim que o provisionamento do servidor e do DNS terminar.
No momento, a publicação ainda depende dessa etapa operacional; use as instruções
locais abaixo enquanto o endereço não estiver ativo.

A base disponibilizada na demonstração é fictícia. O assistente usa
`openrouter/free` com uma chave compartilhada e uma cota diária de segurança. Se a
cota acabar, a interface pode solicitar uma chave OpenRouter própria (BYOK) somente
para a sessão atual, mediante confirmação; a chave é enviada ao backend para chamar
o provedor e não é persistida pelo aplicativo. Recomenda-se criar uma chave exclusiva
com limite de gasto e/ou expiração. Tabelas oferecem CSV e PNG; barras, linhas e
métricas oferecem PNG.

## O que está incluído

- Grafo explícito: interpretar → descobrir schema → gerar → validar → executar →
  corrigir/refinar → formatar.
- OpenRouter por API compatível com OpenAI; o padrão é o roteador gratuito
  `openrouter/free`, que seleciona um modelo gratuito disponível com suporte às
  saídas estruturadas usadas pelo agente.
- Schema dinâmico com tabelas, colunas extras, chaves estrangeiras e amostras de valores
  categóricos.
- SQLite em `mode=ro`, `query_only=ON`, limite máximo de 200 linhas, timeout, até seis
  queries e até três correções depois da tentativa inicial.
- Validação com `sqlglot`: somente `SELECT`/`WITH`; escrita, múltiplos statements,
  `PRAGMA`, `ATTACH`, `load_extension` e joins cartesianos são rejeitados.
- Chat Streamlit em pt-BR com etapas operacionais, SQL, amostras dos resultados,
  estados de erro e avisos sem chain-of-thought privado.
- Tabela, barras, linha e métrica; troca local sem nova consulta; CSV e PNG para tabelas,
  PNG para os demais visuais.

## Requisitos

- Python 3.11 ou superior
- [uv](https://docs.astral.sh/uv/)
- Chave do OpenRouter para perguntas reais
- O anexo `anexo_desafio_1.db`, mantido fora do repositório
- Chrome ou Chromium compatível para exportar PNG com Kaleido 1.x

O projeto espera o anexo em `../anexo_desafio_1.db` por padrão. Para usar outro
SQLite compatível localmente, configure `DB_PATH` antes de iniciar o processo. O
arquivo é sempre aberto em modo somente leitura e nunca é copiado pelo aplicativo.

## Configuração

```powershell
uv sync
Copy-Item .env.example .env
```

Preencha apenas a chave no `.env`:

```dotenv
OPENROUTER_API_KEY=sua-chave-local
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
DB_PATH=../anexo_desafio_1.db
OPENROUTER_FREE_DAILY_REQUEST_LIMIT=45
MAX_SQL_FIX_ATTEMPTS=3
MAX_QUERY_BUDGET=6
```

O `.env`, bancos, logs, caches, CSVs e PNGs são ignorados pelo Git. Em redes com uma
autoridade certificadora corporativa, execute `uv sync --system-certs`.

O roteador gratuito ainda exige uma chave OpenRouter e está sujeito aos limites do
provedor. O fluxo público usa somente `openrouter/free`, inclusive com BYOK; o
roteador pode selecionar modelos diferentes ao longo do tempo. A cota local conta
cada chamada real ao modelo, não cada pergunta, e o limite diário compartilhado é
configurável. Use somente dados não sensíveis, pois as políticas dos provedores
gratuitos podem variar.

## Validar o anexo

O validador lê o arquivo com `mode=ro`, confirma integridade, schema mínimo, chaves
estrangeiras, contagens e períodos. Colunas extras são aceitas. Divergências entre os
campos denormalizados de `clientes` e os fatos de `compras` aparecem como `WARNING`.

```powershell
python scripts/validate_dataset.py --db ..\anexo_desafio_1.db
```

O relatório esperado para o anexo fornecido contém 100 clientes, 946 compras, 273
atendimentos e 248 registros de campanha.

## Executar

Verifique primeiro a conexão com o provedor:

```powershell
uv run python scripts/smoke_llm.py
```

Sem chave, o script mostra uma mensagem operacional e termina com código 2. Com a chave
configurada, inicie a interface:

```powershell
uv run streamlit run app.py
```

Para trocar a fonte local, altere `DB_PATH` no `.env` e reinicie a aplicação. A
interface pública não aceita caminhos de banco por URL. Caminho ausente ou arquivo
inválido gera uma orientação sem criar ou sobrescrever nada.

## Interface

A barra lateral informa a fonte e o modelo e oferece as cinco perguntas de
demonstração. A interface segue automaticamente o tema claro/escuro do sistema; não
há seletor de tema. O robô é usado como favicon e marca no topo, e o indicador de
carregamento respeita a preferência por movimento reduzido.

Cada resposta contém:

- `status`: `success`, `empty`, `partial` ou `error`;
- texto executivo e `warnings`;
- dados e visualização validada com `available_types`;
- um painel expansível com etapas operacionais, queries, erros corrigidos e amostras;
- downloads compatíveis com o tipo selecionado.

Se o Kaleido não conseguir gerar a imagem, o resultado continua disponível e somente o
download PNG exibe uma mensagem operacional. O Kaleido 1.x não instala um navegador junto
com o pacote. Instale Chrome/Chromium no ambiente uma vez, ou execute
`uv run plotly_get_chrome` (alternativamente, `uv run kaleido_get_chrome`). Se o navegador
não for detectado automaticamente, configure `BROWSER_PATH` no `.env` com o caminho
completo do executável. O aplicativo não baixa navegadores durante uma pergunta.

Confira a exportação estática antes da avaliação:

```powershell
uv run python scripts/smoke_png.py
uv run pytest -m png
```

O smoke check confirma a assinatura de um PNG real sem gravar arquivo no projeto. Quando
o navegador estiver ausente, o teste marcado `png` é ignorado com motivo explícito;
falhas de inicialização com um navegador encontrado continuam sendo reportadas.

## Docker e publicação

`docker build -t data-assistant:test .` cria uma imagem não-root com Chromium e
executa o smoke PNG durante o build. O `compose.yaml` monta o anexo externo em modo
somente leitura e um diretório de runtime separado; não publica a porta 8501. O
perfil `public` liga o Cloudflare Tunnel à rede interna do Compose. Variáveis,
token do Tunnel e banco ficam fora da imagem e do Git.

O [runbook de publicação](DEPLOYMENT.md) descreve inventário DNS, provisionamento
Ubuntu/Debian, chave SSH de deploy dedicada, GitHub Actions/GHCR, verificações de
saúde e rollback. A publicação remota só é habilitada com `PRODUCTION_READY=true`
após o preflight do servidor. Não execute o perfil público sem completar o runbook.

## Arquitetura

```mermaid
flowchart LR
    UI[Streamlit] --> API[DataAssistant.ask]
    API --> I[Interpretar]
    I --> S[Descobrir schema]
    S --> G[Gerar SQL]
    G --> V{Validar}
    V -->|válido| E[Executar em mode=ro]
    V -->|inválido| C[Corrigir até 3x]
    C --> V
    E --> A{Dados suficientes?}
    A -->|não, orçamento disponível| R[Refinar]
    R --> V
    A -->|sim ou limite atingido| F[Formatar contrato]
    F --> UI
```

| Módulo | Responsabilidade |
|---|---|
| `schema.py` | Introspecção e DSL do schema, com cache limitado à sessão |
| `validator.py` | Guardrails AST independentes do LLM |
| `executor.py` | Conexão SQLite somente leitura, limite e timeout |
| `llm.py` / `prompts.py` | Única fronteira com o OpenRouter |
| `graph.py` | Estado, nós e arestas condicionais do LangGraph |
| `contract.py` | Contrato Pydantic entre motor e interface |
| `visualization.py` | Compatibilidade, fallback, Plotly e exportação |
| `assistant.py` | API pública e tratamento operacional de falhas |

As decisões estão registradas nos ADRs 001–010 do material local de arquitetura.

## Perguntas e resultados do anexo

| Pergunta | Resultado esperado no anexo | Visual |
|---|---|---|
| 5 estados com mais clientes que compraram via App em maio | SP 6; MG 3; SC 3; AL 2; ES 2 | Barras |
| Clientes associados a campanhas WhatsApp em 2024 | 33 clientes distintos; 17 interações (`interagiu=1`); 35 envios | Métrica |
| Média de compras por cliente por categoria | Roupas 2,21; Viagens 2,16; Livros 1,98; Serviços 1,96; Eletrônicos 1,92; Alimentos 1,88 | Barras |
| Reclamações não resolvidas por canal | Telefone 19; Chat 18; E-mail 14 | Barras |
| Tendência de reclamações por canal | Série mensal de 2024-07 a 2025-07 | Linha |

As métricas de compras usam a tabela transacional `compras`. Os campos
`clientes.valor_total_gasto` e `clientes.data_ultima_compra` do anexo não reconciliam com
os fatos e permanecem apenas informativos.

## Testes e qualidade

```powershell
uv run pytest
uv run ruff check .
uv run mypy src/
```

Os testes unitários exercitam schema, guardrails, execução e renderização sem simular uma
query gerada. As cinco perguntas de aceite passam exclusivamente pelo agente real: o SQL é
produzido pelo OpenRouter a partir do schema descoberto em runtime. Esses testes usam o
marcador `llm` e são ignorados quando a chave não existe:

```powershell
uv run pytest -m llm
```

## Limites conhecidos e próximos passos

- O Streamlit aceita sessões independentes, mas esta implantação tem um processo de
  aplicação; escalar horizontalmente exige coordenação dos limites de abuso.
- A descoberta envia o schema completo ao modelo; seleção semântica de tabelas ou RAG
  passa a ser útil em bancos grandes.
- O cardápio visual cobre quatro tipos intencionalmente simples; filtros e gráficos
  compostos ficam para uma evolução.
- Autenticação, memória entre sessões, persistência de conversas e exportação PDF estão
  fora deste MVP.
- O Desafio Técnico 2 possui somente arquitetura de referência e não é entrada deste
  aplicativo.
