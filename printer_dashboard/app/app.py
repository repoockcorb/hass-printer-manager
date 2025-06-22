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
    """Handle printer data storage using Home Assistant storage"""
    
    def __init__(self):
        self.storage_path = '/data/printers.json'

    def load_printers(self):
        """Load printers from storage"""
        try:
            if os.path.exists(self.storage_path):
                with open(self.storage_path, 'r') as f:
                    return json.load(f)
            return []
        except Exception as e:
            logger.error(f"Error loading printers: {e}")
            return []

    def save_printers(self, printers):
        """Save printers to storage"""
        try:
            os.makedirs('/data', exist_ok=True)
            with open(self.storage_path, 'w') as f:
                json.dump(printers, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving printers: {e}")
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
    """Add a new printer"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'type', 'url']
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Load existing printers
        printers = printer_storage.load_printers()
        
        # Check for duplicate names
        if any(printer['name'] == data['name'] for printer in printers):
            return jsonify({'error': 'Printer name already exists'}), 400
        
        # Create new printer
        printer = {
            'id': str(len(printers) + 1),
            'name': data['name'],
            'type': data['type'],
            'url': data['url'],
            'created_at': data.get('created_at', '')
        }
        
        printers.append(printer)
        
        if printer_storage.save_printers(printers):
            return jsonify(printer), 201
        else:
            return jsonify({'error': 'Failed to save printer'}), 500
            
    except Exception as e:
        logger.error(f"Error adding printer: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/printers/<printer_id>', methods=['DELETE'])
@require_auth
def delete_printer(printer_id):
    """Delete a printer"""
    try:
        printers = printer_storage.load_printers()
        printers = [p for p in printers if p['id'] != printer_id]
        
        if printer_storage.save_printers(printers):
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to delete printer'}), 500
            
    except Exception as e:
        logger.error(f"Error deleting printer: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/printers/<printer_id>', methods=['PUT'])
@require_auth
def update_printer(printer_id):
    """Update a printer"""
    try:
        data = request.get_json()
        printers = printer_storage.load_printers()
        
        for printer in printers:
            if printer['id'] == printer_id:
                printer.update(data)
                break
        else:
            return jsonify({'error': 'Printer not found'}), 404
        
        if printer_storage.save_printers(printers):
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to update printer'}), 500
            
    except Exception as e:
        logger.error(f"Error updating printer: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'version': '1.0.0'})

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    logger.info("Starting Printer Dashboard Flask App...")
    app.run(host='0.0.0.0', port=5000, debug=False) 