#!/bin/bash
# Copy local OAuth tokens and DBs into the Docker volume.
# Run from repo root: ./deploy/scripts/init-data-volume.sh
#
# Use before first `docker compose -f docker-compose.prod.yml up`, or after
# `docker compose down` to restore from local backup.
#
# Usage: ./init-data-volume.sh [volume_name]
# Default volume: woodfamily-ai-v2_app_data (from docker-compose project name)

set -e
VOLUME="${1:-woodfamily-ai-v2_app_data}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

# Ensure volume exists
docker volume create "$VOLUME" 2>/dev/null || true
echo "Initializing volume: $VOLUME"

# Create directory structure and copy files
docker run --rm -v "$VOLUME":/data -v "$REPO_ROOT":/src alpine sh -c '
  mkdir -p /data/woody /data/dashboard /data/chroma_db
  if [ -f /src/.google_tokens.json ]; then
    cp /src/.google_tokens.json /data/.google_tokens.json
    echo "Copied .google_tokens.json"
  fi
  if [ -f /src/.yahoo_tokens.json ]; then
    cp /src/.yahoo_tokens.json /data/.yahoo_tokens.json
    echo "Copied .yahoo_tokens.json"
  fi
  if [ -d /src/chroma_db ] && [ "$(ls -A /src/chroma_db 2>/dev/null)" ]; then
    cp -r /src/chroma_db/* /data/chroma_db/
    echo "Copied chroma_db"
  fi
  if [ -f /src/woody/app.db ]; then
    cp /src/woody/app.db /data/woody/app.db
    echo "Copied woody/app.db"
  fi
  if [ -f /src/dashboard/dashboard.db ]; then
    cp /src/dashboard/dashboard.db /data/dashboard/dashboard.db
    echo "Copied dashboard/dashboard.db"
  fi
  echo "Done."
'
