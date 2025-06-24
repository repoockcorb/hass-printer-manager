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
        
        // File upload modal elements (query DOM early)
        this.uploadModal = document.getElementById('upload-modal');
        this.uploadBtn = document.getElementById('files-btn');
        this.uploadCloseBtn = document.getElementById('upload-modal-close');
        this.uploadConfirmBtn = document.getElementById('upload-confirm');
        this.gcodeFileInput = document.getElementById('gcode-file-input');
        this.printerSelect = document.getElementById('printer-select');

        this.init();
        this.setupThumbnailModal();
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
            document.getElementById('mobile-status-filter').value = e.target.value;
            this.applyFilters();
        });
        
        document.getElementById('type-filter').addEventListener('change', (e) => {
            this.filters.type = e.target.value;
            document.getElementById('mobile-type-filter').value = e.target.value;
            this.applyFilters();
        });
        
        // Mobile filter controls
        document.getElementById('mobile-status-filter').addEventListener('change', (e) => {
            this.filters.status = e.target.value;
            document.getElementById('status-filter').value = e.target.value;
            this.applyFilters();
            this.closeMobileMenu();
        });

        document.getElementById('mobile-type-filter').addEventListener('change', (e) => {
            this.filters.type = e.target.value;
            document.getElementById('type-filter').value = e.target.value;
            this.applyFilters();
            this.closeMobileMenu();
        });

        // Mobile menu controls
        document.querySelector('.menu-toggle').addEventListener('click', () => {
            document.querySelector('.side-menu').classList.add('show');
            document.querySelector('.menu-overlay').style.display = 'block';
        });

        document.querySelector('.menu-overlay').addEventListener('click', () => {
            this.closeMobileMenu();
        });

        // Mobile buttons
        document.getElementById('mobile-files-btn').addEventListener('click', () => {
            this.showUploadModal();
            this.closeMobileMenu();
        });

        document.getElementById('mobile-refresh-btn').addEventListener('click', () => {
            this.refreshAll();
            this.closeMobileMenu();
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
                this.hideUploadModal();
            } else if (e.key === 'r' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                this.refreshAll();
            }
        });

        // Upload button
        if (this.uploadBtn) {
            this.uploadBtn.addEventListener('click', () => this.showUploadModal());
        }

        // Fallback: event delegation to capture clicks in complex ingress DOMs
        document.addEventListener('click', (e) => {
            const target = e.target.closest('#files-btn');
            if (target) {
                e.preventDefault();
                this.showUploadModal();
            }
        });

        if (this.uploadCloseBtn) {
            this.uploadCloseBtn.addEventListener('click', () => this.hideUploadModal());
        }

        // Confirm upload
        if (this.uploadConfirmBtn) {
            this.uploadConfirmBtn.addEventListener('click', () => this.uploadAndSendGcode());
        }

        // Send file buttons (delegated)
        document.addEventListener('click', (e) => {
            const btn = e.target.closest('.btn-send-file');
            if (btn) {
                const file = btn.getAttribute('data-file');
                this.sendExistingFile(file);
            }
        });

        // Delete file buttons (delegated)
        document.addEventListener('click', (e) => {
            const delBtn = e.target.closest('.btn-delete-file');
            if (delBtn) {
                const file = delBtn.getAttribute('data-file');
                this.deleteFile(file);
            }
        });

        // Initialize drag and drop
        this.initDragAndDrop();

        // Close menu when clicking outside
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.side-menu') && !e.target.closest('.menu-toggle')) {
                sideMenu.classList.remove('show');
                menuOverlay.classList.remove('show');
                document.body.style.overflow = '';
            }
        });

        // Menu Toggle
        document.querySelector('.menu-toggle').addEventListener('click', () => {
            document.querySelector('.side-menu').classList.add('show');
            document.querySelector('.menu-overlay').style.display = 'block';
        });

        document.querySelector('.menu-overlay').addEventListener('click', () => {
            document.querySelector('.side-menu').classList.remove('show');
            document.querySelector('.menu-overlay').style.display = 'none';
        });

        // Sync desktop and mobile filters
        document.getElementById('status-filter').addEventListener('change', (e) => {
            document.getElementById('mobile-status-filter').value = e.target.value;
            this.applyFilters();
        });

        document.getElementById('mobile-status-filter').addEventListener('change', (e) => {
            document.getElementById('status-filter').value = e.target.value;
            this.applyFilters();
            this.closeMobileMenu();
        });

        document.getElementById('type-filter').addEventListener('change', (e) => {
            document.getElementById('mobile-type-filter').value = e.target.value;
            this.applyFilters();
        });

        document.getElementById('mobile-type-filter').addEventListener('change', (e) => {
            document.getElementById('type-filter').value = e.target.value;
            this.applyFilters();
            this.closeMobileMenu();
        });

        // Sync desktop and mobile buttons
        document.getElementById('files-btn').addEventListener('click', this.showUploadModal.bind(this));
        document.getElementById('mobile-files-btn').addEventListener('click', () => {
            this.showUploadModal();
            this.closeMobileMenu();
        });

        document.getElementById('refresh-btn').addEventListener('click', this.refreshAll.bind(this));
        document.getElementById('mobile-refresh-btn').addEventListener('click', () => {
            this.refreshAll();
            this.closeMobileMenu();
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
                    lastUpdate: null,
                    thumbnailFile: null // Track which file's thumbnail is loaded
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
        
        if (status.file) {
            fileName.textContent = status.file;
            const progVal = (status.progress !== undefined && status.progress !== null) ? status.progress : 0;
            progressFill.style.width = `${progVal}%`;
            progressText.textContent = `${progVal}%`;

            // Show thumbnail button
            const thumbBtn = card.querySelector('.thumb-btn');
            if (thumbBtn) thumbBtn.style.display = 'inline-flex';
        } else {
            fileName.textContent = 'No active print';
            progressFill.style.width = '0%';
            progressText.textContent = '0%';

            // Show thumbnail button
            const thumbBtn = card.querySelector('.thumb-btn');
            if (thumbBtn) thumbBtn.style.display = 'none';
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
        let errorCount = 0;
        
        for (const [name, printer] of this.printers.entries()) {
            totalCount++;
            
            if (!printer.status || !printer.status.online) {
                errorCount++;
            } else {
                const state = printer.status.state.toLowerCase();
                if (['printing'].includes(state)) {
                    printingCount++;
                } else {
                    idleCount++;
                }
            }
        }
        
        document.getElementById('total-count').textContent = totalCount;
        document.getElementById('printing-count').textContent = printingCount;
        document.getElementById('idle-count').textContent = idleCount;
        document.getElementById('error-count').textContent = errorCount;
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
            let response;
            const directInfo=this.getDirectControlInfo(printerName);

            const directSupported=['home','jog','gcode'];
            const printActions=['pause','resume','cancel'];

            if(directInfo && directSupported.includes(action)){
                // use direct Moonraker control for supported actions
                console.log(`🔀 Using direct control for ${printerName} ${action}`);
                const url=`api/direct-control/${directInfo.host}/${directInfo.port}/${action}`;
                const body={};
                if(action==='jog' || action==='home'){
                    /* parameters already handled elsewhere */
                }
                if(directInfo.api_key) body.api_key=directInfo.api_key;
                response=await fetch(url,{method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
            }else if(printActions.includes(action)){
                // use new printer/print API for print control actions
                response = await fetch(`api/printer/${printerName}/print/${action}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });
            }else{
                // regular routed API for other actions
                response = await fetch(`api/control/${printerName}/${action}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });
            }
            
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
                // Add timestamp to the snapshot URL to prevent caching
                const imageUrl = new URL(snapshotData.snapshot_url);
                imageUrl.searchParams.set('_', timestamp);
                
                console.log('Loading image from URL:', imageUrl.toString()); // Debug log
                
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
                    console.error('Failed URL:', imageUrl.toString()); // Debug log
                    console.error('Current time:', new Date().toLocaleTimeString());
                };
                
                // Set the image source with the timestamped URL
                stream.src = imageUrl.toString();
                
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
        // Stop the refresh interval first
        this.stopCameraRefresh();
        
        // Clear the current printer reference
        this.currentCameraPrinter = null;
        
        // Get all the modal elements
        const modal = document.getElementById('camera-modal');
        const stream = document.getElementById('camera-stream');
        const loading = document.getElementById('camera-loading');
        const error = document.getElementById('camera-error');
        
        // Hide all elements
        modal.style.display = 'none';
        if (loading) loading.style.display = 'none';
        if (error) error.style.display = 'none';
        
        // Clear the image source and remove event listeners
        if (stream) {
            stream.onload = null;
            stream.onerror = null;
            stream.src = '';
        }
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
        }, 500); // Very fast refresh to test token expiration
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

    async loadThumbnail(printerName, file, card) {
        try {
            const response = await fetch(`api/thumbnail/${encodeURIComponent(printerName)}?file=${encodeURIComponent(file)}`);
            if (response.ok) {
                const blob = await response.blob();
                const objectURL = URL.createObjectURL(blob);
                const thumbImg = card.querySelector('.print-thumbnail');
                if (thumbImg) {
                    thumbImg.src = objectURL;
                    thumbImg.style.display = 'block';
                }
            }
        } catch (error) {
            // Silently fail; backend already returns placeholder PNG
        }
    }

    /* =================== Upload Modal =================== */
    showUploadModal() {
        if (!this.uploadModal) return;
        this.populatePrinterSelect();
        this.loadFileList();
        this.uploadModal.style.display = 'flex';
    }

    hideUploadModal() {
        if (!this.uploadModal) return;
        this.uploadModal.style.display = 'none';
        // Reset form
        if (this.gcodeFileInput) this.gcodeFileInput.value = '';
        document.getElementById('upload-progress').style.display = 'none';
        document.getElementById('upload-error').style.display = 'none';
    }

    populatePrinterSelect() {
        if (!this.printerSelect) return;
        this.printerSelect.innerHTML = '';
        for (const [name] of this.printers.entries()) {
            const opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name;
            this.printerSelect.appendChild(opt);
        }
    }

    async uploadAndSendGcode() {
        const file = this.gcodeFileInput.files[0];
        const printer = this.printerSelect.value;
        const progressEl = document.getElementById('upload-progress');
        const errorEl = document.getElementById('upload-error');
        if (!file) {
            errorEl.textContent = 'Please select a file';
            errorEl.style.display = 'block';
            return;
        }
        errorEl.style.display = 'none';
        progressEl.style.display = 'block';

        try {
            // 1. Upload file to server
            const formData = new FormData();
            formData.append('file', file);
            const uploadResp = await fetch('api/gcode/upload', { method: 'POST', body: formData });
            const uploadResJson = await uploadResp.json();
            if (!uploadResp.ok || !uploadResJson.success) {
                throw new Error(uploadResJson.error || 'Upload failed');
            }

            this.showNotification(`File "${uploadResJson.file}" uploaded`, 'success');
            // Clear file input and refresh list
            if (this.gcodeFileInput) this.gcodeFileInput.value = '';
            this.loadFileList();
        } catch (err) {
            console.error('Upload error', err);
            errorEl.textContent = err.message;
            errorEl.style.display = 'block';
            progressEl.style.display = 'none';
        }
    }

    /* =================== File list =================== */
    async loadFileList() {
        const container = document.getElementById('file-list-container');
        if (!container) return;
        container.innerHTML = '<p style="color:#94a3b8;">Loading...</p>';
        try {
            const resp = await fetch('api/gcode/files');
            const files = await resp.json();
            container.innerHTML = '';
            if (!files.length) {
                container.innerHTML = '<p style="color:#94a3b8;">No files uploaded.</p>';
                return;
            }
            files.forEach(f => {
                const row = document.createElement('div');
                row.className = 'file-row';
                row.style.display = 'flex';
                row.style.alignItems = 'center';
                row.style.justifyContent = 'space-between';
                row.style.padding = '0.25rem 0';

                const thumb = document.createElement('img');
                thumb.className = 'file-thumb';
                thumb.src = `files/thumbnail?filename=${encodeURIComponent(f.name)}`;

                const nameEl = document.createElement('span');
                nameEl.textContent = f.name;
                nameEl.style.flex = '1';
                nameEl.style.color = '#e0e6ed';

                const sizeEl = document.createElement('span');
                sizeEl.textContent = this.formatBytes(f.size);
                sizeEl.style.marginRight = '0.5rem';
                sizeEl.style.color = '#94a3b8';

                const sendBtn = document.createElement('button');
                sendBtn.className = 'btn-icon btn-send-icon btn-send-file';
                sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i>';
                sendBtn.setAttribute('data-file', f.name);

                const delBtn = document.createElement('button');
                delBtn.className = 'btn-icon btn-delete-icon btn-delete-file';
                delBtn.innerHTML = '<i class="fas fa-trash"></i>';
                delBtn.setAttribute('data-file', f.name);

                row.appendChild(thumb);
                row.appendChild(nameEl);
                row.appendChild(sizeEl);
                row.appendChild(delBtn);
                row.appendChild(sendBtn);
                container.appendChild(row);
            });
        } catch (err) {
            container.innerHTML = `<p style="color:#f87171;">Error: ${err.message}</p>`;
        }
    }

    formatBytes(bytes) {
        const sizes = ['B', 'KB', 'MB', 'GB'];
        if (bytes === 0) return '0 B';
        const i = Math.floor(Math.log(bytes) / Math.log(1024));
        return parseFloat((bytes / Math.pow(1024, i)).toFixed(2)) + ' ' + sizes[i];
    }

    async sendExistingFile(fileName) {
        const printer = this.printerSelect.value;
        const errorEl = document.getElementById('upload-error');
        const progressEl = document.getElementById('upload-progress');
        errorEl.style.display = 'none';
        progressEl.style.display = 'block';
        progressEl.textContent = 'Sending...';
        try {
            const sendResp = await fetch('api/gcode/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ printer, file: fileName, start: true })
            });
            const sendJson = await sendResp.json();
            if (!sendResp.ok || !sendJson.success) {
                throw new Error(sendJson.error || 'Send failed');
            }
            this.showNotification(`File sent to ${printer} successfully`, 'success');
            this.hideUploadModal();
        } catch (err) {
            errorEl.textContent = err.message;
            errorEl.style.display = 'block';
        } finally {
            progressEl.style.display = 'none';
        }
    }

    // Delete stored file and refresh list
    async deleteFile(fileName) {
        const confirmDelete = confirm(`Delete ${fileName}?`);
        if (!confirmDelete) return;

        try {
            const resp = await fetch(`api/gcode/files/${encodeURIComponent(fileName)}`, {method: 'DELETE'});
            const json = await resp.json();
            if (!resp.ok || !json.success) {
                throw new Error(json.error || 'Delete failed');
            }
            this.showNotification(`Deleted ${fileName}`, 'success');
            this.loadFileList();
        } catch (err) {
            this.showNotification(err.message, 'error');
        }
    }

    /* ---------------- Drag & Drop Init ---------------- */
    initDragAndDrop() {
        const dz = document.getElementById('gcode-drop-zone');
        const fileInput = this.gcodeFileInput;
        const selectBtn = document.getElementById('gcode-select-btn');
        if (!dz || !fileInput) return;

        const processFiles = (fileList) => {
            Array.from(fileList).forEach(f => {
                this.uploadSingleFile(f);
            });
        };

        dz.addEventListener('click', () => fileInput.click());
        if (selectBtn) selectBtn.addEventListener('click', (e)=>{e.stopPropagation();fileInput.click();});

        dz.addEventListener('dragover', (e)=>{e.preventDefault(); dz.classList.add('drag-over');});
        dz.addEventListener('dragleave', ()=>dz.classList.remove('drag-over'));
        dz.addEventListener('drop', (e)=>{
            e.preventDefault(); dz.classList.remove('drag-over');
            processFiles(e.dataTransfer.files);
        });

        fileInput.addEventListener('change', (e)=>{
            processFiles(e.target.files);
        });
    }

    async uploadSingleFile(file) {
        const progressEl = document.getElementById('upload-progress');
        const errorEl = document.getElementById('upload-error');
        errorEl.style.display = 'none';
        progressEl.style.display = 'block';
        progressEl.textContent = `Uploading ${file.name}...`;
        try {
            const formData = new FormData();
            formData.append('file', file);
            const resp = await fetch('api/gcode/upload', {method:'POST', body: formData});
            const json = await resp.json();
            if (!resp.ok || !json.success) throw new Error(json.error||'Upload failed');
            this.showNotification(`Uploaded ${file.name}`, 'success');
            this.loadFileList();
        } catch(err){
            errorEl.textContent = err.message;
            errorEl.style.display='block';
        } finally {
            progressEl.style.display='none';
        }
    }

    /* ---------------- Thumbnail Modal ---------------- */
    setupThumbnailModal() {
        const thumbModal = document.getElementById('thumb-modal');
        const closeBtn = document.querySelector('.thumb-modal-close');
        const footerClose = document.getElementById('thumb-close');

        if (closeBtn) closeBtn.addEventListener('click', ()=>this.hideThumbModal());
        if (footerClose) footerClose.addEventListener('click', ()=>this.hideThumbModal());

        thumbModal.addEventListener('click',(e)=>{ if(e.target===thumbModal) this.hideThumbModal(); });

        // delegate thumb button clicks
        document.addEventListener('click',(e)=>{
            const btn=e.target.closest('.thumb-btn');
            if(btn){
                const card=btn.closest('.printer-card');
                const printerName=card.getAttribute('data-printer-name');
                const printer=this.printers.get(printerName);
                if(printer && printer.status && printer.status.file){
                    this.showThumbModal(printerName, printer.status.file);
                }
            }
        });
    }

    showThumbModal(printerName, fileName){
        const modal=document.getElementById('thumb-modal');
        const img=document.getElementById('thumb-img');
        const load=document.getElementById('thumb-loading');
        const err=document.getElementById('thumb-error');
        img.style.display='none'; err.style.display='none'; load.style.display='flex';
        modal.style.display='flex';

        const tryUrls=[
            `files/thumbnail?filename=${encodeURIComponent(fileName)}`,
            `api/thumbnail/${encodeURIComponent(printerName)}?file=${encodeURIComponent(fileName)}`
        ];

        const fetchThumbnail=(urls)=>{
            if(!urls.length){throw new Error('no thumb');}
            const url=urls.shift();
            return fetch(url).then(r=>{
               if(r.ok) return r.blob();
               return fetchThumbnail(urls);
            });
        };

        fetchThumbnail(tryUrls)
            .then(blob=>{
                const url=URL.createObjectURL(blob);
                img.src=url;
                img.onload=()=>URL.revokeObjectURL(url);
                load.style.display='none';
                img.style.display='block';
            })
            .catch(()=>{
                load.style.display='none';
                err.style.display='flex';
            });
    }

    hideThumbModal(){
        document.getElementById('thumb-modal').style.display='none';
    }

    closeMobileMenu() {
        document.querySelector('.side-menu').classList.remove('show');
        document.querySelector('.menu-overlay').style.display = 'none';
    }

    updateStatusCounts() {
        const printers = document.querySelectorAll('.printer-card');
        let total = printers.length;
        let printing = 0;
        let idle = 0;
        let error = 0;

        printers.forEach(printer => {
            const status = printer.getAttribute('data-status').toLowerCase();
            if (status === 'printing') printing++;
            else if (status === 'idle') idle++;
            else if (status === 'error') error++;
        });

        document.getElementById('total-count').textContent = total;
        document.getElementById('printing-count').textContent = printing;
        document.getElementById('idle-count').textContent = idle;
        document.getElementById('error-count').textContent = error;
    }
}

// Initialize the dashboard when the DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new PrintFarmDashboard();
});

// Handle page visibility changes to pause/resume updates
document.addEventListener('visibilitychange', () => {
    if (window.dashboard) {
        if (document.hidden) {
            window.dashboard.stopAutoUpdate();
        } else {
            window.dashboard.startAutoUpdate();
            window.dashboard.refreshAll();
        }
    }
});

// Handle beforeunload to cleanup
window.addEventListener('beforeunload', () => {
    if (window.dashboard) {
        window.dashboard.stopAutoUpdate();
    }
}); 