let activeMenuId = null;
let isModalOpen = false;
let isLoading = false;
let folders = [
    {
        id: 1,
        name: "hook_videos (4)",
        items: 5,
        modified: "Feb. 13, 2025, 2:34 p.m."
    }
];
let uploadProgress = 0;
let renamingFolderId = null;
let newFolderName = "";
let timeoutId = null;

function toggleMenu(event, folderId) {
    event.stopPropagation();
    if (timeoutId) clearTimeout(timeoutId);
    
    timeoutId = setTimeout(() => {
        if (activeMenuId === folderId) {
            document.getElementById(`actions-${folderId}`).style.display = 'none';
            activeMenuId = null;
        } else {
            if (activeMenuId) {
                document.getElementById(`actions-${activeMenuId}`).style.display = 'none';
            }
            document.getElementById(`actions-${folderId}`).style.display = 'block';
            activeMenuId = folderId;
        }
    }, 150);
}

document.addEventListener('click', (event) => {
    if (!event.target.closest('.actions') && !event.target.classList.contains('menu')) {
        if (activeMenuId) {
            document.getElementById(`actions-${activeMenuId}`).style.display = 'none';
            activeMenuId = null;
        }
    }
});

function openModal() {
    document.getElementById('uploadModal').style.display = 'block';
    isModalOpen = true;
    uploadProgress = 0;
    document.getElementById('progressPercent').textContent = '0%';
    document.getElementById('progressBar').style.width = '0%';
}

function closeModal() {
    document.getElementById('uploadModal').style.display = 'none';
    isModalOpen = false;
    uploadProgress = 0;
    document.getElementById('progressPercent').textContent = '0%';
    document.getElementById('progressBar').style.width = '0%';
}

// Function to create a ZIP file from the selected folder
async function createZipFromFolder(files) {
    showProgress(10, "Creating ZIP file...");
    
    // Load JSZip dynamically
    if (typeof JSZip === 'undefined') {
        await loadJSZip();
    }

    const zip = new JSZip();
    let processedCount = 0;
    const totalFiles = files.length;
    
    // Extract the root folder name from the first file's path
    const rootFolder = files[0].webkitRelativePath.split('/')[0];

    try {
        // Add each file to the ZIP
        for (const file of files) {
            const relativePath = file.webkitRelativePath;
            
            // Create a promise to read the file
            const fileContent = await readFileAsArrayBuffer(file);
            
            // Add to ZIP with relative path preserved
            zip.file(relativePath, fileContent);
            
            // Update progress
            processedCount++;
            const percent = Math.floor(10 + (processedCount / totalFiles) * 60);
            showProgress(percent, `Adding file ${processedCount} of ${totalFiles}`);
        }
        
        // Generate the ZIP file
        showProgress(70, "Generating ZIP file...");
        const content = await zip.generateAsync({
            type: "blob",
            compression: "DEFLATE",
            compressionOptions: { level: 6 }
        }, (metadata) => {
            const percent = Math.floor(70 + metadata.percent * 0.2);
            showProgress(percent, `Compressing: ${metadata.percent.toFixed(1)}%`);
        });
        
        showProgress(90, "Finalizing ZIP file...");
        
        // Create a File object from the Blob
        const zipFile = new File([content], `${rootFolder}.zip`, { type: "application/zip" });
        
        showProgress(95, "ZIP file ready for upload");
        return zipFile;
    } catch (error) {
        console.error("Error creating ZIP file:", error);
        alert("Failed to create ZIP file: " + error.message);
        return null;
    }
}

// Helper function to load JSZip library dynamically
function loadJSZip() {
    return new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = 'https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js';
        script.integrity = 'sha512-XMVd28F1oH/O71fzwBnV7HucLxVwtxf26XV8P4wPk26EDxuGZ91N8bsOttmnomcCD3CS5ZMRL50H0GgOHvegtg==';
        script.crossOrigin = 'anonymous';
        script.referrerPolicy = 'no-referrer';
        script.onload = () => resolve();
        script.onerror = () => reject(new Error('Failed to load JSZip'));
        document.head.appendChild(script);
    });
}

// Helper function to read a file as ArrayBuffer
function readFileAsArrayBuffer(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (e) => resolve(e.target.result);
        reader.onerror = (e) => reject(e.target.error);
        reader.readAsArrayBuffer(file);
    });
}

// Function to update progress bar and text
function showProgress(percent, message) {
    uploadProgress = Math.min(percent, 100);
    document.getElementById('progressPercent').textContent = `${uploadProgress}%`;
    document.getElementById('progressBar').style.width = `${uploadProgress}%`;
    console.log(message);
}

document.getElementById('uploadForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const files = document.getElementById('fileInput').files;
    if (!files || files.length === 0) return;

    try {
        isLoading = true;
        document.getElementById('loader').style.display = 'block';
        
        // Create a ZIP file from the selected folder
        const zipFile = await createZipFromFolder(files);
        if (!zipFile) {
            isLoading = false;
            document.getElementById('loader').style.display = 'none';
            return;
        }
        
        // Create a FormData object for the upload
        const formData = new FormData(document.getElementById('uploadForm'));
        
        // Remove any existing files from the formData
        formData.delete('folder');
        
        // Add the ZIP file
        formData.append('zip_file', zipFile);
        
        // Show initial upload status
        showProgress(95, "Starting upload to server...");
        
        // Set up upload timeout handler
        const uploadTimeout = setTimeout(() => {
            console.log("Upload taking longer than expected, but still in progress...");
            showProgress(99, "Upload still in progress... Please be patient.");
        }, 30000); // 30 seconds timeout
        
        // Submit the form with fetch
        const response = await fetch(document.getElementById('uploadForm').action, {
            method: 'POST',
            body: formData,
            credentials: 'same-origin'
        });
        
        // Clear timeout
        clearTimeout(uploadTimeout);
        
        if (response.ok) {
            showProgress(100, "Upload complete!");
            
            // Show success message
            const uploadModal = document.getElementById('uploadModal');
            if (uploadModal) {
                const modalContent = uploadModal.querySelector('.modal-content');
                if (modalContent) {
                    const successMsg = document.createElement('div');
                    successMsg.style.color = 'green';
                    successMsg.style.margin = '10px 0';
                    successMsg.style.textAlign = 'center';
                    successMsg.style.fontWeight = 'bold';
                    successMsg.textContent = "Upload successful! Refreshing page...";
                    modalContent.appendChild(successMsg);
                }
            }
            
            // Refresh after a short delay
            setTimeout(() => {
                window.location.reload();
            }, 1500);
        } else {
            const errorText = await response.text();
            throw new Error(`Server responded with an error: ${errorText}`);
        }
    } catch (error) {
        console.error("Error during upload:", error);
        alert("Upload failed: " + error.message);
        
        // If the request failed but files were already processed on the server,
        // refresh the page to show the new files
        if (uploadProgress >= 95) {
            if (confirm("The upload might have partially succeeded. Do you want to refresh the page to check?")) {
                window.location.reload();
            }
        }
    } finally {
        isLoading = false;
        document.getElementById('loader').style.display = 'none';
    }
});

function startRename(id, currentName) {
    // Show an alert to verify this function is being called
    alert("Starting rename for asset ID: " + id + " with current name: " + currentName);
    
    renamingFolderId = id;
    newFolderName = currentName;
    
    // Find the correct element to modify based on whether it's a folder or file
    let item;
    if (document.querySelector(`.folder-item[data-folder-id="${id}"]`)) {
        item = document.querySelector(`.folder-item[data-folder-id="${id}"] .folder-name`);
    } else {
        const fileItem = document.querySelector(`[data-asset-id="${id}"] .file-name`);
        if (fileItem) {
            item = fileItem;
        } else {
            // Try to find in child items
            const childItem = document.querySelector(`.child-item .actions#actions-${id}`);
            if (childItem) {
                item = childItem.closest('.child-item').querySelector('.file-name');
            }
        }
    }
    
    if (!item) {
        alert("Could not find item to rename: " + id);
        return;
    }
    
    // Close all action menus
    document.querySelectorAll('.actions').forEach(menu => menu.style.display = 'none');
    
    // Create inline rename form
    const container = item.parentElement;
    const currentContent = container.innerHTML;
    
    // Create input field
    const input = document.createElement('input');
    input.type = 'text';
    input.value = currentName;
    input.style.padding = '5px';
    input.style.marginRight = '5px';
    input.style.width = '200px';
    
    // Create save button
    const saveBtn = document.createElement('button');
    saveBtn.textContent = 'Save';
    saveBtn.style.padding = '5px 10px';
    saveBtn.style.background = '#9662f9';
    saveBtn.style.color = 'white';
    saveBtn.style.border = 'none';
    saveBtn.style.borderRadius = '4px';
    saveBtn.style.cursor = 'pointer';
    
    // Create cancel button
    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancel';
    cancelBtn.style.padding = '5px 10px';
    cancelBtn.style.background = '#f0f0f0';
    cancelBtn.style.marginLeft = '5px';
    cancelBtn.style.border = 'none';
    cancelBtn.style.borderRadius = '4px';
    cancelBtn.style.cursor = 'pointer';
    
    // Replace content with form
    container.innerHTML = '';
    container.appendChild(input);
    container.appendChild(saveBtn);
    container.appendChild(cancelBtn);
    
    // Focus input field
    input.focus();
    input.select();
    
    // Cancel button event
    cancelBtn.addEventListener('click', function() {
        container.innerHTML = currentContent;
    });
    
    // Save button event
    saveBtn.addEventListener('click', function() {
        const newName = input.value.trim();
        if (!newName) {
            container.innerHTML = currentContent;
            return;
        }
        
        // Display loading indicator
        document.getElementById('loader').style.display = 'block';
        
        // Get CSRF token
        const csrfToken = getCsrfToken();
        alert("Sending rename request with CSRF token: " + (csrfToken ? "Found token" : "No token found"));
        
        // Make a direct form submission instead of fetch
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/rename-asset/${id}/`;
        form.style.display = 'none';
        
        // Add CSRF token
        const csrfInput = document.createElement('input');
        csrfInput.type = 'hidden';
        csrfInput.name = 'csrfmiddlewaretoken';
        csrfInput.value = csrfToken;
        form.appendChild(csrfInput);
        
        // Add new name
        const nameInput = document.createElement('input');
        nameInput.type = 'hidden';
        nameInput.name = 'new_name';
        nameInput.value = newName;
        form.appendChild(nameInput);
        
        // Add form to document and submit
        document.body.appendChild(form);
        form.submit();
    });
    
    // Handle enter/escape keys
    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            saveBtn.click();
        } else if (e.key === 'Escape') {
            cancelBtn.click();
        }
    });
}

function deleteFolder(id) {
    if (confirm("Are you sure you want to delete this item? This cannot be undone.")) {
        isLoading = true;
        document.getElementById('loader').style.display = 'block';
        
        // Get the CSRF token from a cookie or meta tag
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || 
                         document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='))?.split('=')[1];
        
        console.log("Deleting asset ID:", id);
        console.log("CSRF Token:", csrfToken ? "Found token" : "No token found");
        
        // Make API call to delete the asset
        fetch(`/delete-asset/${id}/`, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'X-CSRFToken': csrfToken,
                'Accept': 'application/json'
            }
        })
        .then(response => {
            console.log("Delete response status:", response.status);
            if (response.ok) {
                return response.json().then(data => {
                    console.log("Delete successful:", data);
                    
                    // Show success message
                    const successMessage = document.createElement('div');
                    successMessage.className = 'success-message';
                    successMessage.textContent = data.message || 'Asset deleted successfully!';
                    successMessage.style.position = 'fixed';
                    successMessage.style.top = '20px';
                    successMessage.style.left = '50%';
                    successMessage.style.transform = 'translateX(-50%)';
                    successMessage.style.backgroundColor = '#4CAF50';
                    successMessage.style.color = 'white';
                    successMessage.style.padding = '15px 20px';
                    successMessage.style.borderRadius = '4px';
                    successMessage.style.zIndex = '9999';
                    document.body.appendChild(successMessage);
                    
                    // Remove from UI
                    removeAssetFromUI(id);
                    
                    // Remove the message and reload after a delay
                    setTimeout(() => {
                        if (successMessage.parentNode) {
                            successMessage.parentNode.removeChild(successMessage);
                        }
                        window.location.reload();
                    }, 1500);
                });
            } else {
                return response.json().then(
                    // Handle error with data
                    data => {
                        console.error("Delete failed:", data);
                        alert(data.error || "Failed to delete asset. Please try again.");
                    },
                    // Handle error without json response
                    () => {
                        console.error("Delete failed with status:", response.status);
                        alert("Failed to delete asset. Server responded with status: " + response.status);
                    }
                );
            }
        })
        .catch(error => {
            console.error("Error deleting asset:", error);
            alert("Error connecting to server: " + error.message);
        })
        .finally(() => {
            isLoading = false;
            document.getElementById('loader').style.display = 'none';
        });
    }
    
    if (activeMenuId === id) {
        document.getElementById(`actions-${id}`).style.display = 'none';
        activeMenuId = null;
    }
}

// Helper function to get CSRF token
function getCsrfToken() {
    const csrfCookie = document.cookie.split(';').find(cookie => cookie.trim().startsWith('csrftoken='));
    if (csrfCookie) {
        return csrfCookie.split('=')[1];
    }
    // Fallback to get from DOM if cookie method fails
    return document.querySelector('[name=csrfmiddlewaretoken]')?.value;
}

// Helper function to remove asset from UI
function removeAssetFromUI(id) {
    // Check if it's a folder
    const folderItem = document.querySelector(`.folder-item[data-folder-id="${id}"]`);
    
    if (folderItem) {
        // It's a folder, also remove all child items
        const childItems = document.querySelectorAll(`.child-item[data-parent-id="${id}"]`);
        childItems.forEach(child => child.remove());
        folderItem.remove();
    } else {
        // It's a file
        const fileItem = document.querySelector(`[data-asset-id="${id}"]`);
        if (fileItem) {
            fileItem.remove();
        } else {
            // Check if it's a child file
            const childItems = document.querySelectorAll(`.child-item`);
            childItems.forEach(item => {
                if (item.querySelector(`#actions-${id}`)) {
                    item.remove();
                }
            });
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // Make sure we have the JSZip library available
    if (typeof JSZip === 'undefined') {
        loadJSZip().catch(err => console.error("Failed to load JSZip:", err));
    }
});