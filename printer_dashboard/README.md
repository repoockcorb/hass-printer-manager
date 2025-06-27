![HAFarm3D Logo](printer_dashboard/static/HAFarm3D.png)

# Print Farm Dashboard

Advanced print farm management with direct Moonraker and OctoPrint API integration, now with Home Assistant camera support!

## Features

- **Real-time Status Monitoring** - Live updates for printer status, temperatures, progress, and more
- **Multi-Printer Support** - Manage multiple Klipper and OctoPrint printers from one interface
- **Print Control** - Pause, resume, and cancel prints directly from the dashboard
- **Camera Integration** - View live camera feeds from Home Assistant camera entities
- **Modern UI** - Beautiful, responsive interface with dark theme
- **Auto-refresh** - Automatic status updates every 10 seconds
- **Filtering** - Filter printers by status and type

## Camera Feature

The dashboard now supports displaying camera feeds for each printer using Home Assistant camera entities. 

### Setup

1. Configure your cameras in Home Assistant
2. Add the `camera_entity` field to your printer configuration
3. Set up Home Assistant API access (automatically configured when running as a Home Assistant add-on)

### Example Configuration

```yaml
printers:
  - name: "Ender 3 Pro"
    type: "klipper"
    url: "http://192.168.1.100"
    api_key: "your-api-key"
    camera_entity: "camera.ender3_camera"
  
  - name: "Prusa i3 MK3S"
    type: "octoprint"
    url: "http://192.168.1.101"
    api_key: "your-octoprint-api-key"
    camera_entity: "camera.prusa_webcam"

home_assistant:
  url: "http://supervisor/core"  # Auto-configured for HA add-on
  token: ""  # Auto-configured for HA add-on
```

### Camera Features

- **Live Preview** - Click the camera button on any printer card to view the camera feed
- **Auto-refresh** - Camera snapshots refresh every 3 seconds
- **Full-screen Modal** - Large, clear view of your printer's camera
- **Error Handling** - Graceful fallback when cameras are unavailable

## Screenshots

The dashboard provides a card-based layout showing:
- Printer status and connectivity
- Current print progress with visual progress bars
- Real-time temperature monitoring (extruder and bed)
- Print time and remaining time estimates
- Current XYZ positions
- Control buttons for print management

## Installation

### Home Assistant Add-on (Recommended)

1. Add this repository to your Home Assistant add-on store
2. Install the "Print Farm Dashboard" add-on
3. Configure your printers in the add-on configuration
4. Start the add-on

### Manual Installation

1. Clone this repository
2. Install dependencies: `pip install -r requirements.txt`
3. Create configuration file (see example above)
4. Run: `python app/app.py`

## Configuration

The dashboard supports both Klipper (via Moonraker) and OctoPrint printers. Each printer can optionally have a camera entity configured.

### Required Fields
- `name`: Display name for the printer
- `type`: Either "klipper" or "octoprint"
- `url`: Base URL of the printer API

### Optional Fields
- `api_key`: API key for authentication (required for OctoPrint)
- `camera_entity`: Home Assistant camera entity ID

## API Endpoints

- `GET /api/printers` - Get all printer configurations
- `GET /api/status` - Get status for all printers
- `GET /api/status/<printer_name>` - Get status for specific printer
- `POST /api/control/<printer_name>/<action>` - Control printer (pause/resume/cancel)
- `GET /api/camera/<printer_name>/stream` - Get camera stream URL
- `GET /api/camera/<printer_name>/snapshot` - Get camera snapshot URL

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

For issues and feature requests, please check the GitHub repository.

## Changelog

### Version 2.0.0
- Complete rewrite with direct API integration
- Modern responsive web interface
- Real-time status updates
- Print control functionality
- Support for both Klipper and OctoPrint
- Enhanced error handling and logging

### Version 1.x
- Legacy iframe-based implementation 