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
import urllib.parse
from werkzeug.utils import secure_filename
import base64
import re
import tempfile
import yaml
import asyncio
from typing import Optional, Dict, Any
from urllib.parse import urlparse
from werkzeug.utils import secure_filename
from flask import Flask, render_template, jsonify, request, url_for, send_file, Response
try:
    from moonraker_api import MoonrakerClient, MoonrakerListener
    MOONRAKER_API_AVAILABLE = True
except ImportError:
    MOONRAKER_API_AVAILABLE = False

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static', static_url_path='/static')

# Configure Flask for file uploads
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

# Directory to store uploaded gcode files (persistent in HA add-on)
GCODE_STORAGE_DIR = '/data/gcode_files'

# Ensure storage directory exists
os.makedirs(GCODE_STORAGE_DIR, exist_ok=True)

# ---------------- Thumbnail extraction for stored G-code files ----------------

THUMB_RE_BEGIN = re.compile(r";\s*thumbnail begin (\d+)x(\d+) \d+", re.IGNORECASE)
THUMB_RE_END = re.compile(r";\s*thumbnail end", re.IGNORECASE)


def _extract_embedded_thumbnail(path: str):
    """Parse a G-code file and return PNG bytes of the largest embedded thumbnail found."""
    try:
        thumbnails = []
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            collecting = False
            current_size = (0, 0)
            b64_lines = []
            
            for line in fh:
                if not collecting:
                    match = THUMB_RE_BEGIN.match(line)
                    if match:
                        width, height = int(match.group(1)), int(match.group(2))
                        current_size = (width, height)
                        collecting = True
                        b64_lines = []
                        continue
                else:
                    if THUMB_RE_END.match(line):
                        if b64_lines:
                            try:
                                b64_data = "".join(b64_lines)
                                thumbnail_bytes = base64.b64decode(b64_data)
                                # Store thumbnail with its size for later comparison
                                thumbnails.append((current_size[0] * current_size[1], thumbnail_bytes))
                            except Exception as e:
                                logger.debug(f"Failed to decode thumbnail {current_size}: {e}")
                        collecting = False
                        b64_lines = []
                        continue
                    # Remove leading '; ' or ';'
                    cleaned = line.lstrip(';').strip()
                    b64_lines.append(cleaned)
            
            # Return the largest thumbnail (by pixel count)
            if thumbnails:
                thumbnails.sort(key=lambda x: x[0], reverse=True)  # Sort by pixel count, largest first
                largest_thumbnail = thumbnails[0][1]
                logger.debug(f"Selected largest thumbnail from {len(thumbnails)} available thumbnails")
                return largest_thumbnail
                
    except Exception as e:
        logger.debug(f"No thumbnail extracted from {path}: {e}")
    return None


@app.route('/api/gcode/thumbnail/<path:filename>')
def get_gcode_thumbnail(filename):
    """Return thumbnail PNG for stored gcode file or 404."""
    safe_name = secure_filename(filename)
    file_path = os.path.join(GCODE_STORAGE_DIR, safe_name)
    if not os.path.isfile(file_path):
        return jsonify({'error': 'File not found'}), 404

    img_bytes = _extract_embedded_thumbnail(file_path)
    if img_bytes:
        return Response(img_bytes, mimetype='image/png')

    # fallback placeholder (1x1 transparent png)
    placeholder = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg=="
    )
    return Response(placeholder, mimetype='image/png')

@app.route('/files/thumbnail')
def get_file_thumbnail():
    """Return thumbnail PNG for stored gcode file using simplified path format."""
    filename = request.args.get('filename') or request.args.get('file')
    if not filename:
        return jsonify({'error': 'Missing filename parameter'}), 400

    safe_name = secure_filename(filename)
    file_path = os.path.join(GCODE_STORAGE_DIR, safe_name)
    if not os.path.isfile(file_path):
        return jsonify({'error': 'File not found'}), 404

    img_bytes = _extract_embedded_thumbnail(file_path)
    if img_bytes:
        return Response(img_bytes, mimetype='image/png')

    # fallback placeholder (1x1 transparent png)
    placeholder = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg=="
    )
    return Response(placeholder, mimetype='image/png')

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
        """Send G-code command to printer"""
        try:
            # Send gcode command using Moonraker's gcode/script endpoint
            response = self._make_request('printer/gcode/script', method='POST', 
                                        data={'script': gcode_command}, timeout=timeout)
            
            if response is None:
                logger.error(f"{self.name} G-code command failed: No response")
                return None
                
            # Handle different response formats
            if isinstance(response, dict):
                if 'error' in response:
                    logger.error(f"{self.name} G-code error: {response['error']}")
                    return None
                logger.info(f"{self.name} G-code response: {response}")
                return response
            elif hasattr(response, 'text') and response.text:
                # Parse text response
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
            
            # First, get list of available objects to detect chamber sensors
            objects_list = self._make_request('printer/objects/list')
            chamber_sensors = []
            chamber_sensor_types = {}  # Store sensor type for each chamber sensor
            if objects_list and 'result' in objects_list:
                available_objects = objects_list.get('result', {}).get('objects', [])
                for obj in available_objects:
                    # Look for various chamber temperature sensor patterns
                    if ('temperature_sensor' in obj and 'chamber' in obj.lower()) or \
                       ('temperature_fan' in obj and 'chamber' in obj.lower()) or \
                       ('heater_generic' in obj and 'chamber' in obj.lower()):
                        chamber_sensors.append(obj)
                        # Store the sensor type for later use in temperature setting
                        if 'temperature_sensor' in obj:
                            chamber_sensor_types[obj] = 'temperature_sensor'
                        elif 'temperature_fan' in obj:
                            chamber_sensor_types[obj] = 'temperature_fan'
                        elif 'heater_generic' in obj:
                            chamber_sensor_types[obj] = 'heater_generic'
            
            # Build query string with chamber sensors
            query_params = 'print_stats&toolhead&extruder&heater_bed&display_status&virtual_sdcard&webhooks'
            for sensor in chamber_sensors:
                query_params += f'&{sensor.replace(" ", "%20")}'
            
            printer_objects = self._make_request(f'printer/objects/query?{query_params}')
            print_stats_direct = self._make_request('printer/print_stats')  # Direct print stats for accurate progress
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
            
            # Get direct print stats for more accurate progress
            direct_print_stats = {}
            if print_stats_direct and 'result' in print_stats_direct:
                direct_print_stats = print_stats_direct.get('result', {}).get('print_stats', {})
            
            def safe_round(value, digits=1):
                try:
                    return round(float(value), digits)
                except (TypeError, ValueError):
                    return 0
            
            # Calculate progress - use virtual_sdcard.progress for most accurate value
            progress = 0
            if virtual_sdcard.get('progress') not in [None, '']:
                try:
                    # virtual_sdcard.progress is decimal (0.0-1.0), convert to percentage
                    progress = round(float(virtual_sdcard['progress']) * 100, 1)
                except (TypeError, ValueError):
                    progress = 0
            elif direct_print_stats.get('progress') not in [None, '']:
                try:
                    # printer/print_stats progress is decimal (0.0-1.0), convert to percentage
                    progress = round(float(direct_print_stats['progress']) * 100, 1)
                except (TypeError, ValueError):
                    progress = 0
            elif display_status.get('progress') not in [None, '']:
                try:
                    # display_status.progress is typically in percentage (0-100)
                    progress = round(float(display_status['progress']) * 100, 1)
                except (TypeError, ValueError):
                    progress = 0
            
            # Get print time - use direct print_stats if available
            print_duration = 0
            if direct_print_stats.get('info', {}).get('print_duration') not in [None, '']:
                print_duration = direct_print_stats.get('info', {}).get('print_duration', 0) or 0
            else:
                print_duration = print_stats.get('print_duration', 0) or 0
            
            # Estimate remaining time
            remaining_time = 0
            if progress > 0 and progress < 100:
                remaining_time = (print_duration / (progress / 100)) - print_duration
            
            # Get filename - prefer direct print_stats
            filename = ''
            if direct_print_stats.get('filename'):
                filename = direct_print_stats.get('filename', '')
            else:
                filename = print_stats.get('filename', '')
            
            # Get state - prefer direct print_stats
            state = 'ready'
            if direct_print_stats.get('state'):
                state = direct_print_stats.get('state', 'ready')
            else:
                state = print_stats.get('state', 'ready')
            
            # Store chamber sensor types for temperature setting
            self.chamber_sensor_types = chamber_sensor_types
            
            # Process chamber temperature sensors
            chamber_temps = []
            for sensor in chamber_sensors:
                sensor_data = status_data.get(sensor, {})
                if sensor_data and 'temperature' in sensor_data:
                    # Extract a friendly name from the sensor name
                    friendly_name = sensor.replace('temperature_sensor ', '').replace('temperature_fan ', '').replace('heater_generic ', '').replace('_', ' ').title()
                    chamber_temps.append({
                        'name': friendly_name,
                        'sensor_id': sensor,  # Store original sensor ID for temperature setting
                        'sensor_type': chamber_sensor_types.get(sensor, 'unknown'),
                        'actual': round(sensor_data.get('temperature', 0), 1),
                        'target': round(sensor_data.get('target', 0), 1) if 'target' in sensor_data else None
                    })
            
            result = {
                'name': self.name,
                'type': 'klipper',
                'online': True,
                'state': state,
                'progress': progress,
                'file': filename,
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
            
            # Add chamber temperatures if any were found
            if chamber_temps:
                result['chamber_temps'] = chamber_temps
                
            return result
            
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
        return self._make_request('printer/print/pause', method='POST', data={})

    def resume_print(self):
        """Resume current print"""
        return self._make_request('printer/print/resume', method='POST', data={})

    def cancel_print(self):
        """Cancel current print"""
        try:
            response = self._make_request('printer/print/cancel', method='POST', data={})
            logger.info(f"Cancel print response: {response}")
            
            if isinstance(response, dict) and 'error' in response:
                return {'success': False, 'error': response['error']}
            else:
                return {'success': True, 'result': response}
        except Exception as e:
            logger.error(f"Error canceling print: {e}")
            return {'success': False, 'error': str(e)}

    def reprint(self):
        """Reprint the last completed file using Moonraker's API"""
        try:
            # Get print history from Moonraker
            history = self._make_request('server/history/list?limit=1')
            if not history or 'result' not in history:
                return {'success': False, 'error': 'Could not get print history'}
            
            # Get the most recent job
            jobs = history.get('result', {}).get('jobs', [])
            if not jobs:
                return {'success': False, 'error': 'No print history found'}
            
            last_job = jobs[0]
            filename = last_job.get('filename')
            
            if not filename:
                return {'success': False, 'error': 'No filename found in last print job'}
            
            logger.info(f"Attempting to reprint file from history: {filename}")
            
            # Start the print using Moonraker's API
            response = self._make_request('printer/print/start', method='POST', data={
                'filename': filename
            })
            
            # Log the full response for debugging
            logger.info(f"Moonraker API response: {response}")
            
            if response:
                if 'error' not in response:
                    return {'success': True}
                else:
                    error_msg = response.get('error', 'Unknown error')
                    logger.error(f"Reprint failed with error: {error_msg}")
                    return {'success': False, 'error': error_msg}
            else:
                return {'success': False, 'error': 'No response from printer'}
                
        except Exception as e:
            logger.error(f"Error during reprint: {str(e)}")
            return {'success': False, 'error': str(e)}

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
    
    def set_temperature(self, heater_type, temperature, heater_name=None):
        """Set temperature for extruder, bed, or chamber heater/fan"""
        try:
            temp = float(temperature)
            if temp < 0:
                temp = 0
        except (ValueError, TypeError):
            return {'success': False, 'error': 'Invalid temperature value'}
        
        try:
            if heater_type == 'extruder':
                # Set extruder temperature
                gcode = f'M104 S{temp}'
            elif heater_type == 'bed':
                # Set bed temperature
                gcode = f'M140 S{temp}'
            elif heater_type == 'chamber' and heater_name:
                # Dynamically determine chamber sensor type and use appropriate command
                sensor_type = self._get_chamber_sensor_type(heater_name)
                gcode = self._get_chamber_temperature_command(heater_name, temp, sensor_type)
                if not gcode:
                    return {'success': False, 'error': f'Unsupported chamber sensor type: {sensor_type}'}
            else:
                return {'success': False, 'error': 'Invalid heater type or missing heater name'}
            
            logger.info(f"{self.name} setting {heater_type} temperature to {temp}°C: {gcode}")
            result = self._send_gcode(gcode, timeout=10)
            
            if result is not None:
                return {'success': True, 'message': f'{heater_type.title()} temperature set to {temp}°C'}
            else:
                return {'success': False, 'error': 'Failed to set temperature'}
                
        except Exception as e:
            logger.error(f"Error setting temperature: {e}")
            return {'success': False, 'error': str(e)}
    
    def _get_chamber_sensor_type(self, heater_name):
        """Get the sensor type for a chamber heater by name"""
        if not hasattr(self, 'chamber_sensor_types'):
            return 'unknown'
            
        # Find sensor by matching the friendly name to the original sensor ID
        for sensor_id, sensor_type in self.chamber_sensor_types.items():
            # Extract friendly name from sensor ID
            friendly_name = sensor_id.replace('temperature_sensor ', '').replace('temperature_fan ', '').replace('heater_generic ', '').replace('_', ' ').title()
            if friendly_name.lower() == heater_name.lower():
                return sensor_type
        
        # If no exact match, try to find by partial match or original sensor name
        heater_lower = heater_name.lower().replace(' ', '_')
        for sensor_id, sensor_type in self.chamber_sensor_types.items():
            if heater_lower in sensor_id.lower():
                return sensor_type
                
        return 'unknown'
    
    def _get_chamber_temperature_command(self, heater_name, temperature, sensor_type):
        """Generate the appropriate G-code command for chamber temperature setting"""
        # Find the actual sensor ID from chamber_sensor_types
        actual_sensor_id = None
        if hasattr(self, 'chamber_sensor_types'):
            for sensor_id, s_type in self.chamber_sensor_types.items():
                # Extract friendly name from sensor ID
                friendly_name = sensor_id.replace('temperature_sensor ', '').replace('temperature_fan ', '').replace('heater_generic ', '').replace('_', ' ').title()
                if friendly_name.lower() == heater_name.lower():
                    actual_sensor_id = sensor_id
                    break
            
            # If no exact match, try partial match
            if not actual_sensor_id:
                heater_lower = heater_name.lower().replace(' ', '_')
                for sensor_id, s_type in self.chamber_sensor_types.items():
                    if heater_lower in sensor_id.lower():
                        actual_sensor_id = sensor_id
                        break
        
        # Fallback to converted name if we can't find the actual sensor ID
        if not actual_sensor_id:
            sensor_name = heater_name.lower().replace(' ', '_')
        else:
            # Extract just the sensor name part (without the prefix)
            if 'temperature_fan' in actual_sensor_id:
                sensor_name = actual_sensor_id.replace('temperature_fan ', '')
            elif 'heater_generic' in actual_sensor_id:
                sensor_name = actual_sensor_id.replace('heater_generic ', '')
            else:
                sensor_name = heater_name.lower().replace(' ', '_')
        
        if sensor_type == 'temperature_fan':
            # For temperature fans, use SET_TEMPERATURE_FAN_TARGET
            return f'SET_TEMPERATURE_FAN_TARGET temperature_fan={sensor_name} target={temperature}'
        elif sensor_type == 'heater_generic':
            # For generic heaters, use SET_HEATER_TEMPERATURE
            return f'SET_HEATER_TEMPERATURE HEATER={sensor_name} TARGET={temperature}'
        elif sensor_type == 'temperature_sensor':
            # Temperature sensors are read-only, cannot set temperature
            return None
        else:
            # Unknown sensor type
            return None


class KlipperWebSocketAPI(KlipperAPI):
    """Enhanced Klipper API using WebSocket connection via moonraker-api"""
    
    def __init__(self, name, printer_type, url, api_key=None):
        super().__init__(name, printer_type, url, api_key)
        self.ws_client = None
        self.ws_listener = None
        self._loop = None
        self._connected = False
        
        # Parse URL to get host and port
        parsed = urlparse(url)
        self.host = parsed.hostname or 'localhost'
        self.port = parsed.port or 7125
        
        if MOONRAKER_API_AVAILABLE:
            self._setup_websocket()
    
    def _setup_websocket(self):
        """Setup WebSocket client for real-time communication"""
        class PrinterListener(MoonrakerListener):
            def __init__(self, printer_api):
                self.printer_api = printer_api
                
            async def state_changed(self, state: str) -> None:
                logger.debug(f"{self.printer_api.name} WebSocket state: {state}")
                self.printer_api._connected = state == "ready"
                
            async def on_exception(self, exception: Exception) -> None:
                logger.error(f"{self.printer_api.name} WebSocket exception: {exception}")
                
            async def on_notification(self, method: str, data) -> None:
                logger.debug(f"{self.printer_api.name} WebSocket notification: {method}")
        
        self.ws_listener = PrinterListener(self)
        self.ws_client = MoonrakerClient(
            self.ws_listener,
            self.host,
            self.port,
            self.api_key
        )
    
    async def connect_websocket(self):
        """Connect to WebSocket if available"""
        if self.ws_client and not self._connected:
            try:
                await self.ws_client.connect()
                return True
            except Exception as e:
                logger.error(f"{self.name} WebSocket connection failed: {e}")
                return False
        return self._connected
    
    async def disconnect_websocket(self):
        """Disconnect WebSocket"""
        if self.ws_client and self._connected:
            try:
                await self.ws_client.disconnect()
                self._connected = False
            except Exception as e:
                logger.error(f"{self.name} WebSocket disconnect failed: {e}")
    
    async def get_thumbnail_async(self, filename: str) -> Optional[bytes]:
        """Get thumbnail data for a file using WebSocket API"""
        if not self.ws_client or not self._connected:
            return None
            
        try:
            # Query file metadata to get thumbnail path
            response = await self.ws_client.request("server.files.metadata", {"filename": filename})
            
            if not response or "result" not in response:
                return None
                
            metadata = response["result"]
            thumbnails = metadata.get("thumbnails", [])
            
            if not thumbnails:
                return None
            
            # Get the largest thumbnail available
            largest_thumb = max(thumbnails, key=lambda t: t.get("width", 0) * t.get("height", 0))
            thumb_path = largest_thumb.get("relative_path")
            
            if not thumb_path:
                return None
            
            # Download thumbnail data
            thumb_response = await self.ws_client.request("server.files.get_file", {
                "path": f"gcodes/{thumb_path}"
            })
            
            if thumb_response and "result" in thumb_response:
                return thumb_response["result"]
                
        except Exception as e:
            logger.error(f"{self.name} Failed to get thumbnail via WebSocket: {e}")
            
        return None
    
    def get_thumbnail(self, filename: str) -> Optional[bytes]:
        """Synchronous wrapper for thumbnail retrieval"""
        if not MOONRAKER_API_AVAILABLE or not self.ws_client:
            # Fallback to HTTP method
            return self._get_thumbnail_http(filename)
            
        # Run async method in event loop
        try:
            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
            
            # Ensure connection
            if not self._connected:
                self._loop.run_until_complete(self.connect_websocket())
            
            if self._connected:
                return self._loop.run_until_complete(self.get_thumbnail_async(filename))
                
        except Exception as e:
            logger.error(f"{self.name} Async thumbnail retrieval failed: {e}")
            
        # Fallback to HTTP
        return self._get_thumbnail_http(filename)
    
    def _get_thumbnail_http(self, filename: str) -> Optional[bytes]:
        """Fallback HTTP method for thumbnail retrieval"""
        try:
            # Get file metadata first
            metadata_response = self._make_request(f'server/files/metadata?filename={filename}')
            if not metadata_response or 'result' not in metadata_response:
                return None
                
            metadata = metadata_response['result']
            thumbnails = metadata.get('thumbnails', [])
            
            if not thumbnails:
                return None
            
            # Get the largest thumbnail
            largest_thumb = max(thumbnails, key=lambda t: t.get('width', 0) * t.get('height', 0))
            thumb_path = largest_thumb.get('relative_path')
            
            if not thumb_path:
                return None
            
            # Download thumbnail
            thumb_url = f"{self.url.rstrip('/')}/server/files/gcodes/{thumb_path}"
            response = requests.get(thumb_url, timeout=10)
            
            if response.status_code == 200:
                return response.content
                
        except Exception as e:
            logger.error(f"{self.name} HTTP thumbnail retrieval failed: {e}")
            
        return None


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
            
            # Define safe_round function first
            def safe_round(value, digits=1):
                try:
                    return round(float(value), digits)
                except (TypeError, ValueError):
                    return 0
            
            # Parse temperature data safely
            temps = printer_status.get('temperature', {}) if isinstance(printer_status, dict) else {}
            tool0 = temps.get('tool0', {})
            bed = temps.get('bed', {})
            
            # Look for chamber temperature sensors in OctoPrint
            chamber_temps = []
            for key, temp_data in temps.items():
                if 'chamber' in key.lower() and isinstance(temp_data, dict) and 'actual' in temp_data:
                    # Extract friendly name
                    friendly_name = key.replace('_', ' ').title()
                    chamber_temps.append({
                        'name': friendly_name,
                        'actual': safe_round(temp_data.get('actual', 0)),
                        'target': safe_round(temp_data.get('target', 0)) if temp_data.get('target') is not None else None
                    })
            
            # Parse job data
            job = job_status.get('job', {}) if isinstance(job_status, dict) else {}
            progress = job_status.get('progress', {}) if isinstance(job_status, dict) else {}
            state = printer_status.get('state', {}) if isinstance(printer_status, dict) else {}
            
            # Parse position data from main printer endpoint
            position_data = printer_status.get('position', {}) if isinstance(printer_status, dict) else {}
            position = {
                'x': safe_round(position_data.get('x', 0), 2),
                'y': safe_round(position_data.get('y', 0), 2),
                'z': safe_round(position_data.get('z', 0), 2)
            }
            
            # Calculate remaining time
            remaining = progress.get('printTimeLeft') or 0
            remaining_formatted = self._format_time(remaining) if remaining else "Unknown"
            
            result = {
                'name': self.name,
                'type': 'octoprint',
                'online': True,
                'state': state.get('text', 'unknown').lower() if isinstance(state, dict) else 'unknown',
                'progress': safe_round(progress.get('completion', 0)),
                'file': job.get('file', {}).get('name', '') if isinstance(job, dict) else '',
                'file_uploaded': job.get('file', {}).get('date', None) if isinstance(job, dict) else None,
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
                'position': position,
                'message': state.get('text', '') if isinstance(state, dict) else '',
                'ready': state.get('flags', {}).get('ready', False) if isinstance(state, dict) else False
            }
            
            # Add chamber temperatures if any were found
            if chamber_temps:
                result['chamber_temps'] = chamber_temps
                
            return result
            
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
    
    def reprint(self):
        """Reprint the last completed file using OctoPrint's API"""
        try:
            # Get current job information to find the last printed file
            job_status = self._make_request('api/job')
            if not job_status:
                return {'success': False, 'error': 'Could not get job information'}
            
            # Check if there's a current or recent job
            job = job_status.get('job', {})
            file_info = job.get('file', {})
            filename = file_info.get('name', '')
            
            if not filename:
                return {'success': False, 'error': 'No file found to reprint'}
            
            # Get file path for OctoPrint (usually in format "path/filename.gcode")
            file_path = file_info.get('path', filename)
            
            logger.info(f"Attempting to reprint file: {file_path}")
            
            # Start the print using OctoPrint's API
            response = self._make_request('api/files/local/' + file_path.replace('/', '%2F'), 
                                        method='POST', 
                                        data={'command': 'select', 'print': True})
            
            # Log the full response for debugging
            logger.info(f"OctoPrint reprint response: {response}")
            
            # OctoPrint typically returns 204 (no content) on success for this operation
            # If we get here without an exception, consider it successful
            return {'success': True}
                
        except Exception as e:
            logger.error(f"Error during reprint: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def set_temperature(self, heater_type, temperature, heater_name=None):
        """Set temperature for extruder, bed, or chamber heater"""
        try:
            temp = float(temperature)
            if temp < 0:
                temp = 0
        except (ValueError, TypeError):
            return {'success': False, 'error': 'Invalid temperature value'}
        
        try:
            if heater_type == 'extruder':
                # Set extruder temperature
                data = {'command': 'target', 'targets': {'tool0': temp}}
                response = self._make_request('api/printer/tool', method='POST', data=data)
            elif heater_type == 'bed':
                # Set bed temperature
                data = {'command': 'target', 'target': temp}
                response = self._make_request('api/printer/bed', method='POST', data=data)
            elif heater_type == 'chamber':
                # For OctoPrint chamber heaters, we need to use G-code commands
                # This assumes the chamber heater responds to M141 (chamber temperature)
                data = {'command': f'M141 S{temp}'}
                response = self._make_request('api/printer/command', method='POST', data=data)
            else:
                return {'success': False, 'error': 'Invalid heater type'}
            
            logger.info(f"{self.name} setting {heater_type} temperature to {temp}°C")
            
            # OctoPrint typically returns 204 (no content) on success
            if response is not None or hasattr(response, 'status_code'):
                return {'success': True, 'message': f'{heater_type.title()} temperature set to {temp}°C'}
            else:
                return {'success': False, 'error': 'Failed to set temperature'}
                
        except Exception as e:
            logger.error(f"Error setting temperature: {e}")
            return {'success': False, 'error': str(e)}

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
                # Use WebSocket API if available, otherwise fall back to regular HTTP API
                if MOONRAKER_API_AVAILABLE and config.get('use_websocket', True):
                    printer = KlipperWebSocketAPI(name, 'klipper', url, api_key)
                    logger.info(f"Using WebSocket API for {name}")
                else:
                    printer = KlipperAPI(name, 'klipper', url, api_key)
                    logger.info(f"Using HTTP API for {name}")
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
            elif action == 'reprint':
                result = printer.reprint()
            elif action == 'home':
                axes = kwargs.get('axes')
                result = printer.home_printer(axes)
            elif action == 'jog':
                axis = kwargs.get('axis')
                distance = kwargs.get('distance')
                if not axis or distance is None:
                    return {'success': False, 'error': 'Missing axis or distance for jog command'}
                result = printer.jog_printer(axis, distance)
            elif action == 'set_temperature':
                heater_type = kwargs.get('heater_type')
                temperature = kwargs.get('temperature')
                heater_name = kwargs.get('heater_name')
                if not heater_type or temperature is None:
                    return {'success': False, 'error': 'Missing heater_type or temperature for temperature command'}
                result = printer.set_temperature(heater_type, temperature, heater_name)
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
        # Get the absolute path to the root directory (one level up from app directory)
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        local_config = os.path.join(root_dir, 'options.json')
        
        # Check if we're in development mode (not in Home Assistant add-on)
        if os.path.exists(local_config):
            self.config_file = local_config
            logger.info(f"Running in development mode, using local config: {local_config}")
        else:
            self.config_file = '/data/options.json'
            logger.info("Running in production mode, using /data/options.json")
        
        logger.info(f"PrinterStorage initialized with config file: {self.config_file}")
        self._load_printers()
    
    def _load_printers(self):
        """Load and initialize printers from configuration"""
        printers_config = self.get_printers()
        printer_manager.printers.clear()
        
        for printer_config in printers_config:
            printer_manager.add_printer(printer_config)
    
    def get_printers(self):
        """Load printers from configuration file"""
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
    
    def get_temperature_presets(self):
        """Load temperature presets from configuration file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    
                    # Default presets
                    default_presets = {
                        'extruder': [0, 200, 220, 250],
                        'bed': [0, 60, 80, 100],
                        'chamber': [0, 40, 60, 80]
                    }
                    
                    # Get custom presets from config, fallback to defaults
                    presets = config.get('temperature_presets', default_presets)
                    
                    # Ensure all heater types have presets
                    for heater_type in default_presets:
                        if heater_type not in presets:
                            presets[heater_type] = default_presets[heater_type]
                    
                    logger.info(f"Loaded temperature presets: {presets}")
                    return presets
            else:
                logger.warning(f"Config file {self.config_file} does not exist, using default presets")
                return {
                    'extruder': [0, 200, 220, 250],
                    'bed': [0, 60, 80, 100],
                    'chamber': [0, 40, 60, 80]
                }
        except Exception as e:
            logger.error(f"Error loading temperature presets: {e}")
            return {
                'extruder': [0, 200, 220, 250],
                'bed': [0, 60, 80, 100],
                'chamber': [0, 40, 60, 80]
            }
    
    def get_room_light_entity(self):
        """Load room light entity from configuration file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    light_entity = config.get('room_light_entity', '')
                    logger.info(f"Loaded room light entity: {light_entity}")
                    return light_entity
            else:
                logger.warning(f"Config file {self.config_file} does not exist")
                return ''
        except Exception as e:
            logger.error(f"Error loading room light entity: {e}")
            return ''

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
    
    def _make_request(self, endpoint, method='GET', data=None, timeout=10):
        """Make HTTP request to Home Assistant API using internal URL"""
        try:
            headers = {
                'Authorization': f'Bearer {self.token}',
                'Content-Type': 'application/json',
                'Cache-Control': 'no-cache'
            }
            
            url = f"{self.internal_url}/api/{endpoint.lstrip('/')}"
            
            # Add cache-busting parameter for state requests
            if 'states/' in endpoint and method == 'GET':
                url += f"?_={int(time.time() * 1000)}"
            
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method == 'POST':
                response = requests.post(url, headers=headers, json=data, timeout=timeout)
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

@app.route('/api/printer/<printer_name>/print/<action>', methods=['POST'])
def printer_print_control(printer_name, action):
    """API endpoint to control print jobs (pause, resume, cancel)"""
    try:
        logger.info(f"Print control request: {printer_name} -> {action}")
        
        # Validate action
        allowed_actions = ['pause', 'resume', 'cancel', 'reprint']
        if action not in allowed_actions:
            return jsonify({'success': False, 'error': f'Invalid action: {action}. Allowed: {allowed_actions}'}), 400
        
        result = printer_manager.control_printer(printer_name, action)
        logger.info(f"Print control result: {result}")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error controlling print on {printer_name}: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/printer/<printer_name>/temperature', methods=['POST'])
def set_printer_temperature(printer_name):
    """Set temperature for extruder, bed, or chamber"""
    try:
        data = request.get_json() or {}
        heater_type = data.get('heater_type')
        temperature = data.get('temperature')
        heater_name = data.get('heater_name')  # For chamber heaters that need specific heater names
        
        if not heater_type or temperature is None:
            return jsonify({'success': False, 'error': 'Missing heater_type or temperature'}), 400
        
        logger.info(f"Temperature control request: {printer_name} -> {heater_type} = {temperature}°C")
        
        result = printer_manager.control_printer(printer_name, 'set_temperature', 
                                               heater_type=heater_type, 
                                               temperature=temperature,
                                               heater_name=heater_name)
        logger.info(f"Temperature control result: {result}")
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error setting temperature: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/temperature-presets')
def get_temperature_presets():
    """Get temperature presets from configuration"""
    try:
        presets = storage.get_temperature_presets()
        return jsonify({'success': True, 'presets': presets})
    except Exception as e:
        logger.error(f"Error getting temperature presets: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/room-light/status')
def get_room_light_status():
    """Get the current status of the configured room light entity"""
    try:
        # Get light entity from configuration
        light_entity = storage.get_room_light_entity()
        if not light_entity:
            return jsonify({'success': False, 'error': 'No room light entity configured'}), 400
        
        logger.info(f"Getting status for light entity: {light_entity}")
        
        # Get light state from Home Assistant
        entity_state = ha_api._make_request(f'states/{light_entity}')
        if not entity_state:
            return jsonify({'success': False, 'error': 'Failed to get light status from Home Assistant'}), 500
        
        # Extract light state information
        state = entity_state.get('state', 'unknown')
        attributes = entity_state.get('attributes', {})
        
        light_status = {
            'entity_id': light_entity,
            'state': state,
            'is_on': state == 'on',
            'brightness': attributes.get('brightness'),
            'friendly_name': attributes.get('friendly_name', light_entity),
            'last_changed': entity_state.get('last_changed'),
            'last_updated': entity_state.get('last_updated')
        }
        
        logger.info(f"Light status: {light_status}")
        return jsonify({'success': True, 'light': light_status})
        
    except Exception as e:
        logger.error(f"Error getting room light status: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/room-light/control', methods=['POST'])
def control_room_light():
    """Control the configured room light entity (turn on/off)"""
    try:
        # Get light entity from configuration
        light_entity = storage.get_room_light_entity()
        if not light_entity:
            return jsonify({'success': False, 'error': 'No room light entity configured'}), 400
        
        # Get action from request
        data = request.get_json() or {}
        action = data.get('action')  # 'turn_on' or 'turn_off'
        
        if action not in ['turn_on', 'turn_off']:
            return jsonify({'success': False, 'error': 'Invalid action. Use "turn_on" or "turn_off"'}), 400
        
        logger.info(f"Controlling light {light_entity}: {action}")
        
        # Call Home Assistant service
        service_data = {
            'entity_id': light_entity
        }
        
        # Add brightness if turning on and provided
        if action == 'turn_on' and 'brightness' in data:
            service_data['brightness'] = data['brightness']
        
        # Make service call to Home Assistant
        service_response = ha_api._make_request(f'services/light/{action}', method='POST', data=service_data)
        
        logger.info(f"Light control response: {service_response}")
        
        # Return success (Home Assistant typically returns empty response for successful service calls)
        return jsonify({'success': True, 'action': action, 'entity_id': light_entity})
        
    except Exception as e:
        logger.error(f"Error controlling room light: {e}")
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

# Helper to fetch and proxy remote thumbnail images

def _proxy_thumbnail(remote_url: str, headers=None, timeout: int = 10):
    """Fetch a remote image and return (bytes, content_type) or (None, None) on failure."""
    try:
        resp = requests.get(remote_url, headers=headers or {}, timeout=timeout, stream=True)
        resp.raise_for_status()
        content_type = resp.headers.get('Content-Type', 'image/png')
        data = resp.content
        return data, content_type
    except Exception as e:
        logger.error(f"Failed to proxy thumbnail from {remote_url}: {e}")
        return None, None


@app.route('/api/thumbnail/<printer_name>')
def get_thumbnail(printer_name):
    """Get print thumbnail for current job"""
    try:
        if printer_name not in printer_manager.printers:
            return jsonify({'error': 'Printer not found'}), 404
            
        printer = printer_manager.printers[printer_name]
        
        # Get current status to find filename
        status = printer.get_status()
        if not status or not status.get('online', False):
            return jsonify({'error': 'Printer offline'}), 503
        
        filename = status.get('file', '').strip()
        if not filename:
            return jsonify({'error': 'No active print job'}), 404
        
        # Try to get thumbnail using enhanced WebSocket API if available
        thumbnail_data = None
        if hasattr(printer, 'get_thumbnail'):
            try:
                thumbnail_data = printer.get_thumbnail(filename)
            except Exception as e:
                logger.error(f"Enhanced thumbnail retrieval failed for {printer_name}: {e}")
        
        # Fallback to original thumbnail retrieval method for Klipper
        if not thumbnail_data and printer.printer_type == 'klipper':
            try:
                # Get file metadata first
                metadata_response = printer._make_request(f'server/files/metadata?filename={filename}')
                if not metadata_response or 'result' not in metadata_response:
                    return jsonify({'error': 'Could not get file metadata'}), 404
                    
                metadata = metadata_response['result']
                thumbnails = metadata.get('thumbnails', [])
                
                if not thumbnails:
                    return jsonify({'error': 'No thumbnails available'}), 404
                
                # Get the largest thumbnail
                largest_thumb = max(thumbnails, key=lambda t: t.get('width', 0) * t.get('height', 0))
                thumb_path = largest_thumb.get('relative_path')
                
                if not thumb_path:
                    return jsonify({'error': 'No valid thumbnail path'}), 404
                
                # Download thumbnail
                thumb_url = f"{printer.url.rstrip('/')}/server/files/gcodes/{thumb_path}"
                response = requests.get(thumb_url, timeout=10)
                
                if response.status_code == 200:
                    thumbnail_data = response.content
                
            except Exception as e:
                logger.error(f"Fallback thumbnail retrieval failed for {printer_name}: {e}")
        
        # Handle OctoPrint thumbnails
        elif not thumbnail_data and printer.printer_type == 'octoprint':
            try:
                # OctoPrint file metadata contains a direct thumbnail URL
                import urllib.parse
                meta_endpoint = f"api/files/local/{urllib.parse.quote(filename, safe='')}"
                meta = printer._make_request(meta_endpoint)
                
                if meta:
                    thumb_path = meta.get('thumbnail')
                    if thumb_path:
                        # Construct thumbnail URL
                        if thumb_path.startswith('/'):
                            thumb_url = f"{printer.url}{thumb_path}"
                        else:
                            thumb_url = f"{printer.url}/{thumb_path}"
                        
                        # Set up headers for OctoPrint
                        headers = {}
                        if printer.api_key:
                            headers['X-Api-Key'] = printer.api_key
                        
                        # Download thumbnail
                        response = requests.get(thumb_url, headers=headers, timeout=10)
                        if response.status_code == 200:
                            thumbnail_data = response.content
                            
            except Exception as e:
                logger.error(f"OctoPrint thumbnail retrieval failed for {printer_name}: {e}")
        
        # Return thumbnail or placeholder
        if thumbnail_data:
            # Determine content type based on data
            content_type = 'image/jpeg'  # Default
            if thumbnail_data.startswith(b'\x89PNG'):
                content_type = 'image/png'
            elif thumbnail_data.startswith(b'GIF'):
                content_type = 'image/gif'
            
            return Response(thumbnail_data, mimetype=content_type)
        else:
            # Return placeholder transparent PNG (1×1)
            placeholder_png = base64.b64decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg=='
            )
            return Response(placeholder_png, mimetype='image/png')
            
    except Exception as e:
        logger.error(f"Error getting thumbnail for {printer_name}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/thumbnail-enhanced/<printer_name>/<filename>')
def get_thumbnail_enhanced(printer_name, filename):
    """Enhanced thumbnail endpoint with WebSocket API support"""
    try:
        if printer_name not in printer_manager.printers:
            return jsonify({'error': 'Printer not found'}), 404
            
        printer = printer_manager.printers[printer_name]
        
        # Check if printer supports enhanced thumbnail retrieval
        if hasattr(printer, 'get_thumbnail'):
            try:
                thumbnail_data = printer.get_thumbnail(filename)
                if thumbnail_data:
                    # Determine content type
                    content_type = 'image/jpeg'  # Default
                    if thumbnail_data.startswith(b'\x89PNG'):
                        content_type = 'image/png'
                    elif thumbnail_data.startswith(b'GIF'):
                        content_type = 'image/gif'
                    
                    return Response(thumbnail_data, mimetype=content_type)
            except Exception as e:
                logger.error(f"Enhanced thumbnail retrieval failed: {e}")
        
        return jsonify({'error': 'Thumbnail not available or unsupported'}), 404
        
    except Exception as e:
        logger.error(f"Error in enhanced thumbnail endpoint: {e}")
        return jsonify({'error': str(e)}), 500

############################################
# G-code upload and dispatch endpoints
############################################

ALLOWED_GCODE_EXT = {'.gcode', '.gco', '.gc'}

def _is_allowed_gcode(filename: str) -> bool:
    _, ext = os.path.splitext(filename.lower())
    return ext in ALLOWED_GCODE_EXT

@app.route('/api/gcode/files')
def list_gcode_files():
    """Return list of gcode files available on the server."""
    try:
        files = []
        for fname in os.listdir(GCODE_STORAGE_DIR):
            if _is_allowed_gcode(fname):
                size = os.path.getsize(os.path.join(GCODE_STORAGE_DIR, fname))
                files.append({'name': fname, 'size': size})
        return jsonify(sorted(files, key=lambda f: f['name'].lower()))
    except Exception as e:
        logger.error(f"Error listing gcode files: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/gcode/upload', methods=['POST'])
def upload_gcode():
    """Upload a gcode file to the server storage."""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file part'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No selected file'}), 400

        filename = secure_filename(file.filename)
        if not _is_allowed_gcode(filename):
            return jsonify({'success': False, 'error': 'Invalid file extension'}), 400

        save_path = os.path.join(GCODE_STORAGE_DIR, filename)
        file.save(save_path)
        logger.info(f"Saved uploaded gcode to {save_path}")
        return jsonify({'success': True, 'file': filename})
    except Exception as e:
        logger.error(f"Error uploading gcode: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Add error handler for file upload size limit
@app.errorhandler(413)
def too_large(e):
    logger.error("File upload too large - 413 error")
    return jsonify({'success': False, 'error': 'File too large. Maximum size is 100MB.'}), 413

@app.route('/api/gcode/send', methods=['POST'])
def send_gcode_to_printer():
    """Send an existing gcode file to a specified printer and optionally start the print."""
    try:
        data = request.get_json() or {}
        printer_name = data.get('printer')
        file_name = data.get('file')
        start_print = bool(data.get('start', True))

        if not printer_name or not file_name:
            return jsonify({'success': False, 'error': 'Missing printer or file parameter'}), 400

        if printer_name not in printer_manager.printers:
            return jsonify({'success': False, 'error': 'Printer not found'}), 404

        local_path = os.path.join(GCODE_STORAGE_DIR, file_name)
        if not os.path.isfile(local_path):
            return jsonify({'success': False, 'error': 'File not found on server'}), 404

        printer = printer_manager.printers[printer_name]

        with open(local_path, 'rb') as f:
            files = {'file': (file_name, f, 'application/octet-stream')}
            if printer.printer_type == 'klipper':
                headers = {}
                if printer.api_key:
                    headers['Authorization'] = f'Bearer {printer.api_key}'
                upload_url = f"{printer.url}/server/files/upload"
                logger.info(f"Uploading {file_name} to {printer_name} at {upload_url}")
                resp = requests.post(upload_url, headers=headers, files=files, timeout=120)
                resp.raise_for_status()
                if start_print:
                    # start the print
                    start_url = f"{printer.url}/printer/print/start"
                    data_json = {'filename': file_name}
                    req_headers = headers.copy()
                    req_headers['Content-Type'] = 'application/json'
                    requests.post(start_url, headers=req_headers, json=data_json, timeout=10)
            elif printer.printer_type == 'octoprint':
                headers = {'X-Api-Key': printer.api_key} if printer.api_key else {}
                upload_url = f"{printer.url}/api/files/local"
                logger.info(f"Uploading {file_name} to OctoPrint {printer_name}")
                
                # Prepare form data for OctoPrint
                form_data = {}
                if start_print:
                    form_data['print'] = 'true'  # Tell OctoPrint to start printing immediately
                
                resp = requests.post(upload_url, headers=headers, files=files, data=form_data, timeout=120)
                logger.info(f"OctoPrint upload response: {resp.status_code}")
                if resp.text:
                    logger.info(f"OctoPrint upload response body: {resp.text}")
                resp.raise_for_status()
                
                # If not starting print immediately, we need to select and start it manually
                if not start_print:
                    # File uploaded but not printing - could add manual selection logic here if needed
                    pass
            else:
                return jsonify({'success': False, 'error': 'Unsupported printer type'}), 400

        return jsonify({'success': True})

    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP error sending gcode to printer: {e}")
        return jsonify({'success': False, 'error': str(e)}), 502
    except Exception as e:
        logger.error(f"Error sending gcode to printer: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/gcode/files/<path:filename>', methods=['DELETE'])
def delete_gcode_file(filename):
    """Delete a stored G-code file."""
    safe_name = secure_filename(filename)
    path = os.path.join(GCODE_STORAGE_DIR, safe_name)
    if not os.path.exists(path):
        return jsonify({'success': False, 'error': 'File not found'}), 404
    try:
        os.remove(path)
        logger.info(f"Deleted G-code file {path}")
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Delete failed for {path}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    logger.info("Starting Print Farm Dashboard Flask app...")
    from waitress import serve
    logger.info("Using Waitress production WSGI server")
    serve(app, host='127.0.0.1', port=5001, threads=6) 