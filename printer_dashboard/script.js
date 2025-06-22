class PrinterDashboard {
    constructor() {
        this.printers = JSON.parse(localStorage.getItem('printers')) || [];
        this.activeTab = localStorage.getItem('activeTab') || null;
        this.init();
    }

    init() {
        // Check if loaded in iframe (Home Assistant)
        if (!this.isInIFrame()) {
            this.showIFrameOnlyMessage();
            return;
        }
        
        this.setupEventListeners();
        this.renderPrinters();
        this.updateUI();
    }

    isInIFrame() {
        try {
            return window.self !== window.top;
        } catch (e) {
            return true;
        }
    }

    showIFrameOnlyMessage() {
        document.body.innerHTML = `
            <div class="iframe-only-container">
                <div class="iframe-only-box">
                    <h2>🖨️ Printer Dashboard</h2>
                    <h3>Access Restricted</h3>
                    <p>This dashboard can only be accessed through Home Assistant.</p>
                    <div class="access-info">
                        <div class="info-item">
                            <span class="info-icon">🏠</span>
                            <span>Use Home Assistant Panel or Dashboard Card</span>
                        </div>
                        <div class="info-item">
                            <span class="info-icon">🔒</span>
                            <span>Direct URL access is disabled for security</span>
                        </div>
                        <div class="info-item">
                            <span class="info-icon">⚙️</span>
                            <span>Configure in your Home Assistant instance</span>
                        </div>
                    </div>
                    <div class="setup-instructions">
                        <h4>Setup Instructions:</h4>
                        <ol>
                            <li>Add panel to <code>configuration.yaml</code></li>
                            <li>Or use as iframe card in dashboard</li>
                            <li>Access through Home Assistant interface</li>
                        </ol>
                    </div>
                </div>
            </div>
            <style>
                .iframe-only-container {
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 100vh;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    padding: 20px;
                }
                .iframe-only-box {
                    background: rgba(255, 255, 255, 0.95);
                    backdrop-filter: blur(10px);
                    padding: 40px;
                    border-radius: 15px;
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
                    text-align: center;
                    max-width: 500px;
                    width: 100%;
                }
                .iframe-only-box h2 {
                    color: #4c51bf;
                    margin-bottom: 10px;
                    font-size: 2rem;
                }
                .iframe-only-box h3 {
                    color: #ef4444;
                    margin-bottom: 20px;
                    font-weight: 600;
                }
                .iframe-only-box p {
                    color: #64748b;
                    margin-bottom: 30px;
                    font-size: 1.1rem;
                }
                .access-info {
                    margin-bottom: 30px;
                }
                .info-item {
                    display: flex;
                    align-items: center;
                    gap: 12px;
                    padding: 12px;
                    background: #f8fafc;
                    border-radius: 8px;
                    margin-bottom: 10px;
                    text-align: left;
                }
                .info-icon {
                    font-size: 1.5rem;
                    width: 30px;
                    text-align: center;
                }
                .setup-instructions {
                    background: #f0f9ff;
                    padding: 20px;
                    border-radius: 8px;
                    border-left: 4px solid #0ea5e9;
                    text-align: left;
                }
                .setup-instructions h4 {
                    color: #0ea5e9;
                    margin-bottom: 15px;
                    font-size: 1.1rem;
                }
                .setup-instructions ol {
                    margin-left: 20px;
                    color: #374151;
                }
                .setup-instructions li {
                    margin-bottom: 8px;
                    line-height: 1.5;
                }
                .setup-instructions code {
                    background: #e2e8f0;
                    padding: 2px 6px;
                    border-radius: 4px;
                    font-family: monospace;
                    color: #4c51bf;
                }
                @media (max-width: 768px) {
                    .iframe-only-container {
                        padding: 15px;
                    }
                    .iframe-only-box {
                        padding: 30px 20px;
                    }
                    .iframe-only-box h2 {
                        font-size: 1.5rem;
                    }
                    .info-item {
                        flex-direction: column;
                        text-align: center;
                        gap: 8px;
                    }
                }
            </style>
        `;
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

        // Add printer form submission
        document.getElementById('addPrinterForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.addPrinter();
        });

        // Escape key to close modal
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.hideAddPrinterModal();
            }
        });
    }

    showAddPrinterModal() {
        document.getElementById('addPrinterModal').style.display = 'block';
        document.getElementById('printerName').focus();
    }

    hideAddPrinterModal() {
        document.getElementById('addPrinterModal').style.display = 'none';
        document.getElementById('addPrinterForm').reset();
    }

    addPrinter() {
        const name = document.getElementById('printerName').value.trim();
        const type = document.getElementById('printerType').value;
        const url = document.getElementById('printerUrl').value.trim();

        if (!name || !type || !url) {
            alert('Please fill in all fields');
            return;
        }

        // Validate URL format
        try {
            new URL(url);
        } catch {
            alert('Please enter a valid URL (e.g., http://192.168.1.100)');
            return;
        }

        // Check if printer with this name already exists
        if (this.printers.some(printer => printer.name === name)) {
            alert('A printer with this name already exists');
            return;
        }

        const printer = {
            id: Date.now().toString(),
            name,
            type,
            url: this.normalizeUrl(url),
            addedAt: new Date().toISOString()
        };

        this.printers.push(printer);
        this.savePrinters();
        this.renderPrinters();
        this.hideAddPrinterModal();
        this.updateUI();

        // Auto-select the newly added printer
        this.switchTab(printer.id);
    }

    normalizeUrl(url) {
        // Ensure URL has protocol
        if (!url.startsWith('http://') && !url.startsWith('https://')) {
            url = 'http://' + url;
        }
        return url;
    }

    removePrinter(printerId) {
        const printer = this.printers.find(p => p.id === printerId);
        if (!printer) return;

        if (confirm(`Are you sure you want to remove "${printer.name}"?`)) {
            this.printers = this.printers.filter(p => p.id !== printerId);
            this.savePrinters();
            
            // If this was the active tab, switch to another tab or show welcome
            if (this.activeTab === printerId) {
                const remainingPrinters = this.printers;
                if (remainingPrinters.length > 0) {
                    this.switchTab(remainingPrinters[0].id);
                } else {
                    this.activeTab = null;
                    localStorage.removeItem('activeTab');
                }
            }
            
            this.renderPrinters();
            this.updateUI();
        }
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
        const hasPlinters = this.printers.length > 0;
        const welcomeScreen = document.getElementById('welcomeScreen');
        const tabContainer = document.querySelector('.tab-container');

        if (hasPlinters) {
            welcomeScreen.style.display = 'none';
            tabContainer.style.display = 'block';
        } else {
            welcomeScreen.style.display = 'flex';
            tabContainer.style.display = 'none';
        }
    }

    savePrinters() {
        localStorage.setItem('printers', JSON.stringify(this.printers));
    }

    // Export/Import functions for backup
    exportSettings() {
        const settings = {
            printers: this.printers,
            activeTab: this.activeTab
        };
        const dataStr = JSON.stringify(settings, null, 2);
        const dataBlob = new Blob([dataStr], { type: 'application/json' });
        const url = URL.createObjectURL(dataBlob);
        
        const link = document.createElement('a');
        link.href = url;
        link.download = 'printer-dashboard-settings.json';
        link.click();
        
        URL.revokeObjectURL(url);
    }

    importSettings(file) {
        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                const settings = JSON.parse(e.target.result);
                if (settings.printers && Array.isArray(settings.printers)) {
                    this.printers = settings.printers;
                    this.activeTab = settings.activeTab || null;
                    this.savePrinters();
                    this.renderPrinters();
                    this.updateUI();
                    alert('Settings imported successfully!');
                } else {
                    alert('Invalid settings file format');
                }
            } catch (error) {
                alert('Error importing settings: ' + error.message);
            }
        };
        reader.readAsText(file);
    }
}

// Initialize the dashboard
const dashboard = new PrinterDashboard();

// Add keyboard shortcuts (only if in iframe)
document.addEventListener('keydown', (e) => {
    if (!dashboard.isInIFrame()) return;
    
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

// Add context menu for advanced options (right-click on header) - only if in iframe
document.addEventListener('DOMContentLoaded', () => {
    if (!dashboard.isInIFrame()) return;
    
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

// Hidden file input for importing - only create if in iframe
if (dashboard.isInIFrame()) {
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
} 