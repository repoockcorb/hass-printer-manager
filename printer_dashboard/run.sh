#!/bin/bash
set -e

# ==============================================================================
# Start the Print Farm Dashboard add-on
# ==============================================================================

echo "[INFO] Starting Print Farm Dashboard..."

# Export environment variables for the Flask app
export SUPERVISOR_TOKEN="${SUPERVISOR_TOKEN}"
export HASSIO_TOKEN="${HASSIO_TOKEN}"
export HOME_ASSISTANT_URL="http://supervisor/core"

# Create data directory if it doesn't exist
mkdir -p /data

# Function to handle shutdown gracefully
shutdown() {
    echo "[INFO] Shutting down services..."
    pkill -f "python3 app.py" || true
    pkill nginx || true
    exit 0
}

# Trap signals for graceful shutdown
trap shutdown SIGTERM SIGINT

# Start nginx in background (simple reverse proxy)
echo "[INFO] Starting nginx reverse proxy..."
nginx &

# Wait a moment for nginx to start
sleep 2

# Start the Flask application
echo "[INFO] Starting Print Farm Dashboard backend..."
cd /app
python3 app.py &

# Wait for background processes
wait 