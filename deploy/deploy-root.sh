#!/usr/bin/env bash
# Install root-owned at /usr/local/sbin/data-assistant-deploy after server preflight.
set -euo pipefail
umask 077

deploy_tag=${1-}
if [[ $# -ne 1 || ! "$deploy_tag" =~ ^sha-[0-9a-f]{40}$ ]]; then
    echo 'Tag de imagem inválida.' >&2
    exit 64
fi
if [[ $(id -u) -ne 0 ]]; then
    echo 'O deploy requer o wrapper sudo restrito.' >&2
    exit 77
fi

deploy_dir=/home/atila/assistente-virtual-dados
state_dir=/var/lib/data-assistant
state_file="$state_dir/deployed-image"
image_prefix=ghcr.io/fujiiatila-dev/assistente-virtual-de-dados

if [[ ! -f "$deploy_dir/compose.yaml" || ! -f "$deploy_dir/.env" ||
      ! -s "$deploy_dir/data/anexo_desafio_1.db" ||
      ! -s "$deploy_dir/runtime/tunnel.env" ]]; then
    echo 'Compose, banco ou configuração de runtime ausente; provisionamento incompleto.' >&2
    exit 78
fi
mkdir -p "$state_dir"
cd "$deploy_dir"

previous_tag=
if [[ -f "$state_file" ]]; then
    IFS= read -r previous_tag < "$state_file" || true
    if [[ ! "$previous_tag" =~ ^sha-[0-9a-f]{40}$ ]]; then
        previous_tag=
    fi
fi

wait_healthy() {
    local container_id health_state attempt
    container_id="$(docker compose ps -q app)"
    [[ -n "$container_id" ]] || return 1
    for ((attempt = 0; attempt < 30; attempt++)); do
        health_state="$(docker inspect --format '{{.State.Health.Status}}' "$container_id" 2>/dev/null || true)"
        [[ "$health_state" == healthy ]] && return 0
        [[ "$health_state" == unhealthy ]] && return 1
        sleep 2
    done
    return 1
}

logs_clean() {
    local capture
    capture="$(mktemp)"
    if ! docker compose --profile public logs --no-color --tail=200 app cloudflared > "$capture" 2>&1; then
        rm -f "$capture"
        echo 'Não foi possível inspecionar os logs do deploy.' >&2
        return 1
    fi
    if grep -Eiq 'sk-or-|TUNNEL_TOKEN=|OPENROUTER_API_KEY=|Traceback \(most recent call last\)' "$capture"; then
        rm -f "$capture"
        echo 'Logs contêm marcador sensível ou traceback; deploy rejeitado.' >&2
        return 1
    fi
    rm -f "$capture"
}

export APP_IMAGE="$image_prefix:$deploy_tag"
docker compose --profile public pull app cloudflared
if docker compose --profile public up -d --no-build app cloudflared \
    && wait_healthy \
    && docker compose exec -T app python scripts/smoke_container.py --db /data/source.sqlite3 \
    && docker compose exec -T app python scripts/smoke_png.py \
    && logs_clean; then
    printf '%s\n' "$deploy_tag" > "$state_file.new"
    mv -f "$state_file.new" "$state_file"
    echo "Deploy saudável: $deploy_tag"
    exit 0
fi

echo 'Nova versão sem saúde; iniciando rollback da aplicação.' >&2
if [[ -n "$previous_tag" && "$previous_tag" != "$deploy_tag" ]]; then
    export APP_IMAGE="$image_prefix:$previous_tag"
    docker compose --profile public pull app
    docker compose --profile public up -d --no-build app cloudflared
    if wait_healthy; then
        echo "Rollback saudável: $previous_tag" >&2
    else
        echo 'Rollback falhou; intervenção manual necessária.' >&2
    fi
else
    echo 'Nenhuma tag anterior válida registrada; intervenção manual necessária.' >&2
fi
exit 1
