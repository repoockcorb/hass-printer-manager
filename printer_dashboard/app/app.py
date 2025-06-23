#!/usr/bin/env python3

import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, Response, stream_with_context
import requests
from requests.exceptions import RequestException, Timeout
import threading
import time
import urllib3
import base64
import io
from flask_socketio import SocketIO, emit
import uuid
import json as json_lib

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config['SECRET_KEY'] = 'your-secret-key-here'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', logger=True, engineio_logger=False)

# Disable insecure request warnings globally (useful when upstream camera has self-signed certificate)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Store active camera streams
active_streams = {}
stream_threads = {}

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
    
    def control_printer(self, name, action):
        """Control a specific printer (pause/resume/cancel)"""
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

@app.route('/')
def index():
    """Main dashboard page"""
    logger.info("Serving main dashboard page")
    return render_template('index.html')

@app.route('/api/printers')
def get_printers():
    """API endpoint to get all printer configurations"""
    try:
        printers = storage.get_printers()
        logger.info(f"API: Returning {len(printers)} printer configs")
        return jsonify(printers)
    except Exception as e:
        logger.error(f"Error in get_printers API: {e}")
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
        result = printer_manager.control_printer(printer_name, action)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error controlling {printer_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy', 
        'printers_count': len(printer_manager.printers),
        'last_update': max(printer_manager.last_update.values()).isoformat() if printer_manager.last_update else None
    })

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

@app.route('/camera/<printer_name>')
def proxy_camera(printer_name):
    """Reverse-proxy the MJPEG camera stream to avoid mixed-content issues"""
    # Check if this is a snapshot request instead of a stream
    is_snapshot_request = request.args.get('snapshot') is not None
    
    printer_cfg = next((p for p in storage.get_printers() if p.get('name').lower().replace(' ','_')==printer_name.lower().replace(' ','_')), None)
    if not printer_cfg:
        return jsonify({'error':'printer not found'}),404
    cam_url = printer_cfg.get('camera_url')
    if not cam_url:
        return jsonify({'error':'camera_url not configured'}),404
    
    # If snapshot is requested but we have a dedicated snapshot_url, use that instead
    if is_snapshot_request and printer_cfg.get('snapshot_url'):
        return proxy_snapshot(printer_name)
    
    try:
        # Accept self-signed certificates by skipping verification so the proxy still works over HTTPS.
        headers = {}
        if is_snapshot_request:
            # For snapshot requests, we want a single JPEG frame
            headers['Accept'] = 'image/jpeg'
            
        upstream = requests.get(cam_url, stream=True, timeout=10, verify=False)
        upstream.raise_for_status()
    except Exception as e:
        logger.error(f"Camera proxy error for {printer_name}: {e}")
        return jsonify({'error': str(e)}), 502

    # Preserve upstream Content-Type when it already specifies a boundary.
    content_type_header = upstream.headers.get('Content-Type', '') or ''

    # Peek at the first chunk so we can sniff the boundary string if missing.
    pre_buffer = b''
    try:
        pre_buffer = next(upstream.iter_content(chunk_size=2048))
    except StopIteration:
        pass  # Empty stream – we'll handle below

    boundary_param = None

    if 'multipart' in content_type_header.lower() and 'boundary=' in content_type_header.lower():
        # Use upstream header as-is when boundary param present.
        content_type = content_type_header
    else:
        # Try to detect boundary from the first chunk (it usually starts with --BOUNDARY) .
        import re
        m = re.match(rb'--([^\r\n; ]+)', pre_buffer)
        if m:
            boundary_param = m.group(1).decode('utf-8', 'ignore')
        else:
            boundary_param = 'frame'

        # Ensure there is a space before boundary per RFC.
        content_type = f'multipart/x-mixed-replace; boundary={boundary_param}'

    response_headers = {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no',
        'Content-Encoding': 'identity',
        # Allow embedding inside Home Assistant mobile (WKWebView) via relaxed CORS
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': '*'
    }
    
    def generate():
        try:
            # Yield the pre-buffered bytes first (if any) so no data is lost.
            if pre_buffer:
                yield pre_buffer
            # Stream the remaining content
            for chunk in upstream.iter_content(chunk_size=4096):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    # Handle snapshot requests differently
    if is_snapshot_request:
        # For snapshot mode, we return the first JPEG frame we can extract
        try:
            chunk_data = b''
            for chunk in upstream.iter_content(chunk_size=4096):
                chunk_data += chunk
                # Look for JPEG start and end markers
                start_idx = chunk_data.find(b'\xff\xd8')  # JPEG start
                end_idx = chunk_data.find(b'\xff\xd9')    # JPEG end
                
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    # Extract the JPEG frame
                    jpeg_data = chunk_data[start_idx:end_idx+2]
                    return Response(
                        jpeg_data,
                        content_type='image/jpeg',
                        headers={
                            'Cache-Control': 'no-cache, no-store, must-revalidate',
                            'Pragma': 'no-cache',
                            'Expires': '0',
                            'Access-Control-Allow-Origin': '*',
                            'Access-Control-Allow-Headers': '*'
                        }
                    )
                    
                # Prevent excessive buffering
                if len(chunk_data) > 1024*1024:  # 1MB limit
                    break
                    
        except Exception as e:
            logger.error(f"Error extracting snapshot from stream: {e}")
        finally:
            upstream.close()
            
        # If we can't extract a frame, return an error
        return jsonify({'error': 'Could not extract snapshot from stream'}), 502

    return Response(
        stream_with_context(generate()),
        content_type=content_type,
        headers=response_headers,
        direct_passthrough=True
    )

@app.route('/snapshot/<printer_name>')
def proxy_snapshot(printer_name):
    """Proxy single snapshot image to avoid mixed-content"""
    cfg = next((p for p in storage.get_printers() if p.get('name').lower().replace(' ','_')==printer_name.lower().replace(' ','_')), None)
    if not cfg or not cfg.get('snapshot_url'):
        return jsonify({'error':'snapshot_url not configured'}),404
    try:
        up = requests.get(cfg['snapshot_url'], timeout=10, verify=False)
        up.raise_for_status()
    except Exception as exc:
        logger.error(f"Snapshot proxy error for {printer_name}: {exc}")
        return jsonify({'error':str(exc)}),502
    return Response(up.content,
                    content_type=up.headers.get('Content-Type','image/jpeg'),
                    headers={
                        'Cache-Control':'no-cache, no-store, must-revalidate',
                        'Pragma':'no-cache',
                        'Expires':'0',
                        'Access-Control-Allow-Origin':'*',
                        'Access-Control-Allow-Headers':'*'
                    })

@app.route('/camera-sse/<printer_name>')
def camera_sse_stream(printer_name):
    """Server-Sent Events stream for camera frames as base64 data"""
    printer_cfg = next((p for p in storage.get_printers() if p.get('name').lower().replace(' ','_')==printer_name.lower().replace(' ','_')), None)
    if not printer_cfg:
        return jsonify({'error':'printer not found'}), 404
        
    cam_url = printer_cfg.get('camera_url')
    snapshot_url = printer_cfg.get('snapshot_url')
    
    if not cam_url and not snapshot_url:
        return jsonify({'error':'no camera configured'}), 404
    
    def generate_frames():
        """Generate base64-encoded frames for SSE"""
        while True:
            try:
                frame_data = None
                
                if snapshot_url:
                    # Use snapshot URL if available
                    response = requests.get(snapshot_url, timeout=5, verify=False)
                    if response.status_code == 200:
                        frame_data = response.content
                else:
                    # Extract frame from MJPEG stream
                    response = requests.get(cam_url, stream=True, timeout=5, verify=False)
                    if response.status_code == 200:
                        chunk_data = b''
                        for chunk in response.iter_content(chunk_size=4096):
                            chunk_data += chunk
                            # Look for JPEG markers
                            start_idx = chunk_data.find(b'\xff\xd8')
                            end_idx = chunk_data.find(b'\xff\xd9')
                            
                            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                                frame_data = chunk_data[start_idx:end_idx+2]
                                break
                                
                            if len(chunk_data) > 1024*1024:  # 1MB limit
                                break
                        response.close()
                
                if frame_data:
                    # Convert to base64
                    base64_frame = base64.b64encode(frame_data).decode('utf-8')
                    yield f"data: data:image/jpeg;base64,{base64_frame}\n\n"
                else:
                    yield f"data: error\n\n"
                    
            except Exception as e:
                logger.error(f"SSE camera error: {e}")
                yield f"data: error\n\n"
                
            time.sleep(0.5)  # ~2 FPS to avoid overwhelming the client
    
    return Response(
        generate_frames(),
        content_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': '*'
        }
    )

@app.route('/camera-canvas/<printer_name>')
def camera_canvas_data(printer_name):
    """REST endpoint that returns a single base64 frame for canvas rendering"""
    printer_cfg = next((p for p in storage.get_printers() if p.get('name').lower().replace(' ','_')==printer_name.lower().replace(' ','_')), None)
    if not printer_cfg:
        return jsonify({'error':'printer not found'}), 404
        
    cam_url = printer_cfg.get('camera_url')
    snapshot_url = printer_cfg.get('snapshot_url')
    
    if not cam_url and not snapshot_url:
        return jsonify({'error':'no camera configured'}), 404
    
    try:
        frame_data = None
        
        if snapshot_url:
            response = requests.get(snapshot_url, timeout=5, verify=False)
            if response.status_code == 200:
                frame_data = response.content
        else:
            # Extract single frame from MJPEG
            response = requests.get(cam_url, stream=True, timeout=5, verify=False)
            if response.status_code == 200:
                chunk_data = b''
                for chunk in response.iter_content(chunk_size=4096):
                    chunk_data += chunk
                    start_idx = chunk_data.find(b'\xff\xd8')
                    end_idx = chunk_data.find(b'\xff\xd9')
                    
                    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                        frame_data = chunk_data[start_idx:end_idx+2]
                        break
                        
                    if len(chunk_data) > 1024*1024:
                        break
                response.close()
        
        if frame_data:
            base64_frame = base64.b64encode(frame_data).decode('utf-8')
            return jsonify({
                'success': True,
                'data': f"data:image/jpeg;base64,{base64_frame}",
                'timestamp': time.time()
            })
        else:
            return jsonify({'success': False, 'error': 'No frame data'}), 502
            
    except Exception as e:
        logger.error(f"Canvas camera error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 502

# WebRTC Signaling Server
@socketio.on('join_camera')
def handle_join_camera(data):
    """Handle client joining a camera stream"""
    printer_name = data.get('printer_name')
    client_id = data.get('client_id', str(uuid.uuid4()))
    
    logger.info(f"Client {client_id} joining camera stream for {printer_name}")
    
    # Store client info
    if printer_name not in active_streams:
        active_streams[printer_name] = {}
    active_streams[printer_name][client_id] = request.sid
    
    # Start camera stream thread if not already running
    if printer_name not in stream_threads:
        thread = threading.Thread(target=camera_stream_worker, args=(printer_name,))
        thread.daemon = True
        thread.start()
        stream_threads[printer_name] = thread
    
    emit('camera_joined', {'client_id': client_id, 'printer_name': printer_name})

@socketio.on('leave_camera')
def handle_leave_camera(data):
    """Handle client leaving a camera stream"""
    printer_name = data.get('printer_name')
    client_id = data.get('client_id')
    
    logger.info(f"Client {client_id} leaving camera stream for {printer_name}")
    
    # Remove client
    if printer_name in active_streams and client_id in active_streams[printer_name]:
        del active_streams[printer_name][client_id]
        
        # If no more clients, stop the stream
        if not active_streams[printer_name]:
            del active_streams[printer_name]
            if printer_name in stream_threads:
                # Thread will stop when it sees no active streams
                del stream_threads[printer_name]
    
    emit('camera_left', {'client_id': client_id, 'printer_name': printer_name})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnect - cleanup any streams"""
    logger.info(f"Client {request.sid} disconnected")
    
    # Find and remove this client from all streams
    for printer_name in list(active_streams.keys()):
        for client_id in list(active_streams[printer_name].keys()):
            if active_streams[printer_name][client_id] == request.sid:
                del active_streams[printer_name][client_id]
                
        # Clean up empty streams
        if not active_streams[printer_name]:
            del active_streams[printer_name]
            if printer_name in stream_threads:
                del stream_threads[printer_name]

def camera_stream_worker(printer_name):
    """Background worker that streams camera frames via WebSocket"""
    logger.info(f"Starting camera stream worker for {printer_name}")
    
    # Get printer config
    printer_cfg = next((p for p in storage.get_printers() if p.get('name').lower().replace(' ','_')==printer_name.lower().replace(' ','_')), None)
    if not printer_cfg:
        logger.error(f"Printer {printer_name} not found for camera stream")
        return
    
    cam_url = printer_cfg.get('camera_url')
    snapshot_url = printer_cfg.get('snapshot_url')
    
    if not cam_url and not snapshot_url:
        logger.error(f"No camera configured for {printer_name}")
        return
    
    while printer_name in active_streams and active_streams[printer_name]:
        try:
            frame_data = None
            
            if snapshot_url:
                # Use snapshot URL for better reliability
                response = requests.get(snapshot_url, timeout=5, verify=False)
                if response.status_code == 200:
                    frame_data = response.content
            else:
                # Extract frame from MJPEG stream
                response = requests.get(cam_url, stream=True, timeout=5, verify=False)
                if response.status_code == 200:
                    chunk_data = b''
                    for chunk in response.iter_content(chunk_size=4096):
                        chunk_data += chunk
                        start_idx = chunk_data.find(b'\xff\xd8')
                        end_idx = chunk_data.find(b'\xff\xd9')
                        
                        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                            frame_data = chunk_data[start_idx:end_idx+2]
                            break
                            
                        if len(chunk_data) > 1024*1024:
                            break
                    response.close()
            
            if frame_data:
                # Convert to base64 and emit to all clients
                base64_frame = base64.b64encode(frame_data).decode('utf-8')
                data_uri = f"data:image/jpeg;base64,{base64_frame}"
                
                # Send to all connected clients for this printer
                if printer_name in active_streams:
                    for client_id, session_id in active_streams[printer_name].items():
                        socketio.emit('camera_frame', {
                            'printer_name': printer_name,
                            'frame_data': data_uri,
                            'timestamp': time.time()
                        }, room=session_id)
            
        except Exception as e:
            logger.error(f"Camera stream error for {printer_name}: {e}")
        
        # Control frame rate (2-3 FPS for efficiency)
        time.sleep(0.4)
    
    logger.info(f"Camera stream worker stopped for {printer_name}")

if __name__ == '__main__':
    logger.info("Starting Print Farm Dashboard Flask app...")
    try:
        # Try to run with eventlet first
        socketio.run(app, host='127.0.0.1', port=5001, debug=False, use_reloader=False)
    except RuntimeError as e:
        if "Werkzeug" in str(e):
            logger.warning("Werkzeug warning detected, running with allow_unsafe_werkzeug=True")
            socketio.run(app, host='127.0.0.1', port=5001, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)
        else:
            raise 