# Specs Delta: implement-data-assistant

## ADDED Requirements

### Requirement: Motor de perguntas em linguagem natural

O sistema SHALL aceitar uma pergunta em linguagem natural e retornar uma resposta
fundamentada em dados reais do banco SQLite, sem queries hardcoded contra o schema.

#### Scenario: Pergunta simples com uma consulta

- **WHEN** o usuário pergunta "Quantos clientes interagiram com campanhas de WhatsApp em 2024?"
- **THEN** o sistema executa o grafo, consulta o banco e devolve resposta numérica correta
- **AND** a resposta cita os dados usados (query executada)

#### Scenario: Pergunta complexa com múltiplas consultas

- **WHEN** a pergunta exige passos intermediários (ex.: "Quais categorias de produto tiveram o maior número de compras em média por cliente?")
- **THEN** o sistema executa mais de uma consulta quando necessário (refinamento)
- **AND** a resposta final combina os resultados parciais

#### Scenario: Pergunta sem resposta nos dados

- **WHEN** a pergunta não pode ser respondida com o schema disponível
- **THEN** o sistema responde honestamente explicando o que tentou
- **AND** NUNCA inventa dados ou colunas

### Requirement: Descoberta dinâmica de schema

O sistema SHALL descobrir tabelas, colunas, tipos, relações e valores categóricos
diretamente do banco em tempo de execução, a cada execução do grafo.

#### Scenario: Schema refletido na geração de SQL

- **WHEN** o grafo inicia a execução
- **THEN** o nó de schema introspecta `sqlite_master`, `PRAGMA table_info` e `PRAGMA foreign_key_list`
- **AND** o prompt de geração recebe o schema descoberto (não um schema fixo no código)

#### Scenario: Amostragem de valores categóricos

- **WHEN** uma coluna TEXT de baixa cardinalidade é descoberta (ex.: `canal`, `categoria`, `tipo_contato`)
- **THEN** o sistema amostra valores distintos com `LIMIT` e os inclui no contexto do LLM
- **AND** o cache da introspecção dura no máximo a sessão

### Requirement: Fonte de dados configurável e compatível com o anexo

O sistema MUST aceitar o SQLite fornecido pelo desafio por configuração, abrir a fonte
em modo somente leitura e tolerar colunas adicionais sem quebrar a descoberta dinâmica.

#### Scenario: Execução com o anexo oficial

- **GIVEN** `DB_PATH` aponta para `anexo_desafio_1.db`
- **WHEN** o usuário envia uma pergunta
- **THEN** o motor abre o arquivo com URI `mode=ro`
- **AND** ativa `query_only=ON` e `foreign_keys=ON` na conexão
- **AND** descobre as quatro tabelas e suas relações em runtime
- **AND** não altera o arquivo durante a execução

#### Scenario: Colunas extras no banco

- **GIVEN** uma tabela possui colunas além das descritas no enunciado
- **WHEN** o nó de schema é executado
- **THEN** as colunas extras são refletidas no contexto do LLM
- **AND** a execução não depende de uma lista fixa de colunas

#### Scenario: Arquivo ausente ou inválido

- **GIVEN** o caminho configurado não existe ou não é um SQLite legível
- **WHEN** uma pergunta é iniciada
- **THEN** a interface exibe uma mensagem operacional clara
- **AND** não exibe stack trace cru nem tenta criar ou sobrescrever o arquivo

### Requirement: Guardrails de execução de SQL

O sistema SHALL executar somente leitura com validação determinística pré-execução,
independente do comportamento do LLM.

#### Scenario: Statement de escrita é rejeitado

- **WHEN** o LLM gera `DROP TABLE clientes` ou `DELETE FROM ...`
- **THEN** o validador rejeita antes da execução
- **AND** o sistema entra no loop de correção registrando o passo

#### Scenario: Múltiplos statements são rejeitados

- **WHEN** o SQL contém mais de um statement separado por `;`
- **THEN** o validador rejeita com mensagem clara

#### Scenario: LIMIT obrigatório

- **WHEN** o SQL gerado não tem `LIMIT`
- **THEN** o executor injeta um limite padrão (200 linhas)

#### Scenario: Conexão imutável

- **WHEN** o banco é aberto
- **THEN** a URI usa `mode=ro` (somente-leitura no nível do motor)

### Requirement: Auto-correção de SQL

O sistema SHALL detectar erros de execução, reenviar o erro ao LLM e tentar corrigir a
query, com orçamento limitado de tentativas.

#### Scenario: Coluna inexistente é corrigida

- **WHEN** o SQLite retorna `no such column: X` para a query gerada
- **THEN** o nó de correção recebe pergunta + schema + SQL anterior + mensagem de erro
- **AND** uma nova query é gerada e executada dentro do orçamento de 3 tentativas de correção

#### Scenario: Orçamento de correção esgotado

- **WHEN** as 3 tentativas de correção falham
- **THEN** o sistema responde com incapacidade honesta e a trilha do que tentou
- **AND** NUNCA retorna stack trace cru para o usuário

#### Scenario: Refinamento para dados insuficientes

- **WHEN** a query executa mas o resultado não basta para responder (ex.: vazio em pergunta quantitativa)
- **THEN** o grafo roteia para refinamento (nova consulta complementar), não para correção da mesma query
- **AND** o orçamento total de consultas por pergunta é 6

### Requirement: Interpretação temporal e semântica de contagem

O sistema MUST explicitar o período considerado quando a pergunta não informa o ano e
MUST distinguir quantidade de clientes, envios e interações.

#### Scenario: Mês sem ano explícito

- **GIVEN** a pergunta informa apenas um mês, como "em maio"
- **WHEN** existem registros desse mês em um ou mais anos
- **THEN** a consulta considera os anos disponíveis
- **AND** a resposta informa o período efetivamente consultado

#### Scenario: Clientes que interagiram

- **GIVEN** a pergunta solicita quantos clientes interagiram com uma campanha
- **WHEN** há múltiplos registros de campanha para o mesmo cliente
- **THEN** a resposta conta clientes distintos com `interagiu = 1`
- **AND** não confunde o resultado com o total de envios ou de interações

### Requirement: Visualização apropriada

O sistema SHALL escolher a forma de apresentação considerando o intent da pergunta e
SHOULD respeitar pedido explícito de formato do usuário, com fallback determinístico.

#### Scenario: Lista vira tabela

- **WHEN** a resposta é uma lista ("Liste os 5 estados...")
- **THEN** o bloco de visualização indica `table`

#### Scenario: Tendência vira linha

- **WHEN** a pergunta fala em tendência/evolução temporal ("tendência de reclamações por canal no último ano")
- **THEN** o bloco de visualização indica `line` com x = período e y = métricas por canal
- **AND** a consulta considera apenas registros com `tipo_contato = 'Reclamação'`

#### Scenario: Comparação vira barra

- **WHEN** a pergunta compara categorias ("número de reclamações não resolvidas por canal")
- **THEN** o bloco de visualização indica `bar`
- **AND** a consulta considera apenas registros com `tipo_contato = 'Reclamação'`

#### Scenario: Fallback por contrato inválido

- **WHEN** o LLM indica tipo de visual inexistente ou colunas que não estão no resultado
- **THEN** o frontend faz fallback para `table` sem quebrar

#### Scenario: Pedido explícito do usuário

- **WHEN** o usuário pede "mostre como gráfico de barras"
- **THEN** o formato pedido tem prioridade sobre a escolha automática (quando válido)

### Requirement: Tratamento semântico de campos denormalizados

O sistema MUST preservar o banco de entrada e SHOULD priorizar tabelas transacionais
quando um campo agregado do cadastro não puder ser reconciliado com seus fatos de origem.

#### Scenario: Agregado de cliente inconsistente

- **GIVEN** `clientes.valor_total_gasto` ou `clientes.data_ultima_compra` diverge das
  agregações correspondentes em `compras`
- **WHEN** a pergunta solicita uma métrica operacional de compras
- **THEN** o agente usa `compras` como fonte de verdade
- **AND** não reescreve nem corrige os dados do banco
- **AND** registra a divergência como aviso técnico quando ela for relevante para a
  resposta

### Requirement: Transparência do raciocínio

A interface SHALL exibir os passos do grafo executados, as queries SQL e os resultados
intermediários de cada resposta.

#### Scenario: Painel de raciocínio

- **WHEN** o assistente termina de responder
- **THEN** um expander mostra a linha do tempo de nós executados em ordem
- **AND** cada query executada aparece em bloco de código com seu resultado/tabla

### Requirement: Interface de chat

O sistema SHALL oferecer chat em Streamlit com histórico persistente durante a sessão.

#### Scenario: Histórico da sessão

- **WHEN** o usuário faz múltiplas perguntas na mesma sessão
- **THEN** o histórico completo (perguntas, respostas, visuais) permanece visível

#### Scenario: Perguntas de exemplo

- **WHEN** a app abre
- **THEN** as 5 perguntas do enunciado estão disponíveis para executar com um clique

### Requirement: Tema e linguagem visual do produto

A interface SHALL usar a linguagem visual Material 3 sobre os componentes do Streamlit e
MUST oferecer os modos `System`, `Light` e `Dark`, com `System` como padrão da sessão.

#### Scenario: Tema padrão do sistema

- **GIVEN** o usuário abre a aplicação pela primeira vez
- **WHEN** nenhuma preferência de tema foi definida na sessão
- **THEN** a interface usa o modo `System`
- **AND** não força um tema claro ou escuro contra a preferência do sistema

#### Scenario: Override de tema

- **GIVEN** a aplicação está aberta
- **WHEN** o usuário escolhe `Light` ou `Dark`
- **THEN** a interface e as visualizações usam o override selecionado
- **AND** a preferência permanece válida durante a sessão

### Requirement: Alternância e exportação de visualizações

A interface MUST permitir alternar entre visualizações compatíveis sem executar novamente
a pergunta e MUST exportar o resultado conforme o tipo selecionado.

#### Scenario: Troca de visualização

- **GIVEN** uma resposta possui mais de um tipo disponível
- **WHEN** o usuário altera o seletor de visualização
- **THEN** a mesma resposta é redesenhada localmente
- **AND** nenhuma nova query ou chamada LLM é executada

#### Scenario: Exportação de tabela

- **GIVEN** a visualização ativa é uma tabela
- **WHEN** o usuário solicita exportação
- **THEN** a interface oferece CSV e PNG
- **AND** os arquivos representam os dados retornados pelo motor

#### Scenario: Exportação de gráfico ou métrica

- **GIVEN** a visualização ativa é linha, barras ou métrica
- **WHEN** o usuário solicita exportação
- **THEN** a interface oferece PNG
- **AND** não oferece CSV como ação principal para esses tipos

#### Scenario: Renderer de imagem indisponível

- **GIVEN** o renderer de PNG não está instalado ou falha
- **WHEN** o usuário solicita uma imagem
- **THEN** a resposta continua visível
- **AND** a interface exibe uma mensagem operacional clara

### Requirement: Estados e evidências da interface

A interface SHALL representar estados de sucesso, vazio, parcial e erro, e MUST mostrar
evidências técnicas sem expor chain-of-thought privado.

#### Scenario: Resposta com evidências

- **GIVEN** o motor conclui uma pergunta
- **WHEN** a resposta é exibida
- **THEN** um painel expansível mostra etapas, queries, erros corrigidos e amostra dos
  resultados
- **AND** prompts internos, credenciais e raciocínio privado não são exibidos

#### Scenario: Falha operacional

- **GIVEN** o banco está ausente, a chave LLM não existe ou o orçamento foi esgotado
- **WHEN** a execução falha
- **THEN** a interface mostra status `error` ou `partial` com uma orientação acionável
- **AND** nunca mostra stack trace cru
