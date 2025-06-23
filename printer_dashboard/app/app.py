#!/usr/bin/env python3

import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, Response
import requests
from requests.exceptions import RequestException, Timeout
import threading
import time

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static', static_url_path='/static')

class PrinterAPI:
    """Base class for printer API interactions"""
    
    def __init__(self, name, printer_type, url, api_key=None):
        self.name = name
        self.printer_type = printer_type.lower()  # 'klipper' or 'octoprint'
        self.url = url.rstrip('/')
        self.api_key = api_key
        self.last_update = None
        self.status_cache = {}
        
    def _make_request(self, endpoint, method='GET', data=None, timeout=5, allow_status=None):
        """Make HTTP request with proper headers
        allow_status: list of HTTP status codes that are accepted as non-error
        """
        if allow_status is None:
            allow_status = []
        try:
            headers = {'Content-Type': 'application/json'}
            
            if self.printer_type == 'octoprint' and self.api_key:
                headers['X-Api-Key'] = self.api_key
            elif self.printer_type == 'klipper' and self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'
                
            url = f"{self.url}/{endpoint.lstrip('/')}"
            
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method == 'POST':
                response = requests.post(url, headers=headers, json=data, timeout=timeout)
            else:
                raise ValueError(f"Unsupported method: {method}")
                
            if response.status_code in allow_status:
                return response.json() if response.text else None
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"Request failed for {self.name}: {e}")
            return None
    
    def get_status(self):
        """Get printer status - override in subclasses"""
        return {
            'name': self.name,
            'type': self.printer_type,
            'online': False,
            'state': 'offline',
            'error': 'Not implemented'
        }

class KlipperAPI(PrinterAPI):
    """Moonraker API for Klipper printers"""
    
    def get_status(self):
        """Get comprehensive printer status"""
        try:
            # Get printer status
            printer_info = self._make_request('printer/info')
            printer_objects = self._make_request('printer/objects/query?print_stats&toolhead&extruder&heater_bed&display_status&virtual_sdcard&webhooks')
            job_queue = self._make_request('server/job_queue/status')
            
            if not printer_objects:
                return {
                    'name': self.name,
                    'type': 'klipper',
                    'online': False,
                    'state': 'offline',
                    'error': 'Cannot connect to printer'
                }
            
            result = printer_objects.get('result', {})
            status_data = result.get('status', {}) if isinstance(result, dict) else {}
            print_stats = status_data.get('print_stats', {})
            toolhead = status_data.get('toolhead', {})
            extruder = status_data.get('extruder', {})
            heater_bed = status_data.get('heater_bed', {})
            display_status = status_data.get('display_status', {})
            virtual_sdcard = status_data.get('virtual_sdcard', {})
            webhooks = status_data.get('webhooks', {})
            
            def safe_round(value, digits=1):
                try:
                    return round(float(value), digits)
                except (TypeError, ValueError):
                    return 0
            
            # Calculate progress
            progress = 0
            if virtual_sdcard.get('progress') not in [None, '']:
                try:
                    progress = round(float(virtual_sdcard['progress']) * 100, 1)
                except (TypeError, ValueError):
                    progress = 0
            
            # Get print time
            print_duration = print_stats.get('print_duration', 0) or 0
            
            # Estimate remaining time
            remaining_time = 0
            if progress > 0 and progress < 100:
                remaining_time = (print_duration / (progress / 100)) - print_duration
            
            return {
                'name': self.name,
                'type': 'klipper',
                'online': True,
                'state': print_stats.get('state', 'ready'),
                'progress': progress,
                'file': print_stats.get('filename', ''),
                'print_time': self._format_time(print_duration),
                'remaining_time': self._format_time(remaining_time),
                'extruder_temp': {
                    'actual': round(extruder.get('temperature', 0), 1),
                    'target': round(extruder.get('target', 0), 1)
                },
                'bed_temp': {
                    'actual': round(heater_bed.get('temperature', 0), 1),
                    'target': round(heater_bed.get('target', 0), 1)
                },
                'position': {
                    'x': round(toolhead.get('position', [0, 0, 0, 0])[0], 2),
                    'y': round(toolhead.get('position', [0, 0, 0, 0])[1], 2),
                    'z': round(toolhead.get('position', [0, 0, 0, 0])[2], 2)
                },
                'message': display_status.get('message', ''),
                'klippy_state': webhooks.get('state', 'unknown'),
                'queue_status': job_queue.get('result', {}).get('queued_jobs', []) if job_queue else []
            }
            
        except Exception as e:
            logger.error(f"Error getting Klipper status for {self.name}: {e}")
            return {
                'name': self.name,
                'type': 'klipper',
                'online': False,
                'state': 'error',
                'error': str(e)
            }
    
    def _format_time(self, seconds):
        """Format seconds into HH:MM:SS"""
        if seconds <= 0:
            return "00:00:00"
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    def pause_print(self):
        """Pause current print"""
        return self._make_request('printer/print/pause', method='POST')
    
    def resume_print(self):
        """Resume current print"""
        return self._make_request('printer/print/resume', method='POST')
    
    def cancel_print(self):
        """Cancel current print"""
        return self._make_request('printer/print/cancel', method='POST')
    
    def home_printer(self, axes=None):
        """Home printer axes. If axes is None, homes all axes"""
        if axes is None:
            axes = ['X', 'Y', 'Z']
        elif isinstance(axes, str):
            axes = [axes.upper()]
        
        gcode_commands = []
        for axis in axes:
            if axis.upper() in ['X', 'Y', 'Z']:
                gcode_commands.append(f"G28 {axis.upper()}")
        
        if gcode_commands:
            return self._make_request('printer/gcode/script', method='POST', 
                                    data={'script': '\n'.join(gcode_commands)})
        return None
    
    def jog_printer(self, axis, distance):
        """Jog printer in specified axis by distance (in mm)"""
        axis = axis.upper()
        if axis not in ['X', 'Y', 'Z']:
            return None
            
        try:
            distance = float(distance)
        except (ValueError, TypeError):
            return None
        
        # Use relative positioning
        gcode = f"G91\nG1 {axis}{distance} F3000\nG90"
        return self._make_request('printer/gcode/script', method='POST', 
                                data={'script': gcode})

class OctoPrintAPI(PrinterAPI):
    """OctoPrint API for OctoPrint printers"""
    
    def get_status(self):
        """Get comprehensive printer status"""
        try:
            # Get printer status
            printer_status = self._make_request('api/printer', allow_status=[409])
            job_status = self._make_request('api/job')
            
            if not printer_status or not job_status:
                return {
                    'name': self.name,
                    'type': 'octoprint',
                    'online': False,
                    'state': 'offline',
                    'error': 'Cannot connect to printer'
                }
            
            # Normalize missing data
            if printer_status is None:
                printer_status = {}
            if job_status is None:
                job_status = {}
            
            # Parse temperature data safely
            temps = printer_status.get('temperature', {}) if isinstance(printer_status, dict) else {}
            tool0 = temps.get('tool0', {})
            bed = temps.get('bed', {})
            
            def safe_round(value, digits=1):
                try:
                    return round(float(value), digits)
                except (TypeError, ValueError):
                    return 0
            
            # Parse job data
            job = job_status.get('job', {}) if isinstance(job_status, dict) else {}
            progress = job_status.get('progress', {}) if isinstance(job_status, dict) else {}
            state = printer_status.get('state', {}) if isinstance(printer_status, dict) else {}
            
            # Calculate remaining time
            remaining = progress.get('printTimeLeft') or 0
            remaining_formatted = self._format_time(remaining) if remaining else "Unknown"
            
            return {
                'name': self.name,
                'type': 'octoprint',
                'online': True,
                'state': state.get('text', 'unknown').lower() if isinstance(state, dict) else 'unknown',
                'progress': safe_round(progress.get('completion', 0)),
                'file': job.get('file', {}).get('name', '') if isinstance(job, dict) else '',
                'print_time': self._format_time(progress.get('printTime', 0) or 0),
                'remaining_time': remaining_formatted,
                'extruder_temp': {
                    'actual': safe_round(tool0.get('actual', 0)),
                    'target': safe_round(tool0.get('target', 0))
                },
                'bed_temp': {
                    'actual': safe_round(bed.get('actual', 0)),
                    'target': safe_round(bed.get('target', 0))
                },
                'position': state.get('position', {'x': 0, 'y': 0, 'z': 0}) if isinstance(state, dict) else {'x':0,'y':0,'z':0},
                'message': state.get('text', '') if isinstance(state, dict) else '',
                'ready': state.get('flags', {}).get('ready', False) if isinstance(state, dict) else False
            }
            
        except Exception as e:
            logger.error(f"Error getting OctoPrint status for {self.name}: {e}")
            return {
                'name': self.name,
                'type': 'octoprint',
                'online': False,
                'state': 'error',
                'error': str(e)
            }
    
    def _format_time(self, seconds):
        """Format seconds into HH:MM:SS"""
        if not seconds or seconds <= 0:
            return "00:00:00"
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    def pause_print(self):
        """Pause current print"""
        return self._make_request('api/job', method='POST', data={'command': 'pause', 'action': 'pause'})
    
    def resume_print(self):
        """Resume current print"""
        return self._make_request('api/job', method='POST', data={'command': 'pause', 'action': 'resume'})
    
    def cancel_print(self):
        """Cancel current print"""
        return self._make_request('api/job', method='POST', data={'command': 'cancel'})
    
    def home_printer(self, axes=None):
        """Home printer axes. If axes is None, homes all axes"""
        if axes is None:
            axes = ['x', 'y', 'z']
        elif isinstance(axes, str):
            axes = [axes.lower()]
        
        # OctoPrint home command format
        command_data = {'command': 'home', 'axes': axes}
        return self._make_request('api/printer/printhead', method='POST', data=command_data)
    
    def jog_printer(self, axis, distance):
        """Jog printer in specified axis by distance (in mm)"""
        axis = axis.lower()
        if axis not in ['x', 'y', 'z']:
            return None
            
        try:
            distance = float(distance)
        except (ValueError, TypeError):
            return None
        
        # OctoPrint jog command format
        command_data = {
            'command': 'jog',
            axis: distance
        }
        return self._make_request('api/printer/printhead', method='POST', data=command_data)

class PrinterManager:
    """Manages multiple printer connections and status updates"""
    
    def __init__(self):
        self.printers = {}
        self.status_cache = {}
        self.last_update = {}
        self.update_interval = 5  # seconds
        self.running = False
        self.update_thread = None
        
    def add_printer(self, config):
        """Add a printer from configuration"""
        name = config.get('name')
        printer_type = config.get('type', 'klipper').lower()
        url = config.get('url')
        api_key = config.get('api_key')
        
        if not name or not url:
            logger.error(f"Invalid printer config: {config}")
            return False
            
        try:
            if printer_type in ['klipper', 'moonraker']:
                printer = KlipperAPI(name, 'klipper', url, api_key)
            elif printer_type == 'octoprint':
                printer = OctoPrintAPI(name, 'octoprint', url, api_key)
            else:
                logger.error(f"Unsupported printer type: {printer_type}")
                return False
                
            self.printers[name] = printer
            logger.info(f"Added printer: {name} ({printer_type})")
            return True
            
        except Exception as e:
            logger.error(f"Error adding printer {name}: {e}")
            return False
    
    def get_all_status(self):
        """Get status for all printers"""
        results = {}
        for name, printer in self.printers.items():
            try:
                status = printer.get_status()
                results[name] = status
                self.status_cache[name] = status
                self.last_update[name] = datetime.now()
            except Exception as e:
                logger.error(f"Error getting status for {name}: {e}")
                results[name] = {
                    'name': name,
                    'online': False,
                    'state': 'error',
                    'error': str(e)
                }
        return results
    
    def get_printer_status(self, name):
        """Get status for a specific printer"""
        if name in self.printers:
            return self.printers[name].get_status()
        return None
    
    def control_printer(self, name, action, **kwargs):
        """Control a specific printer (pause/resume/cancel/home/jog)"""
        if name not in self.printers:
            return {'success': False, 'error': 'Printer not found'}
            
        printer = self.printers[name]
        try:
            if action == 'pause':
                result = printer.pause_print()
            elif action == 'resume':
                result = printer.resume_print()
            elif action == 'cancel':
                result = printer.cancel_print()
            elif action == 'home':
                axes = kwargs.get('axes')
                result = printer.home_printer(axes)
            elif action == 'jog':
                axis = kwargs.get('axis')
                distance = kwargs.get('distance')
                if not axis or distance is None:
                    return {'success': False, 'error': 'Missing axis or distance for jog command'}
                result = printer.jog_printer(axis, distance)
            else:
                return {'success': False, 'error': 'Invalid action'}
                
            return {'success': True, 'result': result}
            
        except Exception as e:
            logger.error(f"Error controlling printer {name}: {e}")
            return {'success': False, 'error': str(e)}

# Initialize global printer manager
printer_manager = PrinterManager()

class PrinterStorage:
    def __init__(self):
        self.config_file = '/data/options.json'
        logger.info(f"PrinterStorage initialized with config file: {self.config_file}")
        self._load_printers()
    
    def _load_printers(self):
        """Load and initialize printers from configuration"""
        printers_config = self.get_printers()
        printer_manager.printers.clear()
        
        for printer_config in printers_config:
            printer_manager.add_printer(printer_config)
    
    def get_printers(self):
        """Load printers from Home Assistant add-on configuration"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    printers = config.get('printers', [])
                    logger.info(f"Loaded {len(printers)} printers from config")
                    return printers
            else:
                logger.warning(f"Config file {self.config_file} does not exist")
                return []
        except Exception as e:
            logger.error(f"Error loading printers: {e}")
            return []

# Initialize storage
storage = PrinterStorage()

class HomeAssistantAPI:
    """Home Assistant API integration for camera feeds"""
    
    def __init__(self, url=None, token=None):
        # For internal API calls, use supervisor URL
        self.internal_url = (url or os.environ.get('SUPERVISOR_URL', 'http://supervisor/core')).rstrip('/')
        self.token = token or os.environ.get('SUPERVISOR_TOKEN', '')
        
        # For camera URLs that browsers need to access, we need the external HA URL
        # Try to determine the external URL from the request context
        self.external_url = None
        
        logger.info(f"HomeAssistantAPI initialized with internal URL: {self.internal_url}")
        logger.info(f"Supervisor token available: {'Yes' if self.token else 'No'}")
        if self.token:
            logger.info(f"Supervisor token (first 10 chars): {self.token[:10]}...")
        else:
            logger.warning("No supervisor token available - camera access may fail")
    
    def _get_external_ha_url(self, base_url=None):
        """Get the external Home Assistant URL that browsers can access"""
        if base_url:
            # Use the provided base URL from the frontend
            # But force HTTPS for Nabu Casa cloud URLs
            if '.ui.nabu.casa' in base_url and base_url.startswith('http://'):
                base_url = base_url.replace('http://', 'https://')
                logger.info(f"Forced HTTPS for Nabu Casa URL: {base_url}")
            
            logger.info(f"Using provided base URL: {base_url}")
            return base_url.rstrip('/')
            
        try:
            # Try to get from Flask request context
            from flask import request
            if request:
                # Extract the base URL from the current request
                host = request.host
                scheme = request.scheme
                
                # Force HTTPS for Nabu Casa domains
                if '.ui.nabu.casa' in host:
                    scheme = 'https'
                    logger.info(f"Forced HTTPS for Nabu Casa domain: {host}")
                
                external_url = f"{scheme}://{host}"
                logger.info(f"Detected external HA URL from request: {external_url}")
                return external_url
        except Exception as e:
            logger.warning(f"Could not detect external HA URL from request: {e}")
        
        # Fallback: assume standard HA port
        return "http://homeassistant.local:8123"
    
    def _make_request(self, endpoint, method='GET', timeout=10):
        """Make HTTP request to Home Assistant API using internal URL"""
        try:
            headers = {
                'Authorization': f'Bearer {self.token}',
                'Content-Type': 'application/json',
                'Cache-Control': 'no-cache'
            }
            
            url = f"{self.internal_url}/api/{endpoint.lstrip('/')}"
            
            # Add cache-busting parameter for state requests
            if 'states/' in endpoint:
                url += f"?_={int(time.time() * 1000)}"
            
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=timeout)
            else:
                raise ValueError(f"Unsupported method: {method}")
                
            response.raise_for_status()
            return response.json() if response.text else None
            
        except Exception as e:
            logger.error(f"Home Assistant request failed: {e}")
            return None
    
    def get_camera_snapshot_url(self, entity_id, base_url=None):
        """Get camera snapshot URL with proper authSig JWT tokens"""
        try:
            logger.info(f"Getting camera snapshot for entity: {entity_id}")
            if base_url:
                logger.info(f"Using dynamic base URL from frontend: {base_url}")
            else:
                logger.info("No base URL provided, will auto-detect from request context")
            
            # First, get the entity_picture which contains the properly signed URL
            entity_state = self._make_request(f'states/{entity_id}')
            if not entity_state:
                logger.error(f"No entity state returned for {entity_id}")
                return None
            
            entity_picture = entity_state.get('attributes', {}).get('entity_picture', '')
            if not entity_picture:
                logger.error(f"No entity_picture found for {entity_id}")
                return None
            
            logger.info(f"Entity picture URL: {entity_picture}")
            
            # The entity_picture contains the signed URL with authSig token
            # Convert it to external URL that browsers can access
            external_url = self._get_external_ha_url(base_url)
            logger.info(f"Using external HA URL: {external_url}")
            
            # The entity_picture is a relative URL like:
            # /api/camera_proxy/camera.prusa_mk3s_mmu3?token=abc123&authSig=JWT_TOKEN
            if entity_picture.startswith('/'):
                full_camera_url = f"{external_url}{entity_picture}"
            else:
                # If it's already a full URL, replace the base
                full_camera_url = entity_picture.replace(self.internal_url, external_url)
            
            logger.info(f"Final camera URL with authSig: {full_camera_url}")
            return full_camera_url
                
        except Exception as e:
            logger.error(f"Error getting camera snapshot URL for {entity_id}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None
    
    def get_camera_stream_url(self, entity_id, base_url=None):
        """Get camera stream URL for entity"""
        try:
            # For streams, we'll use the snapshot URL approach since streams 
            # use the same token mechanism
            snapshot_url = self.get_camera_snapshot_url(entity_id, base_url)
            if snapshot_url and 'camera_proxy/' in snapshot_url:
                # Convert snapshot to stream URL
                stream_url = snapshot_url.replace('/api/camera_proxy/', '/api/camera_proxy_stream/')
                logger.info(f"Camera stream URL for {entity_id}: {stream_url}")
                return stream_url
                
            return None
            
        except Exception as e:
            logger.error(f"Error getting camera stream URL for {entity_id}: {e}")
            return None

# Initialize Home Assistant API
def get_ha_config():
    """Get Home Assistant configuration from add-on config"""
    try:
        if os.path.exists('/data/options.json'):
            with open('/data/options.json', 'r') as f:
                config = json.load(f)
                ha_config = config.get('home_assistant', {})
                return ha_config.get('url'), ha_config.get('token')
    except Exception as e:
        logger.error(f"Error loading HA config: {e}")
    return None, None

ha_url, ha_token = get_ha_config()
ha_api = HomeAssistantAPI(ha_url, ha_token)

@app.route('/')
def index():
    """Main dashboard page"""
    logger.info("Serving main dashboard page")
    return render_template('index.html')

@app.route('/api/printers')
def get_printers():
    """API endpoint to get all printer configurations"""
    try:
        logger.info("API: get_printers called")
        logger.info(f"Request URL: {request.url}")
        logger.info(f"Request host: {request.host}")
        logger.info(f"Request headers: {dict(request.headers)}")
        
        printers = storage.get_printers()
        logger.info(f"API: Returning {len(printers)} printer configs")
        logger.info(f"Printer configs: {printers}")
        
        return jsonify(printers)
    except Exception as e:
        logger.error(f"Error in get_printers API: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify([]), 500

@app.route('/api/status')
def get_all_status():
    """API endpoint to get status for all printers"""
    try:
        status = printer_manager.get_all_status()
        logger.debug(f"API: Returning status for {len(status)} printers")
        return jsonify(status)
    except Exception as e:
        logger.error(f"Error in get_all_status API: {e}")
        return jsonify({}), 500

@app.route('/api/status/<printer_name>')
def get_printer_status(printer_name):
    """API endpoint to get status for a specific printer"""
    try:
        status = printer_manager.get_printer_status(printer_name)
        if status:
            return jsonify(status)
        else:
            return jsonify({'error': 'Printer not found'}), 404
    except Exception as e:
        logger.error(f"Error getting status for {printer_name}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/control/<printer_name>/<action>', methods=['POST'])
def control_printer(printer_name, action):
    """API endpoint to control a printer"""
    try:
        # Get additional parameters from request JSON
        data = request.get_json() or {}
        
        # Extract parameters for different actions
        kwargs = {}
        if action == 'home':
            kwargs['axes'] = data.get('axes')  # Can be None for all axes, or specific axes like ['X', 'Y']
        elif action == 'jog':
            kwargs['axis'] = data.get('axis')  # Required: 'X', 'Y', or 'Z'
            kwargs['distance'] = data.get('distance')  # Required: distance in mm
        
        result = printer_manager.control_printer(printer_name, action, **kwargs)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error controlling {printer_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    logger.info("Health check called")
    logger.info(f"Request URL: {request.url}")
    logger.info(f"Request host: {request.host}")
    logger.info(f"Number of printers: {len(printer_manager.printers)}")
    
    health_data = {
        'status': 'healthy', 
        'printers_count': len(printer_manager.printers),
        'last_update': max(printer_manager.last_update.values()).isoformat() if printer_manager.last_update else None,
        'request_info': {
            'url': request.url,
            'host': request.host,
            'method': request.method,
            'user_agent': request.headers.get('User-Agent', '')
        }
    }
    
    logger.info(f"Health check response: {health_data}")
    return jsonify(health_data)

@app.route('/debug/static')
def debug_static():
    """Debug endpoint to check static file configuration"""
    import os
    static_path = app.static_folder
    static_files = []
    if os.path.exists(static_path):
        static_files = os.listdir(static_path)
    
    return jsonify({
        'static_folder': app.static_folder,
        'static_url_path': app.static_url_path,
        'static_files': static_files,
        'working_directory': os.getcwd(),
        'static_path_exists': os.path.exists(static_path)
    })

@app.route('/api/ha-info')
def get_ha_info():
    """API endpoint to get Home Assistant connection information for dynamic URL detection"""
    try:
        # Get the request context information
        request_info = {
            'request_host': request.host,
            'request_url': request.url,
            'request_base_url': request.base_url,
            'request_origin': request.headers.get('Origin', ''),
            'user_agent': request.headers.get('User-Agent', ''),
            'x_forwarded_for': request.headers.get('X-Forwarded-For', ''),
            'x_forwarded_proto': request.headers.get('X-Forwarded-Proto', ''),
            'x_forwarded_host': request.headers.get('X-Forwarded-Host', ''),
        }
        
        # Try to get HA config
        ha_config = {}
        try:
            ha_config['internal_url'] = ha_api.internal_url
            # Try to detect external URL from request
            external_url = ha_api._get_external_ha_url()
            ha_config['detected_external_url'] = external_url
        except Exception as e:
            logger.warning(f"Could not get HA config info: {e}")
        
        # Build suggested URLs, ensuring HTTPS for Nabu Casa
        suggested_urls = []
        
        # Current request base
        current_base = f"{request.scheme}://{request.host}"
        if '.ui.nabu.casa' in request.host and request.scheme == 'http':
            current_base = f"https://{request.host}"
        suggested_urls.append(current_base)
        
        # Origin header
        origin = request.headers.get('Origin', '')
        if origin:
            if '.ui.nabu.casa' in origin and origin.startswith('http://'):
                origin = origin.replace('http://', 'https://')
            suggested_urls.append(origin)
        
        # Detected HA URL
        detected_url = ha_config.get('detected_external_url', '')
        if detected_url:
            suggested_urls.append(detected_url)
        
        # Remove duplicates and empty strings
        suggested_urls = list(dict.fromkeys([url for url in suggested_urls if url]))
        
        return jsonify({
            'request_info': request_info,
            'ha_config': ha_config,
            'suggested_base_urls': suggested_urls
        })
        
    except Exception as e:
        logger.error(f"Error in ha-info endpoint: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/debug/config')
def debug_config():
    """Debug endpoint to check printer configuration"""
    try:
        printers = storage.get_printers()
        debug_info = {
            'printer_count': len(printers),
            'printers': []
        }
        
        for printer in printers:
            printer_info = {
                'name': printer.get('name'),
                'type': printer.get('type'),
                'has_camera_entity': 'camera_entity' in printer,
                'camera_entity': printer.get('camera_entity', 'Not configured')
            }
            debug_info['printers'].append(printer_info)
        
        return jsonify(debug_info)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/camera/<printer_name>/stream')
def get_camera_stream(printer_name):
    """API endpoint to get camera stream URL for a printer"""
    try:
        # Get base_url from query parameters
        base_url = request.args.get('base_url')
        
        printers = storage.get_printers()
        printer_config = next((p for p in printers if p['name'] == printer_name), None)
        
        if not printer_config:
            return jsonify({'error': 'Printer not found'}), 404
        
        camera_entity = printer_config.get('camera_entity')
        if not camera_entity:
            return jsonify({'error': 'No camera entity configured for this printer'}), 404
        
        stream_url = ha_api.get_camera_stream_url(camera_entity, base_url)
        if not stream_url:
            return jsonify({'error': 'Camera stream not available'}), 404
        
        return jsonify({'stream_url': stream_url})
        
    except Exception as e:
        logger.error(f"Error getting camera stream for {printer_name}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/camera/<printer_name>/snapshot')
def get_camera_snapshot(printer_name):
    """API endpoint to get camera snapshot URL for a printer"""
    try:
        logger.info(f"Camera snapshot request for printer: {printer_name}")
        
        # Get base_url from query parameters
        base_url = request.args.get('base_url')
        logger.info(f"Using base_url from request: {base_url}")
        
        printers = storage.get_printers()
        printer_config = next((p for p in printers if p['name'] == printer_name), None)
        
        if not printer_config:
            logger.error(f"Printer not found: {printer_name}")
            logger.info(f"Available printers: {[p.get('name') for p in printers]}")
            return jsonify({'error': 'Printer not found'}), 404
        
        camera_entity = printer_config.get('camera_entity')
        if not camera_entity:
            logger.error(f"No camera entity configured for printer: {printer_name}")
            logger.info(f"Printer config: {printer_config}")
            return jsonify({'error': 'No camera entity configured for this printer'}), 404
        
        logger.info(f"Using camera entity: {camera_entity}")
        
        snapshot_url = ha_api.get_camera_snapshot_url(camera_entity, base_url)
        if not snapshot_url:
            logger.error(f"Failed to get snapshot URL for camera entity: {camera_entity}")
            return jsonify({'error': 'Camera snapshot not available'}), 404
        
        logger.info(f"Returning snapshot URL: {snapshot_url}")
        return jsonify({'snapshot_url': snapshot_url})
        
    except Exception as e:
        logger.error(f"Error getting camera snapshot for {printer_name}: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    logger.info("Starting Print Farm Dashboard Flask app...")
    app.run(host='127.0.0.1', port=5001, debug=False) 