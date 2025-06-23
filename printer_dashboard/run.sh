#!/bin/bash
set -e

# ==============================================================================
# Start the Print Farm Dashboard add-on
# ==============================================================================

echo "Starting Print Farm Dashboard..."

cd /opt/printer_dashboard/app

# Check if dependencies are installed
echo "Checking dependencies..."
python -c "import flask, requests, yaml" || {
    echo "Installing dependencies..."
    pip install -r ../requirements.txt
}

echo "Dependencies verified successfully"

# Start the Flask application
echo "Starting Flask app..."
exec python app.py 