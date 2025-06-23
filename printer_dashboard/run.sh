#!/bin/bash
set -e

# ==============================================================================
# Start the Print Farm Dashboard add-on
# ==============================================================================

echo "Starting Print Farm Dashboard..."

cd /app

# Check if dependencies are installed
echo "Checking dependencies..."
python3 -c "import flask, requests, yaml" || {
    echo "Installing dependencies..."
    pip3 install -r requirements.txt
}

echo "Dependencies verified successfully"

# Start the Flask application
echo "Starting Flask app..."
exec python3 app.py 