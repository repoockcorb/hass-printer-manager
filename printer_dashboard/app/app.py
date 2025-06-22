#!/usr/bin/env python3

import os
import json
import logging
from flask import Flask, render_template, request, jsonify, redirect, session, url_for
import requests
from functools import wraps

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'printer-dashboard-secret-key')

# Home Assistant configuration
SUPERVISOR_TOKEN = os.environ.get('SUPERVISOR_TOKEN')
HASSIO_TOKEN = os.environ.get('HASSIO_TOKEN')
HOME_ASSISTANT_URL = os.environ.get('HOME_ASSISTANT_URL', 'http://supervisor/core')

class HomeAssistantAuth:
    """Handle Home Assistant authentication"""
    
    def __init__(self):
        self.session = requests.Session()
        if SUPERVISOR_TOKEN:
            self.session.headers.update({
                'Authorization': f'Bearer {SUPERVISOR_TOKEN}',
                'Content-Type': 'application/json'
            })

    def validate_token(self, token):
        """Validate Home Assistant access token"""
        try:
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{HOME_ASSISTANT_URL}/api/', headers=headers, timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return False

    def get_user_info(self, token):
        """Get user information from Home Assistant"""
        try:
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(f'{HOME_ASSISTANT_URL}/api/auth/user', headers=headers, timeout=5)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"User info error: {e}")
            return None

class PrinterStorage:
    """Handle printer data from Home Assistant configuration"""
    
    def __init__(self):
        self.options_path = '/data/options.json'

    def load_printers(self):
        """Load printers from Home Assistant configuration"""
        try:
            if os.path.exists(self.options_path):
                with open(self.options_path, 'r') as f:
                    options = json.load(f)
                    printers = options.get('printers', [])
                    
                    # Add IDs to printers if they don't have them
                    for i, printer in enumerate(printers):
                        if 'id' not in printer:
                            printer['id'] = str(i + 1)
                    
                    return printers
            return []
        except Exception as e:
            logger.error(f"Error loading printers from configuration: {e}")
            return []

    def save_printers(self, printers):
        """Printers are managed through Home Assistant configuration - read-only"""
        logger.warning("Printers are configured through Home Assistant add-on configuration")
        return False

# Initialize components
ha_auth = HomeAssistantAuth()
printer_storage = PrinterStorage()

def require_auth(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if running in Home Assistant ingress mode
        if 'X-Ingress-Path' in request.headers:
            # In ingress mode, authentication is handled by Home Assistant
            return f(*args, **kwargs)
        
        # Check for access token
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            token = request.args.get('access_token')
        
        if not token or not ha_auth.validate_token(token):
            return jsonify({'error': 'Authentication required'}), 401
        
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
@require_auth
def index():
    """Main dashboard page"""
    user_info = None
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if token:
        user_info = ha_auth.get_user_info(token)
    
    return render_template('index.html', user_info=user_info)

@app.route('/api/printers', methods=['GET'])
@require_auth
def get_printers():
    """Get all printers"""
    printers = printer_storage.load_printers()
    return jsonify(printers)

@app.route('/api/printers', methods=['POST'])
@require_auth
def add_printer():
    """Add printer endpoint - disabled (use configuration tab)"""
    return jsonify({
        'error': 'Adding printers is disabled. Please configure printers in the add-on configuration tab.',
        'message': 'Go to Settings → Add-ons → Printer Dashboard → Configuration to add printers.'
    }), 400

@app.route('/api/printers/<printer_id>', methods=['DELETE'])
@require_auth
def delete_printer(printer_id):
    """Delete printer endpoint - disabled (use configuration tab)"""
    return jsonify({
        'error': 'Deleting printers is disabled. Please configure printers in the add-on configuration tab.',
        'message': 'Go to Settings → Add-ons → Printer Dashboard → Configuration to manage printers.'
    }), 400

@app.route('/api/printers/<printer_id>', methods=['PUT'])
@require_auth
def update_printer(printer_id):
    """Update printer endpoint - disabled (use configuration tab)"""
    return jsonify({
        'error': 'Updating printers is disabled. Please configure printers in the add-on configuration tab.',
        'message': 'Go to Settings → Add-ons → Printer Dashboard → Configuration to manage printers.'
    }), 400

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'version': '1.0.0'})

@app.route('/api/debug')
@require_auth  
def debug_info():
    """Debug endpoint to show current configuration"""
    printers = printer_storage.load_printers()
    debug_data = {
        'printers_count': len(printers),
        'printers': printers,
        'proxy_paths': []
    }
    
    # Generate expected proxy paths
    for printer in printers:
        if printer.get('url', '').startswith('http'):
            slug = printer['name'].replace(' ', '_').lower()
            debug_data['proxy_paths'].append({
                'name': printer['name'],
                'original_url': printer['url'],
                'slug': slug,
                'proxy_path': f'/proxy/{slug}/',
                'upstream_name': f'{slug}_up'
            })
    
    return jsonify(debug_data)

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    logger.info("Starting Printer Dashboard Flask App...")
    app.run(host='0.0.0.0', port=5000, debug=False) 