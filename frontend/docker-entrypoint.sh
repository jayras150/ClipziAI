#!/bin/sh
# =============================================================================
# Entrypoint frontend Clipzi AI
# Menulis ulang /app/public/runtime-env.js setiap container start, sehingga
# NEXT_PUBLIC_API_URL bisa diubah tanpa perlu rebuild image.
# =============================================================================
set -eu

API_URL="${NEXT_PUBLIC_API_URL:-http://localhost:8000}"

# Buang trailing slash agar tidak jadi "//api/..."
API_URL="${API_URL%/}"

mkdir -p /app/public
cat > /app/public/runtime-env.js <<EOF
window.__ENV__ = { NEXT_PUBLIC_API_URL: "${API_URL}" };
EOF

echo "[entrypoint] runtime-env.js dibuat dengan NEXT_PUBLIC_API_URL=${API_URL}"

exec "$@"
