#!/bin/bash
# VM Setup Verification Script
# Run this after setup to verify everything is working
# Usage: bash vm-verify-setup.sh

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_DIR="/home/ubuntu/aem-guides-dataset-studio"
VM_IP=$(hostname -I | awk '{print $1}')

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}VM Setup Verification${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check Docker
echo -n "Checking Docker... "
if command -v docker &> /dev/null; then
    echo -e "${GREEN}✓${NC}"
    docker --version
else
    echo -e "${RED}✗ Docker not found${NC}"
    exit 1
fi

# Check Docker Compose
echo -n "Checking Docker Compose... "
if docker compose version &> /dev/null || command -v docker-compose &> /dev/null; then
    echo -e "${GREEN}✓${NC}"
    docker compose version 2>/dev/null || docker-compose --version
else
    echo -e "${RED}✗ Docker Compose not found${NC}"
    exit 1
fi

# Check project directory
echo -n "Checking project directory... "
if [ -d "$PROJECT_DIR" ]; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗ Project directory not found: $PROJECT_DIR${NC}"
    exit 1
fi

# Check docker-compose.yml
echo -n "Checking docker-compose.yml... "
if [ -f "$PROJECT_DIR/docker-compose.yml" ]; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗ docker-compose.yml not found${NC}"
    exit 1
fi

# Check .env file
echo -n "Checking .env file... "
if [ -f "$PROJECT_DIR/.env" ]; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${YELLOW}⚠ .env file not found (using defaults)${NC}"
fi

# Check Docker containers
echo ""
echo "Checking Docker containers..."
cd "$PROJECT_DIR"
docker compose ps

# Check if containers are running
echo ""
echo -n "Checking PostgreSQL container... "
if docker compose ps postgres | grep -q "Up"; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${RED}✗ Not running${NC}"
fi

echo -n "Checking Backend container... "
if docker compose ps backend | grep -q "Up"; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${RED}✗ Not running${NC}"
fi

echo -n "Checking Frontend container... "
if docker compose ps frontend | grep -q "Up"; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${RED}✗ Not running${NC}"
fi

# Check database connectivity
echo ""
echo -n "Checking database connection... "
if docker compose exec -T postgres pg_isready -U postgres &> /dev/null; then
    echo -e "${GREEN}✓ Connected${NC}"
else
    echo -e "${RED}✗ Cannot connect${NC}"
fi

# Check backend health
echo ""
echo -n "Checking backend health endpoint... "
if curl -f http://localhost:8000/health &> /dev/null; then
    echo -e "${GREEN}✓ Healthy${NC}"
    curl -s http://localhost:8000/health | head -1
else
    echo -e "${YELLOW}⚠ Backend not responding (may still be starting)${NC}"
fi

# Check frontend
echo ""
echo -n "Checking frontend... "
if curl -f http://localhost/ &> /dev/null; then
    echo -e "${GREEN}✓ Accessible${NC}"
else
    echo -e "${YELLOW}⚠ Frontend not responding${NC}"
fi

# Display access URLs
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Access URLs${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "Frontend:    http://${VM_IP}/"
echo "Backend:    http://${VM_IP}:8000"
echo "API Docs:   http://${VM_IP}:8000/docs"
echo "Health:     http://${VM_IP}:8000/health"
echo ""

# Check disk space
echo ""
echo -e "${BLUE}Disk Space:${NC}"
df -h / | tail -1

# Check memory
echo ""
echo -e "${BLUE}Memory Usage:${NC}"
free -h

echo ""
echo -e "${GREEN}Verification Complete!${NC}"
echo ""
