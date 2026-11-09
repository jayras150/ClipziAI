#!/bin/sh
# =============================================================================
# Entrypoint frontend Clipzi AI
# Menulis ulang /app/public/runtime-env.js setiap container start, sehingga
# NEXT_PUBLIC_API_URL bisa diubah tanpa perlu rebuild image.
# =============================================================================
set -eu

API_URL="${NEXT_PUBLIC_API_URL:-http://localhost:8000}"
GOOGLE_CLIENT_ID="${NEXT_PUBLIC_GOOGLE_CLIENT_ID:-}"

# Buang trailing slash agar tidak jadi "//api/..."
API_URL="${API_URL%/}"

mkdir -p /app/public
cat > /app/public/runtime-env.js <<EOF
window.__ENV__ = { NEXT_PUBLIC_API_URL: "${API_URL}", NEXT_PUBLIC_GOOGLE_CLIENT_ID: "${GOOGLE_CLIENT_ID}" };
EOF

echo "[entrypoint] runtime-env.js dibuat dengan NEXT_PUBLIC_API_URL=${API_URL}"
echo "[entrypoint] google sign-in: $([ -n "$GOOGLE_CLIENT_ID" ] && echo enabled || echo 'not configured')"

exec "$@"
