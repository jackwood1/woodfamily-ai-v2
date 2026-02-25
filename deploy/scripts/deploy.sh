#!/bin/bash
# Deploy script – run on EC2 after merge to main.
# Usage: ./deploy/scripts/deploy.sh [repo_path]
# Default: run from repo root (e.g. cd ~/woodfamily-ai-v2 && ./deploy/scripts/deploy.sh)
#
# Prerequisites: .env exists, Docker running, repo cloned.

set -e

REPO_PATH="${1:-$(pwd)}"
cd "$REPO_PATH"

echo "==> Deploying from $(pwd)"

# Pull latest main
git fetch origin
git checkout main
git pull origin main

# Build and bring up services
echo "==> Building and starting containers..."
docker compose -f docker-compose.prod.yml build --quiet
docker compose -f docker-compose.prod.yml up -d

echo "==> Deploy complete. Checking health..."
sleep 5
curl -sf http://localhost:8000/health && echo " Dashboard OK" || echo " Dashboard not ready"
curl -sf http://localhost:9000/health && echo " Woody OK" || echo " Woody not ready"
