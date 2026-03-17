#!/bin/bash
# Fix large_scale recipe error - Rebuild backend
# Usage: ./fix-large-scale-error.sh

set -e

echo "Fixing large_scale recipe error..."
echo ""

# Verify fix is in source file
echo "1. Checking source file..."
if grep -A 10 "elif recipe_type == \"large_scale\"" backend/app/tasks/generate_dataset.py | grep -q "progress_callback"; then
    echo "   ERROR: progress_callback still present in source!"
    echo "   Fixing..."
    # This shouldn't happen if fix was applied, but just in case
    sed -i '/progress_callback=progress_callback/d' backend/app/tasks/generate_dataset.py
    echo "   SUCCESS: Removed progress_callback"
else
    echo "   SUCCESS: Source file is correct (no progress_callback)"
fi

# Stop backend
echo ""
echo "2. Stopping backend..."
docker-compose stop backend
docker-compose rm -f backend

# Remove old image
echo ""
echo "3. Removing old backend image..."
docker rmi aem-guides-dataset-studio-backend 2>/dev/null || echo "   Image not found (will be rebuilt)"

# Rebuild with no cache
echo ""
echo "4. Rebuilding backend with NO CACHE..."
docker-compose build --no-cache backend

# Start backend
echo ""
echo "5. Starting backend..."
docker-compose up -d backend

# Wait and check
echo ""
echo "6. Waiting for backend to be ready..."
sleep 15

# Check logs
echo ""
echo "7. Checking backend logs..."
docker-compose logs backend --tail=30

echo ""
echo "============================"
echo "SUCCESS: Rebuild Complete!"
echo "============================"
echo ""
echo "Next: Test large_scale generation again"
echo "The error should be fixed now"
echo ""
