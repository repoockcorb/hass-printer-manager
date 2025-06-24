#!/bin/bash
set -e

# ==============================================================================
# Start the Print Farm Dashboard add-on
# ==============================================================================

echo "[INFO] Starting Print Farm Dashboard..."
echo "[INFO] Environment: Home Assistant Add-on"
echo "[INFO] Working directory: $(pwd)"
echo "[INFO] Available space in /data: $(df -h /data 2>/dev/null | tail -1 | awk '{print $4}' || echo 'N/A')"

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

# Set environment variables for Flask
export FLASK_APP=app/app.py
export FLASK_ENV=production
export HOST=0.0.0.0
export PORT=5001

# Create necessary directories
mkdir -p /data/gcode_files
chmod 755 /data/gcode_files

# Install Python dependencies
echo "[INFO] Installing dependencies..."
pip install --no-cache-dir -r requirements.txt

# Start the Flask application
echo "[INFO] Starting Print Farm Dashboard backend..."
cd app
python app.py &

# Wait for background processes
wait 