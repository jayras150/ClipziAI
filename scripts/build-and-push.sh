#!/usr/bin/env bash
# =============================================================================
# Build & push image Docker Clipzi AI (backend & frontend) ke Docker Hub.
# Dipakai di Linux/macOS atau di dalam instance Vast.ai.
#
# Contoh:
#   ./scripts/build-and-push.sh budi                  # build + push, tag latest
#   ./scripts/build-and-push.sh budi 1.0.0            # tag tertentu
#   BUILD_ONLY=1 ./scripts/build-and-push.sh budi     # build tanpa push
#   TARGET=backend ./scripts/build-and-push.sh budi   # hanya backend
# =============================================================================
set -euo pipefail

DOCKERHUB_USER="${1:-}"
TAG="${2:-latest}"
PLATFORM="${PLATFORM:-linux/amd64}"
BUILD_ONLY="${BUILD_ONLY:-0}"
TARGET="${TARGET:-all}"

if [ -z "$DOCKERHUB_USER" ]; then
  echo "Usage: $0 <dockerhub-user> [tag]" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

BACKEND_IMAGE="${DOCKERHUB_USER}/clipzi-backend:${TAG}"
FRONTEND_IMAGE="${DOCKERHUB_USER}/clipzi-frontend:${TAG}"

echo "== Cek Docker daemon =="
docker version --format '{{.Server.Version}}'

if [ "$TARGET" = "all" ] || [ "$TARGET" = "backend" ]; then
  echo
  echo "== Build backend (${BACKEND_IMAGE}) =="
  docker build \
    --platform "$PLATFORM" \
    -t "$BACKEND_IMAGE" \
    -f "$REPO_ROOT/backend/Dockerfile" \
    "$REPO_ROOT/backend"

  if [ "$BUILD_ONLY" != "1" ]; then
    echo
    echo "== Push backend =="
    docker push "$BACKEND_IMAGE"
  fi
fi

if [ "$TARGET" = "all" ] || [ "$TARGET" = "frontend" ]; then
  echo
  echo "== Build frontend (${FRONTEND_IMAGE}) =="
  docker build \
    --platform "$PLATFORM" \
    -t "$FRONTEND_IMAGE" \
    -f "$REPO_ROOT/frontend/Dockerfile" \
    "$REPO_ROOT/frontend"

  if [ "$BUILD_ONLY" != "1" ]; then
    echo
    echo "== Push frontend =="
    docker push "$FRONTEND_IMAGE"
  fi
fi

echo
echo "== Selesai =="
echo "Backend : ${BACKEND_IMAGE}"
echo "Frontend: ${FRONTEND_IMAGE}"
echo
echo "Contoh menjalankan di instance (Vast.ai / VPS):"
echo "  docker run -d --name clipzi-api -p 8000:8000 --env-file backend/.env ${BACKEND_IMAGE}"
echo "  docker run -d --name clipzi-web -p 3000:3000 -e NEXT_PUBLIC_API_URL=http://IP_PUBLIK:8000 ${FRONTEND_IMAGE}"
