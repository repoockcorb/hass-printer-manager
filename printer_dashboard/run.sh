#!/bin/bash
set -e

# ==============================================================================
# Start the Printer Dashboard add-on
# ==============================================================================

echo "[INFO] Starting Printer Dashboard..."

# Export environment variables for the Flask app
export SUPERVISOR_TOKEN="${SUPERVISOR_TOKEN}"
export HASSIO_TOKEN="${HASSIO_TOKEN}"
export HOME_ASSISTANT_URL="http://supervisor/core"

# Create data directory if it doesn't exist
mkdir -p /data

# Start nginx in background
echo "[INFO] Starting nginx..."
nginx &

# Function to handle shutdown gracefully
shutdown() {
    echo "[INFO] Shutting down services..."
    pkill -f "python3 app.py" || true
    pkill nginx || true
    exit 0
}

# Trap signals for graceful shutdown
trap shutdown SIGTERM SIGINT

# Start the Flask application in foreground
echo "[INFO] Starting Python Flask backend..."
cd /app
python3 app.py &

# Wait for background processes
wait 