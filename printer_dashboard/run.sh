#!/usr/bin/with-contenv bashio

# ==============================================================================
# Start the Printer Dashboard add-on
# ==============================================================================

# Get configuration options
SSL=$(bashio::config 'ssl')
CERTFILE=$(bashio::config 'certfile')
KEYFILE=$(bashio::config 'keyfile')

# Export environment variables for the Flask app
export SUPERVISOR_TOKEN="${SUPERVISOR_TOKEN}"
export HASSIO_TOKEN="${HASSIO_TOKEN}"
export HOME_ASSISTANT_URL="http://supervisor/core"

bashio::log.info "Starting Printer Dashboard..."

# Start nginx for ingress support
if bashio::config.true 'ssl'; then
    bashio::log.info "SSL enabled, using certificates"
    # Configure nginx for SSL
    sed -i "s/CERTFILE/${CERTFILE}/g" /etc/nginx/nginx.conf
    sed -i "s/KEYFILE/${KEYFILE}/g" /etc/nginx/nginx.conf
fi

# Start nginx in background
nginx &

# Start the Flask application
bashio::log.info "Starting Python Flask backend..."
cd /app
python3 app.py 