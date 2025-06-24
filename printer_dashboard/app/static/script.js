// Configuration for direct Moonraker control
const DIRECT_CONTROL_CONFIG = {
    // Enable/disable automatic direct control detection
    enableAutoDetection: true,
    
    // Debug logging for direct control
    debugLogging: true
};

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
        this.selectedDistance = 0.1; // Default jog distance
        this.currentMovementPrinter = null; // Track which printer's movement modal is open
        this.isMovementInProgress = false; // Track movement command progress
        
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
        
        // Movement modal controls
        const movementModal = document.getElementById('movement-modal');
        const movementCloseBtn = document.querySelector('.movement-modal-close');
        const movementCloseFooterBtn = document.getElementById('movement-close');
        
        if (movementCloseBtn) movementCloseBtn.addEventListener('click', () => this.hideMovementModal());
        if (movementCloseFooterBtn) movementCloseFooterBtn.addEventListener('click', () => this.hideMovementModal());
        
        // Click outside movement modal to close
        movementModal.addEventListener('click', (e) => {
            if (e.target === movementModal) {
                this.hideMovementModal();
            }
        });
        
        // Distance selector buttons
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('btn-distance')) {
                // Remove active class from all distance buttons
                document.querySelectorAll('.btn-distance').forEach(btn => btn.classList.remove('active'));
                // Add active class to clicked button
                e.target.classList.add('active');
                this.selectedDistance = parseFloat(e.target.getAttribute('data-distance'));
            }
        });
        
        // Movement action buttons (homing)
        document.addEventListener('click', (e) => {
            if (e.target.closest('.btn-movement-action')) {
                const btn = e.target.closest('.btn-movement-action');
                const action = btn.getAttribute('data-action');
                const axes = btn.getAttribute('data-axes');
                
                if (action === 'home') {
                    this.performHomeAction(axes);
                }
            }
        });
        
        // Jog buttons
        document.addEventListener('click', (e) => {
            if (e.target.closest('.btn-jog')) {
                const btn = e.target.closest('.btn-jog');
                const axis = btn.getAttribute('data-axis');
                const direction = parseFloat(btn.getAttribute('data-direction'));
                
                this.performJogAction(axis, direction);
            }
        });
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.hideModal();
                this.hideCameraModal();
                this.hideMovementModal();
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
                
                // Log extracted connection info if debug enabled
                if (DIRECT_CONTROL_CONFIG.debugLogging) {
                    const directInfo = this.getDirectControlInfo(config.name);
                    if (directInfo) {
                        console.log(`🔧 ${config.name}: Will use direct control ${directInfo.host}:${directInfo.port}`);
                    }
                }
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
                    if (action === 'movement') {
                        this.showMovementModal(printerName);
                    } else {
                        this.showControlModal(printerName, action);
                    }
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
    
    /**
     * Get the dynamic base URL for camera access
     * This handles different environments like HA mobile app, external URLs, etc.
     */
    async getDynamicBaseUrl() {
        // Strategy 1: Check if we're in HA mobile app context
        const userAgent = navigator.userAgent;
        const isHAApp = userAgent.includes('Home Assistant') || userAgent.includes('homeassistant');
        
        // Strategy 2: Check URL patterns to detect HA context
        const currentUrl = window.location.href;
        const isHAIngress = currentUrl.includes('/api/hassio_ingress/') || currentUrl.includes('/hassio_ingress/');
        const isNabuCasa = currentUrl.includes('.ui.nabu.casa');
        
        let baseUrl = window.location.origin;
        
        // Strategy 3: Force HTTPS for Nabu Casa cloud access
        if (isNabuCasa && baseUrl.startsWith('http://')) {
            baseUrl = baseUrl.replace('http://', 'https://');
            console.log(`Forced HTTPS for Nabu Casa: ${baseUrl}`);
        }
        
        // Strategy 4: If we're in HA ingress or mobile app, try to extract the external HA URL
        if (isHAIngress || isHAApp) {
            // Try to get the HA base URL from the current URL
            // Example: https://abc123.ui.nabu.casa/api/hassio_ingress/xyz/
            // Should become: https://abc123.ui.nabu.casa
            
            const urlParts = currentUrl.split('/');
            if (urlParts.length >= 3) {
                // Get protocol and host (first 3 parts: https:, '', host)
                const protocol = urlParts[0]; // https: or http:
                const host = urlParts[2]; // host:port or nabu.casa domain
                
                // Force HTTPS for cloud/external access
                const finalProtocol = (isNabuCasa || host.includes('.ui.nabu.casa')) ? 'https:' : protocol;
                baseUrl = `${finalProtocol}//${host}`;
                console.log(`Detected HA context, using base URL: ${baseUrl}`);
            }
            
            // Strategy 5: For mobile app or complex scenarios, ask the backend for help
            try {
                const haInfoResponse = await fetch('api/ha-info');
                if (haInfoResponse.ok) {
                    const haInfo = await haInfoResponse.json();
                    console.log('HA Info from backend:', haInfo);
                    
                    // Use the best available URL from the backend suggestions
                    const suggestedUrls = haInfo.suggested_base_urls || [];
                    for (const suggestedUrl of suggestedUrls) {
                        if (suggestedUrl && suggestedUrl.trim() && suggestedUrl !== baseUrl) {
                            let finalSuggestedUrl = suggestedUrl.trim();
                            
                            // Force HTTPS for Nabu Casa URLs
                            if (finalSuggestedUrl.includes('.ui.nabu.casa') && finalSuggestedUrl.startsWith('http://')) {
                                finalSuggestedUrl = finalSuggestedUrl.replace('http://', 'https://');
                            }
                            
                            baseUrl = finalSuggestedUrl;
                            console.log(`Using backend suggested base URL (HTTPS enforced): ${baseUrl}`);
                            break;
                        }
                    }
                }
            } catch (e) {
                console.warn('Could not fetch HA info from backend:', e);
            }
        }
        
        console.log(`Dynamic base URL detection:`, {
            userAgent: userAgent,
            isHAApp: isHAApp,
            isHAIngress: isHAIngress,
            isNabuCasa: isNabuCasa,
            currentUrl: currentUrl,
            detectedBaseUrl: baseUrl
        });
        
        return baseUrl;
    }

    async loadCameraFeed() {
        if (!this.currentCameraPrinter) return;
        
        const stream = document.getElementById('camera-stream');
        const loading = document.getElementById('camera-loading');
        const error = document.getElementById('camera-error');
        
        try {
            // Get the dynamic base URL using our smart detection
            const baseUrl = await this.getDynamicBaseUrl();
            
            // Get fresh snapshot URL with dynamic base_url
            const timestamp = Date.now();
            const snapshotResponse = await fetch(`api/camera/${this.currentCameraPrinter}/snapshot?base_url=${encodeURIComponent(baseUrl)}&_=${timestamp}`);
            
            if (!snapshotResponse.ok) {
                throw new Error(`API request failed: ${snapshotResponse.status} ${snapshotResponse.statusText}`);
            }
            
            const snapshotData = await snapshotResponse.json();
            
            console.log('API Response:', snapshotData); // Debug log
            console.log('Using base URL:', baseUrl); // Debug log
            
            if (snapshotData.snapshot_url) {
                // Use the snapshot URL directly without any modifications
                const imageUrl = snapshotData.snapshot_url;
                
                console.log('Loading image from URL:', imageUrl); // Debug log
                
                stream.onload = () => {
                    loading.style.display = 'none';
                    stream.style.display = 'block';
                    error.style.display = 'none';
                    console.log('✅ Camera image loaded successfully at:', new Date().toLocaleTimeString()); // Debug log
                };
                
                stream.onerror = (e) => {
                    loading.style.display = 'none';
                    error.style.display = 'flex';
                    error.querySelector('p').textContent = 'Failed to load camera image';
                    console.error('❌ Camera image failed to load:', e); // Debug log
                    console.error('Failed URL:', imageUrl); // Debug log
                    console.error('Current time:', new Date().toLocaleTimeString());
                };
                
                // Set the image source directly
                stream.src = imageUrl;
                
                // Start auto-refresh to get fresh images
                this.startCameraRefresh();
            } else {
                throw new Error(snapshotData.error || 'No snapshot_url in response');
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
        // Refresh every 500ms for very fast camera updates
        this.cameraRefreshInterval = setInterval(() => {
            this.loadCameraFeed();
        }, 3000); // Very fast refresh to test token expiration
    }
    
    stopCameraRefresh() {
        if (this.cameraRefreshInterval) {
            clearInterval(this.cameraRefreshInterval);
            this.cameraRefreshInterval = null;
        }
    }
    
    hideMovementModal() {
        const modal = document.getElementById('movement-modal');
        modal.style.display = 'none';
        this.currentMovementPrinter = null;
    }
    
    getDirectControlInfo(printerName) {
        /**
         * Check if a Klipper printer needs direct control and extract connection info from existing URL
         * Returns null if no direct control needed (OctoPrint or direct access), or {host, port} for Klipper direct control
         */
        const printer = this.printers.get(printerName);
        if (!printer || !printer.config) return null;
        
        // Check if auto-detection is enabled
        if (!DIRECT_CONTROL_CONFIG.enableAutoDetection) return null;
        
        const config = printer.config;
        
        // Only apply direct control for Klipper/Moonraker printers
        const isKlipper = config.type === 'klipper';
        
        // Don't use direct control for OctoPrint - let it use the original API
        if (!isKlipper) {
            if (DIRECT_CONTROL_CONFIG.debugLogging) {
                console.log(`📡 ${printerName} (${config.type}): Using original API (not Klipper)`);
            }
            return null;
        }
        
        // For Klipper printers, check if we're accessing through ingress
        const isIngressAccess = window.location.href.includes('/api/hassio_ingress/');
        
        // Extract host and port from the configured URL for Klipper printers
        try {
            const url = new URL(config.url);
            const host = url.hostname;
            const port = url.port || (url.protocol === 'https:' ? 443 : 80);
            
            // For Moonraker, default port is 7125 if not specified and protocol is http
            const moonrakerPort = url.port || (url.protocol === 'http:' ? 7125 : port);
            
            if (DIRECT_CONTROL_CONFIG.debugLogging) {
                console.log(`⚠️ Using direct control for ${printerName} (Klipper)`);
                console.log(`📋 Extracted from config URL: ${config.url}`);
                console.log(`📡 Direct connection: ${host}:${moonrakerPort}`);
                console.log(`🔗 Access method: ${isIngressAccess ? 'Home Assistant Ingress' : 'Direct'}`);
            }
            
            return {
                host: host,
                port: parseInt(moonrakerPort),
                api_key: config.api_key || null
            };
            
        } catch (error) {
            if (DIRECT_CONTROL_CONFIG.debugLogging) {
                console.error(`❌ Failed to parse URL for ${printerName}: ${config.url}`, error);
            }
            return null;
        }
    }

    showMovementModal(printerName) {
        const modal = document.getElementById('movement-modal');
        const title = document.getElementById('movement-modal-title');
        
        if (!modal) {
            console.error('Movement modal not found in DOM!');
            return;
        }
        
        if (!title) {
            console.error('Movement modal title not found in DOM!');
            return;
        }
        
        // Set title
        title.textContent = `${printerName} Movement Controls`;
        
        // Store current printer
        this.currentMovementPrinter = printerName;
        
        // Show modal
        modal.style.display = 'flex';
        
        // Reset distance selection to default
        const distanceButtons = document.querySelectorAll('.btn-distance');
        distanceButtons.forEach(btn => btn.classList.remove('active'));
        
        const defaultButton = document.querySelector('.btn-distance[data-distance="0.1"]');
        if (defaultButton) {
            defaultButton.classList.add('active');
            this.selectedDistance = 0.1;
        }
    }
    
    async performHomeAction(axes) {
        if (!this.currentMovementPrinter) return;
        
        // Prevent multiple simultaneous commands
        if (this.isMovementInProgress) {
            this.showNotification('Movement command already in progress', 'warning');
            return;
        }
        
        this.isMovementInProgress = true;
        this.setMovementButtonsState(false); // Disable buttons
        
        try {
            // Check if we need to use direct control
            const directInfo = this.getDirectControlInfo(this.currentMovementPrinter);
            
            let response, requestData = {};
            
            // Show loading notification
            const axesText = axes || 'all axes';
            this.showNotification(`Homing ${axesText}... Please wait`, 'info');
            
            if (directInfo) {
                // Use direct control API
                console.log(`🔀 Using direct control for ${this.currentMovementPrinter} home command`);
                
                if (axes && axes !== 'all') {
                    requestData.axes = [axes];
                }
                if (directInfo.api_key) {
                    requestData.api_key = directInfo.api_key;
                }
                
                console.log(`Homing ${this.currentMovementPrinter} via direct API: ${axes || 'all axes'}`);
                
                response = await fetch(`api/direct-control/${directInfo.host}/${directInfo.port}/home`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(requestData)
                });
            } else {
                // Use regular API
                console.log(`📡 Using regular API for ${this.currentMovementPrinter} home command`);
                
                if (axes && axes !== 'all') {
                    requestData.axes = [axes];
                }
                
                console.log(`Homing ${this.currentMovementPrinter}: ${axes || 'all axes'}`);
                
                response = await fetch(`api/control/${this.currentMovementPrinter}/home`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(requestData)
                });
            }
            
            const result = await response.json();
            
            if (result.success) {
                this.showNotification(`Homing ${axesText} completed successfully`, 'success');
            } else {
                this.showNotification(`Homing failed: ${result.error}`, 'error');
            }
            
        } catch (error) {
            console.error('Error performing home action:', error);
            this.showNotification(`Homing failed: ${error.message}`, 'error');
        } finally {
            this.isMovementInProgress = false;
            this.setMovementButtonsState(true); // Re-enable buttons
        }
    }
    
    async performJogAction(axis, direction) {
        if (!this.currentMovementPrinter || !this.selectedDistance) return;
        
        // Prevent multiple simultaneous commands
        if (this.isMovementInProgress) {
            this.showNotification('Movement command already in progress', 'warning');
            return;
        }
        
        this.isMovementInProgress = true;
        this.setMovementButtonsState(false); // Disable buttons
        
        const distance = this.selectedDistance * direction;
        
        try {
            // Show loading notification
            this.showNotification(`Jogging ${axis}${distance > 0 ? '+' : ''}${distance}mm... Please wait`, 'info');
            
            // Check if we need to use direct control
            const directInfo = this.getDirectControlInfo(this.currentMovementPrinter);
            
            let response;
            
            if (directInfo) {
                // Use direct control API
                console.log(`🔀 Using direct control for ${this.currentMovementPrinter} jog command`);
                
                const requestData = {
                    axis: axis,
                    distance: distance
                };
                if (directInfo.api_key) {
                    requestData.api_key = directInfo.api_key;
                }
                
                console.log(`Jogging ${this.currentMovementPrinter} via direct API: ${axis}${distance > 0 ? '+' : ''}${distance}mm`);
                
                response = await fetch(`api/direct-control/${directInfo.host}/${directInfo.port}/jog`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(requestData)
                });
            } else {
                // Use regular API
                console.log(`📡 Using regular API for ${this.currentMovementPrinter} jog command`);
                console.log(`Jogging ${this.currentMovementPrinter}: ${axis}${distance > 0 ? '+' : ''}${distance}mm`);
                
                response = await fetch(`api/control/${this.currentMovementPrinter}/jog`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        axis: axis,
                        distance: distance
                    })
                });
            }
            
            const result = await response.json();
            
            if (result.success) {
                this.showNotification(`Jogged ${axis}${distance > 0 ? '+' : ''}${distance}mm successfully`, 'success');
            } else {
                this.showNotification(`Jog failed: ${result.error}`, 'error');
            }
            
        } catch (error) {
            console.error('Error performing jog action:', error);
            this.showNotification(`Jog failed: ${error.message}`, 'error');
        } finally {
            this.isMovementInProgress = false;
            this.setMovementButtonsState(true); // Re-enable buttons
        }
    }
    
    setMovementButtonsState(enabled) {
        /**
         * Enable or disable movement control buttons
         */
        const modal = document.getElementById('movement-modal');
        if (!modal) return;
        
        const buttons = modal.querySelectorAll('button');
        buttons.forEach(button => {
            if (enabled) {
                button.disabled = false;
                button.style.opacity = '1';
            } else {
                button.disabled = true;
                button.style.opacity = '0.6';
            }
        });
    }
}

// File Management Class
class FileManager {
    constructor() {
        this.files = [];
        this.printers = [];
        this.init();
    }

    init() {
        this.setupEventListeners();
    }

    setupEventListeners() {
        // Files button
        document.getElementById('files-btn').addEventListener('click', () => {
            this.showFilesModal();
        });

        // Files modal controls
        const filesModal = document.getElementById('files-modal');
        const filesCloseBtn = document.querySelector('.files-modal-close');
        const filesCloseFooterBtn = document.getElementById('files-close');

        if (filesCloseBtn) filesCloseBtn.addEventListener('click', () => this.hideFilesModal());
        if (filesCloseFooterBtn) filesCloseFooterBtn.addEventListener('click', () => this.hideFilesModal());

        // Click outside modal to close
        filesModal.addEventListener('click', (e) => {
            if (e.target === filesModal) {
                this.hideFilesModal();
            }
        });

        // Upload controls
        const uploadBtn = document.getElementById('upload-btn');
        const fileInput = document.getElementById('file-input');
        const uploadArea = document.getElementById('upload-area');

        uploadBtn.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', (e) => this.handleFileSelect(e));

        // Drag and drop
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('dragover');
        });

        uploadArea.addEventListener('dragleave', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
        });

        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            this.handleFileSelect({ target: { files: e.dataTransfer.files } });
        });

        // Send file modal controls
        const sendFileModal = document.getElementById('send-file-modal');
        const sendCloseBtn = sendFileModal.querySelector('.modal-close');
        const sendCancelBtn = document.getElementById('send-cancel');
        const sendConfirmBtn = document.getElementById('send-confirm');

        if (sendCloseBtn) sendCloseBtn.addEventListener('click', () => this.hideSendFileModal());
        if (sendCancelBtn) sendCancelBtn.addEventListener('click', () => this.hideSendFileModal());
        if (sendConfirmBtn) sendConfirmBtn.addEventListener('click', () => this.confirmSendFile());

        // Click outside send modal to close
        sendFileModal.addEventListener('click', (e) => {
            if (e.target === sendFileModal) {
                this.hideSendFileModal();
            }
        });

        // File actions delegation
        document.addEventListener('click', (e) => {
            if (e.target.closest('.file-download')) {
                const fileId = e.target.closest('.file-item').getAttribute('data-file-id');
                this.downloadFile(fileId);
            } else if (e.target.closest('.file-delete')) {
                const fileId = e.target.closest('.file-item').getAttribute('data-file-id');
                this.deleteFile(fileId);
            } else if (e.target.closest('.file-send')) {
                const fileItem = e.target.closest('.file-item');
                const fileId = fileItem.getAttribute('data-file-id');
                const printerSelect = fileItem.querySelector('.printer-select');
                const printerName = printerSelect.value;
                
                if (!printerName) {
                    this.showNotification('Please select a printer first', 'warning');
                    return;
                }
                
                this.showSendFileModal(fileId, printerName);
            }
        });
    }

    async showFilesModal() {
        document.getElementById('files-modal').style.display = 'flex';
        await this.loadFiles();
        await this.loadPrinters();
    }

    hideFilesModal() {
        document.getElementById('files-modal').style.display = 'none';
    }

    async loadFiles() {
        try {
            const response = await fetch('api/files');
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            this.files = await response.json();
            this.renderFiles();
        } catch (error) {
            console.error('Error loading files:', error);
            this.showNotification('Failed to load files', 'error');
        }
    }

    async loadPrinters() {
        try {
            const response = await fetch('api/printers');
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            this.printers = await response.json();
            this.updatePrinterSelects();
        } catch (error) {
            console.error('Error loading printers:', error);
        }
    }

    updatePrinterSelects() {
        const printerSelects = document.querySelectorAll('.printer-select');
        printerSelects.forEach(select => {
            // Clear existing options except the first one
            while (select.children.length > 1) {
                select.removeChild(select.lastChild);
            }

            // Add printer options
            this.printers.forEach(printer => {
                const option = document.createElement('option');
                option.value = printer.name;
                option.textContent = printer.name;
                select.appendChild(option);
            });
        });
    }

    renderFiles() {
        const filesList = document.getElementById('files-list');
        const filesEmptyState = document.getElementById('files-empty-state');
        const filesCount = document.getElementById('files-count');

        filesCount.textContent = `${this.files.length} file${this.files.length !== 1 ? 's' : ''}`;

        if (this.files.length === 0) {
            filesList.style.display = 'none';
            filesEmptyState.style.display = 'block';
            return;
        }

        filesList.style.display = 'flex';
        filesEmptyState.style.display = 'none';

        filesList.innerHTML = '';

        this.files.forEach(file => {
            const fileItem = this.createFileItem(file);
            filesList.appendChild(fileItem);
        });

        // Update printer selects after rendering
        this.updatePrinterSelects();
    }

    createFileItem(file) {
        const template = document.getElementById('file-item-template');
        const fileItem = template.content.cloneNode(true);

        const container = fileItem.querySelector('.file-item');
        container.setAttribute('data-file-id', file.id);

        // File name
        fileItem.querySelector('.file-name').textContent = file.filename;

        // Thumbnail
        const thumbnailImage = fileItem.querySelector('.thumbnail-image');
        const thumbnailPlaceholder = fileItem.querySelector('.thumbnail-placeholder');
        
        if (file.thumbnail) {
            thumbnailImage.src = file.thumbnail;
            thumbnailImage.style.display = 'block';
            thumbnailPlaceholder.style.display = 'none';
        } else {
            thumbnailImage.style.display = 'none';
            thumbnailPlaceholder.style.display = 'flex';
        }

        // File metadata
        fileItem.querySelector('.file-size').textContent = this.formatFileSize(file.file_size);
        fileItem.querySelector('.file-date').textContent = this.formatDate(file.upload_time);

        // Optional metadata
        if (file.metadata.estimated_time) {
            const timeRow = fileItem.querySelector('.estimated-time');
            timeRow.style.display = 'flex';
            timeRow.querySelector('.file-estimated-time').textContent = file.metadata.estimated_time;
        }

        if (file.metadata.layer_height) {
            const layerRow = fileItem.querySelector('.layer-height');
            layerRow.style.display = 'flex';
            layerRow.querySelector('.file-layer-height').textContent = `${file.metadata.layer_height}mm`;
        }

        if (file.metadata.infill) {
            const infillRow = fileItem.querySelector('.infill');
            infillRow.style.display = 'flex';
            infillRow.querySelector('.file-infill').textContent = `${(parseFloat(file.metadata.infill) * 100).toFixed(0)}%`;
        }

        if (file.metadata.filament_used) {
            const filamentRow = fileItem.querySelector('.filament-used');
            filamentRow.style.display = 'flex';
            filamentRow.querySelector('.file-filament-used').textContent = file.metadata.filament_used;
        }

        if (file.metadata.nozzle_temp || file.metadata.bed_temp) {
            const tempRow = fileItem.querySelector('.temperatures');
            tempRow.style.display = 'flex';
            const temps = [];
            if (file.metadata.nozzle_temp) temps.push(`E: ${file.metadata.nozzle_temp}°C`);
            if (file.metadata.bed_temp) temps.push(`B: ${file.metadata.bed_temp}°C`);
            tempRow.querySelector('.file-temperatures').textContent = temps.join(', ');
        }

        return fileItem;
    }

    async handleFileSelect(event) {
        const files = Array.from(event.target.files);
        
        if (files.length === 0) return;

        // Validate files
        const validFiles = files.filter(file => {
            if (!file.name.toLowerCase().endsWith('.gcode')) {
                this.showNotification(`${file.name} is not a G-code file`, 'warning');
                return false;
            }
            return true;
        });

        if (validFiles.length === 0) return;

        // Upload files one by one
        for (const file of validFiles) {
            await this.uploadFile(file);
        }

        // Clear the input
        event.target.value = '';
    }

    async uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);

        try {
            this.showUploadProgress(0);
            
            console.log(`Starting upload of ${file.name} (${file.size} bytes)`);
            
            const response = await fetch('api/files/upload', {
                method: 'POST',
                body: formData
            });

            console.log(`Upload response status: ${response.status}`);
            
            let result;
            const contentType = response.headers.get('content-type');
            
            if (contentType && contentType.includes('application/json')) {
                result = await response.json();
            } else {
                // Handle non-JSON responses (e.g., HTML error pages)
                const text = await response.text();
                console.error('Non-JSON response:', text);
                throw new Error(`Server returned non-JSON response (${response.status}): ${text.substring(0, 100)}...`);
            }

            if (!response.ok) {
                throw new Error(result.error || `Server error: ${response.status}`);
            }

            if (!result.success) {
                throw new Error(result.error || 'Upload failed');
            }

            console.log('Upload successful:', result);
            this.showNotification(`${file.name} uploaded successfully`, 'success');
            
            // Reload files list
            await this.loadFiles();

        } catch (error) {
            console.error('Upload error:', error);
            
            // Provide more specific error messages
            let errorMessage = error.message;
            if (errorMessage.includes('JSON')) {
                errorMessage = 'Server configuration error. Please check the logs.';
            } else if (errorMessage.includes('NetworkError') || errorMessage.includes('fetch')) {
                errorMessage = 'Network error. Please check your connection.';
            }
            
            this.showNotification(`Upload failed: ${errorMessage}`, 'error');
        } finally {
            this.hideUploadProgress();
        }
    }

    showUploadProgress(progress) {
        const uploadProgress = document.getElementById('upload-progress');
        const uploadContent = document.querySelector('.upload-content');
        const progressFill = document.getElementById('upload-progress-fill');
        const progressText = document.getElementById('upload-progress-text');

        uploadContent.style.display = 'none';
        uploadProgress.style.display = 'block';
        progressFill.style.width = `${progress}%`;
        progressText.textContent = progress < 100 ? 'Uploading...' : 'Processing...';
    }

    hideUploadProgress() {
        setTimeout(() => {
            const uploadProgress = document.getElementById('upload-progress');
            const uploadContent = document.querySelector('.upload-content');
            
            uploadProgress.style.display = 'none';
            uploadContent.style.display = 'block';
        }, 1000);
    }

    async deleteFile(fileId) {
        if (!confirm('Are you sure you want to delete this file?')) {
            return;
        }

        try {
            const response = await fetch(`api/files/${fileId}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Delete failed');
            }

            this.showNotification('File deleted successfully', 'success');
            await this.loadFiles();

        } catch (error) {
            console.error('Delete error:', error);
            this.showNotification(`Delete failed: ${error.message}`, 'error');
        }
    }

    downloadFile(fileId) {
        const file = this.files.find(f => f.id === fileId);
        if (!file) return;

        const link = document.createElement('a');
        link.href = `api/files/${fileId}/download`;
        link.download = file.filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }

    showSendFileModal(fileId, printerName) {
        const file = this.files.find(f => f.id === fileId);
        if (!file) return;

        document.getElementById('send-file-name').textContent = file.filename;
        document.getElementById('send-printer-name').textContent = printerName;
        
        this.pendingSend = { fileId, printerName, filename: file.filename };
        document.getElementById('send-file-modal').style.display = 'flex';
    }

    hideSendFileModal() {
        document.getElementById('send-file-modal').style.display = 'none';
        this.pendingSend = null;
    }

    async confirmSendFile() {
        if (!this.pendingSend) return;

        const { fileId, printerName, filename } = this.pendingSend;

        try {
            const response = await fetch(`api/files/${fileId}/send`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    printer_name: printerName
                })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Send failed');
            }

            const result = await response.json();
            this.showNotification(`${filename} sent to ${printerName}`, 'success');
            this.hideSendFileModal();

        } catch (error) {
            console.error('Send error:', error);
            this.showNotification(`Send failed: ${error.message}`, 'error');
        }
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    }

    formatDate(dateString) {
        const date = new Date(dateString);
        return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { 
            hour: '2-digit', 
            minute: '2-digit' 
        });
    }

    showNotification(message, type = 'info') {
        // Use the dashboard's notification system if available
        if (window.printFarmDashboard && window.printFarmDashboard.showNotification) {
            window.printFarmDashboard.showNotification(message, type);
        } else {
            // Fallback to alert
            alert(message);
        }
    }
}

// Initialize the dashboard when the page loads
document.addEventListener('DOMContentLoaded', () => {
    window.printFarmDashboard = new PrintFarmDashboard();
    window.fileManager = new FileManager();
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

// -----------------------------------------------------------------------------
// Ensure trailing slash for Home Assistant ingress URLs
// When the dashboard is accessed through /api/hassio_ingress/<slug> without the
// trailing "/", making a relative request like "api/files" will drop the slug
// and hit the wrong endpoint.  We detect that situation early and reload the
// page with the trailing slash so that all subsequent relative paths resolve
// correctly, both locally and via Nabu Casa remote access.
// -----------------------------------------------------------------------------
(function ensureIngressTrailingSlash() {
    try {
        const { pathname, search, hash } = window.location;
        const ingressMatch = pathname.match(/\/api\/hassio_ingress\/[^/]+$/);
        if (ingressMatch && !pathname.endsWith('/')) {
            const newUrl = pathname + '/' + (search || '') + (hash || '');
            // Use replace so we don't pollute the browser history
            window.location.replace(newUrl);
        }
    } catch (e) {
        // Fail silently; better to continue loading than crash the script
        console.warn('Ingress trailing slash check failed:', e);
    }
})(); 