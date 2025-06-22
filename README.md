# Printer Dashboard - Home Assistant Add-on

A comprehensive printer management dashboard for Home Assistant that allows you to manage multiple 3D printer interfaces like Mainsail, OctoPrint, and custom web interfaces in a unified tabbed interface.

## Features

- 🖨️ **Multiple Printer Support** - Add unlimited printers (Mainsail, OctoPrint, custom URLs)
- 🏠 **Home Assistant Integration** - Uses HA authentication and database
- 🔒 **Secure Access** - Protected by Home Assistant's authentication system
- 💾 **Persistent Storage** - Data stored in Home Assistant's database
- 📱 **Responsive Design** - Works on desktop, tablet, and mobile
- ⚡ **Real-time Loading** - Fast iframe loading with loading indicators
- 🎨 **Modern UI** - Beautiful, intuitive interface with smooth animations
- 🔧 **Easy Management** - Add, remove, and organize printers easily

## Installation

### Method 1: Add Repository to Supervisor

1. In Home Assistant, go to **Supervisor** → **Add-on Store**
2. Click the menu (⋮) in the top right → **Repositories**
3. Add this repository URL: `https://github.com/yourusername/printer-dashboard-addon`
4. Find "Printer Dashboard" in the add-on store
5. Click **Install**

### Method 2: Manual Installation

1. Copy this entire folder to `/addons/printer_dashboard/` in your Home Assistant config directory
2. Restart Home Assistant
3. Go to **Supervisor** → **Add-on Store** → **Local Add-ons**
4. Find "Printer Dashboard" and click **Install**

## Configuration

The add-on supports the following configuration options:

```yaml
ssl: false
certfile: fullchain.pem
keyfile: privkey.pem
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `ssl` | boolean | `false` | Enable SSL/TLS encryption |
| `certfile` | string | `fullchain.pem` | SSL certificate file |
| `keyfile` | string | `privkey.pem` | SSL private key file |

## Usage

### Starting the Add-on

1. Install and configure the add-on
2. Click **Start**
3. Access the dashboard via:
   - **Web UI** button in the add-on page
   - Direct URL: `http://your-ha-ip:8099`
   - Ingress URL (appears in sidebar when enabled)

### Adding Printers

1. Click the **"+ Add Printer"** button
2. Fill in the details:
   - **Printer Name**: A friendly name for your printer
   - **Printer Type**: Choose from Mainsail, OctoPrint, or Custom URL
   - **Printer URL**: The full URL to your printer interface
3. Click **"Add Printer"**

### Managing Printers

- **Switch between printers**: Click the tabs at the top
- **Remove a printer**: Click the ✕ on the printer's tab
- **Export settings**: Right-click the header → Export Settings
- **Import settings**: Right-click the header → Import Settings

### Keyboard Shortcuts

- **Ctrl/Cmd + K**: Add new printer
- **Ctrl/Cmd + 1-9**: Switch between printer tabs

## Authentication

The add-on uses Home Assistant's built-in authentication system:

- **Ingress Mode**: Automatically authenticated through Home Assistant
- **Direct Access**: Requires Home Assistant access token
- **Panel Mode**: Uses Home Assistant's session authentication

## Data Storage

All printer configurations are stored in the add-on's data directory (`/data/printers.json`), which persists across restarts and updates.

## API Endpoints

The add-on provides a REST API for managing printers:

- `GET /api/printers` - List all printers
- `POST /api/printers` - Add a new printer
- `PUT /api/printers/<id>` - Update a printer
- `DELETE /api/printers/<id>` - Remove a printer
- `GET /api/health` - Health check

## Troubleshooting

### Add-on Won't Start

1. Check the logs in the add-on page
2. Ensure port 8099 is available
3. Verify Home Assistant has sufficient resources

### Can't Access Printer Interfaces

1. Verify the printer URLs are correct and accessible
2. Check if the printers are on the same network
3. Ensure no firewall is blocking the connections

### Authentication Issues

1. Restart the add-on
2. Clear browser cache and cookies
3. Check Home Assistant authentication settings

## Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/printer-dashboard-addon/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/printer-dashboard-addon/discussions)
- **Home Assistant Community**: [Community Forum](https://community.home-assistant.io/)

## Screenshots

![Printer Dashboard Welcome Screen](screenshots/welcome.png)
![Multiple Printers View](screenshots/printers.png)
![Add Printer Modal](screenshots/add-printer.png)

## Changelog

### v1.0.0
- Initial release
- Home Assistant authentication integration
- Multiple printer support
- Modern responsive UI
- REST API backend
- Export/import functionality

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## Credits

- Built with Flask and modern web technologies
- Uses Home Assistant's authentication system
- Designed for the 3D printing community 