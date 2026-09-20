# Diagramas de Sequência — Pipeline de Documentos (Desafio 2)

> Material de apoio para a entrevista técnica. Dois níveis: o fluxo feliz simplificado
> (explicação de abertura) e o fluxo completo com todos os desvios (aprofundamento).

---

## 1. Fluxo feliz simplificado (visão de abertura)

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operador/ERP
    participant CLI as pipeline run (CLI/Worker)
    participant SS as State Store
    participant IN as Ingestão (IR)
    participant CL as Classificação (cascata)
    participant EX as Extração (escada)
    participant VA as Validação
    participant PE as Persistência

    Op->>CLI: aponta pasta/fila de PDFs
    CLI->>SS: registra job (id = sha256 do arquivo)
    CLI->>IN: processa PDF
    IN-->>SS: IR pronta (texto + layout)
    CLI->>CL: classifica a partir da IR
    CL-->>SS: tipo + confiança
    CLI->>EX: extrai campos (schema do tipo)
    EX-->>SS: JSON bruto + modelo usado
    CLI->>VA: valida contra JSON Schema + regras
    VA-->>SS: válido, confiança alta
    CLI->>PE: grava JSONL + CSV + manifest
    PE-->>Op: saída disponível para o ERP
```

**Narração de 30 segundos:** cada documento é um job idempotente indexado pelo hash do
arquivo. Ele atravessa cinco estágios — ingestão com representação intermediária,
classificação em cascata, extração com escada de modelos, validação contra schema e
persistência versionada. O state store registra cada transição, então qualquer falha é
isolada, retomável e auditável.

---

## 2. Fluxo completo com desvios (aprofundamento)

```mermaid
sequenceDiagram
    autonumber
    participant CLI as Orquestrador
    participant SS as State Store
    participant IN as Ingestão
    participant OCR as OCR (sob demanda)
    participant CL as Classificador
    participant LLM1 as LLM barato (Flash)
    participant LLM2 as LLM forte (Pro)
    participant VA as Validador
    participant HU as Revisão humana
    participant PE as Persistência

    CLI->>SS: cria job (id=sha256, status=ingested)
    CLI->>IN: abre PDF (mode somente leitura)
    IN->>IN: mede densidade de texto por página

    alt camada de texto presente
        IN->>SS: IR = texto parseado (custo ~0)
    else scan/imagem
        IN->>OCR: páginas de baixa densidade
        OCR-->>SS: IR = texto OCR + bboxes
    end

    CLI->>CL: regras determinísticas sobre a IR
    alt regras resolvem (~80%)
        CL-->>SS: tipo + confiança alta (custo 0)
    else ambíguo
        CL->>LLM1: trecho representativo da IR
        LLM1-->>SS: {type, confidence} (JSON fechado)
    end

    alt confiança < limiar OU tipo improvável
        CLI->>HU: enfileira para revisão
        HU-->>SS: tipo confirmado/corrigido (vira dado de treino)
    end

    CLI->>LLM1: extração 1ª tentativa (constrained decoding vs schema)
    LLM1-->>VA: JSON bruto
    VA->>VA: JSON Schema + semântica (soma itens ≈ total, CNPJ, datas) + ancoragem na IR

    alt validação OK
        VA-->>SS: extraído, confiança calculada
    else falhou (1ª tentativa)
        VA->>LLM2: retry com erro estruturado como feedback
        LLM2-->>VA: JSON corrigido
        alt validação OK
            VA-->>SS: extraído (via modelo forte)
        else falhou de novo
            VA->>HU: fila de revisão com erros anexados
            HU-->>SS: campos corrigidos
        end
    end

    CLI->>PE: grava out/<run_id>/ (JSONL + CSV + manifest)
    Note over PE,SS: envelope: pipeline_version, prompt_version,<br/>model_id, confidence, processed_at

    alt erro transiente (rate limit/rede)
        CLI->>CLI: backoff e retentativa do estágio
    else erro permanente (PDF corrompido)
        CLI->>SS: status=failed + motivo estruturado (lote segue)
    else crash do worker
        Note over CLI,SS: reinício retoma do último estágio concluído<br/>(nenhum estágio refeito)
    end
```

**Pontos para destacar ao explicar:**

1. **Todo LLM tem saída validada por máquina** — o modelo nunca é a última palavra:
   schema, regras semânticas e ancoragem na IR antecedem qualquer aceite (trecho da
   extração até a persistência).
2. **A cascata só paga o modelo caro quando vale** — regras resolvem ~80% da
   classificação (primeiro `alt` do classificador) e o modelo forte só entra no retry
   da extração (segundo `alt` do validador).
3. **Falha tem três destinos, nunca um quarto** — retentativa (transiente), fila de
   revisão (incerto) ou `failed` estruturado (permanente); o lote nunca para.
4. **O state store é a espinha dorsal** — cada seta `-->>SS` é um checkpoint: é ele que
   transforma "script que processa arquivos" em "pipeline reprodutível e retomável".

---

## 3. Versão alternativa: fusão de estágios (pergunta provável)

Se perguntarem "e se você quiser reduzir ainda mais o custo?":

```mermaid
sequenceDiagram
    autonumber
    participant IN as Ingestão (IR)
    participant CLX as Classificação+Extração (prompt único)
    participant VA as Validador
    participant SS as State Store

    IN->>CLX: IR (doc com camada de texto, alta confiança esperada)
    CLX->>VA: {type, fields...} numa só chamada de LLM
    VA->>VA: valida tipo e campos juntos
    alt tudo válido
        VA-->>SS: classificado e extraído (1 chamada em vez de 2)
    else inválido
        VA-->>SS: degrada para pipeline em 2 estágios (cascata normal)
    end
```

A tese: o pipeline em estágios separados é o caminho **robusto padrão**; a fusão é uma
otimização **opcional e degradável** para o subconjunto fácil — nunca o contrário.
