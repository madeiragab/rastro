#!/usr/bin/env bash
# Backup do banco.
#
#   ./deploy/backup.sh              faz o backup
#   ./deploy/backup.sh --restaurar arquivo.sql.gz    restaura
#
# Instale no cron da máquina:
#   0 3 * * * cd /opt/rastro && ./deploy/backup.sh >> /var/log/rastro-backup.log 2>&1
#
# Backup que nunca foi restaurado não é backup. Teste a restauração pelo menos
# uma vez antes de precisar dela.

set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

COMPOSE="docker compose -f docker-compose.prod.yml --env-file .env.production"
DESTINO="${RAIZ}/backups"
RETENCAO_DIAS="${RETENCAO_DIAS:-14}"

# shellcheck disable=SC1091
set -a; source .env.production; set +a

mkdir -p "$DESTINO"

restaurar() {
  local arquivo="$1"
  [ -f "$arquivo" ] || { echo "arquivo não encontrado: $arquivo" >&2; exit 1; }

  echo "ATENÇÃO: isto SUBSTITUI o banco atual por $arquivo"
  read -rp "digite 'restaurar' para confirmar: " confirmacao
  [ "$confirmacao" = "restaurar" ] || { echo "cancelado"; exit 1; }

  echo "parando a API para ninguém escrever durante a restauração..."
  $COMPOSE stop api

  gunzip -c "$arquivo" | $COMPOSE exec -T db psql -U "$POSTGRES_USER" -d postgres \
    -v ON_ERROR_STOP=1 >/dev/null

  $COMPOSE start api
  echo "restaurado."
}

if [ "${1:-}" = "--restaurar" ]; then
  restaurar "${2:-}"
  exit 0
fi

CARIMBO="$(date +%Y-%m-%d_%H%M)"
ARQUIVO="${DESTINO}/rastro_${CARIMBO}.sql.gz"

# --clean --create para o dump reconstruir o banco do zero na restauração.
$COMPOSE exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --create \
  | gzip > "$ARQUIVO"

TAMANHO="$(du -h "$ARQUIVO" | cut -f1)"
echo "$(date '+%F %T') backup: $ARQUIVO ($TAMANHO)"

# Um dump que sai vazio ou minúsculo é sinal de falha silenciosa.
BYTES="$(stat -c%s "$ARQUIVO" 2>/dev/null || stat -f%z "$ARQUIVO")"
if [ "$BYTES" -lt 1024 ]; then
  echo "ERRO: backup suspeito de tão pequeno ($BYTES bytes)" >&2
  exit 1
fi

find "$DESTINO" -name 'rastro_*.sql.gz' -mtime "+${RETENCAO_DIAS}" -delete
echo "$(date '+%F %T') retenção: mantidos os últimos ${RETENCAO_DIAS} dias"

# Lembrete honesto: isto guarda o backup NA MESMA MÁQUINA do banco. Se a
# máquina se perder, o backup se perde junto. Copie para fora — rclone para um
# bucket, ou scp para outro servidor.
