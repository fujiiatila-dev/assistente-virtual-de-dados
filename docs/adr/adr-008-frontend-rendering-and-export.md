# ADR-008: Material 3, Plotly e exportação de resultados

- **Status:** Aceito
- **Data:** 2026-09-20
- **Desafio:** Técnico 1 — Assistente Virtual de Dados

## Contexto

O frontend precisa ser familiar para um CTO, oferecer tema claro/escuro, permitir a
troca da visualização sem nova consulta e exportar tabelas e gráficos como arquivos.
Os componentes nativos do Streamlit cobrem chat, layout e downloads, mas não oferecem
um contrato único para alternância e exportação de todos os visuais.

## Alternativas consideradas

1. **`st.line_chart`/`st.bar_chart` e captura da tela** — simples, mas frágil para
   exportação PNG e inconsistente entre tabela e gráficos.
2. **Altair/Vega-Lite** — bom para gráficos declarativos, mas exige uma camada adicional
   para exportar tabelas e manter o mesmo contrato de imagem.
3. **Plotly + Kaleido** — renderer único para linha, barras, métrica e tabela, com
   exportação PNG programática e interação local sem nova chamada ao motor.
4. **Biblioteca Material Web/React embutida** — visualmente próxima do Material 3, mas
   adiciona uma aplicação frontend paralela e aumenta o risco de integração com
   Streamlit no prazo do desafio.

## Decisão

- Usar **Material 3 como linguagem visual**, aplicada aos componentes nativos do
  Streamlit por meio de tokens e estilos mínimos; não criar uma aplicação React paralela.
- Usar **Plotly** como renderer único das visualizações e **Kaleido** para gerar PNG.
- Usar `st.download_button` para entregar CSV e PNG.
- O backend informa `available_types`; o usuário troca a visualização localmente, sem
  nova query ou chamada LLM.
- A tabela oferece CSV e PNG; linha, barras e métrica oferecem PNG.
- O tema da sessão possui `System` como padrão e overrides `Light`/`Dark`. Se o
  Streamlit não permitir detecção confiável do tema do sistema na versão fixada, a app
  deve respeitar a configuração nativa e comunicar claramente o override disponível,
  sem depender de seletores CSS internos instáveis.

## Consequências

**Positivas**

- Exportação reproduzível e testável, sem screenshot da viewport.
- Troca de visualização não consome orçamento do agente.
- Contrato explícito de estados, avisos e tipos disponíveis melhora a previsibilidade da UI.
- Material 3 mantém familiaridade sem introduzir um segundo stack frontend.

**Negativas / Riscos**

- Kaleido adiciona dependência e deve ser validado no ambiente de execução; se o backend
  de imagem falhar, a UI deve manter a resposta e desabilitar apenas a exportação.
- Customização visual profunda do Streamlit pode depender da versão; estilos devem ser
  pequenos, sem acoplamento a classes internas.
- Plotly aumenta o tamanho das dependências, mas reduz a complexidade do contrato de
  renderização e exportação.
