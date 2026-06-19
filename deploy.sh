#!/bin/bash

# Configuration
PI_HOST="devpi"
PI_DEST="~/Desktop/robot_home_use/"

echo "🚀 Syncing files to Raspberry Pi ($PI_HOST)..."

# Use rsync to sync files, excluding virtual environments, python caches, git metadata, and local configurations
rsync -avz --delete \
    --exclude '.git/' \
    --exclude '.gitignore' \
    --exclude '__pycache__/' \
    --exclude '*.pyc' \
    --exclude 'venv/' \
    --exclude '.venv/' \
    --exclude 'node_modules/' \
    --exclude '.env' \
    --exclude 'deploy.sh' \
    --exclude 'backend/models/' \
    --exclude '*.db' \
    ./ "$PI_HOST:$PI_DEST"

echo "✅ Sync complete!"
