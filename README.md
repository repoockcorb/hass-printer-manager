# Print Farm Dashboard

Advanced print farm management Home Assistant add-on with direct Moonraker and OctoPrint API integration. This add-on transforms your Home Assistant into a comprehensive 3D printer management system similar to AutoFarm3D.

## Features

- **Real-time Monitoring**: Live status updates for all your 3D printers
- **Multi-Platform Support**: Works with both Klipper (via Moonraker) and OctoPrint printers
- **Modern Web Interface**: Beautiful, responsive dashboard with real-time updates
- **Print Control**: Pause, resume, and cancel prints directly from the dashboard  
- **Temperature Control**: Click any temperature display to set target temperatures
- **Custom Temperature Presets**: Configure custom temperature presets for extruder, bed, and chamber
- **Chamber Temperature Support**: Automatic detection and display of chamber temperature sensors
- **Comprehensive Status**: View temperatures, progress, positions, and print times
- **Filtering & Search**: Filter printers by status and type
- **Auto-refresh**: Configurable auto-refresh with pause when tab is not active
- **Mobile Responsive**: Works perfectly on desktop, tablet, and mobile devices

## Screenshots

The dashboard provides a card-based layout showing:
- Printer status and connectivity
- Current print progress with visual progress bars
- Real-time temperature monitoring (extruder and bed)
- Print time and remaining time estimates
- Current XYZ positions
- Control buttons for print management

## Installation

1. Add this repository to your Home Assistant Add-on Store
2. Install the "Print Farm Dashboard" add-on
3. Configure your printers in the add-on configuration
4. Start the add-on
5. Access the dashboard through the Web UI or Home Assistant sidebar

## Configuration

### Basic Configuration

Add your printers to the configuration. Here's an example setup:

```yaml
printers:
  - name: "Ender 3 Pro"
    type: "klipper"
    url: "http://192.168.1.100"
    api_key: "your_moonraker_api_key_if_required"
    
  - name: "Prusa MK3S"
    type: "octoprint"
    url: "http://192.168.1.101"
    api_key: "your_octoprint_api_key"
    
  - name: "Voron 2.4"
    type: "klipper"
    url: "http://voron.local"

temperature_presets:
  extruder: [0, 180, 200, 215, 220, 230, 250]
  bed: [0, 50, 60, 70, 80, 90, 100]
  chamber: [0, 35, 40, 45, 50, 60]
```

### Configuration Options

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| `name` | string | Yes | Display name for the printer |
| `type` | string | Yes | Printer type: `klipper` or `octoprint` |
| `url` | string | Yes | Base URL of the printer (Moonraker or OctoPrint) |
| `api_key` | string | No | API key for authentication (if required) |
| `camera_entity` | string | No | Home Assistant camera entity ID |

### Temperature Presets

Configure custom temperature presets for quick access:

| Option | Type | Description | Default |
|--------|------|-------------|---------|
| `temperature_presets.extruder` | array | Extruder temperature presets in °C | `[0, 200, 220, 250]` |
| `temperature_presets.bed` | array | Bed temperature presets in °C | `[0, 60, 80, 100]` |
| `temperature_presets.chamber` | array | Chamber temperature presets in °C | `[0, 40, 60, 80]` |

### Klipper/Moonraker Setup

For Klipper printers with Moonraker:

1. **URL Format**: Use the Moonraker URL (typically port 7125)
   ```
   http://your-printer-ip:7125
   ```

2. **API Key**: Usually not required for local network access, but can be configured in Moonraker if needed

3. **Moonraker Configuration**: Ensure your moonraker.conf has CORS enabled:
   ```ini
   [authorization]
   cors_domains:
       http://homeassistant.local:8123
       http://your-ha-ip:8123
   ```

### OctoPrint Setup  

For OctoPrint printers:

1. **URL Format**: Use the OctoPrint URL (typically port 80 or 5000)
   ```
   http://your-printer-ip
   ```

2. **API Key**: Required - get this from OctoPrint Settings > API
   
3. **CORS Configuration**: Add your Home Assistant URL to OctoPrint's CORS settings

## API Endpoints

The add-on exposes several API endpoints:

- `GET /api/printers` - Get printer configurations
- `GET /api/status` - Get status for all printers  
- `GET /api/status/<printer_name>` - Get status for specific printer
- `POST /api/control/<printer_name>/<action>` - Control printer (pause/resume/cancel)
- `POST /api/printer/<printer_name>/temperature` - Set printer temperatures
- `GET /api/temperature-presets` - Get configured temperature presets
- `GET /api/health` - Health check endpoint

## Supported Printer States

### Klipper/Moonraker States
- `ready` - Printer is ready for commands
- `printing` - Currently printing
- `paused` - Print is paused
- `complete` - Print completed successfully
- `cancelled` - Print was cancelled
- `error` - Printer error state
- `offline` - Cannot connect to printer

### OctoPrint States  
- `operational` - Printer is ready
- `printing` - Currently printing
- `paused` - Print is paused
- `cancelling` - Print is being cancelled
- `error` - Printer error state
- `offline` - Cannot connect to printer

## Troubleshooting

### Common Issues

1. **Printer shows as offline**
   - Check if the URL is correct and accessible
   - Verify the printer is powered on and connected to network
   - Check firewall settings

2. **API authentication errors**
   - Verify API key is correct for OctoPrint printers
   - Check CORS settings in Moonraker/OctoPrint

3. **Slow updates**
   - Check network connectivity to printers
   - Increase update interval if needed
   - Verify printer APIs are responding quickly

### Debug Mode

Enable debug logging in the add-on configuration to see detailed API communication:

```yaml
log_level: debug
```

### Network Configuration

Ensure your Home Assistant instance can reach all configured printers:

1. **Same Network**: Printers should be on the same network as Home Assistant
2. **Firewall**: Check that required ports are open
3. **DNS**: Use IP addresses if hostname resolution fails

## Contributing

This add-on is open source. Feel free to contribute improvements, bug fixes, or new features.

## Support

For issues and support:
1. Check the troubleshooting section above
2. Enable debug logging to get detailed error information  
3. Create an issue with logs and configuration details

## Changelog

### Version 4.3.0
- **Temperature Control**: Click any temperature display to set target temperatures
- **Configurable Temperature Presets**: Add custom temperature presets via Home Assistant add-on configuration
- **Chamber Temperature Support**: Automatic detection and display of chamber temperature sensors
- **Enhanced Configuration UI**: Temperature presets now configurable through Home Assistant add-on manager
- **Improved Documentation**: Comprehensive configuration guide and examples

### Version 4.2.x
- WebSocket support for Klipper printers
- Enhanced thumbnail support
- Production server deployment
- Bug fixes and stability improvements

### Version 2.0.0
- Complete rewrite with direct API integration
- Modern responsive web interface
- Real-time status updates
- Print control functionality
- Support for both Klipper and OctoPrint
- Enhanced error handling and logging

### Version 1.x
- Legacy iframe-based implementation 