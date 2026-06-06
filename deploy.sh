#!/usr/bin/env bash
# AEM Guides Dataset Studio — Linux VM Deploy Script
# Usage: ./deploy.sh [--build] [--pull] [--stop]
set -e

PROJECT="aem-studio"
COMPOSE_FILE="docker-compose.yml"

# ── Helpers ──────────────────────────────────────────────────────────────────
info()  { echo -e "\033[0;34m[INFO]\033[0m  $*"; }
ok()    { echo -e "\033[0;32m[OK]\033[0m    $*"; }
warn()  { echo -e "\033[0;33m[WARN]\033[0m  $*"; }
die()   { echo -e "\033[0;31m[ERROR]\033[0m $*" >&2; exit 1; }

# ── Preflight ─────────────────────────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || die "Docker is not installed. Run: curl -fsSL https://get.docker.com | sh"
command -v docker compose >/dev/null 2>&1 || die "Docker Compose v2 not found. Update Docker or install the plugin."

# ── Parse args ────────────────────────────────────────────────────────────────
BUILD=false PULL=false STOP=false
for arg in "$@"; do
  case $arg in
    --build)  BUILD=true ;;
    --pull)   PULL=true ;;
    --stop)   STOP=true ;;
    --help|-h)
      echo "Usage: $0 [--build] [--pull] [--stop]"
      echo "  --build   Force rebuild of all images"
      echo "  --pull    Pull latest base images before build"
      echo "  --stop    Stop and remove containers"
      exit 0 ;;
  esac
done

# ── Stop ─────────────────────────────────────────────────────────────────────
if $STOP; then
  info "Stopping containers..."
  docker compose -p $PROJECT -f $COMPOSE_FILE down
  ok "Stopped."
  exit 0
fi

# ── .env.docker check ─────────────────────────────────────────────────────────
if [ ! -f ".env.docker" ]; then
  warn ".env.docker not found — creating from template."
  cp .env.docker.example .env.docker
  echo ""
  echo "  ┌─────────────────────────────────────────────────────────────┐"
  echo "  │  IMPORTANT: Edit .env.docker before continuing.            │"
  echo "  │  Set at minimum: LLM_PROVIDER, AZURE_OPENAI_API_KEY, etc.  │"
  echo "  └─────────────────────────────────────────────────────────────┘"
  echo ""
  read -p "Press Enter to continue after editing .env.docker, or Ctrl+C to abort..." _
fi

# ── Build ─────────────────────────────────────────────────────────────────────
BUILD_ARGS=""
if $PULL; then
  info "Pulling latest base images..."
  BUILD_ARGS="--pull"
fi

if $BUILD || $PULL; then
  info "Building images (this may take a few minutes on first run)..."
  docker compose -p $PROJECT -f $COMPOSE_FILE build $BUILD_ARGS
  ok "Build complete."
fi

# ── Start ─────────────────────────────────────────────────────────────────────
info "Starting services..."
docker compose -p $PROJECT -f $COMPOSE_FILE up -d

# ── Health wait ───────────────────────────────────────────────────────────────
info "Waiting for backend to be healthy..."
for i in $(seq 1 20); do
  STATUS=$(docker inspect --format='{{.State.Health.Status}}' aem-studio-backend 2>/dev/null || echo "starting")
  if [ "$STATUS" = "healthy" ]; then
    ok "Backend is healthy."
    break
  fi
  if [ $i -eq 20 ]; then
    warn "Backend health check timed out. Check logs: docker logs aem-studio-backend"
    break
  fi
  echo "  Waiting... ($i/20) status=$STATUS"
  sleep 5
done

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
ok "AEM Guides Dataset Studio is running."
echo ""
echo "  Frontend : http://$(hostname -I | awk '{print $1}')/"
echo "  Backend  : http://$(hostname -I | awk '{print $1}'):8001/health"
echo "  Logs     : docker compose -p $PROJECT logs -f"
echo "  Stop     : ./deploy.sh --stop"
echo ""
