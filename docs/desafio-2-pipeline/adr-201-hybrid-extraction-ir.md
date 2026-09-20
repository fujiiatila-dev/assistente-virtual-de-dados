# ADR-201: Extração de conteúdo híbrida com IR intermediária

- **Status:** Proposto (arquitetura de referência — desafio não implementado)
- **Data:** 2026-09-20
- **Desafio:** Técnico 2 — Pipeline de Documentos

## Contexto

A entrada são 50 PDFs "digitalizados", mas em produção o backlog virá de digitalizações
reais: alguns PDFs têm camada de texto embutida (PDFs nativos ou OCR prévio), outros são
imagem pura. Ler tudo com OCR custa caro e introduz erro; ler só a camada de texto falha
nos escaneados. Além disso, classificação e extração têm necessidades diferentes: a
classificação precisa de pouco texto (primeiras seções, padrões); a extração precisa de
texto integral + pistas de layout.

Alternativas consideradas:

1. **OCR universal em tudo** — uniforme, mas multiplica custo e latência em ~100% dos
   documentos para beneficiar só a fração escaneada, e OCR desnecessário degrada texto
   que já era limpo.
2. **LLM multimodal lendo o PDF direto** — tenta resolver tudo numa chamada; caro para
   classificar, impede cache de conteúdo e mistura extração de conteúdo com raciocínio.
3. **Extração híbrida com IR intermediária** — camada de texto primeiro; OCR apenas no
   que precisa; estrutura comum para os estágios seguintes.

## Decisão

Dois componentes:

1. **Detector de camada de texto:** para cada página, extrair com biblioteca de parse
   (ex.: PyMuPDF) e medir densidade de texto. Abaixo do limiar → página vai para OCR
   (ex.: Tesseract ou serviço de OCR), que roda **em paralelo** como estágio próprio.
2. **Representação Intermediária (IR):** estrutura serializável (JSON) por documento:
   páginas, texto por página, blocos com bbox, metadados (num. de páginas, tabelas
   detectáveis). Classificação e extração consomem a IR, nunca o PDF.

A IR é gravada no state store — reprocessar classificação/extração não relê o PDF.

## Consequências

**Positivas**
- Custo de conteúdo concentrado onde é necessário; docs com camada de texto custam ~zero.
- IR desacopla: trocar de OCR ou parser não toca nos estágios de IA; cache e retomada por
  estágio ficam naturais.
- Testes: fixtures de IR substituem PDFs nos testes unitários dos estágios seguintes.

**Negativas / Riscos**
- Duas bibliotecas/serviços de extração para manter.
- Limiar de densidade é heurístico — calibrar com o golden set; em caso de dúvida, OCR
  (falso negativo custa pouco; falso positivo, nada).
- IR adiciona volume no storage — trivial frente ao custo de re-OCR.
