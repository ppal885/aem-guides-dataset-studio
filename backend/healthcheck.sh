#!/bin/bash
set -e

# Check if backend is responding
if curl -f http://localhost:8000/health > /dev/null 2>&1; then
    exit 0
else
    exit 1
fi
