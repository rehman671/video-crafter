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
    // Define video extensions to accept
    const videoExtensions = ['.mp4', '.webm', '.ogg', '.mov', '.avi', '.wmv', '.flv', '.mkv', '.m4v', '.mpg', '.mpeg', '.3gp', '.3g2'];

    // Filter to include only video files and log what's being excluded
    const allFiles = Array.from(files);
    const videoFiles = [];
    const excludedFiles = [];

    console.log(`\n🎬 PROCESSING FOLDER FOR VIDEO FILES`);
    console.log(`Total files to process: ${allFiles.length}`);

    for (const file of allFiles) {
        const fileName = file.name.toLowerCase();
        const extension = fileName.substring(fileName.lastIndexOf('.'));
        const isVideo = videoExtensions.includes(extension);

        if (isVideo) {
            videoFiles.push(file);
            console.log(`✅ INCLUDING VIDEO: ${file.webkitRelativePath} (${extension})`);
        } else {
            excludedFiles.push(file);
            console.log(`❌ EXCLUDING NON-VIDEO: ${file.webkitRelativePath} (${extension || 'no extension'})`);
        }
    }

    // Log summary
    console.log(`\n📊 FILE FILTERING SUMMARY:`);
    console.log(`Total files found: ${allFiles.length}`);
    console.log(`Video files to include: ${videoFiles.length}`);
    console.log(`Non-video files excluded: ${excludedFiles.length}`);

    // Log excluded file types breakdown
    const excludedTypes = {};
    excludedFiles.forEach(file => {
        const ext = file.name.split('.').pop() || 'no-extension';
        excludedTypes[ext] = (excludedTypes[ext] || 0) + 1;
    });

    if (Object.keys(excludedTypes).length > 0) {
        console.log(`\n🚫 EXCLUDED FILE TYPES:`);
        Object.entries(excludedTypes).forEach(([ext, count]) => {
            console.log(`  .${ext}: ${count} file(s)`);
        });
    }

    if (videoFiles.length === 0) {
        console.error('⚠️ No video files found to compress!');
        alert('No video files found in the selected folder. Please select a folder containing video files.');
        return null;
    }

    showProgress(10, `Creating ZIP file with ${videoFiles.length} video files (excluded ${excludedFiles.length} non-video files)...`);

    // Load JSZip dynamically
    if (typeof JSZip === 'undefined') {
        await loadJSZip();
    }

    const zip = new JSZip();
    let processedCount = 0;
    const totalFiles = videoFiles.length;

    // Extract the root folder name from the first file's path
    const rootFolder = videoFiles[0].webkitRelativePath.split('/')[0];
    console.log(`\n📦 Creating ZIP for root folder: ${rootFolder}`);

    try {
        // Add each video file to the ZIP
        for (const file of videoFiles) {
            const relativePath = file.webkitRelativePath;
            console.log(`  Adding to ZIP: ${relativePath}`);

            // Create a promise to read the file
            const fileContent = await readFileAsArrayBuffer(file);

            // Add to ZIP with relative path preserved
            zip.file(relativePath, fileContent);

            // Update progress
            processedCount++;
            const percent = Math.floor(10 + (processedCount / totalFiles) * 60);
            showProgress(percent, `Adding video file ${processedCount} of ${totalFiles}`);
        }

        // Generate the ZIP file
        showProgress(70, "Generating ZIP file...");
        console.log('\n🗜️ Compressing ZIP file...');
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
        console.log(`✅ ZIP file created successfully with ${videoFiles.length} video files`);
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

// Helper function to check if a file is a video file
function isVideoFile(file) {
    const videoExtensions = ['.mp4', '.webm', '.ogg', '.mov', '.avi', '.wmv', '.flv', '.mkv', '.m4v', '.mpg', '.mpeg', '.3gp', '.3g2'];
    const fileName = file.name.toLowerCase();
    const extension = fileName.substring(fileName.lastIndexOf('.'));
    const isVideo = videoExtensions.includes(extension);

    // Log the check result for debugging
    if (!isVideo) {
        console.log(`🔍 Not a video file: ${file.name} (extension: ${extension})`);
    }

    return isVideo;
}

// Modified upload form handler to process subfolders individually
// Modified upload form handler to process subfolders individually - without spinner
document.getElementById('uploadForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const files = document.getElementById('fileInput').files;
    if (!files || files.length === 0) {
        alert('Please choose a folder to upload');
        return;
    }

    try {
        // Initialize UI for upload process
        updateProgressBar(0);
        updateUploadStatus('Starting upload process...');

        // Disable the upload button and show uploading text
        const uploadButton = document.querySelector('.upload-btn');
        if (uploadButton) {
            uploadButton.disabled = true;
            uploadButton.textContent = 'Uploading...';
        }

        // Get CSRF token
        const csrfToken = getCsrfToken();

        // Get the root folder name
        const rootFolder = files[0].webkitRelativePath.split('/')[0];
        console.log("Root folder:", rootFolder);

        // Organize files by subfolder
        const subfolders = {};
        // Organize video files by subfolder
        for (const file of files) {
            // Only process video files
            if (!isVideoFile(file)) {
                console.log(`Skipping non-video file: ${file.webkitRelativePath}`);
                continue;
            }

            const pathParts = file.webkitRelativePath.split('/');

            // Skip files directly in the root folder (we want only subfolders)
            if (pathParts.length <= 2) continue;

            const subfolder = pathParts[1];
            if (!subfolders[subfolder]) {
                subfolders[subfolder] = [];
            }
            subfolders[subfolder].push(file);
        }

        console.log("Subfolders found:", Object.keys(subfolders));

        // If no subfolders found, fall back to zipping the whole folder
        if (Object.keys(subfolders).length === 0) {
            console.log("No subfolders found, zipping entire folder");
            updateUploadStatus('No subfolders found, processing entire folder...');
            const videoFiles = Array.from(files).filter(file => isVideoFile(file));

            if (videoFiles.length === 0) {
                alert('No video files found in the selected folder');
                updateUploadStatus('No video files found');
                if (uploadButton) {
                    uploadButton.disabled = false;
                    uploadButton.textContent = 'Upload';
                }
                return;
            }
            const zipFile = await createZipFromFolder(files);
            if (!zipFile) {
                updateUploadStatus('Failed to create ZIP file');

                // Re-enable the upload button
                if (uploadButton) {
                    uploadButton.disabled = false;
                    uploadButton.textContent = 'Upload';
                }
                return;
            }

            const result = await uploadZipFile(zipFile, rootFolder, csrfToken);

            // Handle result
            if (result.success) {
                updateUploadStatus('Upload completed successfully!');
                addSuccessMessage("Upload successful!");
                setTimeout(() => window.location.reload(), 1500);
            } else {
                updateUploadStatus("Upload failed: " + (result.error || "Unknown error"));

                // Re-enable the upload button
                if (uploadButton) {
                    uploadButton.disabled = false;
                    uploadButton.textContent = 'Upload';
                }
            }

            return;
        }

        // Display status
        updateUploadStatus(`Found ${Object.keys(subfolders).length} subfolders to process`);

        // Initialize progress tracking
        const totalSubfolders = Object.keys(subfolders).length;
        let completedSubfolders = 0;
        let successCount = 0;

        try {
            // Process each subfolder in sequence
            for (const [subfolderName, files] of Object.entries(subfolders)) {
                try {
                    // Skip empty subfolders
                    if (files.length === 0) {
                        console.log(`Skipping empty subfolder: ${subfolderName}`);
                        completedSubfolders++;
                        continue;
                    }

                    // Update status
                    const folderIndex = completedSubfolders + 1;
                    updateUploadStatus(`Processing subfolder: ${subfolderName} (${folderIndex}/${totalSubfolders})`);

                    console.log(`Creating ZIP for subfolder: ${subfolderName}`);

                    // Create ZIP for this subfolder
                    const zipFile = await createZipFromSubfolder(files, subfolderName);
                    if (!zipFile) {
                        throw new Error(`Failed to create ZIP for subfolder: ${subfolderName}`);
                    }

                    console.log(`Uploading ZIP for subfolder: ${subfolderName}`);

                    // Upload the ZIP file
                    const result = await uploadZipFile(zipFile, subfolderName, csrfToken);

                    // Update progress
                    completedSubfolders++;
                    if (result.success) {
                        successCount++;
                        console.log(`Successfully uploaded subfolder: ${subfolderName}`);
                    } else {
                        console.error(`Failed to upload subfolder: ${subfolderName}`, result.error);
                    }

                    // Update progress bar
                    const progressPercent = Math.round((completedSubfolders / totalSubfolders) * 100);
                    updateProgressBar(progressPercent);
                    updateUploadStatus(`Processed ${completedSubfolders}/${totalSubfolders} subfolders (${successCount} successful)`);

                } catch (error) {
                    console.error(`Error processing subfolder ${subfolderName}:`, error);
                    completedSubfolders++;

                    // Update progress bar even on error
                    const progressPercent = Math.round((completedSubfolders / totalSubfolders) * 100);
                    updateProgressBar(progressPercent);
                    updateUploadStatus(`Error on subfolder ${subfolderName}: ${error.message}`);
                }
            }

            // Process results
            if (successCount === totalSubfolders) {
                updateUploadStatus('All subfolders uploaded successfully!');
                updateProgressBar(100);

                // Show success message in modal
                addSuccessMessage("Upload successful! Refreshing page...");

                // Reload page after a brief delay
                setTimeout(() => {
                    window.location.reload();
                }, 2000);
            } else if (successCount > 0) {
                // Some uploads successful
                updateUploadStatus(`Completed with ${successCount}/${totalSubfolders} subfolders uploaded successfully.`);

                // Show mixed success message
                addSuccessMessage(`Completed with ${successCount}/${totalSubfolders} subfolders uploaded successfully. Refreshing page...`);

                // Reload page after a brief delay
                setTimeout(() => {
                    window.location.reload();
                }, 3000);
            } else {
                // All uploads failed
                updateUploadStatus(`Failed to upload any subfolders. Please try again.`);

                // Re-enable the upload button
                if (uploadButton) {
                    uploadButton.disabled = false;
                    uploadButton.textContent = 'Upload';
                }
            }
        } catch (error) {
            console.error("Error in folder upload process:", error);
            updateUploadStatus(`Error: ${error.message}`);

            // Re-enable the upload button
            if (uploadButton) {
                uploadButton.disabled = false;
                uploadButton.textContent = 'Upload';
            }
        }

    } catch (error) {
        console.error("Error during upload:", error);
        updateUploadStatus("Upload failed: " + error.message);

        // Re-enable the upload button
        const uploadButton = document.querySelector('.upload-btn');
        if (uploadButton) {
            uploadButton.disabled = false;
            uploadButton.textContent = 'Upload';
        }
    }
});
// Function to create a ZIP file from subfolder files
async function createZipFromSubfolder(files, subfolderName) {
    // Define video extensions to accept
    const videoExtensions = ['.mp4', '.webm', '.ogg', '.mov', '.avi', '.wmv', '.flv', '.mkv', '.m4v', '.mpg', '.mpeg', '.3gp', '.3g2'];

    console.log(`\n🗂️ Processing subfolder: ${subfolderName}`);
    console.log(`Files passed to function: ${files.length}`);

    // Filter video files and log what we find
    const allFiles = Array.from(files);
    const videoFiles = [];
    const unexpectedFiles = [];

    for (const file of allFiles) {
        const fileName = file.name.toLowerCase();
        const extension = fileName.substring(fileName.lastIndexOf('.'));
        const isVideo = videoExtensions.includes(extension);

        if (isVideo) {
            videoFiles.push(file);
            console.log(`✅ VIDEO in subfolder: ${file.webkitRelativePath}`);
        } else {
            unexpectedFiles.push(file);
            console.log(`⚠️ UNEXPECTED NON-VIDEO in subfolder: ${file.webkitRelativePath}`);
        }
    }

    if (unexpectedFiles.length > 0) {
        console.warn(`⚠️ Found ${unexpectedFiles.length} non-video files in subfolder - excluding them`);
    }

    if (videoFiles.length === 0) {
        console.log(`❌ No video files in subfolder: ${subfolderName}`);
        return null;
    }

    updateUploadStatus(`Creating ZIP for subfolder: ${subfolderName} (${videoFiles.length} video files)`);

    // Load JSZip dynamically if it's not already loaded
    if (typeof JSZip === 'undefined') {
        await loadJSZip();
    }

    const zip = new JSZip();
    let processedCount = 0;
    const totalFiles = videoFiles.length;

    try {
        // Add each video file to the ZIP, preserving the subfolder structure
        for (const file of videoFiles) {
            // Get the relative path starting from the subfolder
            const pathParts = file.webkitRelativePath.split('/');
            const relativePath = pathParts.slice(1).join('/'); // Remove the main folder name

            console.log(`📦 Adding to subfolder ZIP: ${relativePath}`);

            // Create a promise to read the file
            const fileContent = await readFileAsArrayBuffer(file);

            // Add to ZIP with relative path preserved
            zip.file(relativePath, fileContent);

            // Update progress
            processedCount++;
            updateUploadStatus(`${subfolderName} - Adding video file ${processedCount} of ${totalFiles}`);
        }

        // Generate the ZIP file
        updateUploadStatus(`${subfolderName} - Compressing video files...`);
        const content = await zip.generateAsync({
            type: "blob",
            compression: "DEFLATE",
            compressionOptions: { level: 6 }
        }, (metadata) => {
            updateUploadStatus(`${subfolderName} - Compressing: ${metadata.percent.toFixed(1)}%`);
        });

        // Create a File object from the Blob
        const zipFile = new File([content], `${subfolderName}.zip`, { type: "application/zip" });

        updateUploadStatus(`${subfolderName} - ZIP file ready for upload`);
        console.log(`✅ Subfolder ZIP created successfully with ${videoFiles.length} video files`);
        return zipFile;
    } catch (error) {
        console.error(`❌ Error creating ZIP for subfolder ${subfolderName}:`, error);
        updateUploadStatus(`Error creating ZIP for subfolder ${subfolderName}: ${error.message}`);
        return null;
    }
}

// Function to upload a single ZIP file to the server
function uploadZipFile(zipFile, folderName, csrfToken) {
    return new Promise((resolve, reject) => {
        // Create a FormData object for this upload
        const formData = new FormData();

        // Add the ZIP file
        formData.append('zip_file', zipFile);

        // Add the folder name
        formData.append('main_folder_name', folderName);

        // Create an XHR request
        const xhr = new XMLHttpRequest();

        xhr.upload.addEventListener('progress', (event) => {
            if (event.lengthComputable) {
                const percentComplete = Math.round((event.loaded / event.total) * 100);
                updateUploadStatus(`Uploading ${folderName}: ${percentComplete}%`);
            }
        });

        xhr.addEventListener('load', function () {
            if (xhr.status === 200) {
                try {
                    // Some APIs may return empty response with 200 status - treat this as success
                    if (!xhr.responseText || xhr.responseText.trim() === '') {
                        updateUploadStatus(`Uploaded ${folderName} successfully!`);
                        resolve({ success: true });
                        return;
                    }

                    // Try to parse JSON response
                    const response = JSON.parse(xhr.responseText);

                    // Consider 200 status as success even if response doesn't have a success field
                    if (response.success === undefined || response.success) {
                        updateUploadStatus(`Uploaded ${folderName} successfully!`);
                        resolve({ success: true, response });
                    } else {
                        // Server explicitly returned success: false
                        updateUploadStatus(`Upload failed for ${folderName}: ${response.error || 'Unknown error'}`);
                        resolve({ success: false, error: response.error || 'Unknown error' });
                    }
                } catch (e) {
                    // If JSON parsing fails but status is 200, still treat as success
                    console.log(`JSON parsing error for ${folderName}, but status is 200. Treating as success.`);
                    updateUploadStatus(`Uploaded ${folderName} successfully!`);
                    resolve({ success: true });
                }
            } else {
                // HTTP error
                updateUploadStatus(`Upload failed for ${folderName}: Server returned ${xhr.status}`);
                resolve({ success: false, error: `Server returned ${xhr.status}` });
            }
        });

        xhr.addEventListener('error', function () {
            // Network error
            updateUploadStatus(`Upload failed for ${folderName}: Network error`);
            resolve({ success: false, error: 'Network error' });
        });

        xhr.addEventListener('abort', function () {
            // Upload aborted
            updateUploadStatus(`Upload aborted for ${folderName}`);
            resolve({ success: false, error: 'Upload aborted' });
        });

        // Send the request
        xhr.open('POST', document.getElementById('uploadForm').action);
        xhr.setRequestHeader('X-CSRFToken', csrfToken);
        xhr.send(formData);
    });
}

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
    cancelBtn.addEventListener('click', function () {
        container.innerHTML = currentContent;
    });

    // Save button event
    saveBtn.addEventListener('click', function () {
        const newName = input.value.trim();
        if (!newName) {
            container.innerHTML = currentContent;
            return;
        }

        // Display loading indicator
        // document.getElementById('loader').style.display = 'block';

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
    input.addEventListener('keydown', function (e) {
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

// Helper functions for UI updates
function updateProgressBar(percent) {
    uploadProgress = Math.min(percent, 100);
    document.getElementById('progressBar').style.width = `${uploadProgress}%`;
    document.getElementById('progressPercent').textContent = `${uploadProgress}%`;
}
function updateUploadStatus(message) {
    console.log(message);
    // If there's a status element in the modal, update it
    const modalContent = document.querySelector('.modal-content');
    if (modalContent) {
        // Check if status element exists, create it if not
        let statusElement = modalContent.querySelector('.upload-status');
        if (!statusElement) {
            statusElement = document.createElement('div');
            statusElement.className = 'upload-status';
            statusElement.style.margin = '10px 0';
            statusElement.style.fontSize = '14px';
            statusElement.style.color = '#555';

            // Find proper insertion point
            const buttons = modalContent.querySelector('.modal-buttons');
            const form = modalContent.querySelector('form');

            // Append to form if it exists
            if (form) {
                // Find the div with progress bar to insert after
                const progressDiv = form.querySelector('.progress-bar').parentNode;
                if (progressDiv && progressDiv.parentNode) {
                    progressDiv.parentNode.insertBefore(statusElement, progressDiv.nextSibling);
                } else {
                    // If can't find specific element, append to form
                    form.appendChild(statusElement);
                }
            } else if (buttons && buttons.parentNode) {
                // Insert before buttons if buttons exist
                buttons.parentNode.insertBefore(statusElement, buttons);
            } else {
                // Last resort, just append to modal content
                modalContent.appendChild(statusElement);
            }
        }

        statusElement.textContent = message;
    }
}
function addSuccessMessage(message) {
    const modalContent = document.querySelector('.modal-content');
    if (modalContent) {
        // Remove any existing success message
        const existingMsg = modalContent.querySelector('.success-message');
        if (existingMsg) {
            existingMsg.remove();
        }

        // Create success message
        const successMsg = document.createElement('div');
        successMsg.className = 'success-message';
        successMsg.style.color = 'green';
        successMsg.style.margin = '10px 0';
        successMsg.style.textAlign = 'center';
        successMsg.style.fontWeight = 'bold';
        successMsg.textContent = message;

        // Find proper place to add the message
        const form = modalContent.querySelector('form');
        if (form) {
            // Add it to the end of the form before buttons
            const buttons = form.querySelector('.modal-buttons');
            if (buttons) {
                form.insertBefore(successMsg, buttons);
            } else {
                // If no buttons, just append to form
                form.appendChild(successMsg);
            }
        } else {
            // If no form, append to modal content
            modalContent.appendChild(successMsg);
        }
    }
}
document.addEventListener('DOMContentLoaded', () => {
    // Make sure we have the JSZip library available
    if (typeof JSZip === 'undefined') {
        loadJSZip().catch(err => console.error("Failed to load JSZip:", err));
    }
});