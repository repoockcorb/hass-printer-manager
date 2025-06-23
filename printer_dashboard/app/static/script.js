class PrintFarmDashboard {
    constructor() {
        this.printers = new Map();
        this.updateInterval = 10000; // 10 seconds
        this.updateTimer = null;
        this.isUpdating = false;
        this.filters = {
            status: 'all',
            type: 'all'
        };
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.showLoading();
        this.loadPrinters();
        this.startAutoUpdate();
    }
    
    setupEventListeners() {
        // Refresh button
        document.getElementById('refresh-btn').addEventListener('click', () => {
            this.refreshAll();
        });
        
        // Filter controls
        document.getElementById('status-filter').addEventListener('change', (e) => {
            this.filters.status = e.target.value;
            this.applyFilters();
        });
        
        document.getElementById('type-filter').addEventListener('change', (e) => {
            this.filters.type = e.target.value;
            this.applyFilters();
        });
        
        // Modal controls
        const modal = document.getElementById('confirm-modal');
        const closeBtn = document.querySelector('.modal-close');
        const cancelBtn = document.getElementById('modal-cancel');
        
        closeBtn.addEventListener('click', () => this.hideModal());
        cancelBtn.addEventListener('click', () => this.hideModal());
        
        // Click outside modal to close
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                this.hideModal();
            }
        });
        
        // Camera modal controls
        const cameraModal = document.getElementById('camera-modal');
        const cameraCloseBtn = document.querySelector('.camera-modal-close');
        const cameraCloseFooterBtn = document.getElementById('camera-close');
        const cameraRefreshBtn = document.getElementById('camera-refresh');
        
        if (cameraCloseBtn) cameraCloseBtn.addEventListener('click', () => this.hideCameraModal());
        if (cameraCloseFooterBtn) cameraCloseFooterBtn.addEventListener('click', () => this.hideCameraModal());
        if (cameraRefreshBtn) cameraRefreshBtn.addEventListener('click', () => this.refreshCameraFeed());
        
        // Click outside camera modal to close
        cameraModal.addEventListener('click', (e) => {
            if (e.target === cameraModal) {
                this.hideCameraModal();
            }
        });
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.hideModal();
                this.hideCameraModal();
            } else if (e.key === 'r' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                this.refreshAll();
            }
        });
    }
    
    async loadPrinters() {
        try {
            const response = await fetch('api/printers');
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const printerConfigs = await response.json();
            
            if (printerConfigs.length === 0) {
                this.showEmptyState();
                return;
            }
            
            // Initialize printer objects
            printerConfigs.forEach(config => {
                this.printers.set(config.name, {
                    config: config,
                    status: null,
                    lastUpdate: null
                });
            });
            
            this.hideLoading();
            this.createPrinterCards();
            this.updateAllStatus();
            
        } catch (error) {
            console.error('Error loading printers:', error);
            this.showError(`Failed to load printers: ${error.message}`);
        }
    }
    
    async updateAllStatus() {
        if (this.isUpdating) return;
        
        this.isUpdating = true;
        this.setRefreshButtonState(true);
        
        try {
            const response = await fetch('api/status');
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const statusData = await response.json();
            
            // Update each printer's status
            for (const [printerName, printer] of this.printers.entries()) {
                if (statusData[printerName]) {
                    printer.status = statusData[printerName];
                    printer.lastUpdate = new Date();
                    this.updatePrinterCard(printerName, printer);
                }
            }
            
            this.updateSummary();
            this.applyFilters();
            
        } catch (error) {
            console.error('Error updating status:', error);
            this.showError(`Failed to update printer status: ${error.message}`);
        } finally {
            this.isUpdating = false;
            this.setRefreshButtonState(false);
        }
    }
    
    createPrinterCards() {
        const grid = document.getElementById('printers-grid');
        const template = document.getElementById('printer-card-template');
        
        grid.innerHTML = '';
        
        for (const [printerName, printer] of this.printers.entries()) {
            const card = template.content.cloneNode(true);
            
            // Set printer name as data attribute
            card.querySelector('.printer-card').setAttribute('data-printer-name', printerName);
            
            // Set basic info
            card.querySelector('.printer-name').textContent = printerName;
            card.querySelector('.printer-type').textContent = printer.config.type || 'klipper';
            
            // Setup camera button
            const cameraBtn = card.querySelector('.camera-btn');
            if (printer.config.camera_entity) {
                cameraBtn.setAttribute('data-camera-entity', printer.config.camera_entity);
                cameraBtn.style.display = 'inline-flex';
                cameraBtn.addEventListener('click', () => {
                    this.showCameraModal(printerName, printer.config.camera_entity);
                });
            }
            
            // Setup control buttons
            const controlButtons = card.querySelectorAll('.btn-control');
            controlButtons.forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const action = e.target.closest('button').getAttribute('data-action');
                    this.showControlModal(printerName, action);
                });
            });
            
            grid.appendChild(card);
        }
    }
    
    updatePrinterCard(printerName, printer) {
        const card = document.querySelector(`[data-printer-name="${printerName}"]`);
        if (!card || !printer.status) return;
        
        const status = printer.status;
        
        // Update status indicator and text
        const statusIndicator = card.querySelector('.status-indicator');
        const statusText = card.querySelector('.status-text');
        
        // Remove existing status classes
        statusIndicator.className = 'status-indicator';
        card.className = card.className.replace(/\s*(offline|printing|paused|error)\s*/g, ' ').trim();
        
        if (!status.online) {
            statusIndicator.classList.add('offline');
            card.classList.add('offline');
            statusText.textContent = 'Offline';
        } else {
            const state = status.state.toLowerCase();
            statusText.textContent = this.formatStatusText(state);
            
            if (['printing'].includes(state)) {
                statusIndicator.classList.add('printing');
                card.classList.add('printing');
            } else if (['paused'].includes(state)) {
                statusIndicator.classList.add('paused');
                card.classList.add('paused');
            } else if (['error'].includes(state)) {
                statusIndicator.classList.add('offline');
                card.classList.add('error');
            } else {
                statusIndicator.classList.add('online');
            }
        }
        
        // Update file name and progress
        const fileName = card.querySelector('.file-name');
        const progressFill = card.querySelector('.progress-fill');
        const progressText = card.querySelector('.progress-text');
        
        if (status.file && status.progress > 0) {
            fileName.textContent = status.file;
            progressFill.style.width = `${status.progress}%`;
            progressText.textContent = `${status.progress}%`;
        } else {
            fileName.textContent = 'No active print';
            progressFill.style.width = '0%';
            progressText.textContent = '0%';
        }
        
        // Update temperatures
        if (status.extruder_temp) {
            card.querySelector('.temp-actual').textContent = `${status.extruder_temp.actual}°`;
            card.querySelector('.temp-target').textContent = `${status.extruder_temp.target}°`;
        }
        
        if (status.bed_temp) {
            const bedActual = card.querySelectorAll('.temp-actual')[1];
            const bedTarget = card.querySelectorAll('.temp-target')[1];
            if (bedActual) bedActual.textContent = `${status.bed_temp.actual}°`;
            if (bedTarget) bedTarget.textContent = `${status.bed_temp.target}°`;
        }
        
        // Update times
        card.querySelector('.print-time').textContent = status.print_time || '00:00:00';
        card.querySelector('.remaining-time').textContent = status.remaining_time || '00:00:00';
        
        // Update positions
        if (status.position) {
            card.querySelector('.x-pos').textContent = status.position.x || '0.00';
            card.querySelector('.y-pos').textContent = status.position.y || '0.00';
            card.querySelector('.z-pos').textContent = status.position.z || '0.00';
        }
        
        // Update control buttons visibility
        const pauseBtn = card.querySelector('.pause-btn');
        const resumeBtn = card.querySelector('.resume-btn');
        const cancelBtn = card.querySelector('.cancel-btn');
        
        const isPrinting = status.online && ['printing'].includes(status.state.toLowerCase());
        const isPaused = status.online && ['paused'].includes(status.state.toLowerCase());
        const hasActiveJob = status.file && status.progress > 0;
        
        pauseBtn.style.display = isPrinting ? 'inline-flex' : 'none';
        resumeBtn.style.display = isPaused ? 'inline-flex' : 'none';
        cancelBtn.style.display = hasActiveJob ? 'inline-flex' : 'none';
        
        // Update last update time
        const updateTime = card.querySelector('.update-time');
        if (printer.lastUpdate) {
            updateTime.textContent = this.formatRelativeTime(printer.lastUpdate);
        }
    }
    
    updateSummary() {
        let totalCount = 0;
        let printingCount = 0;
        let idleCount = 0;
        let offlineCount = 0;
        
        for (const [name, printer] of this.printers.entries()) {
            totalCount++;
            
            if (!printer.status || !printer.status.online) {
                offlineCount++;
            } else {
                const state = printer.status.state.toLowerCase();
                if (['printing'].includes(state)) {
                    printingCount++;
                } else {
                    idleCount++;
                }
            }
        }
        
        document.getElementById('total-printers').textContent = totalCount;
        document.getElementById('printing-count').textContent = printingCount;
        document.getElementById('idle-count').textContent = idleCount;
        document.getElementById('offline-count').textContent = offlineCount;
    }
    
    applyFilters() {
        const cards = document.querySelectorAll('.printer-card');
        
        cards.forEach(card => {
            const printerName = card.getAttribute('data-printer-name');
            const printer = this.printers.get(printerName);
            
            if (!printer || !printer.status) {
                card.style.display = 'none';
                return;
            }
            
            let show = true;
            
            // Status filter
            if (this.filters.status !== 'all') {
                const status = printer.status;
                let statusMatch = false;
                
                if (this.filters.status === 'offline' && !status.online) {
                    statusMatch = true;
                } else if (this.filters.status === 'printing' && status.online && ['printing'].includes(status.state.toLowerCase())) {
                    statusMatch = true;
                } else if (this.filters.status === 'paused' && status.online && ['paused'].includes(status.state.toLowerCase())) {
                    statusMatch = true;
                } else if (this.filters.status === 'idle' && status.online && !['printing', 'paused'].includes(status.state.toLowerCase())) {
                    statusMatch = true;
                }
                
                if (!statusMatch) show = false;
            }
            
            // Type filter
            if (this.filters.type !== 'all') {
                if (printer.status.type !== this.filters.type) {
                    show = false;
                }
            }
            
            card.style.display = show ? 'block' : 'none';
        });
    }
    
    showControlModal(printerName, action) {
        const modal = document.getElementById('confirm-modal');
        const title = document.getElementById('modal-title');
        const message = document.getElementById('modal-message');
        const confirmBtn = document.getElementById('modal-confirm');
        
        const actionTexts = {
            pause: {
                title: 'Pause Print',
                message: `Are you sure you want to pause the print on "${printerName}"?`,
                buttonText: 'Pause'
            },
            resume: {
                title: 'Resume Print',
                message: `Are you sure you want to resume the print on "${printerName}"?`,
                buttonText: 'Resume'
            },
            cancel: {
                title: 'Cancel Print',
                message: `Are you sure you want to cancel the print on "${printerName}"? This action cannot be undone.`,
                buttonText: 'Cancel Print'
            }
        };
        
        const actionData = actionTexts[action];
        if (!actionData) return;
        
        title.textContent = actionData.title;
        message.textContent = actionData.message;
        confirmBtn.textContent = actionData.buttonText;
        
        // Set button style based on action
        confirmBtn.className = 'btn ' + (action === 'cancel' ? 'btn-danger' : 'btn-primary');
        
        // Setup confirm handler
        confirmBtn.onclick = () => {
            this.hideModal();
            this.controlPrinter(printerName, action);
        };
        
        modal.style.display = 'flex';
    }
    
    hideModal() {
        document.getElementById('confirm-modal').style.display = 'none';
    }
    
    async controlPrinter(printerName, action) {
        try {
            const response = await fetch(`api/control/${printerName}/${action}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showNotification(`${action} command sent to ${printerName}`, 'success');
                // Refresh status after a short delay
                setTimeout(() => this.updateAllStatus(), 2000);
            } else {
                this.showNotification(`Failed to ${action} ${printerName}: ${result.error}`, 'error');
            }
            
        } catch (error) {
            console.error(`Error controlling printer ${printerName}:`, error);
            this.showNotification(`Failed to ${action} ${printerName}: ${error.message}`, 'error');
        }
    }
    
    showNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.innerHTML = `
            <span>${message}</span>
            <button class="notification-close">&times;</button>
        `;
        
        // Add styles
        const style = document.createElement('style');
        style.textContent = `
            .notification {
                position: fixed;
                top: 20px;
                right: 20px;
                background: rgba(30, 41, 59, 0.95);
                border: 1px solid rgba(148, 163, 184, 0.2);
                border-radius: 8px;
                padding: 1rem 1.5rem;
                color: #e0e6ed;
                z-index: 1001;
                display: flex;
                align-items: center;
                gap: 1rem;
                max-width: 400px;
                animation: slideIn 0.3s ease-out;
            }
            
            .notification-success {
                border-left: 4px solid #34d399;
            }
            
            .notification-error {
                border-left: 4px solid #f87171;
            }
            
            .notification-close {
                background: none;
                border: none;
                color: #94a3b8;
                cursor: pointer;
                font-size: 1.2rem;
                padding: 0;
            }
            
            .notification-close:hover {
                color: #e0e6ed;
            }
            
            @keyframes slideIn {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
        `;
        
        if (!document.querySelector('#notification-styles')) {
            style.id = 'notification-styles';
            document.head.appendChild(style);
        }
        
        // Add to page
        document.body.appendChild(notification);
        
        // Setup close handler
        notification.querySelector('.notification-close').addEventListener('click', () => {
            notification.remove();
        });
        
        // Auto remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 5000);
    }
    
    startAutoUpdate() {
        this.updateTimer = setInterval(() => {
            this.updateAllStatus();
        }, this.updateInterval);
    }
    
    stopAutoUpdate() {
        if (this.updateTimer) {
            clearInterval(this.updateTimer);
            this.updateTimer = null;
        }
    }
    
    refreshAll() {
        this.updateAllStatus();
    }
    
    setRefreshButtonState(loading) {
        const btn = document.getElementById('refresh-btn');
        const icon = btn.querySelector('i');
        
        if (loading) {
            icon.classList.add('fa-spin');
            btn.disabled = true;
        } else {
            icon.classList.remove('fa-spin');
            btn.disabled = false;
        }
    }
    
    showLoading() {
        document.getElementById('loading-state').style.display = 'flex';
        document.getElementById('printers-grid').style.display = 'none';
        document.getElementById('empty-state').style.display = 'none';
        document.getElementById('error-state').style.display = 'none';
    }
    
    hideLoading() {
        document.getElementById('loading-state').style.display = 'none';
        document.getElementById('printers-grid').style.display = 'grid';
    }
    
    showEmptyState() {
        document.getElementById('loading-state').style.display = 'none';
        document.getElementById('printers-grid').style.display = 'none';
        document.getElementById('empty-state').style.display = 'flex';
        document.getElementById('error-state').style.display = 'none';
    }
    
    showError(message) {
        document.getElementById('loading-state').style.display = 'none';
        document.getElementById('printers-grid').style.display = 'none';
        document.getElementById('empty-state').style.display = 'none';
        document.getElementById('error-state').style.display = 'flex';
        document.getElementById('error-message').textContent = message;
    }
    
    formatStatusText(status) {
        const statusMap = {
            'ready': 'Ready',
            'printing': 'Printing',
            'paused': 'Paused',
            'complete': 'Complete',
            'cancelled': 'Cancelled',
            'error': 'Error',
            'offline': 'Offline',
            'standby': 'Standby',
            'operational': 'Ready'
        };
        
        return statusMap[status] || status.charAt(0).toUpperCase() + status.slice(1);
    }
    
    formatRelativeTime(date) {
        const now = new Date();
        const diffMs = now - date;
        const diffSecs = Math.floor(diffMs / 1000);
        const diffMins = Math.floor(diffSecs / 60);
        const diffHours = Math.floor(diffMins / 60);
        const diffDays = Math.floor(diffHours / 24);
        
        if (diffSecs < 60) {
            return 'Just now';
        } else if (diffMins < 60) {
            return `${diffMins}m ago`;
        } else if (diffHours < 24) {
            return `${diffHours}h ago`;
        } else {
            return `${diffDays}d ago`;
        }
    }
    
    async showCameraModal(printerName, cameraEntity) {
        const modal = document.getElementById('camera-modal');
        const title = document.getElementById('camera-modal-title');
        const stream = document.getElementById('camera-stream');
        const loading = document.getElementById('camera-loading');
        const error = document.getElementById('camera-error');
        
        // Set title
        title.textContent = `${printerName} Camera`;
        
        // Show modal and loading state
        modal.style.display = 'flex';
        loading.style.display = 'flex';
        stream.style.display = 'none';
        error.style.display = 'none';
        
        this.currentCameraPrinter = printerName;
        
        // Load fresh camera feed
        await this.loadCameraFeed();
    }
    
    async loadCameraFeed() {
        if (!this.currentCameraPrinter) return;
        
        const stream = document.getElementById('camera-stream');
        const loading = document.getElementById('camera-loading');
        const error = document.getElementById('camera-error');
        
        try {
            // Get fresh snapshot URL
            const timestamp = Date.now();
            const snapshotResponse = await fetch(`api/camera/${this.currentCameraPrinter}/snapshot?_=${timestamp}`);
            const snapshotData = await snapshotResponse.json();
            
            console.log('API Response:', snapshotData); // Debug log
            
            if (snapshotResponse.ok && snapshotData.snapshot_url) {
                // Use the snapshot URL directly without any modifications
                const imageUrl = snapshotData.snapshot_url;
                
                console.log('Loading image from URL:', imageUrl); // Debug log
                
                stream.onload = () => {
                    loading.style.display = 'none';
                    stream.style.display = 'block';
                    error.style.display = 'none';
                    console.log('Camera image loaded successfully'); // Debug log
                };
                
                stream.onerror = (e) => {
                    loading.style.display = 'none';
                    error.style.display = 'flex';
                    error.querySelector('p').textContent = 'Failed to load camera image';
                    console.error('Camera image failed to load:', e); // Debug log
                    console.error('Failed URL:', imageUrl); // Debug log
                };
                
                // Set the image source directly
                stream.src = imageUrl;
                
                // Start auto-refresh to get fresh images
                this.startCameraRefresh();
            } else {
                throw new Error(snapshotData.error || 'Failed to get camera snapshot');
            }
        } catch (err) {
            console.error('Error loading camera feed:', err);
            loading.style.display = 'none';
            error.style.display = 'flex';
            error.querySelector('p').textContent = err.message || 'Camera feed unavailable';
        }
    }
    
    hideCameraModal() {
        const modal = document.getElementById('camera-modal');
        const stream = document.getElementById('camera-stream');
        
        modal.style.display = 'none';
        stream.src = '';
        this.currentCameraPrinter = null;
        this.stopCameraRefresh();
    }
    
    async refreshCameraFeed() {
        // Just call loadCameraFeed which gets fresh tokens
        await this.loadCameraFeed();
    }
    
    startCameraRefresh() {
        this.stopCameraRefresh();
        // Refresh every 3 seconds to get fresh tokens and images
        this.cameraRefreshInterval = setInterval(() => {
            this.loadCameraFeed();
        }, 3000);
    }
    
    stopCameraRefresh() {
        if (this.cameraRefreshInterval) {
            clearInterval(this.cameraRefreshInterval);
            this.cameraRefreshInterval = null;
        }
    }
}

// Initialize the dashboard when the page loads
document.addEventListener('DOMContentLoaded', () => {
    window.printFarmDashboard = new PrintFarmDashboard();
});

// Handle page visibility changes to pause/resume updates
document.addEventListener('visibilitychange', () => {
    if (window.printFarmDashboard) {
        if (document.hidden) {
            window.printFarmDashboard.stopAutoUpdate();
        } else {
            window.printFarmDashboard.startAutoUpdate();
            window.printFarmDashboard.refreshAll();
        }
    }
});

// Handle beforeunload to cleanup
window.addEventListener('beforeunload', () => {
    if (window.printFarmDashboard) {
        window.printFarmDashboard.stopAutoUpdate();
    }
}); 