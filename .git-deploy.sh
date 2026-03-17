#!/bin/bash
# Git-based deployment script for VM
# Usage: ./git-deploy.sh [branch] [vm_ip] [vm_user] [vm_path]

set -e

BRANCH=${1:-main}
VM_IP=${2:-${VM_IP:-192.168.1.100}}
VM_USER=${3:-${VM_USER:-ubuntu}}
VM_PATH=${4:-${VM_PATH:-/home/ubuntu/aem-guides-dataset-studio}}

echo "=== Git-based Deployment ==="
echo "Branch: $BRANCH"
echo "VM: $VM_USER@$VM_IP:$VM_PATH"

# Check if git repo
if [ ! -d .git ]; then
    echo "Initializing git repository..."
    git init
    echo "Git repository initialized!"
    echo ""
    echo "Next steps:"
    echo "1. Add remote: git remote add origin <your-repo-url>"
    echo "2. Commit files: git add . && git commit -m 'Initial commit'"
    echo "3. Push: git push -u origin $BRANCH"
    exit 0
fi

# Check for uncommitted changes
if [ -n "$(git status --porcelain)" ]; then
    echo "Warning: You have uncommitted changes"
    git status --short
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Deployment cancelled."
        exit 1
    fi
fi

# Push to remote
echo "Pushing to remote..."
if git push origin $BRANCH 2>/dev/null; then
    echo "Push successful!"
else
    echo "Push failed or remote not configured. Continuing with local deployment..."
fi

# Deploy on VM
echo "Deploying on VM..."
ssh $VM_USER@$VM_IP << EOF
    set -e
    cd $VM_PATH
    echo "Current directory: \$(pwd)"
    echo "Fetching latest changes..."
    git fetch origin 2>&1 || echo "Remote not configured, using local repo"
    git checkout $BRANCH 2>&1 || git checkout -b $BRANCH
    git pull origin $BRANCH 2>&1 || echo "Pull failed, using local changes"
    
    echo "Checking for docker-compose..."
    if [ -f docker-compose.yml ]; then
        echo "Restarting services..."
        docker-compose restart
        echo "Services restarted!"
    else
        echo "No docker-compose.yml found, skipping restart"
    fi
    
    echo "Deployment complete!"
EOF

echo "Done!"
