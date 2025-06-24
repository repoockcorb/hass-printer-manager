#!/usr/bin/env python3

import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, Response, send_from_directory
import requests
from requests.exceptions import RequestException, Timeout
import threading
import time
import urllib.parse
import base64
import re
from werkzeug.utils import secure_filename
import uuid
import hashlib

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
    
    def _send_gcode(self, gcode_command, timeout=30):
        """Send G-code command to Moonraker using URL parameters
        
        Args:
            gcode_command: The G-code to send
            timeout: Timeout in seconds (default 30 for movement commands)
        """
        try:
            # Encode the G-code command for URL
            encoded_gcode = urllib.parse.quote(gcode_command)
            endpoint = f"printer/gcode/script?script={encoded_gcode}"
            
            headers = {'Content-Type': 'application/json'}
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'
                
            url = f"{self.url}/{endpoint}"
            logger.info(f"{self.name} sending G-code via URL: {url} (timeout: {timeout}s)")
            
            response = requests.post(url, headers=headers, timeout=timeout)
            logger.info(f"{self.name} G-code response status: {response.status_code}")
            
            # Check if the request was successful
            response.raise_for_status()
            
            # Parse response - Moonraker may return empty response for successful G-code
            if response.text:
                try:
                    result = response.json()
                    logger.info(f"{self.name} G-code response JSON: {result}")
                except ValueError as e:
                    logger.warning(f"{self.name} G-code response not JSON: {response.text}")
                    result = {'status': 'ok', 'response_text': response.text}
            else:
                # Empty response is often success for G-code commands
                logger.info(f"{self.name} G-code response empty (likely success)")
                result = {'status': 'ok', 'response': 'empty'}
            
            return result
            
        except requests.exceptions.Timeout as e:
            logger.error(f"{self.name} G-code command timed out after {timeout}s: {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"{self.name} G-code HTTP request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"{self.name} G-code command failed: {e}")
            return None
    
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
        if axes is None or axes == 'all':
            # Home all axes with a single G28 command
            gcode = "G28"
            timeout = 60  # Homing all axes can take a long time
            logger.info(f"{self.name} homing all axes: {gcode}")
        elif isinstance(axes, str):
            # Home a single axis
            axis = axes.upper()
            if axis in ['X', 'Y', 'Z']:
                gcode = f"G28 {axis}"
                timeout = 45  # Single axis homing is usually faster
                logger.info(f"{self.name} homing {axis} axis: {gcode}")
            else:
                logger.error(f"{self.name} invalid axis for homing: {axes}")
                return {'success': False, 'error': f'Invalid axis: {axes}'}
        elif isinstance(axes, list):
            # Home specific axes
            valid_axes = [ax.upper() for ax in axes if ax.upper() in ['X', 'Y', 'Z']]
            if valid_axes:
                gcode = f"G28 {' '.join(valid_axes)}"
                timeout = 50  # Multiple axes
                logger.info(f"{self.name} homing axes {valid_axes}: {gcode}")
            else:
                logger.error(f"{self.name} no valid axes for homing: {axes}")
                return {'success': False, 'error': f'No valid axes: {axes}'}
        else:
            logger.error(f"{self.name} invalid axes parameter: {axes}")
            return {'success': False, 'error': f'Invalid axes parameter: {axes}'}
        
        # Use the new _send_gcode method for Moonraker with appropriate timeout
        logger.info(f"{self.name} starting homing operation (timeout: {timeout}s)")
        result = self._send_gcode(gcode, timeout=timeout)
        
        # Check if the G-code was sent successfully
        # Moonraker returns None on failure, but may return empty dict {} on success
        if result is not None:
            logger.info(f"{self.name} home command completed successfully: {result}")
            return {'success': True, 'result': result}
        else:
            logger.error(f"{self.name} home command failed or timed out")
            return {'success': False, 'error': 'Homing command failed or timed out'}
    
    def jog_printer(self, axis, distance):
        """Jog printer in specified axis by distance (in mm)"""
        axis = axis.upper()
        if axis not in ['X', 'Y', 'Z']:
            logger.error(f"{self.name} invalid axis for jogging: {axis}")
            return {'success': False, 'error': f'Invalid axis: {axis}'}
            
        try:
            distance = float(distance)
        except (ValueError, TypeError):
            logger.error(f"{self.name} invalid distance for jogging: {distance}")
            return {'success': False, 'error': f'Invalid distance: {distance}'}
        
        # Use relative positioning with safer feedrate
        # G91: relative mode, G0: rapid move, G90: absolute mode
        gcode = f"G91\nG0 {axis}{distance} F1800\nG90"
        
        # Jog timeout based on distance (larger moves take longer)
        timeout = max(15, min(30, abs(distance) * 2))  # 15-30 seconds based on distance
        
        logger.info(f"{self.name} jogging {axis}{distance:+.1f}mm: {gcode.replace(chr(10), ' | ')} (timeout: {timeout}s)")
        
        # Use the new _send_gcode method for Moonraker with appropriate timeout
        result = self._send_gcode(gcode, timeout=timeout)
        
        # Check if the G-code was sent successfully
        # Moonraker returns None on failure, but may return empty dict {} on success
        if result is not None:
            logger.info(f"{self.name} jog command completed successfully: {result}")
            return {'success': True, 'result': result}
        else:
            logger.error(f"{self.name} jog command failed or timed out")
            return {'success': False, 'error': 'Jog command failed or timed out'}

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

class GCodeFile:
    """Represents a G-code file with metadata and thumbnail"""
    
    def __init__(self, filename, filepath, file_size):
        self.id = str(uuid.uuid4())
        self.filename = filename
        self.filepath = filepath
        self.file_size = file_size
        self.upload_time = datetime.now()
        self.thumbnail_base64 = None
        self.metadata = {}
        self.file_hash = None
        
        # Extract metadata and thumbnail
        self._analyze_file()
    
    def _analyze_file(self):
        """Analyze G-code file to extract metadata and thumbnail"""
        try:
            with open(self.filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(10000)  # Read first 10KB for metadata
                
            # Extract thumbnail (PrusaSlicer format)
            thumbnail_match = re.search(r'; thumbnail begin (\d+)x(\d+) (\d+)\n(.*?)\n; thumbnail end', content, re.DOTALL)
            if thumbnail_match:
                width, height, size = thumbnail_match.groups()[:3]
                thumbnail_data = thumbnail_match.group(4)
                # Clean up the thumbnail data
                thumbnail_data = re.sub(r'^; ', '', thumbnail_data, flags=re.MULTILINE)
                thumbnail_data = thumbnail_data.replace('\n', '')
                self.thumbnail_base64 = f"data:image/png;base64,{thumbnail_data}"
                logger.info(f"Extracted thumbnail for {self.filename}: {width}x{height}")
            
            # Extract metadata
            self.metadata = {
                'estimated_time': self._extract_metadata(content, r'estimated printing time.*?(\d+h\s*\d+m|\d+m\s*\d+s|\d+h|\d+m|\d+s)'),
                'layer_height': self._extract_metadata(content, r'layer_height\s*=\s*([\d.]+)'),
                'infill': self._extract_metadata(content, r'fill_density\s*=\s*([\d.]+)'),
                'filament_used': self._extract_metadata(content, r'filament used.*?([\d.]+m|[\d.]+g)'),
                'slicer': self._extract_metadata(content, r'generated by\s+([^\n]+)|Sliced by\s+([^\n]+)'),
                'nozzle_temp': self._extract_metadata(content, r'M104 S(\d+)|M109 S(\d+)'),
                'bed_temp': self._extract_metadata(content, r'M140 S(\d+)|M190 S(\d+)'),
                'total_layers': self._count_layers(content)
            }
            
            # Calculate file hash for deduplication
            self.file_hash = self._calculate_file_hash()
            
        except Exception as e:
            logger.error(f"Error analyzing G-code file {self.filename}: {e}")
    
    def _extract_metadata(self, content, pattern):
        """Extract metadata using regex pattern"""
        try:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                # Return first non-None group
                for group in match.groups():
                    if group:
                        return group.strip()
            return None
        except Exception:
            return None
    
    def _count_layers(self, content):
        """Count layer changes in G-code"""
        try:
            layer_matches = re.findall(r';LAYER:\d+|;layer \d+|; layer \d+', content, re.IGNORECASE)
            return len(layer_matches) if layer_matches else None
        except Exception:
            return None
    
    def _calculate_file_hash(self):
        """Calculate MD5 hash of file for deduplication"""
        try:
            hash_md5 = hashlib.md5()
            with open(self.filepath, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception:
            return None
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'filename': self.filename,
            'file_size': self.file_size,
            'upload_time': self.upload_time.isoformat(),
            'thumbnail': self.thumbnail_base64,
            'metadata': self.metadata,
            'file_hash': self.file_hash
        }

class FileManager:
    """Manages uploaded G-code files"""
    
    def __init__(self):
        # Use a more accessible directory path
        self.upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
        self.files = {}  # id -> GCodeFile
        self.max_files = 50  # Maximum number of files to keep
        
        # Create upload directory with proper error handling
        try:
            os.makedirs(self.upload_dir, exist_ok=True)
            logger.info(f"File upload directory created/verified: {self.upload_dir}")
        except Exception as e:
            logger.error(f"Failed to create upload directory {self.upload_dir}: {e}")
            # Fallback to temp directory
            import tempfile
            self.upload_dir = os.path.join(tempfile.gettempdir(), 'printer_dashboard_files')
            os.makedirs(self.upload_dir, exist_ok=True)
            logger.info(f"Using fallback upload directory: {self.upload_dir}")
        
        # Load existing files
        self._load_existing_files()
    
    def _load_existing_files(self):
        """Load existing files from upload directory"""
        try:
            if os.path.exists(self.upload_dir):
                for filename in os.listdir(self.upload_dir):
                    if filename.endswith('.gcode'):
                        filepath = os.path.join(self.upload_dir, filename)
                        file_size = os.path.getsize(filepath)
                        gcode_file = GCodeFile(filename, filepath, file_size)
                        self.files[gcode_file.id] = gcode_file
                        
            logger.info(f"Loaded {len(self.files)} existing G-code files")
        except Exception as e:
            logger.error(f"Error loading existing files: {e}")
    
    def upload_file(self, file_obj, filename):
        """Upload and process a new G-code file"""
        filepath = None
        try:
            # Validate upload directory
            if not os.path.exists(self.upload_dir):
                logger.error(f"Upload directory does not exist: {self.upload_dir}")
                raise Exception(f"Upload directory not available: {self.upload_dir}")
            
            if not os.access(self.upload_dir, os.W_OK):
                logger.error(f"Upload directory is not writable: {self.upload_dir}")
                raise Exception(f"Upload directory not writable: {self.upload_dir}")
            
            # Secure the filename
            filename = secure_filename(filename)
            if not filename:
                raise Exception("Invalid filename after security filtering")
                
            if not filename.endswith('.gcode'):
                filename += '.gcode'
            
            # Create unique filename to avoid conflicts
            base_name, ext = os.path.splitext(filename)
            unique_filename = f"{base_name}_{int(time.time())}{ext}"
            filepath = os.path.join(self.upload_dir, unique_filename)
            
            logger.info(f"Saving file to: {filepath}")
            
            # Save file
            file_obj.save(filepath)
            
            if not os.path.exists(filepath):
                raise Exception(f"File was not saved successfully: {filepath}")
                
            file_size = os.path.getsize(filepath)
            if file_size == 0:
                raise Exception("Uploaded file is empty")
            
            logger.info(f"File saved successfully, size: {file_size} bytes")
            
            # Create GCodeFile object
            gcode_file = GCodeFile(filename, filepath, file_size)
            
            # Check for duplicates
            duplicate_id = self._find_duplicate(gcode_file.file_hash)
            if duplicate_id:
                os.remove(filepath)  # Remove the duplicate
                logger.info(f"Duplicate file detected: {filename}")
                return self.files[duplicate_id]
            
            # Add to collection
            self.files[gcode_file.id] = gcode_file
            
            # Clean up old files if needed
            self._cleanup_old_files()
            
            logger.info(f"Uploaded G-code file: {filename} ({file_size} bytes) with ID: {gcode_file.id}")
            return gcode_file
            
        except Exception as e:
            logger.error(f"Error uploading file {filename}: {e}", exc_info=True)
            # Clean up partial file if it exists
            if filepath and os.path.exists(filepath):
                try:
                    os.remove(filepath)
                    logger.info(f"Cleaned up partial file: {filepath}")
                except Exception as cleanup_error:
                    logger.error(f"Failed to clean up partial file {filepath}: {cleanup_error}")
            raise
    
    def _find_duplicate(self, file_hash):
        """Find duplicate file by hash"""
        if not file_hash:
            return None
        for file_id, gcode_file in self.files.items():
            if gcode_file.file_hash == file_hash:
                return file_id
        return None
    
    def _cleanup_old_files(self):
        """Remove oldest files if over limit"""
        if len(self.files) > self.max_files:
            # Sort by upload time and remove oldest
            sorted_files = sorted(self.files.items(), key=lambda x: x[1].upload_time)
            files_to_remove = sorted_files[:-self.max_files]
            
            for file_id, gcode_file in files_to_remove:
                try:
                    os.remove(gcode_file.filepath)
                    del self.files[file_id]
                    logger.info(f"Removed old file: {gcode_file.filename}")
                except Exception as e:
                    logger.error(f"Error removing old file {gcode_file.filename}: {e}")
    
    def get_file(self, file_id):
        """Get file by ID"""
        return self.files.get(file_id)
    
    def get_all_files(self):
        """Get all files sorted by upload time (newest first)"""
        return sorted(self.files.values(), key=lambda x: x.upload_time, reverse=True)
    
    def delete_file(self, file_id):
        """Delete a file"""
        gcode_file = self.files.get(file_id)
        if gcode_file:
            try:
                os.remove(gcode_file.filepath)
                del self.files[file_id]
                logger.info(f"Deleted file: {gcode_file.filename}")
                return True
            except Exception as e:
                logger.error(f"Error deleting file {gcode_file.filename}: {e}")
        return False
    
    def send_to_printer(self, file_id, printer_name):
        """Send file to a specific printer"""
        gcode_file = self.files.get(file_id)
        if not gcode_file:
            return {'success': False, 'error': 'File not found'}
        
        if printer_name not in printer_manager.printers:
            return {'success': False, 'error': 'Printer not found'}
        
        printer = printer_manager.printers[printer_name]
        
        try:
            if printer.printer_type == 'klipper':
                return self._send_to_moonraker(gcode_file, printer)
            elif printer.printer_type == 'octoprint':
                return self._send_to_octoprint(gcode_file, printer)
            else:
                return {'success': False, 'error': 'Unsupported printer type'}
        except Exception as e:
            logger.error(f"Error sending file to printer {printer_name}: {e}")
            return {'success': False, 'error': str(e)}
    
    def _send_to_moonraker(self, gcode_file, printer):
        """Send file to Moonraker printer"""
        try:
            url = f"{printer.url}/server/files/upload"
            
            headers = {}
            if printer.api_key:
                headers['Authorization'] = f'Bearer {printer.api_key}'
            
            with open(gcode_file.filepath, 'rb') as f:
                files = {'file': (gcode_file.filename, f, 'application/octet-stream')}
                data = {'root': 'gcodes'}
                
                response = requests.post(url, headers=headers, files=files, data=data, timeout=30)
                response.raise_for_status()
                
            logger.info(f"Successfully sent {gcode_file.filename} to {printer.name}")
            return {'success': True, 'message': f'File sent to {printer.name}'}
            
        except Exception as e:
            logger.error(f"Error sending file to Moonraker {printer.name}: {e}")
            return {'success': False, 'error': str(e)}
    
    def _send_to_octoprint(self, gcode_file, printer):
        """Send file to OctoPrint printer"""
        try:
            url = f"{printer.url}/api/files/local"
            
            headers = {}
            if printer.api_key:
                headers['X-Api-Key'] = printer.api_key
            
            with open(gcode_file.filepath, 'rb') as f:
                files = {'file': (gcode_file.filename, f, 'application/octet-stream')}
                
                response = requests.post(url, headers=headers, files=files, timeout=30)
                response.raise_for_status()
                
            logger.info(f"Successfully sent {gcode_file.filename} to {printer.name}")
            return {'success': True, 'message': f'File sent to {printer.name}'}
            
        except Exception as e:
            logger.error(f"Error sending file to OctoPrint {printer.name}: {e}")
            return {'success': False, 'error': str(e)}

# Initialize file manager
file_manager = FileManager()

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
        logger.info(f"Control request: {printer_name} -> {action}")
        
        # Get additional parameters from request JSON
        data = request.get_json() or {}
        logger.info(f"Control request data: {data}")
        
        # Extract parameters for different actions
        kwargs = {}
        if action == 'home':
            kwargs['axes'] = data.get('axes')  # Can be None for all axes, or specific axes like ['X', 'Y']
            logger.info(f"Home action with axes: {kwargs['axes']}")
        elif action == 'jog':
            kwargs['axis'] = data.get('axis')  # Required: 'X', 'Y', or 'Z'
            kwargs['distance'] = data.get('distance')  # Required: distance in mm
            logger.info(f"Jog action with axis={kwargs['axis']}, distance={kwargs['distance']}")
        
        result = printer_manager.control_printer(printer_name, action, **kwargs)
        logger.info(f"Control result: {result}")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error controlling {printer_name}: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
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

@app.route('/debug/printer-config')
def debug_printer_config():
    """Debug endpoint to show current printer configurations"""
    try:
        printer_configs = []
        for name, printer in printer_manager.printers.items():
            printer_configs.append({
                'name': name,
                'type': printer.printer_type,
                'url': printer.url,
                'api_key': '***' if printer.api_key else None
            })
        
        # Also load raw config from file
        raw_config = []
        if os.path.exists('/data/options.json'):
            with open('/data/options.json', 'r') as f:
                config = json.load(f)
                raw_config = config.get('printers', [])
        
        return jsonify({
            'active_printers': printer_configs,
            'raw_config': raw_config,
            'config_file_path': '/data/options.json'
        })
        
    except Exception as e:
        logger.error(f"Error in debug printer config: {e}")
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

@app.route('/api/test-gcode/<printer_name>', methods=['POST'])
def test_gcode(printer_name):
    """Test endpoint to send simple G-code to a printer"""
    try:
        logger.info(f"G-code test request for: {printer_name}")
        
        # Get G-code from request
        data = request.get_json() or {}
        gcode = data.get('gcode', 'M115')  # Default to M115 (get firmware info)
        
        logger.info(f"Sending test G-code: {gcode}")
        
        if printer_name not in printer_manager.printers:
            return jsonify({'success': False, 'error': 'Printer not found'}), 404
            
        printer = printer_manager.printers[printer_name]
        
        # Use appropriate method based on printer type
        if printer.printer_type == 'klipper':
            result = printer._send_gcode(gcode)
        else:
            # For OctoPrint, use the original method
            result = printer._make_request('printer/gcode/script', method='POST', 
                                         data={'script': gcode})
        
        logger.info(f"G-code test result: {result}")
        
        return jsonify({
            'success': True, 
            'gcode': gcode,
            'result': result,
            'printer_type': printer.printer_type
        })
        
    except Exception as e:
        logger.error(f"Error in G-code test: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/direct-control/<host>/<int:port>/<action>', methods=['POST'])
def direct_control(host, port, action):
    """Direct control API that bypasses printer configuration
    Usage: /api/direct-control/192.168.1.216/7125/home
           /api/direct-control/192.168.1.216/7125/jog
    """
    try:
        logger.info(f"Direct control request: {host}:{port} -> {action}")
        
        # Get additional parameters from request JSON
        data = request.get_json() or {}
        logger.info(f"Direct control request data: {data}")
        
        # Create temporary KlipperAPI instance for direct communication
        temp_printer = KlipperAPI(
            name=f"Direct-{host}",
            printer_type='klipper',
            url=f"http://{host}:{port}",
            api_key=data.get('api_key')  # Optional API key from request
        )
        
        if action == 'home':
            axes = data.get('axes')  # Can be None for all axes, or specific axes like ['X', 'Y']
            logger.info(f"Direct home action with axes: {axes}")
            result = temp_printer.home_printer(axes)
            
        elif action == 'jog':
            axis = data.get('axis')  # Required: 'X', 'Y', or 'Z'
            distance = data.get('distance')  # Required: distance in mm
            logger.info(f"Direct jog action with axis={axis}, distance={distance}")
            
            if not axis or distance is None:
                return jsonify({'success': False, 'error': 'Missing axis or distance for jog command'}), 400
                
            result = temp_printer.jog_printer(axis, distance)
            
        elif action == 'gcode':
            gcode = data.get('gcode')  # Custom G-code command
            logger.info(f"Direct G-code: {gcode}")
            
            if not gcode:
                return jsonify({'success': False, 'error': 'Missing gcode parameter'}), 400
                
            result = temp_printer._send_gcode(gcode)
            result = {'success': True, 'result': result} if result else {'success': False, 'error': 'G-code command failed'}
            
        else:
            return jsonify({'success': False, 'error': 'Invalid action. Supported: home, jog, gcode'}), 400
        
        logger.info(f"Direct control result: {result}")
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in direct control {host}:{port}: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/direct-status/<host>/<int:port>')
def direct_status(host, port):
    """Get status directly from Moonraker instance
    Usage: /api/direct-status/192.168.1.216/7125
    """
    try:
        logger.info(f"Direct status request: {host}:{port}")
        
        # Optional API key from query parameter
        api_key = request.args.get('api_key')
        
        # Create temporary KlipperAPI instance
        temp_printer = KlipperAPI(
            name=f"Direct-{host}",
            printer_type='klipper',
            url=f"http://{host}:{port}",
            api_key=api_key
        )
        
        status = temp_printer.get_status()
        return jsonify(status)
        
    except Exception as e:
        logger.error(f"Error getting direct status from {host}:{port}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/direct-test')
def direct_test():
    """Simple test page for direct control API"""
    return '''
<!DOCTYPE html>
<html>
<head>
    <title>Direct Moonraker Control Test</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .container { max-width: 600px; margin: 0 auto; }
        .section { margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }
        input, button { padding: 8px; margin: 5px; }
        button { background: #007bff; color: white; border: none; border-radius: 3px; cursor: pointer; }
        button:hover { background: #0056b3; }
        .result { margin: 10px 0; padding: 10px; background: #f8f9fa; border-radius: 3px; font-family: monospace; }
        .error { background: #f8d7da; color: #721c24; }
        .success { background: #d4edda; color: #155724; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Direct Moonraker Control Test</h1>
        
        <div class="section">
            <h3>Connection Settings</h3>
            <input type="text" id="host" placeholder="IP Address" value="192.168.1.216">
            <input type="number" id="port" placeholder="Port" value="7125">
            <input type="text" id="apiKey" placeholder="API Key (optional)">
        </div>
        
        <div class="section">
            <h3>Test Status</h3>
            <button onclick="testStatus()">Get Status</button>
            <div id="statusResult" class="result"></div>
        </div>
        
        <div class="section">
            <h3>Home Commands</h3>
            <button onclick="homeAll()">Home All</button>
            <button onclick="homeAxis('X')">Home X</button>
            <button onclick="homeAxis('Y')">Home Y</button>
            <button onclick="homeAxis('Z')">Home Z</button>
            <div id="homeResult" class="result"></div>
        </div>
        
        <div class="section">
            <h3>Jog Commands</h3>
            <button onclick="jog('X', 1)">X +1mm</button>
            <button onclick="jog('X', -1)">X -1mm</button>
            <button onclick="jog('Y', 1)">Y +1mm</button>
            <button onclick="jog('Y', -1)">Y -1mm</button>
            <button onclick="jog('Z', 0.1)">Z +0.1mm</button>
            <button onclick="jog('Z', -0.1)">Z -0.1mm</button>
            <div id="jogResult" class="result"></div>
        </div>
        
        <div class="section">
            <h3>Custom G-code</h3>
            <input type="text" id="customGcode" placeholder="Enter G-code (e.g., M115)" value="M115">
            <button onclick="sendGcode()">Send G-code</button>
            <div id="gcodeResult" class="result"></div>
        </div>
    </div>

    <script>
        function getBaseParams() {
            return {
                host: document.getElementById('host').value,
                port: document.getElementById('port').value,
                apiKey: document.getElementById('apiKey').value
            };
        }
        
        function showResult(elementId, data, isError = false) {
            const element = document.getElementById(elementId);
            element.textContent = JSON.stringify(data, null, 2);
            element.className = 'result ' + (isError ? 'error' : 'success');
        }
        
        async function testStatus() {
            const params = getBaseParams();
            try {
                const url = `/api/direct-status/${params.host}/${params.port}${params.apiKey ? '?api_key=' + params.apiKey : ''}`;
                const response = await fetch(url);
                const data = await response.json();
                showResult('statusResult', data, !response.ok);
            } catch (error) {
                showResult('statusResult', {error: error.message}, true);
            }
        }
        
        async function homeAll() {
            const params = getBaseParams();
            try {
                const url = `/api/direct-control/${params.host}/${params.port}/home`;
                const response = await fetch(url, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({api_key: params.apiKey})
                });
                const data = await response.json();
                showResult('homeResult', data, !response.ok);
            } catch (error) {
                showResult('homeResult', {error: error.message}, true);
            }
        }
        
        async function homeAxis(axis) {
            const params = getBaseParams();
            try {
                const url = `/api/direct-control/${params.host}/${params.port}/home`;
                const response = await fetch(url, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({axes: [axis], api_key: params.apiKey})
                });
                const data = await response.json();
                showResult('homeResult', data, !response.ok);
            } catch (error) {
                showResult('homeResult', {error: error.message}, true);
            }
        }
        
        async function jog(axis, distance) {
            const params = getBaseParams();
            try {
                const url = `/api/direct-control/${params.host}/${params.port}/jog`;
                const response = await fetch(url, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({axis, distance, api_key: params.apiKey})
                });
                const data = await response.json();
                showResult('jogResult', data, !response.ok);
            } catch (error) {
                showResult('jogResult', {error: error.message}, true);
            }
        }
        
        async function sendGcode() {
            const params = getBaseParams();
            const gcode = document.getElementById('customGcode').value;
            if (!gcode) return;
            
            try {
                const url = `/api/direct-control/${params.host}/${params.port}/gcode`;
                const response = await fetch(url, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({gcode, api_key: params.apiKey})
                });
                const data = await response.json();
                showResult('gcodeResult', data, !response.ok);
            } catch (error) {
                showResult('gcodeResult', {error: error.message}, true);
            }
        }
    </script>
</body>
</html>
    '''

@app.route('/api/printers-enhanced')
def get_printers_enhanced():
    """API endpoint to get printer configurations with enhanced direct connection info"""
    try:
        printers_config = storage.get_printers()
        enhanced_printers = []
        
        for printer_config in printers_config:
            enhanced_config = printer_config.copy()
            
            # Try to auto-detect direct connection info for Klipper printers with ingress URLs
            if (enhanced_config.get('type') == 'klipper' and 
                enhanced_config.get('url') and 
                '/api/hassio_ingress/' in enhanced_config.get('url')):
                
                # Try to extract direct connection info from various sources
                direct_host, direct_port = extract_direct_connection_info(enhanced_config)
                
                if direct_host and direct_port:
                    enhanced_config['direct_host'] = direct_host
                    enhanced_config['direct_port'] = direct_port
                    enhanced_config['uses_direct_control'] = True
                    logger.info(f"Auto-detected direct connection for {enhanced_config['name']}: {direct_host}:{direct_port}")
                else:
                    enhanced_config['uses_direct_control'] = False
                    logger.info(f"Could not auto-detect direct connection for {enhanced_config['name']}")
            
            enhanced_printers.append(enhanced_config)
        
        return jsonify(enhanced_printers)
        
    except Exception as e:
        logger.error(f"Error getting enhanced printers: {e}")
        return jsonify({'error': str(e)}), 500

def extract_direct_connection_info(printer_config):
    """Try to extract direct Moonraker connection info from various sources"""
    try:
        # Method 1: Check if already configured
        if printer_config.get('direct_host') and printer_config.get('direct_port'):
            return printer_config['direct_host'], printer_config['direct_port']
        
        # Method 2: Check if there's a moonraker_url field
        if printer_config.get('moonraker_url'):
            return parse_url_for_host_port(printer_config['moonraker_url'])
        
        # Method 3: Try to ping common Moonraker ports on same network
        # Extract network from HA URL if possible
        ha_url = printer_config.get('url', '')
        network_base = extract_network_base_from_ha_url(ha_url)
        
        if network_base:
            # Try common IPs on the same network with port 7125
            for i in range(200, 255):  # Common range for printers
                test_host = f"{network_base}.{i}"
                if test_moonraker_connection(test_host, 7125):
                    logger.info(f"Found Moonraker at {test_host}:7125")
                    return test_host, 7125
        
        # Method 4: Return None if nothing found
        return None, None
        
    except Exception as e:
        logger.error(f"Error extracting direct connection info: {e}")
        return None, None

def parse_url_for_host_port(url):
    """Parse URL to extract host and port"""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or 7125  # Default Moonraker port
        return host, port
    except Exception:
        return None, None

def extract_network_base_from_ha_url(ha_url):
    """Extract network base (e.g., '192.168.1') from Home Assistant URL"""
    try:
        # Look for IP patterns in the URL
        import re
        ip_pattern = r'(\d+\.\d+\.\d+)\.\d+'
        match = re.search(ip_pattern, ha_url)
        if match:
            return match.group(1)
        return None
    except Exception:
        return None

def test_moonraker_connection(host, port, timeout=1):
    """Quick test to see if Moonraker is available at host:port"""
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False

@app.route('/api/files', methods=['GET'])
def get_files():
    """Get all uploaded G-code files"""
    try:
        files = file_manager.get_all_files()
        return jsonify([f.to_dict() for f in files])
    except Exception as e:
        logger.error(f"Error getting files: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/files/upload', methods=['POST'])
def upload_file():
    """Upload a new G-code file"""
    try:
        logger.info("File upload request received")
        
        if 'file' not in request.files:
            logger.warning("No file provided in upload request")
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file_obj = request.files['file']
        if file_obj.filename == '':
            logger.warning("Empty filename in upload request")
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        if not file_obj.filename.lower().endswith('.gcode'):
            logger.warning(f"Invalid file type: {file_obj.filename}")
            return jsonify({'success': False, 'error': 'Only .gcode files are allowed'}), 400
        
        logger.info(f"Starting upload of file: {file_obj.filename}")
        
        # Upload and process file
        gcode_file = file_manager.upload_file(file_obj, file_obj.filename)
        
        logger.info(f"File uploaded successfully: {file_obj.filename}")
        
        return jsonify({
            'success': True,
            'file': gcode_file.to_dict(),
            'message': 'File uploaded successfully'
        })
        
    except Exception as e:
        logger.error(f"Error uploading file: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'Upload failed: {str(e)}'}), 500

@app.route('/api/files/<file_id>', methods=['DELETE'])
def delete_file(file_id):
    """Delete a G-code file"""
    try:
        success = file_manager.delete_file(file_id)
        if success:
            return jsonify({'success': True, 'message': 'File deleted successfully'})
        else:
            return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/files/<file_id>/send', methods=['POST'])
def send_file_to_printer(file_id):
    """Send a G-code file to a specific printer"""
    try:
        data = request.get_json() or {}
        printer_name = data.get('printer_name')
        
        if not printer_name:
            return jsonify({'error': 'Printer name is required'}), 400
        
        result = file_manager.send_to_printer(file_id, printer_name)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception as e:
        logger.error(f"Error sending file to printer: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/files/<file_id>/download')
def download_file(file_id):
    """Download a G-code file"""
    try:
        gcode_file = file_manager.get_file(file_id)
        if not gcode_file:
            return jsonify({'error': 'File not found'}), 404
        
        return send_from_directory(
            os.path.dirname(gcode_file.filepath),
            os.path.basename(gcode_file.filepath),
            as_attachment=True,
            download_name=gcode_file.filename
        )
        
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    logger.info("Starting Print Farm Dashboard Flask app...")
    app.run(host='127.0.0.1', port=5001, debug=False) 