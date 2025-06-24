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
echo "[DEBUG] Before changing directory - current: $(pwd)"
echo "[DEBUG] Contents of /app:"
ls -la /app/ 2>/dev/null || echo "Cannot list /app directory"

cd /app || {
    echo "[ERROR] Failed to change to /app directory"
    echo "[DEBUG] Available directories in root:"
    ls -la /
    exit 1
}

echo "[INFO] Successfully changed to directory: $(pwd)"
echo "[INFO] Files in current directory:"
ls -la

# Install Python dependencies
echo "[INFO] Installing dependencies..."
echo "[DEBUG] Looking for requirements.txt in: $(pwd)"
echo "[DEBUG] Current directory contents:"
ls -la

if [ -f "requirements.txt" ]; then
    echo "[INFO] Found requirements.txt, installing packages..."
    pip install --no-cache-dir -r requirements.txt || {
        echo "[ERROR] Failed to install requirements"
        echo "[DEBUG] Current working directory: $(pwd)"
        echo "[DEBUG] Requirements file exists: $(test -f requirements.txt && echo 'YES' || echo 'NO')"
        echo "[DEBUG] Requirements file content:"
        cat requirements.txt 2>/dev/null || echo "Could not read requirements.txt"
        exit 1
    }
    echo "[INFO] Dependencies installed successfully"
else
    echo "[ERROR] requirements.txt not found in $(pwd)"
    echo "[INFO] Available files:"
    ls -la
    echo "[DEBUG] Searching for requirements.txt in /app hierarchy:"
    find /app -name "requirements.txt" 2>/dev/null || echo "No requirements.txt found in /app"
    exit 1
fi

# Start the Flask application
echo "[INFO] Starting Print Farm Dashboard backend..."
echo "[INFO] Current directory contents: $(ls -la)"
echo "[INFO] Starting Flask app..."
python app.py &
FLASK_PID=$!
echo "[INFO] Flask app started with PID: $FLASK_PID"

# Wait for background processes
echo "[INFO] Waiting for services..."
wait 