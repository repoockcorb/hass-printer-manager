#!/bin/bash
set -e

# ==============================================================================
# Start the Printer Dashboard add-on
# ==============================================================================

echo "Starting Printer Dashboard..."

# Export environment variables for the Flask app
export SUPERVISOR_TOKEN="${SUPERVISOR_TOKEN}"
export HASSIO_TOKEN="${HASSIO_TOKEN}"
export HOME_ASSISTANT_URL="http://supervisor/core"

# Create data directory if it doesn't exist
mkdir -p /data

# Start nginx in background
echo "Starting nginx..."
nginx &

# Start the Flask application
echo "Starting Python Flask backend..."
cd /app
python3 app.py 