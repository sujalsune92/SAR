#!/bin/bash
# Docker startup initialization script
# This script handles database initialization and model setup

set -e

echo "=========================================="
echo "SAR Narrative Generator - Docker Setup"
echo "=========================================="

# Function to wait for a service to be ready
wait_for_service() {
    local host=$1
    local port=$2
    local service=$3
    
    echo "Waiting for $service to be ready..."
    max_attempts=30
    attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if nc -z $host $port 2>/dev/null; then
            echo "✓ $service is ready"
            return 0
        fi
        echo "  Attempt $attempt/$max_attempts - $service not ready yet..."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    echo "✗ $service failed to start"
    return 1
}

# Wait for PostgreSQL
wait_for_service postgres 5432 "PostgreSQL"

# Initialize database
echo ""
echo "Initializing PostgreSQL database..."
python -m backend.database || true

# Seed data
echo ""
echo "Seeding sample data..."
python scripts/seed_data.py || true

# Wait for Ollama
wait_for_service ollama 11434 "Ollama"

# Pull the default model (this may take a while on first run)
echo ""
echo "Preparing Ollama model..."
ollama pull ${OLLAMA_MODEL:-mistral:7b} || true

echo ""
echo "Setup complete! Backend is ready to start."
