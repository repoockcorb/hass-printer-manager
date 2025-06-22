#!/usr/bin/env python3

import os
import json
import logging
from flask import Flask, render_template, jsonify, request
import requests

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class PrinterStorage:
    def __init__(self):
        self.config_file = '/data/options.json'
        logger.info(f"PrinterStorage initialized with config file: {self.config_file}")
    
    def get_printers(self):
        """Load printers from Home Assistant add-on configuration"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    printers = config.get('printers', [])
                    logger.info(f"Loaded {len(printers)} printers from config")
                    for printer in printers:
                        logger.debug(f"Printer: {printer}")
                    return printers
            else:
                logger.warning(f"Config file {self.config_file} does not exist")
                return []
        except Exception as e:
            logger.error(f"Error loading printers: {e}")
            return []

# Initialize storage
storage = PrinterStorage()

@app.route('/')
def index():
    """Main dashboard page"""
    logger.info("Serving main dashboard page")
    return render_template('index.html')

@app.route('/api/printers')
def get_printers():
    """API endpoint to get all printers"""
    try:
        printers = storage.get_printers()
        logger.info(f"API: Returning {len(printers)} printers")
        
        # Convert URLs to proxy paths for remote access
        processed_printers = []
        for printer in printers:
            processed_printer = printer.copy()
            
            # Convert HTTP URLs to proxy paths
            if printer.get('url', '').startswith('http'):
                # Create slug from printer name
                slug = printer['name'].lower().replace(' ', '_')
                processed_printer['url'] = f"/proxy/{slug}/"
                logger.debug(f"Converted {printer['url']} to {processed_printer['url']}")
            
            processed_printers.append(processed_printer)
        
        return jsonify(processed_printers)
    except Exception as e:
        logger.error(f"Error in get_printers API: {e}")
        return jsonify([]), 500

@app.route('/api/printers', methods=['POST'])
def add_printer():
    """API endpoint to add a printer - disabled for config-based management"""
    return jsonify({
        'success': False, 
        'message': 'Adding printers via web interface is disabled. Please use the Configuration tab in Home Assistant to manage printers.'
    }), 400

@app.route('/api/printers/<int:index>', methods=['DELETE'])
def delete_printer(index):
    """API endpoint to delete a printer - disabled for config-based management"""
    return jsonify({
        'success': False, 
        'message': 'Removing printers via web interface is disabled. Please use the Configuration tab in Home Assistant to manage printers.'
    }), 400

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'printers_count': len(storage.get_printers())})

if __name__ == '__main__':
    logger.info("Starting Printer Dashboard Flask app...")
    app.run(host='127.0.0.1', port=5001, debug=True) 