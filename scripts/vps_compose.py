from __future__ import annotations

import os

DOCKERHUB = os.environ.get("VPS_DOCKERHUB", "sujinwo555")
TAG = os.environ.get("VPS_TAG", "1.5.0")
PUBLIC_URL = os.environ.get("VPS_PUBLIC_URL", "https://proxyai.live")
GOOGLE_CLIENT_ID = os.environ.get("VPS_GOOGLE_CLIENT_ID", "")

COMPOSE_TEMPLATE = """# Deployment Clipzi di VPS (satu origin lewat Caddy)
name: clipzi

services:
  backend:
    image: __DOCKERHUB__/clipzi-backend:__TAG__
    container_name: clipzi-api
    env_file:
      - ./backend/.env
    expose:
      - "8000"
    volumes:
      - clipzi_cache:/app/.cache
    mem_limit: 1200m
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://127.0.0.1:8000/api/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 60s
    logging:
      driver: json-file
      options:
        { max-size: "10m", max-file: "3" }

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    image: __DOCKERHUB__/clipzi-frontend:local
    container_name: clipzi-web
    environment:
      NEXT_PUBLIC_API_URL: __PUBLIC_URL__
      NEXT_PUBLIC_GOOGLE_CLIENT_ID: "__GOOGLE_CLIENT_ID__"
    expose:
      - "3000"
    mem_limit: 512m
    restart: unless-stopped
    depends_on:
      - backend
    logging:
      driver: json-file
      options:
        { max-size: "10m", max-file: "3" }

  caddy:
    image: caddy:2-alpine
    container_name: clipzi-caddy
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"
    environment:
      DOMAIN: __PUBLIC_URL__
    volumes:
      - ./deploy/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    mem_limit: 128m
    restart: unless-stopped
    depends_on:
      - backend
      - frontend
    logging:
      driver: json-file
      options:
        { max-size: "10m", max-file: "3" }

volumes:
  caddy_data:
  caddy_config:
  clipzi_cache:
"""


def compose_text() -> str:
    return (
        COMPOSE_TEMPLATE.replace("__DOCKERHUB__", DOCKERHUB)
        .replace("__TAG__", TAG)
        .replace("__PUBLIC_URL__", PUBLIC_URL)
        .replace("__GOOGLE_CLIENT_ID__", GOOGLE_CLIENT_ID)
    )
