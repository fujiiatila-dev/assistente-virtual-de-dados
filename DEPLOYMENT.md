# Publicação de `avaliacao.nalk.com.br`

Este runbook prepara uma demonstração pública sem login. O origin só recebe conexões
internas do `cloudflared`; o app deve publicar a porta somente em `127.0.0.1:8501`.
O ambiente operacional informado é Ubuntu 24.04.4 LTS; não avance o deploy até validar
o acesso SSH de deploy e os gates remotos.

## Próximos passos

O repositório oficial é `fujiiatila-dev/assistente-virtual-de-dados`, com branch `main`.
A publicação só pode ser considerada ativa depois da validação HTTPS, WebSocket, container
e imagem GHCR. Verifique o status de Actions e a disponibilidade do endpoint antes de cada
cutover.

1. **Confirmar a máquina:** verificar versão/arquitetura do Ubuntu/Debian, capacidade,
   disco, permissões e conectividade de saída. Não imprimir nem copiar conteúdo de `.env`.
2. **Revisar DNS:** confirmar que a zona `nalk.com.br` está ativa na Cloudflare, revisar
   MX/TXT preservados e conferir o CNAME do Tunnel. Não criar registro `A`/`AAAA` para o
   IP do origin nem alterar registros de e-mail.
3. **Validar GitHub:** conferir o workflow de CI em `main`, permissões de Actions
   e publicação GHCR. Proteger `main`; preparar Environment `production` e secrets conforme
   a seção abaixo. `gh auth login` permite consultar runs com o CLI; não envie credenciais
   por chat.
4. **Preparar segredos e dados:** criar chave OpenRouter com limite próprio, token dedicado
   do Tunnel e chave SSH de deploy; validar o banco fictício. Guardar tudo diretamente nos
   destinos de runtime/secrets, sem passar por Git, logs ou chat.
5. **Provisionar o servidor:** instalar Docker suportado pela distribuição, criar os
   diretórios root-owned, arquivos `.env`/`runtime/tunnel.env` com modo 0600, banco externo
   somente leitura, scripts root-owned, usuário SSH restrito e regra sudo mínima. Bloquear
   entrada em 8501 e testar saída para GHCR, OpenRouter e Cloudflare Tunnel.
6. **Ativar publicação:** tornar o pacote GHCR legível pelo host; configurar Environment e
   secrets; criar/confirmar o Tunnel e rota para `http://127.0.0.1:8501`; aplicar WAF/rate limit sem Access;
   só então definir `PRODUCTION_READY=true` e executar deploy aprovado.
7. **Aceitar ou reverter:** validar HTTPS/WebSocket, cinco perguntas, quota/BYOK, exports,
   tema, WAF, logs e ausência de porta pública; guardar evidências sem dados sensíveis. Se
   algum gate falhar, manter `PRODUCTION_READY` desativada e corrigir antes da divulgação.

Não avance para os passos 5–7 antes de concluir os pré-requisitos dos passos 1–4.

## Estado e pré-requisitos

- [x] Ubuntu 24.04.4 LTS, Docker 29.6.1 e Compose 5.3.1 informados; validar
  arquitetura, disco, diretórios e conectividade durante o preflight remoto.
- [x] Repositório `fujiiatila-dev/assistente-virtual-de-dados` criado e `main` enviado.
- [ ] `main` ainda não tem regra de proteção configurada.
- [x] Actions e GHCR habilitados; CI e build da imagem no último release de `main`
  concluíram com sucesso. O deploy foi ignorado com `PRODUCTION_READY` ausente.
- [x] A zona está delegada à Cloudflare; nameservers e MX/TXT foram conferidos. Antes do
  cutover, confirmar zona `Active`, hostname e CNAME do Tunnel sem alterar e-mail.
- [ ] Estratégia SSH dedicada informada; autenticação do agente ainda não foi validada.
  O deploy não pode prosseguir até `DEPLOY_USER`, chave e host key serem confirmados.
- [ ] `.env` do servidor já existe; verificar somente presença e modo, sem ler/imprimir
  seu conteúdo. Confirmar `runtime/tunnel.env` e sua permissão `0600` diretamente no host.
- [ ] Banco fictício disponível em `data/anexo_desafio_1.db` e verificado pelo
  `scripts/validate_dataset.py` sem alterar o arquivo.

O `compose.yaml` usa dois arquivos de ambiente **não versionados**: `.env` para o app e
`runtime/tunnel.env` contendo somente `TUNNEL_TOKEN=...` para o conector. Essa separação
evita entregar a chave OpenRouter ao Tunnel ou o token do Tunnel ao app. Os dois arquivos
devem ter permissão 0600. `runtime/` e `.env*` estão ignorados pelo Git. Para validar a
configuração sem renderizar valores, use `docker compose config --no-env-resolution
--no-interpolate --quiet`; nunca publique a saída de `docker compose config` comum.

## DNS e Cloudflare

1. Exporte os registros do provedor atual e compare `NS`, `MX`, `TXT` (SPF, DKIM,
   DMARC), `A`, `AAAA`, `CNAME` e eventuais serviços existentes. Faça a revisão antes de
   alterar nameservers. Registre TTLs e plano de reversão fora do Git.
2. Em uma zona Cloudflare completa, importe e confira todos os registros antes de
   substituir os nameservers no registrador. A modalidade [CNAME parcial][partial]
   mantém o DNS autoritativo atual, mas exige plano Business ou Enterprise; não a assuma
   disponível. Não crie um `A` para o IP do origin.
3. Crie/valide um Tunnel gerenciado remotamente e a rota pública HTTPS
   `avaliacao.nalk.com.br` → `http://127.0.0.1:8501`. O `cloudflared` usa
   `network_mode: host` e lê `TUNNEL_TOKEN` do arquivo de runtime. Não associe
   Cloudflare Access ao hostname de avaliação.
   Confirme conexão saudável e [roteamento público do Tunnel][tunnel].
4. Habilite [rate limiting de borda][rate] para o hostname. Comece com a abertura do
   WebSocket `/_stcore/stream` em, no máximo, 20 handshakes/minuto por IP, mitigação de
   60 segundos, e ajuste após observar uma sessão normal de Streamlit. Se o plano
   permitir outra regra, proteja também bursts de HTTP do hostname (por exemplo,
   120 requisições/minuto/IP), sem bloquear assets ou reconexões normais. Não use
   desafio de e-mail/login. Na aplicação permanecem 5 perguntas/minuto/sessão,
   2 perguntas concorrentes e 2.000 caracteres por pergunta por padrão, inclusive BYOK.
5. Faça um teste controlado abaixo do limite, depois uma pequena sequência acima do
   limite em ambiente de avaliação; registre os limiares reais, ação e resultado no
   `HANDOFF.md` local. Refaça o teste após mudanças de WAF ou Tunnel.

## Servidor (Ubuntu/Debian; adaptar após versão e arquitetura confirmadas)

Use as instruções [oficiais do Docker para a distribuição][docker-install]. Preserve
`/home/atila/assistente-virtual-dados/`, `.env`, `data/` e `runtime/` já existentes. A
conta de deploy não entra no grupo `docker` nem recebe sudo geral. O diretório contém
`compose.yaml`, `.env` 0600, `data/anexo_desafio_1.db` fora do Git, `runtime/` gravável
pelo UID 10001 e `runtime/tunnel.env` 0600 somente para o Docker Compose. Configure no
`.env` do servidor:

```dotenv
OPENROUTER_API_KEY=<definir localmente>
HOST_DB_PATH=/home/atila/assistente-virtual-dados/data/anexo_desafio_1.db
RUNTIME_DIR=/home/atila/assistente-virtual-dados/runtime
OPENROUTER_FREE_DAILY_REQUEST_LIMIT=45
MAX_QUESTION_CHARS=2000
MAX_CONCURRENT_QUESTIONS=2
APP_REQUESTS_PER_MINUTE=5
```

Não copie essas linhas preenchidas para tickets, logs ou Git. Preserve o arquivo SQLite
em `data/anexo_desafio_1.db` fora da imagem; torne-o legível pelo container, mas não gravável.
O mount de banco em `compose.yaml` é `read_only` e não cria arquivo no host se estiver
ausente. Confirme a fonte com `docker compose exec -T app python
scripts/validate_dataset.py --db /data/source.sqlite3`.

No firewall, permita somente o SSH administrativo conforme a política local. Bloqueie
8501/TCP de entrada. Permita saída necessária para Docker/GHCR, OpenRouter e
[conexões do Cloudflare Tunnel][tunnel-firewall]. Não exponha o socket Docker. Verifique
as portas com a ferramenta nativa do SO e `docker compose ps`; a coluna `PORTS` deve
mostrar somente `127.0.0.1:8501->8501/tcp`, sem `0.0.0.0:8501` ou `:::8501`.

Instale `deploy/deploy-root.sh` em `/usr/local/sbin/data-assistant-deploy`, dono root,
modo 0755, e `deploy/deploy-wrapper.sh` em `/usr/local/bin/data-assistant-deploy-wrapper`
com os mesmos dono/modo. Crie uma conta SSH dedicada (por exemplo,
`deploy-assistant`) sem acesso ao grupo Docker. No `authorized_keys` desta conta, use
somente a chave pública dedicada com o prefixo:

```text
restrict,command="/usr/local/bin/data-assistant-deploy-wrapper" ssh-ed25519 <chave pública dedicada>
```

O `sudoers` deve autorizar essa conta **apenas** a executar
`/usr/local/sbin/data-assistant-deploy *` como root, sem senha; valide com `visudo -c`.
O wrapper valida uma tag `sha-` de 40 caracteres hexadecimais e nunca avalia o comando
SSH recebido. O script root valida a tag novamente, usa somente o repositório GHCR
fixo, espera o health check e volta à última tag saudável se necessário. O diretório
`/home/atila/assistente-virtual-dados/` e os scripts de deploy não podem ser editáveis
pela conta SSH restrita; preserve as permissões dos arquivos de runtime existentes.

O pacote GHCR precisa ser legível pelo servidor: torná-lo público é o caminho mais
simples para esta demonstração; se permanecer privado, configure no servidor um token
GHCR somente leitura fora do Git. Não envie esse token para o workflow. O build do
GitHub usa apenas `GITHUB_TOKEN` com `packages: write`.

## GitHub Actions e release

1. Configure um Environment `production`, restrito a `main`, com aprovação humana
   quando o plano do repositório permitir. [As regras variam conforme a visibilidade
   e o plano][environments]. Mantenha a variável de repositório
   `PRODUCTION_READY` ausente até o preflight do servidor e DNS estar aprovado;
   somente então defina-a como `true`. Enquanto isso, o CI pode publicar no GHCR,
   mas o job de deploy é ignorado. Não configure secrets antes de revisar as regras.
2. Salve no Environment: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY` (privada
   dedicada) e `DEPLOY_KNOWN_HOSTS`. Verifique a fingerprint SSH por canal independente
   antes de salvar `DEPLOY_KNOWN_HOSTS`; não use `ssh-keyscan` cegamente no job.
3. O workflow `CI` roda em PR e `main`: `uv sync --locked`, Pytest sem LLM, Ruff,
   Mypy, dataset quando o anexo externo existir e Gitleaks no histórico. Testes
   com chamadas reais ao OpenRouter permanecem opt-in.
4. Após CI verde de um push em `main`, `Publish and deploy` constrói a imagem (inclui
   smoke PNG) e publica `ghcr.io/fujiiatila-dev/assistente-virtual-de-dados:sha-<commit>`.
   Com `PRODUCTION_READY=true`, aciona a conta SSH restrita após aprovação do
   Environment; o script do servidor exige health check, smoke do banco montado,
   exportação PNG e varredura de marcadores sensíveis nos logs antes de registrar
   a nova tag como saudável.
5. Para rollback, execute manualmente `Publish and deploy` em `main` com a tag
   `sha-<commit anterior>` já publicada. Não remova o banco nem o ledger de quota.
   O script também tenta rollback automático se a nova versão não atingir `healthy`.

## Aceite público e evidências

- [ ] `docker compose --profile public ps` mostra `app` saudável e `cloudflared` ativo.
- [ ] `docker compose exec -T app python scripts/smoke_container.py --db
      /data/source.sqlite3` e `scripts/smoke_png.py` passam.
- [ ] `https://avaliacao.nalk.com.br` abre em HTTPS sem login; WebSocket conecta sem
      repetição/reload anômalo. O origin não responde externamente em 8501.
- [ ] As cinco perguntas do README funcionam com a chave compartilhada e os resultados
      usam as tabelas transacionais. Tabela exporta CSV/PNG; barras, linha e métrica PNG.
- [ ] Quota compartilhada mostra aviso; BYOK aparece somente após clique, aceita uma
      chave da sessão, permite limpar e só repete a pergunta após confirmação explícita.
      Outra sessão não vê a chave nem a pergunta pendente.
- [ ] Tema segue claro/escuro do sistema, favicon e logo são o mesmo robô, loader tem
      seis cápsulas e redução de movimento, sidebar não mostra deploy nem cartão verde.
- [ ] WAF bloqueia somente a carga controlada acima do limite configurado; navegação
      normal, downloads e WebSocket abaixo do limite continuam funcionando.
- [ ] Logs do app/Tunnel e Actions não exibem chaves, token, prompts completos ou
      traceback cru. `git status` e `git ls-files` não incluem `.env`, banco, ledger,
      logs, PNG, CSV ou material local de planejamento.

Registre data, versão/tag, resultados e desvios no `HANDOFF.md` local. Evidências com
segredos ou dados de sessão não devem virar artefatos de CI nem arquivos versionados.

[partial]: https://developers.cloudflare.com/dns/zone-setups/partial-setup/setup/
[tunnel]: https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/
[rate]: https://developers.cloudflare.com/waf/rate-limiting-rules/create-zone-dashboard/
[tunnel-firewall]: https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/tunnel-with-firewall/
[docker-install]: https://docs.docker.com/engine/install/
[environments]: https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments
