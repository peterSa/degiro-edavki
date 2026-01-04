document.addEventListener('DOMContentLoaded', function() {
    const dropZone = document.getElementById('dropZone');
    const csvFiles = document.getElementById('csvFiles');
    const filesList = document.getElementById('filesList');
    const fileItems = document.getElementById('fileItems');
    const uploadForm = document.getElementById('uploadForm');
    const processBtn = document.getElementById('processBtn');
    const btnText = document.getElementById('btnText');
    const btnSpinner = document.getElementById('btnSpinner');
    const loadingOverlay = document.getElementById('loadingOverlay');
    const loadingMessage = document.getElementById('loadingMessage');

    // File storage in session
    let uploadedFiles = [];

    // Click on drop zone to trigger file input
    dropZone.addEventListener('click', function(e) {
        if (e.target !== dropZone.querySelector('.drop-zone-content')) {
            csvFiles.click();
        }
    });

    // Drag and drop events
    dropZone.addEventListener('dragover', function(e) {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', function(e) {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', function(e) {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.remove('dragover');
        
        const files = e.dataTransfer.files;
        handleFiles(files);
    });

    // File selection via input
    csvFiles.addEventListener('change', function(e) {
        handleFiles(e.target.files);
    });

    // Handle uploaded files
    function handleFiles(files) {
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            
            // Validate file type
            if (!file.name.endsWith('.csv')) {
                alert('Samo CSV datoteke so dovoljene: ' + file.name);
                continue;
            }
            
            // Validate file size (50MB max)
            if (file.size > 50 * 1024 * 1024) {
                alert('Datoteka je prevelika (max 50MB): ' + file.name);
                continue;
            }
            
            // Check for duplicates
            if (!uploadedFiles.some(f => f.name === file.name)) {
                uploadedFiles.push(file);
            }
        }
        
        updateFileList();
        updateProcessButton();
    }

    // Update file list UI
    function updateFileList() {
        if (uploadedFiles.length === 0) {
            filesList.style.display = 'none';
            return;
        }
        
        filesList.style.display = 'block';
        fileItems.innerHTML = '';
        
        uploadedFiles.forEach((file, index) => {
            const li = document.createElement('li');
            li.className = 'list-group-item';
            li.innerHTML = `
                <span>
                    <i class="bi bi-file-earmark-text me-2"></i>
                    ${file.name} (${formatFileSize(file.size)})
                </span>
                <button type="button" class="btn btn-sm btn-outline-danger" 
                        onclick="removeFile(${index})">
                    <i class="bi bi-x"></i>
                </button>
            `;
            fileItems.appendChild(li);
        });
    }

    // Remove file from list
    window.removeFile = function(index) {
        uploadedFiles.splice(index, 1);
        updateFileList();
        updateProcessButton();
    };

    // Update process button state
    function updateProcessButton() {
        processBtn.disabled = uploadedFiles.length === 0;
    }

    // Format file size
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
    }

    // Form submission
    uploadForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        if (uploadedFiles.length === 0) {
            alert('Prosimo, naložite vsaj eno CSV datoteko.');
            return;
        }

        // Show loading overlay
        loadingOverlay.style.display = 'flex';
        btnText.textContent = 'Obdelava...';
        btnSpinner.classList.remove('d-none');
        processBtn.disabled = true;

        // Prepare form data
        const formData = new FormData();
        uploadedFiles.forEach((file, index) => {
            formData.append('files', file);
        });
        formData.append('year', document.getElementById('reportYear').value);
        formData.append('testMode', document.getElementById('testMode').checked);

        try {
            // First upload files
            const uploadResponse = await fetch('/upload', {
                method: 'POST',
                body: formData
            });

            if (!uploadResponse.ok) {
                const error = await uploadResponse.text();
                alert('Napaka pri nalaganju: ' + error);
                hideLoading();
                return;
            }

            // Then start processing
            const processResponse = await fetch('/process', {
                method: 'POST'
            });

            if (processResponse.ok) {
                // Start polling for status
                startPolling();
            } else {
                const error = await processResponse.text();
                alert('Napaka pri obdelavi: ' + error);
                hideLoading();
            }
        } catch (error) {
            alert('Napaka pri povezovanju s strežnikom: ' + error);
            hideLoading();
        }
    });

    // Start progress polling
    function startPolling() {
        loadingMessage.textContent = 'Obdelava v teku... Prosimo, počakajte.';
        
        const pollInterval = setInterval(async function() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();
                
                if (data.status === 'completed') {
                    clearInterval(pollInterval);
                    hideLoading();
                    window.location.href = data.redirect_url;
                } else if (data.status === 'error') {
                    clearInterval(pollInterval);
                    hideLoading();
                    alert('Napaka pri obdelavi: ' + data.error);
                }
            } catch (error) {
                console.error('Polling error:', error);
            }
        }, 1000);
    }

    // Hide loading overlay
    function hideLoading() {
        loadingOverlay.style.display = 'none';
        btnText.textContent = 'Obdelaj';
        btnSpinner.classList.add('d-none');
        processBtn.disabled = false;
    }

    // Search functionality for tables
    const searchInputs = document.querySelectorAll('[id$="Search"]');
    searchInputs.forEach(input => {
        input.addEventListener('keyup', function() {
            const filter = this.value.toLowerCase();
            const tableId = this.id.replace('Search', '');
            const table = document.getElementById(tableId);
            
            if (table) {
                const rows = table.getElementsByTagName('tbody')[0].getElementsByTagName('tr');
                
                for (let i = 0; i < rows.length; i++) {
                    const text = rows[i].textContent.toLowerCase();
                    rows[i].style.display = text.indexOf(filter) > -1 ? '' : 'none';
                }
            }
        });
    });
});