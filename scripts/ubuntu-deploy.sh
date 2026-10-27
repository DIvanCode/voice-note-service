#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_dir"

profile=cpu
case "${1:-}" in
  "") ;;
  --gpu) profile=gpu ;;
  -h|--help)
    printf 'Usage: %s [--gpu]\n' "$0"
    exit 0
    ;;
  *)
    printf 'Unknown option: %s\n' "$1" >&2
    exit 2
    ;;
esac

for command_name in docker curl; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'Install %s before running this script.\n' "$command_name" >&2
    exit 1
  fi
done
if ! docker compose version >/dev/null 2>&1; then
  printf 'Docker Compose plugin is required.\n' >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  printf 'Docker is not running or this user cannot access it.\n' >&2
  exit 1
fi

umask 077
if [[ ! -f .env ]]; then
  cp .env.example .env
  printf 'Created .env from .env.example.\n'
fi
chmod 600 .env

env_value() {
  local value
  value=$(sed -n "s/^${1}=//p" .env | tail -n 1 | tr -d '\r')
  value=${value#\"}
  value=${value%\"}
  value=${value#\'}
  value=${value%\'}
  printf '%s' "$value"
}

token=$(env_value TELEGRAM_BOT_TOKEN)
if [[ -z "$token" ]]; then
  if [[ ! -t 0 ]]; then
    printf 'Set TELEGRAM_BOT_TOKEN in .env and run this script again.\n' >&2
    exit 1
  fi
  read -r -s -p 'Telegram bot token: ' token
  printf '\n'
  if [[ -z "$token" || "$token" == *$'\n'* ]]; then
    printf 'Telegram bot token cannot be empty.\n' >&2
    exit 1
  fi

  env_temp=$(mktemp "$repo_dir/.env.XXXXXX")
  token_written=0
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" == TELEGRAM_BOT_TOKEN=* ]]; then
      printf 'TELEGRAM_BOT_TOKEN=%s\n' "$token" >> "$env_temp"
      token_written=1
    else
      printf '%s\n' "$line" >> "$env_temp"
    fi
  done < .env
  if [[ "$token_written" -eq 0 ]]; then
    printf 'TELEGRAM_BOT_TOKEN=%s\n' "$token" >> "$env_temp"
  fi
  mv "$env_temp" .env
  chmod 600 .env
fi
unset token

model_file=$(env_value MODEL_FILE)
model_file=${model_file:-Qwen3-0.6B-Q8_0.gguf}
if [[ ! "$model_file" =~ ^[[:alnum:]_.-]+\.gguf$ ]]; then
  printf 'MODEL_FILE must be a GGUF filename inside extractor/models/.\n' >&2
  exit 1
fi

mkdir -p extractor/models data
chmod 755 extractor/models data
model_path="extractor/models/$model_file"
if [[ ! -s "$model_path" ]]; then
  if [[ "$model_file" != Qwen3-0.6B-Q8_0.gguf ]]; then
    printf 'Copy %s to %s and run this script again.\n' "$model_file" "$model_path" >&2
    exit 1
  fi
  printf 'Downloading the default GGUF model (about 640 MB)...\n'
  partial_path="${model_path}.part"
  curl --fail --location --retry 3 --output "$partial_path" \
    'https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q8_0.gguf?download=true'
  if [[ $(stat -c %s "$partial_path") -lt 100000000 ]]; then
    printf 'The downloaded model file is unexpectedly small.\n' >&2
    exit 1
  fi
  mv "$partial_path" "$model_path"
fi
chmod 644 "$model_path"

compose_files=(-f compose.yaml)
if [[ "$profile" == gpu ]]; then
  compose_files+=(-f compose.cuda.yaml)
fi

docker compose "${compose_files[@]}" config --quiet
docker compose "${compose_files[@]}" pull llama
docker compose "${compose_files[@]}" up -d --build
docker compose "${compose_files[@]}" ps
printf '\nBot setup finished. Send /start to your bot in Telegram.\n'
printf 'To view logs: docker compose %s logs -f bot llama\n' "${compose_files[*]}"
