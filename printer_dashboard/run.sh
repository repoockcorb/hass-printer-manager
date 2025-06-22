#!/usr/bin/with-contenv bashio
# ==============================================================================
# Start the Printer Dashboard add-on
# ==============================================================================

bashio::log.info "Starting Printer Dashboard..."

# Export environment variables for the Flask app
export SUPERVISOR_TOKEN="${SUPERVISOR_TOKEN}"
export HASSIO_TOKEN="${HASSIO_TOKEN}"
export HOME_ASSISTANT_URL="http://supervisor/core"

# Create data directory if it doesn't exist
mkdir -p /data

# Start nginx in background
bashio::log.info "Starting nginx..."
nginx &

# Start the Flask application in foreground
bashio::log.info "Starting Python Flask backend..."
cd /app
exec python3 app.py 