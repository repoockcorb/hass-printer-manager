# Print Farm Dashboard Configuration

This document explains all configuration options available in the Home Assistant add-on.

## Configuration Overview

The Print Farm Dashboard add-on can be configured through the Home Assistant add-on manager interface. All configuration is done via the "Configuration" tab in the add-on page.

## Printer Configuration

### Basic Printer Setup

Each printer requires the following basic configuration:

```yaml
printers:
  - name: "My Printer Name"
    type: "klipper"  # or "octoprint"
    url: "http://192.168.1.100:7125"
    api_key: ""  # Optional for Klipper, required for OctoPrint
    camera_entity: "camera.my_printer_cam"  # Optional Home Assistant camera
```

### Printer Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Display name for the printer |
| `type` | string | Yes | Printer type: `klipper` or `octoprint` |
| `url` | string | Yes | Full URL to printer API (including port) |
| `api_key` | string | No | API key (required for OctoPrint, optional for Klipper) |
| `camera_entity` | string | No | Home Assistant camera entity ID |

### Printer Type Details

#### Klipper Printers
- **URL Format**: `http://IP_ADDRESS:7125` (Moonraker default port)
- **API Key**: Optional, only needed if Moonraker requires authentication
- **Features**: WebSocket support, direct G-code commands, enhanced thumbnails

#### OctoPrint Printers  
- **URL Format**: `http://IP_ADDRESS` (default port 80) or `http://IP_ADDRESS:5000`
- **API Key**: Required - found in OctoPrint Settings → API
- **Features**: Standard OctoPrint API integration

## Temperature Presets Configuration

Configure custom temperature presets for quick access when setting temperatures:

```yaml
temperature_presets:
  extruder: [0, 180, 200, 215, 220, 230, 250, 260]
  bed: [0, 50, 60, 70, 80, 90, 100, 110]
  chamber: [0, 35, 40, 45, 50, 60, 70, 80]
```

### Temperature Preset Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `extruder` | array of integers | Hotend temperature presets in °C | `[0, 200, 220, 250]` |
| `bed` | array of integers | Bed temperature presets in °C | `[0, 60, 80, 100]` |
| `chamber` | array of integers | Chamber temperature presets in °C | `[0, 40, 60, 80]` |

### Temperature Preset Examples

#### Basic Configuration
```yaml
temperature_presets:
  extruder: [0, 200, 220]
  bed: [0, 60, 80]
  chamber: [0, 40]
```

#### Multi-Material Setup
```yaml
temperature_presets:
  extruder: [0, 180, 200, 215, 220, 230, 240, 250, 260, 280]
  bed: [0, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 100, 110]
  chamber: [0, 30, 35, 40, 45, 50, 55, 60, 65, 70]
```

#### PLA-Only Printer
```yaml
temperature_presets:
  extruder: [0, 185, 195, 205, 215]
  bed: [0, 50, 55, 60, 65]
  chamber: [0]
```

## Home Assistant Integration

Configure Home Assistant API access for camera feeds and entity integration:

```yaml
home_assistant:
  url: "http://supervisor/core"  # Default for add-on
  token: ""  # Usually auto-configured
```

### Home Assistant Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `url` | string | Home Assistant API URL | `http://supervisor/core` |
| `token` | string | Long-lived access token | Auto-configured |

## Complete Configuration Example

```yaml
printers:
  - name: "Ender 3 V2"
    type: "klipper"
    url: "http://192.168.1.100:7125"
    api_key: ""
    camera_entity: "camera.ender3_camera"
  - name: "Prusa MK3S"
    type: "octoprint"
    url: "http://192.168.1.101"
    api_key: "your-octoprint-api-key-here"
    camera_entity: "camera.prusa_camera"
  - name: "Voron 2.4"
    type: "klipper"
    url: "http://192.168.1.102:7125"
    api_key: ""
    camera_entity: "camera.voron_camera"

home_assistant:
  url: "http://supervisor/core"
  token: ""

temperature_presets:
  extruder: [0, 180, 200, 215, 220, 230, 250, 260]
  bed: [0, 50, 60, 70, 80, 90, 100, 110]
  chamber: [0, 35, 40, 45, 50, 60, 70, 80]
```

## Configuration Tips

### Network Discovery
- Use Home Assistant's network discovery to find printer IP addresses
- Check your router's DHCP client list for printer hostnames
- Use tools like `nmap` to scan your network: `nmap -sn 192.168.1.0/24`

### Camera Integration
- Camera entities must be configured in Home Assistant first
- Use generic camera integration for IP cameras
- MJPEG streams work best for real-time viewing

### API Keys
- **Klipper**: API keys are optional unless you've configured authentication
- **OctoPrint**: API keys are required and found in Settings → API → Global API Key

### Troubleshooting
- Check printer URLs are accessible from Home Assistant
- Verify API keys are correct and have proper permissions
- Ensure camera entities exist and are working in Home Assistant
- Check Home Assistant logs for connection errors

## Advanced Configuration

### Custom Ports
If your printers use non-standard ports:
```yaml
printers:
  - name: "Custom Port Printer"
    type: "klipper"
    url: "http://192.168.1.100:8080"  # Custom port
```

### SSL/HTTPS
For printers with SSL certificates:
```yaml
printers:
  - name: "Secure Printer"
    type: "klipper"
    url: "https://printer.local:7125"
```

### Multiple Instances
You can configure multiple instances of the same printer type:
```yaml
printers:
  - name: "Printer Farm A1"
    type: "klipper"
    url: "http://192.168.1.100:7125"
  - name: "Printer Farm A2" 
    type: "klipper"
    url: "http://192.168.1.101:7125"
  - name: "Printer Farm A3"
    type: "klipper"
    url: "http://192.168.1.102:7125"
``` 