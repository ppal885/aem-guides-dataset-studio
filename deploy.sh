#!/usr/bin/env bash
# AEM Guides UAC backend + evaluation dashboard — Linux VM Deploy Script
# Usage: ./deploy.sh [--build] [--pull] [--stop]
set -Eeuo pipefail

PROJECT="aem-studio"
COMPOSE_FILE="docker-compose.yml"

# ── Helpers ──────────────────────────────────────────────────────────────────
info()  { echo -e "\033[0;34m[INFO]\033[0m  $*"; }
ok()    { echo -e "\033[0;32m[OK]\033[0m    $*"; }
warn()  { echo -e "\033[0;33m[WARN]\033[0m  $*"; }
die()   { echo -e "\033[0;31m[ERROR]\033[0m $*" >&2; exit 1; }

# ── Preflight ─────────────────────────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || die "Docker is not installed. Run: curl -fsSL https://get.docker.com | sh"
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 not found. Update Docker or install the plugin."

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
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" down --remove-orphans
  ok "Backend container stopped. The static dashboard remains available through system Nginx."
  exit 0
fi

[ "$(id -u)" -eq 0 ] || die "Run deploy.sh as root so it can update system Nginx and /var/www."
command -v python3 >/dev/null 2>&1 || die "python3 is required for dashboard aggregation."
command -v nginx >/dev/null 2>&1 || die "system Nginx is required on port 4502."

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
# Stamp the build commit so a deploy can be verified in one API call (result.build_commit).
if command -v git >/dev/null 2>&1 && [ -d .git ]; then
  SHA=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)
  echo "$SHA" > BUILD_COMMIT
  echo "$SHA" > backend/BUILD_COMMIT   # COPY'd into the backend image so the app can read it
  ok "Stamped BUILD_COMMIT=$SHA"
fi

BUILD_ARGS=()
if $PULL; then
  info "Pulling latest base images..."
  BUILD_ARGS+=(--pull)
fi

if $BUILD || $PULL; then
  info "Building images (this may take a few minutes on first run)..."
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" build "${BUILD_ARGS[@]}"
  ok "Build complete."
fi

# ── Start ─────────────────────────────────────────────────────────────────────
info "Starting services..."
docker compose -p "$PROJECT" -f "$COMPOSE_FILE" up -d --remove-orphans

# ── Health wait ───────────────────────────────────────────────────────────────
info "Waiting for backend to be healthy..."
BACKEND_HEALTHY=false
for i in $(seq 1 20); do
  STATUS=$(docker inspect --format='{{.State.Health.Status}}' aem-studio-backend 2>/dev/null || echo "starting")
  if [ "$STATUS" = "healthy" ]; then
    ok "Backend is healthy."
    BACKEND_HEALTHY=true
    break
  fi
  if [ $i -eq 20 ]; then
    warn "Backend health check timed out."
    break
  fi
  echo "  Waiting... ($i/20) status=$STATUS"
  sleep 5
done

if [ "$BACKEND_HEALTHY" != "true" ]; then
  die "Backend is not healthy. Check logs: docker logs aem-studio-backend"
fi

# setup_vm.py owns the single Nginx contract and performs a staged webroot swap.
info "Aggregating and deploying the dashboard to system Nginx on port 4502..."
python3 setup_vm.py --dashboard-only
ok "Dashboard deployed."

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
ok "AEM Guides UAC backend and evaluation dashboard are running."
echo ""
echo "  Dashboard: http://$(hostname -I | awk '{print $1}'):4502/"
echo "  Health   : http://$(hostname -I | awk '{print $1}'):4502/health"
echo "  API      : http://$(hostname -I | awk '{print $1}'):4502/api/"
echo "  MCP      : http://$(hostname -I | awk '{print $1}'):4502/mcp"
echo "  Logs     : docker compose -p $PROJECT -f $COMPOSE_FILE logs -f backend"
echo "  Stop     : ./deploy.sh --stop"
echo ""
