class PrinterDashboard {
    constructor() {
        this.printers = [];
        this.activeTab = localStorage.getItem('activeTab') || null;
        this.apiBase = 'api';
        this.init();
    }

    async init() {
        this.setupEventListeners();
        await this.loadPrinters();
        this.updateUI();
    }

    setupEventListeners() {
        // Add printer button
        document.getElementById('addPrinterBtn').addEventListener('click', () => {
            this.showAddPrinterModal();
        });

        // Close modal
        document.getElementById('closeModal').addEventListener('click', () => {
            this.hideAddPrinterModal();
        });

        document.getElementById('cancelBtn').addEventListener('click', () => {
            this.hideAddPrinterModal();
        });

        // Close modal when clicking outside
        document.getElementById('addPrinterModal').addEventListener('click', (e) => {
            if (e.target === document.getElementById('addPrinterModal')) {
                this.hideAddPrinterModal();
            }
        });

        // Add printer form submission - disabled (use configuration tab)
        document.getElementById('addPrinterForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.showNotification('Printers are configured in the add-on configuration tab. Go to Settings → Add-ons → Printer Dashboard → Configuration to add printers.', 'warning');
        });

        // Escape key to close modal
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.hideAddPrinterModal();
            }
        });
    }

    showLoading(message = 'Loading...') {
        const overlay = document.getElementById('loadingOverlay');
        const text = document.querySelector('.loading-text');
        text.textContent = message;
        overlay.style.display = 'flex';
    }

    hideLoading() {
        document.getElementById('loadingOverlay').style.display = 'none';
    }

    async makeApiRequest(endpoint, options = {}) {
        // ensure no leading slash so we stay inside ingress path
        if (endpoint.startsWith('/')) endpoint = endpoint.slice(1);
        try {
            const response = await fetch(`${this.apiBase}/${endpoint}`, {
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                },
                ...options
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'API request failed');
            }

            return await response.json();
        } catch (error) {
            console.error('API request failed:', error);
            throw error;
        }
    }

    async loadPrinters() {
        try {
            this.showLoading('Loading printers...');
            this.printers = await this.makeApiRequest('/printers');
            this.renderPrinters();
        } catch (error) {
            console.error('Failed to load printers:', error);
            this.showError('Failed to load printers: ' + error.message);
        } finally {
            this.hideLoading();
        }
    }

    showAddPrinterModal() {
        this.showNotification('Printers are configured in the add-on configuration tab. Go to Settings → Add-ons → Printer Dashboard → Configuration to add printers.', 'warning');
    }

    hideAddPrinterModal() {
        document.getElementById('addPrinterModal').style.display = 'none';
        document.getElementById('addPrinterForm').reset();
    }

    // addPrinter() function removed - printers are now configured through Home Assistant configuration tab

    normalizeUrl(url) {
        // Ensure URL has protocol
        if (!url.startsWith('http://') && !url.startsWith('https://')) {
            url = 'http://' + url;
        }
        return url;
    }

    async removePrinter(printerId) {
        this.showNotification('Printers are configured in the add-on configuration tab. Go to Settings → Add-ons → Printer Dashboard → Configuration to manage printers.', 'warning');
    }

    renderPrinters() {
        const tabNav = document.getElementById('tabNav');
        const tabContent = document.getElementById('tabContent');

        // Clear existing tabs
        tabNav.innerHTML = '';
        tabContent.innerHTML = '';

        this.printers.forEach(printer => {
            // Create tab button
            const tabBtn = document.createElement('button');
            tabBtn.className = `tab-btn ${this.activeTab === printer.id ? 'active' : ''}`;
            tabBtn.innerHTML = `
                <span class="tab-icon">${this.getTypeIcon(printer.type)}</span>
                <span class="tab-name">${printer.name}</span>
                <span class="tab-close" onclick="event.stopPropagation(); dashboard.removePrinter('${printer.id}')">&times;</span>
            `;
            tabBtn.addEventListener('click', () => this.switchTab(printer.id));
            tabNav.appendChild(tabBtn);

            // Create tab panel
            const tabPanel = document.createElement('div');
            tabPanel.className = `tab-panel ${this.activeTab === printer.id ? 'active' : ''}`;
            tabPanel.id = `panel-${printer.id}`;
            
            const iframe = document.createElement('iframe');
            iframe.className = 'tab-iframe';
            iframe.src = printer.url;
            iframe.title = printer.name;
            iframe.loading = 'lazy';
            
            // Add loading indicator
            const loadingDiv = document.createElement('div');
            loadingDiv.className = 'loading';
            loadingDiv.textContent = `Loading ${printer.name}...`;
            
            tabPanel.appendChild(loadingDiv);
            tabPanel.appendChild(iframe);

            // Handle iframe load
            iframe.onload = () => {
                loadingDiv.style.display = 'none';
                iframe.style.display = 'block';
            };

            iframe.onerror = () => {
                loadingDiv.innerHTML = `
                    <div style="text-align: center; color: #ef4444;">
                        <h3>Failed to load ${printer.name}</h3>
                        <p>Please check the URL: <a href="${printer.url}" target="_blank">${printer.url}</a></p>
                        <button onclick="location.reload()" style="margin-top: 10px; padding: 8px 16px; background: #4c51bf; color: white; border: none; border-radius: 4px; cursor: pointer;">Retry</button>
                    </div>
                `;
            };

            tabContent.appendChild(tabPanel);
        });
    }

    getTypeIcon(type) {
        const icons = {
            'mainsail': '🚀',
            'octoprint': '🐙',
            'custom': '🖨️'
        };
        return icons[type] || '🖨️';
    }

    switchTab(printerId) {
        this.activeTab = printerId;
        localStorage.setItem('activeTab', printerId);

        // Update tab buttons
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        document.querySelector(`.tab-btn[onclick*="${printerId}"]`)?.parentElement.classList.add('active');

        // Update tab panels
        document.querySelectorAll('.tab-panel').forEach(panel => {
            panel.classList.remove('active');
        });
        document.getElementById(`panel-${printerId}`)?.classList.add('active');

        this.updateUI();
    }

    updateUI() {
        const hasPrinters = this.printers.length > 0;
        const welcomeScreen = document.getElementById('welcomeScreen');
        const tabContainer = document.querySelector('.tab-container');

        if (hasPrinters) {
            welcomeScreen.style.display = 'none';
            tabContainer.style.display = 'block';
        } else {
            welcomeScreen.style.display = 'flex';
            tabContainer.style.display = 'none';
        }
    }

    showError(message) {
        this.showNotification(message, 'error');
    }

    showSuccess(message) {
        this.showNotification(message, 'success');
    }

    showNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.innerHTML = `
            <span class="notification-message">${message}</span>
            <button class="notification-close">&times;</button>
        `;

        // Add to page
        document.body.appendChild(notification);

        // Position notification
        const notifications = document.querySelectorAll('.notification');
        const offset = (notifications.length - 1) * 70;
        notification.style.top = `${20 + offset}px`;

        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentElement) {
                notification.remove();
            }
        }, 5000);

        // Remove on click
        notification.querySelector('.notification-close').addEventListener('click', () => {
            notification.remove();
        });
    }

    // Export/Import functions for backup
    async exportSettings() {
        try {
            const settings = {
                printers: this.printers,
                activeTab: this.activeTab,
                exportedAt: new Date().toISOString()
            };
            const dataStr = JSON.stringify(settings, null, 2);
            const dataBlob = new Blob([dataStr], { type: 'application/json' });
            const url = URL.createObjectURL(dataBlob);
            
            const link = document.createElement('a');
            link.href = url;
            link.download = 'printer-dashboard-settings.json';
            link.click();
            
            URL.revokeObjectURL(url);
            this.showSuccess('Settings exported successfully!');
        } catch (error) {
            this.showError('Failed to export settings: ' + error.message);
        }
    }

    importSettings(file) {
        const reader = new FileReader();
        reader.onload = async (e) => {
            try {
                const settings = JSON.parse(e.target.result);
                if (settings.printers && Array.isArray(settings.printers)) {
                    // Import each printer
                    for (const printer of settings.printers) {
                        try {
                            await this.makeApiRequest('/printers', {
                                method: 'POST',
                                body: JSON.stringify(printer)
                            });
                        } catch (error) {
                            console.warn(`Failed to import printer ${printer.name}:`, error);
                        }
                    }
                    
                    await this.loadPrinters();
                    this.showSuccess('Settings imported successfully!');
                } else {
                    this.showError('Invalid settings file format');
                }
            } catch (error) {
                this.showError('Error importing settings: ' + error.message);
            }
        };
        reader.readAsText(file);
    }
}

// Initialize the dashboard
const dashboard = new PrinterDashboard();

// Add keyboard shortcuts
document.addEventListener('keydown', (e) => {
    // Ctrl/Cmd + K to add new printer
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        dashboard.showAddPrinterModal();
    }
    
    // Ctrl/Cmd + 1-9 to switch between tabs
    if ((e.ctrlKey || e.metaKey) && e.key >= '1' && e.key <= '9') {
        e.preventDefault();
        const index = parseInt(e.key) - 1;
        if (dashboard.printers[index]) {
            dashboard.switchTab(dashboard.printers[index].id);
        }
    }
});

// Add context menu for advanced options (right-click on header)
document.addEventListener('DOMContentLoaded', () => {
    const header = document.querySelector('header');
    if (header) {
        header.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            
            const menu = document.createElement('div');
            menu.style.cssText = `
                position: fixed;
                top: ${e.clientY}px;
                left: ${e.clientX}px;
                background: white;
                border: 1px solid #ccc;
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                z-index: 10000;
                padding: 8px 0;
                min-width: 150px;
            `;
            
            menu.innerHTML = `
                <div style="padding: 8px 16px; cursor: pointer; hover:background: #f5f5f5;" onclick="dashboard.exportSettings(); document.body.removeChild(this.parentElement);">Export Settings</div>
                <div style="padding: 8px 16px; cursor: pointer; hover:background: #f5f5f5;" onclick="document.getElementById('importFile').click(); document.body.removeChild(this.parentElement);">Import Settings</div>
            `;
            
            document.body.appendChild(menu);
            
            // Remove menu when clicking elsewhere
            setTimeout(() => {
                document.addEventListener('click', () => {
                    if (menu.parentElement) {
                        document.body.removeChild(menu);
                    }
                }, { once: true });
            }, 100);
        });
    }
});

// Hidden file input for importing
const importInput = document.createElement('input');
importInput.type = 'file';
importInput.id = 'importFile';
importInput.accept = '.json';
importInput.style.display = 'none';
importInput.addEventListener('change', (e) => {
    if (e.target.files[0]) {
        dashboard.importSettings(e.target.files[0]);
    }
});
document.body.appendChild(importInput); 