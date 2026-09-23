#!/bin/sh
# Forced command for one dedicated SSH key; never evaluate SSH_ORIGINAL_COMMAND.
set -eu

deploy_tag=${SSH_ORIGINAL_COMMAND-}
if ! printf '%s' "$deploy_tag" | grep -Eq '^sha-[0-9a-f]{40}$'; then
    echo 'Tag de imagem inválida.' >&2
    exit 64
fi

exec sudo -n /usr/local/sbin/data-assistant-deploy "$deploy_tag"
