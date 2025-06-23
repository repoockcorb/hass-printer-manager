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
    pkill -f "gunicorn" || true
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

# Start Flask app with gunicorn for production WebSocket support
echo "[INFO] Starting Print Farm Dashboard backend..."
cd /app
# Run gunicorn in foreground so the script doesn't exit
exec gunicorn --worker-class eventlet -w 1 --bind 127.0.0.1:5001 --log-level info app:app 