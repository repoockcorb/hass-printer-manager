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
    pkill -f "python app.py" || true
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

# Change to the app directory (where files are located)
cd /app
echo "[INFO] Current directory: $(pwd)"
echo "[INFO] Files in directory: $(ls -la)"

# Install Python dependencies
echo "[INFO] Installing dependencies..."
if [ -f "requirements.txt" ]; then
    pip install --no-cache-dir -r requirements.txt
else
    echo "[ERROR] requirements.txt not found in $(pwd)"
    echo "[INFO] Available files: $(ls -la)"
    exit 1
fi

# Start the Flask application
echo "[INFO] Starting Print Farm Dashboard backend..."
cd app
echo "[INFO] App directory contents: $(ls -la)"
echo "[INFO] Starting Flask app..."
python app.py &
FLASK_PID=$!
echo "[INFO] Flask app started with PID: $FLASK_PID"

# Wait for background processes
echo "[INFO] Waiting for services..."
wait 