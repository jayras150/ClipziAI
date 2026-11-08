// Nilai default untuk development lokal.
// Saat container Docker berjalan, file ini DITIMPA oleh docker-entrypoint.sh
// menggunakan nilai env NEXT_PUBLIC_API_URL.
window.__ENV__ = window.__ENV__ || {};
