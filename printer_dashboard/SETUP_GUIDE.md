# Complete Setup Guide - Printer Dashboard Home Assistant Addon

This guide will walk you through creating and installing your Printer Dashboard addon from scratch.

## 📋 Prerequisites

- Home Assistant OS or Supervised installation
- Access to Home Assistant Supervisor
- GitHub account (for hosting the addon repository)
- Basic understanding of file management

## 🚀 Part 1: Create the Addon Repository

### Step 1: Create GitHub Repository

1. **Go to GitHub** and create a new repository:
   - Repository name: `printer-dashboard-addon`
   - Description: `Home Assistant addon for managing multiple 3D printer interfaces`
   - Set to **Public** (required for HA addon repositories)
   - Initialize with README ✅

2. **Clone the repository** to your computer:
   ```bash
   git clone https://github.com/yourusername/printer-dashboard-addon.git
   cd printer-dashboard-addon
   ```

### Step 2: Create Addon Directory Structure

Create the following folder structure in your repository:

```
printer-dashboard-addon/
├── printer_dashboard/          # Main addon folder
│   ├── config.yaml
│   ├── Dockerfile
│   ├── run.sh
│   ├── nginx.conf
│   ├── README.md
│   ├── CHANGELOG.md
│   ├── icon.png
│   ├── logo.png
│   └── app/
│       ├── app.py
│       ├── templates/
│       │   └── index.html
│       └── static/
│           ├── script.js
│           └── styles.css
├── repository.yaml             # Repository configuration
└── README.md                   # Repository README
```

### Step 3: Create Repository Configuration

Create `repository.yaml` in the root:

```yaml
name: "Printer Dashboard Add-on Repository"
url: "https://github.com/yourusername/printer-dashboard-addon"
maintainer: "Your Name <your.email@example.com>"
```

### Step 4: Upload All Files

1. **Copy all the addon files** we created into the `printer_dashboard/` folder
2. **Update the URLs** in the files to match your GitHub username:
   - In `config.yaml`: Update the `url` and `image` fields
   - In `README.md`: Update all GitHub URLs
   - In `app.py`: Update maintainer email

3. **Commit and push** to GitHub:
   ```bash
   git add .
   git commit -m "Initial addon release"
   git push origin main
   ```

## 🏠 Part 2: Install in Home Assistant

### Method A: Via Supervisor (Recommended)

#### Step 1: Add Repository to Home Assistant

1. **Open Home Assistant** in your browser
2. **Navigate to Supervisor**:
   - Click **Supervisor** in the sidebar
   - Click **Add-on Store**

3. **Add your repository**:
   - Click the **⋮ menu** (three dots) in the top right
   - Select **Repositories**
   - Click **Add Repository**
   - Enter: `https://github.com/yourusername/printer-dashboard-addon`
   - Click **Add**

#### Step 2: Install the Addon

1. **Refresh the add-on store** (may take a moment)
2. **Find your addon**:
   - Look for "Printer Dashboard" in the add-on list
   - Click on it to open the addon page

3. **Install the addon**:
   - Click **Install**
   - Wait for installation to complete (this may take several minutes)

#### Step 3: Configure the Addon

1. **Go to the Configuration tab**:
   - Leave default settings for now:
   ```yaml
   ssl: false
   certfile: fullchain.pem
   keyfile: privkey.pem
   ```

2. **Optional configurations**:
   - Enable **Auto-start** if you want it to start automatically
   - Enable **Watchdog** for automatic restart on crashes

#### Step 4: Start the Addon

1. **Go to the Info tab**
2. **Click Start**
3. **Monitor the logs**:
   - Click **Log** tab to see startup messages
   - Look for "Starting Printer Dashboard Flask App..."

### Method B: Manual Installation (Advanced)

#### Step 1: Access Home Assistant Files

**Option 1: SSH/Terminal Access**
```bash
# SSH into Home Assistant
ssh root@your-ha-ip

# Navigate to addons folder
cd /addons
```

**Option 2: Samba/SMB Share**
```
\\your-ha-ip\addons\
```

**Option 3: Studio Code Server Addon**
- Install "Studio Code Server" addon
- Access files through VS Code interface

#### Step 2: Create Addon Folder

1. **Create the addon directory**:
   ```bash
   mkdir -p /addons/printer_dashboard
   ```

2. **Copy all addon files** to `/addons/printer_dashboard/`

#### Step 3: Restart and Install

1. **Restart Home Assistant**:
   - **Settings** → **System** → **Restart**

2. **Find the addon**:
   - **Supervisor** → **Add-on Store** → **Local Add-ons**
   - Find "Printer Dashboard" and install

## 🔧 Part 3: First-Time Setup

### Step 1: Access the Dashboard

Once the addon is running, you can access it via:

1. **Web UI Button**:
   - Go to **Supervisor** → **Printer Dashboard**
   - Click **Open Web UI**

2. **Direct URL**:
   - `http://your-ha-ip:8099`

3. **Ingress URL** (if enabled):
   - Look for "Printer Dashboard" in the HA sidebar

### Step 2: Add Your First Printer

1. **Click "Add Printer"**
2. **Fill in the details**:

   **For OctoPrint:**
   ```
   Printer Name: My Ender 3
   Printer Type: OctoPrint
   Printer URL: http://192.168.1.100
   ```

   **For Mainsail:**
   ```
   Printer Name: My Voron
   Printer Type: Mainsail  
   Printer URL: http://192.168.1.101
   ```

   **For Custom Interface:**
   ```
   Printer Name: Custom Printer
   Printer Type: Custom URL
   Printer URL: http://printer.local:8080
   ```

3. **Click "Add Printer"**

### Step 3: Test Functionality

1. **Verify the printer loads** in the iframe
2. **Test tab switching** if you have multiple printers
3. **Test printer removal** by clicking the ✕ on a tab
4. **Test export/import** by right-clicking the header

## 🛠️ Part 4: Troubleshooting

### Common Issues and Solutions

#### Addon Won't Install
**Problem**: Installation fails or addon doesn't appear

**Solutions**:
1. **Check repository URL** - ensure it's correct and public
2. **Wait a few minutes** - GitHub sync can be slow
3. **Refresh the page** and try again
4. **Check addon logs** for error messages

#### Addon Won't Start
**Problem**: Addon shows "stopped" status

**Solutions**:
1. **Check the logs**:
   ```
   Supervisor → Printer Dashboard → Log
   ```
2. **Common issues**:
   - Port 8099 already in use
   - Insufficient memory/resources
   - Malformed configuration

3. **Restart Home Assistant** and try again

#### Can't Access Web UI
**Problem**: "Open Web UI" button doesn't work

**Solutions**:
1. **Try direct URL**: `http://your-ha-ip:8099`
2. **Check firewall settings**
3. **Verify addon is running** (green status)
4. **Check network connectivity**

#### Printer Won't Load
**Problem**: Printer interface shows error or won't load

**Solutions**:
1. **Verify printer URL** is correct and accessible
2. **Check printer is online** - try accessing directly
3. **Network issues**:
   - Ensure HA and printer are on same network
   - Check firewall rules
   - Verify no proxy blocking

4. **CORS issues** - some printer interfaces may block iframe loading

#### Authentication Issues
**Problem**: Gets authentication errors

**Solutions**:
1. **Restart the addon**
2. **Clear browser cache** and cookies
3. **Try incognito/private browsing**
4. **Check HA authentication** settings

### Getting Help

#### Check Logs First
Always check the addon logs for error messages:
```
Supervisor → Printer Dashboard → Log
```

#### Enable Debug Mode
Add to addon configuration:
```yaml
ssl: false
certfile: fullchain.pem
keyfile: privkey.pem
```

#### Community Support
- **Home Assistant Community**: [community.home-assistant.io](https://community.home-assistant.io)
- **GitHub Issues**: Create an issue in your repository
- **Discord**: Home Assistant Discord server

## 🔄 Part 5: Updates and Maintenance

### Updating the Addon

1. **Make changes** to your repository
2. **Update version** in `config.yaml`:
   ```yaml
   version: "1.0.1"
   ```
3. **Commit and push** changes
4. **In Home Assistant**:
   - Go to addon page
   - Click **Update** when available

### Backup Your Data

Your printer configurations are automatically backed up with Home Assistant backups. To manually export:

1. **Right-click the header** in the dashboard
2. **Select "Export Settings"**
3. **Save the JSON file** as backup

### Creating Releases

For better version management:

1. **Tag your releases** in GitHub:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

2. **Create GitHub releases** with changelog
3. **Update build configuration** to use specific tags

## 🎉 Part 6: Advanced Configuration

### Enable SSL/HTTPS

1. **Get SSL certificates** (Let's Encrypt, etc.)
2. **Copy certificates** to addon config folder
3. **Update addon configuration**:
   ```yaml
   ssl: true
   certfile: fullchain.pem
   keyfile: privkey.pem
   ```

### Custom Styling

1. **Edit `app/static/styles.css`** in your repository
2. **Commit changes** and update addon
3. **Restart addon** to apply changes

### API Integration

The addon provides REST API endpoints:

```bash
# Get all printers
curl -H "Authorization: Bearer YOUR_TOKEN" \
     http://your-ha:8099/api/printers

# Add printer via API
curl -X POST \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"name":"API Printer","type":"octoprint","url":"http://printer"}' \
     http://your-ha:8099/api/printers
```

## ✅ Success Checklist

- [ ] Repository created and configured
- [ ] Addon installed in Home Assistant
- [ ] Addon starts without errors
- [ ] Web UI accessible
- [ ] First printer added successfully
- [ ] Printer interface loads in iframe
- [ ] Can switch between multiple printers
- [ ] Export/import functionality works
- [ ] Addon survives restart

## 📞 Support

If you encounter issues:

1. **Check this guide** thoroughly
2. **Review the logs** for error messages  
3. **Search existing issues** on GitHub
4. **Create a new issue** with:
   - Home Assistant version
   - Addon version
   - Error logs
   - Steps to reproduce

---

**Congratulations! 🎉** Your Printer Dashboard addon is now ready to manage all your 3D printers through Home Assistant! 

## Overview
This Home Assistant add-on provides a unified dashboard for managing multiple 3D printer interfaces (Mainsail, OctoPrint, etc.) in a tabbed interface, accessible both locally and remotely via Nabu Casa.

## Features
- **Dynamic Configuration**: Automatically configures nginx on each printer for base path support
- **Tabbed Interface**: Clean, modern interface with tabs for each printer
- **Remote Access**: Works with Nabu Casa for remote access via HTTPS
- **Local Access**: Full functionality on local network
- **Automatic Proxy**: Dynamic nginx proxy generation for seamless integration

## Installation

1. **Add the Repository**:
   - Go to Home Assistant → Settings → Add-ons → Add-on Store
   - Click the three dots (⋮) → Repositories
   - Add: `https://github.com/yourusername/hass-printer-manager`

2. **Install the Add-on**:
   - Find "Printer Dashboard" in the add-on store
   - Click Install

## Configuration

### Basic Configuration

```yaml
ssl: false
certfile: fullchain.pem
keyfile: privkey.pem
printers:
  - name: "Voron 2.4"
    type: "mainsail"
    url: "http://192.168.1.100"
  - name: "Ender 3"
    type: "octoprint"  
    url: "http://192.168.1.101:5000"
ssh_username: "pi"
ssh_password: "your_ssh_password"
ssh_key: ""
```

### SSH Configuration

The add-on needs SSH access to your printers to automatically configure nginx for base path support. You have two options:

#### Option 1: SSH Password
```yaml
ssh_username: "pi"
ssh_password: "your_ssh_password"
ssh_key: ""
```

#### Option 2: SSH Key (Recommended)
```yaml
ssh_username: "pi"
ssh_password: ""
ssh_key: |
  -----BEGIN OPENSSH PRIVATE KEY-----
  your_private_key_content_here
  -----END OPENSSH PRIVATE KEY-----
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `ssl` | boolean | `false` | Enable SSL (requires certificates) |
| `certfile` | string | `fullchain.pem` | SSL certificate file |
| `keyfile` | string | `privkey.pem` | SSL private key file |
| `printers` | list | `[]` | List of printers to manage |
| `ssh_username` | string | `pi` | SSH username for printer access |
| `ssh_password` | string | `""` | SSH password (if not using key) |
| `ssh_key` | string | `""` | SSH private key content |

### Printer Configuration

Each printer in the `printers` list supports:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Display name for the printer |
| `type` | string | Yes | Interface type: `mainsail`, `octoprint`, or `custom` |
| `url` | string | Yes | Full URL to the printer interface |

## How It Works

### Dynamic Nginx Configuration

When the add-on starts, it:

1. **Analyzes your printer configuration** and generates unique proxy paths
2. **Connects to each printer via SSH** using your provided credentials
3. **Automatically configures nginx** on each printer to support base paths like `/proxy/printer_name/`
4. **Creates dynamic proxy rules** in the add-on's nginx to route requests correctly
5. **Maintains backward compatibility** - your printers still work normally at their original URLs

### Base Path Support

The add-on automatically configures each printer's nginx to serve Mainsail/OctoPrint from both:
- **Original path**: `http://192.168.1.100/` (unchanged)
- **Base path**: `http://192.168.1.100/proxy/printer_name/` (new, for Home Assistant integration)

This allows seamless integration with Home Assistant's ingress system while maintaining normal functionality.

### Remote Access via Nabu Casa

The dynamic proxy configuration ensures that:
- **Local access** works normally through your LAN
- **Remote access** works through Nabu Casa HTTPS tunnel
- **Mixed content issues** are avoided by proxying HTTP printer interfaces
- **Static assets** (CSS, JS, images) load correctly in both contexts

## Troubleshooting

### SSH Connection Issues

If you see SSH-related errors in the logs:

1. **Verify SSH credentials** are correct in the configuration
2. **Check SSH is enabled** on your printers
3. **Ensure the add-on can reach** your printer IPs
4. **Try SSH manually** from another machine to test connectivity

### Nginx Configuration Errors

If nginx configuration fails on a printer:

1. **Check the add-on logs** for specific error messages
2. **Verify nginx is installed** on the printer
3. **Ensure sufficient permissions** for the SSH user (sudo access)
4. **Check disk space** on the printer

### 404 Errors in Dashboard

If you see 404 errors when loading printer interfaces:

1. **Check printer URLs** are correct and accessible
2. **Verify base path configuration** was applied successfully
3. **Test direct access** to printer interfaces
4. **Check add-on logs** for proxy configuration issues

### Manual Fallback

If automatic configuration fails, you can manually configure nginx on each printer using the configuration templates provided in the logs.

## Security Considerations

- **SSH credentials** are stored in Home Assistant's secure configuration
- **Network access** is limited to your configured printer IPs
- **No external dependencies** - all communication stays within your network
- **Backward compatibility** ensures existing printer access remains unchanged

## Support

For issues and support:
1. Check the add-on logs for detailed error messages
2. Verify your configuration against this guide
3. Test SSH connectivity manually
4. Report issues with full logs and configuration details 