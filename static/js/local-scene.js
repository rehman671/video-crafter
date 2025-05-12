// SceneEditor LocalStorage Manager
// This script manages the storage and retrieval of user selections for the scene editor

// Object to manage highlighted text and selections in local storage
const SceneEditorStorage = {
    // Storage key prefix to avoid conflicts with other local storage items
    keyPrefix: 'videoCrafter_',
    
    // Save a highlight selection to local storage
    saveHighlight(slideId, text, options) {
        if (!slideId || !text) return false;
        
        // Get existing highlights or create empty object
        const allHighlights = this.getAllHighlights() || {};
        
        // Create a unique key for this text in this slide
        const highlightKey = this._createHighlightKey(slideId, text);
        
        // Store the highlight data
        allHighlights[highlightKey] = {
            slideId: slideId,
            text: text,
            type: options.type || 'file', // 'file' or 'asset'
            timestamp: new Date().getTime(),
            ...options
        };
        
        // Save back to local storage
        localStorage.setItem(`${this.keyPrefix}highlights`, JSON.stringify(allHighlights));
        
        console.log(`Saved highlight: ${highlightKey}`);
        return true;
    },
    
    // Get a specific highlight by slide ID and text
    getHighlight(slideId, text) {
        if (!slideId || !text) return null;
        
        const allHighlights = this.getAllHighlights() || {};
        const highlightKey = this._createHighlightKey(slideId, text);
        
        return allHighlights[highlightKey] || null;
    },
    
    // Get all highlights for a specific slide
    getSlideHighlights(slideId) {
        if (!slideId) return [];
        
        const allHighlights = this.getAllHighlights() || {};
        const slideHighlights = {};
        
        // Filter highlights for this slide
        Object.keys(allHighlights).forEach(key => {
            if (allHighlights[key].slideId === slideId) {
                slideHighlights[key] = allHighlights[key];
            }
        });
        
        return slideHighlights;
    },
    
    // Get all highlights from local storage
    getAllHighlights() {
        const storedHighlights = localStorage.getItem(`${this.keyPrefix}highlights`);
        return storedHighlights ? JSON.parse(storedHighlights) : {};
    },
    
    // Delete a specific highlight
    deleteHighlight(slideId, text) {
        if (!slideId || !text) return false;
        
        const allHighlights = this.getAllHighlights() || {};
        const highlightKey = this._createHighlightKey(slideId, text);
        
        if (allHighlights[highlightKey]) {
            delete allHighlights[highlightKey];
            localStorage.setItem(`${this.keyPrefix}highlights`, JSON.stringify(allHighlights));
            console.log(`Deleted highlight: ${highlightKey}`);
            return true;
        }
        
        return false;
    },
    
    // Clear all highlights from local storage
    clearAllHighlights() {
        localStorage.removeItem(`${this.keyPrefix}highlights`);
        console.log('Cleared all highlights from local storage');
    },
    
    // Save file upload history
    saveFileUpload(filename, fileObj) {
        if (!filename) return false;
        
        const fileUploads = this.getFileUploads() || {};
        
        // Store basic file info (not the actual file)
        fileUploads[filename] = {
            name: filename,
            type: fileObj?.type || 'unknown',
            size: fileObj?.size || 0,
            lastUsed: new Date().getTime()
        };
        
        localStorage.setItem(`${this.keyPrefix}fileUploads`, JSON.stringify(fileUploads));
        
        return true;
    },
    
    // Get file upload history
    getFileUploads() {
        const storedFiles = localStorage.getItem(`${this.keyPrefix}fileUploads`);
        return storedFiles ? JSON.parse(storedFiles) : {};
    },
    
    // Update recent folders and selections
    saveAssetSelection(folderId, assetId) {
        if (!folderId || !assetId) return false;
        
        // Get existing selections
        const assetSelections = this.getAssetSelections() || {};
        
        // Store folder and selection
        if (!assetSelections[folderId]) {
            assetSelections[folderId] = {
                selections: {}
            };
        }
        
        assetSelections[folderId].lastUsed = new Date().getTime();
        assetSelections[folderId].selections[assetId] = {
            lastUsed: new Date().getTime()
        };
        
        localStorage.setItem(`${this.keyPrefix}assetSelections`, JSON.stringify(assetSelections));
        
        return true;
    },
    
    // Get asset selections history
    getAssetSelections() {
        const storedSelections = localStorage.getItem(`${this.keyPrefix}assetSelections`);
        return storedSelections ? JSON.parse(storedSelections) : {};
    },
    
    // Get recent folders by usage
    getRecentFolders(limit = 5) {
        const assetSelections = this.getAssetSelections() || {};
        
        return Object.keys(assetSelections)
            .map(folderId => ({
                id: folderId,
                lastUsed: assetSelections[folderId].lastUsed
            }))
            .sort((a, b) => b.lastUsed - a.lastUsed)
            .slice(0, limit)
            .map(folder => folder.id);
    },
    
    // Get recent assets by usage for a specific folder
    getRecentAssets(folderId, limit = 5) {
        if (!folderId) return [];
        
        const assetSelections = this.getAssetSelections() || {};
        
        if (!assetSelections[folderId] || !assetSelections[folderId].selections) {
            return [];
        }
        
        const folderSelections = assetSelections[folderId].selections;
        
        return Object.keys(folderSelections)
            .map(assetId => ({
                id: assetId,
                lastUsed: folderSelections[assetId].lastUsed
            }))
            .sort((a, b) => b.lastUsed - a.lastUsed)
            .slice(0, limit)
            .map(asset => asset.id);
    },
    
    // Helper method to create a consistent key for highlights
    _createHighlightKey(slideId, text) {
        // Create a simplified version of the text for use as a key
        const simplifiedText = text.toLowerCase().trim().replace(/\s+/g, '_').slice(0, 30);
        return `slide_${slideId}_${simplifiedText}`;
    }
};

// Enhance the popup rendering to show recent selections
function enhancePopupRendering() {
    // Override the existing renderPopup function
    const originalRenderPopup = renderPopup;
    
    renderPopup = function() {
        // Call the original function first
        originalRenderPopup();
        
        // If the popup is open, enhance it with stored data
        if (popupOpen && selectedSlideId) {
            // Check if we have a previous highlight for this text
            const savedHighlight = SceneEditorStorage.getHighlight(selectedSlideId, selectedText);
            
            if (savedHighlight) {
                console.log("Found saved highlight:", savedHighlight);
                
                // If we have a saved highlight, pre-select the appropriate option
                if (savedHighlight.type === 'file' && savedHighlight.fileName) {
                    // Show a note about previous file
                    const uploadText = document.getElementById("upload-text");
                    if (uploadText) {
                        uploadText.innerHTML = `<span style="color: #864AF9">Previously: ${savedHighlight.fileName}</span>`;
                    }
                }
                else if (savedHighlight.type === 'asset' && savedHighlight.folderId && savedHighlight.assetId) {
                    // Pre-select folder and asset
                    setTimeout(() => {
                        const topicSelect = document.getElementById('selected_topic');
                        if (topicSelect) {
                            topicSelect.value = savedHighlight.folderId;
                            // Trigger change event to load assets
                            const event = new Event('change');
                            topicSelect.dispatchEvent(event);
                            
                            // After folder selection is processed, select the asset
                            setTimeout(() => {
                                const assetSelect = document.getElementById('videoSelect');
                                if (assetSelect) {
                                    assetSelect.value = savedHighlight.assetId;
                                    // Trigger change event
                                    const assetEvent = new Event('change');
                                    assetSelect.dispatchEvent(assetEvent);
                                }
                            }, 100);
                        }
                    }, 50);
                }
            }
            
            // Add "Recent Selections" section to the popup
            // addRecentSelectionsToPopup();
        }
    };
}

// // Function to add recent selections to the popup
// function addRecentSelectionsToPopup() {
//     // Get the popup form
//     const popupForm = document.querySelector('.popup-content');
//     if (!popupForm) return;
    
//     // Check if we already added the recent selections
//     if (document.getElementById('recent-selections-container')) return;
    
//     // Get recent folders and file uploads
//     const recentFolders = SceneEditorStorage.getRecentFolders(3);
//     const recentFileUploads = SceneEditorStorage.getFileUploads();
    
//     // Only show section if we have recent selections
//     if (recentFolders.length === 0 && Object.keys(recentFileUploads).length === 0) return;
    
//     // Create recent selections container
//     const recentSelectionsContainer = document.createElement('div');
//     recentSelectionsContainer.id = 'recent-selections-container';
//     recentSelectionsContainer.style.marginTop = '15px';
//     recentSelectionsContainer.style.borderTop = '1px solid #e0e0e0';
//     recentSelectionsContainer.style.paddingTop = '10px';
    
//     let recentSelectionsHTML = `
//         <h4 style="margin: 0 0 10px; color: #333; font-size: 14px;">Recent Selections</h4>
//         <div style="display: flex; flex-wrap: wrap; gap: 5px;">
//     `;
    
//     // Add recent file selections
//     const recentFiles = Object.keys(recentFileUploads)
//         .sort((a, b) => recentFileUploads[b].lastUsed - recentFileUploads[a].lastUsed)
//         .slice(0, 3);
    
//     recentFiles.forEach(filename => {
//         const file = recentFileUploads[filename];
//         recentSelectionsHTML += `
//             <button type="button" class="recent-selection-btn file-btn" data-type="file" data-filename="${filename}"
//                 style="background-color: #f0f0f0; border: 1px solid #ddd; border-radius: 4px; padding: 5px 10px; 
//                       font-size: 12px; cursor: pointer; display: flex; align-items: center; max-width: 150px; overflow: hidden;">
//                 <i class="ri-file-video-line" style="margin-right: 5px; color: #864AF9;"></i>
//                 <span style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${filename}</span>
//             </button>
//         `;
//     });
    
//     // Add recent folder selections
//     recentFolders.forEach(folderId => {
//         recentSelectionsHTML += `
//             <button type="button" class="recent-selection-btn folder-btn" data-type="folder" data-folder-id="${folderId}"
//                 style="background-color: #f0f0f0; border: 1px solid #ddd; border-radius: 4px; padding: 5px 10px; 
//                       font-size: 12px; cursor: pointer; display: flex; align-items: center; max-width: 150px; overflow: hidden;">
//                 <i class="ri-folder-line" style="margin-right: 5px; color: #864AF9;"></i>
//                 <span style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${folderId}</span>
//             </button>
//         `;
//     });
    
//     recentSelectionsHTML += `</div>`;
    
//     recentSelectionsContainer.innerHTML = recentSelectionsHTML;
    
//     // Add the container to the popup
//     popupForm.appendChild(recentSelectionsContainer);
    
//     // Add click event listeners for recent selection buttons
//     document.querySelectorAll('.recent-selection-btn').forEach(btn => {
//         btn.addEventListener('click', handleRecentSelectionClick);
//     });
// }

// Handler for recent selection button clicks
function handleRecentSelectionClick(e) {
    const btn = e.currentTarget;
    const type = btn.dataset.type;
    
    if (type === 'file') {
        const filename = btn.dataset.filename;
        // Show notification that user needs to reselect the file
        const uploadText = document.getElementById("upload-text");
        if (uploadText) {
            uploadText.innerHTML = `<span style="color: #864AF9">Select "${filename}" again</span>`;
        }
        
        // Focus on the file input
        const fileInput = document.getElementById('slide_file');
        if (fileInput) {
            fileInput.click();
        }
    }
    else if (type === 'folder') {
        const folderId = btn.dataset.folderId;
        const topicSelect = document.getElementById('selected_topic');
        
        if (topicSelect) {
            topicSelect.value = folderId;
            // Trigger change event
            const event = new Event('change');
            topicSelect.dispatchEvent(event);
        }
    }
}

// Override the popup file change handler to save to local storage
function enhanceFileChangeHandler() {
    const originalFileChangeHandler = handlePopupFileChange;
    
    handlePopupFileChange = function(e) {
        // Call the original handler
        originalFileChangeHandler(e);
        
        // Save the file selection
        if (popupFile) {
            SceneEditorStorage.saveFileUpload(popupFile.name, popupFile);
        }
    };
}

// Override the topic and video change handlers
function enhanceTopicChangeHandler() {
    const originalTopicChangeHandler = handleTopicChange;
    
    handleTopicChange = function(e) {
        // Call the original handler
        originalTopicChangeHandler(e);
    };
}

function enhanceVideoClipChangeHandler() {
    const originalVideoClipChangeHandler = handleVideoClipChange;
    
    handleVideoClipChange = function(e) {
        // Call the original handler
        originalVideoClipChangeHandler(e);
        
        // Save the asset selection
        const topicSelect = document.getElementById('selected_topic');
        const videoSelect = document.getElementById('videoSelect');
        
        if (topicSelect && videoSelect && topicSelect.value && videoSelect.value) {
            SceneEditorStorage.saveAssetSelection(topicSelect.value, videoSelect.value);
        }
    };
}

// Override the popup submit handler to save selections
function enhancePopupSubmitHandler() {
    const originalPopupSubmitHandler = handlePopupSubmit;
    
    handlePopupSubmit = function(e) {
        // Before submitting, save the current selection
        const fileInput = document.getElementById('slide_file');
        const hasFile = fileInput && fileInput.files && fileInput.files.length > 0;
        const selectedTopic = document.getElementById('selected_topic')?.value;
        const selectedVideo = document.getElementById('videoSelect')?.value;
        
        if (hasFile) {
            // Save file selection
            const file = fileInput.files[0];
            SceneEditorStorage.saveFileUpload(file.name, file);
            
            // Save highlight with file info
            SceneEditorStorage.saveHighlight(selectedSlideId, selectedText, {
                type: 'file',
                fileName: file.name,
                fileType: file.type
            });
        }
        else if (selectedTopic && selectedVideo) {
            // Save asset selection
            SceneEditorStorage.saveAssetSelection(selectedTopic, selectedVideo);
            
            // Save highlight with asset info
            SceneEditorStorage.saveHighlight(selectedSlideId, selectedText, {
                type: 'asset',
                folderId: selectedTopic,
                assetId: selectedVideo
            });
        }
        
        // Call the original handler
        originalPopupSubmitHandler(e);
    };
}

// Add CSS styles for the recent selections section
function addRecentSelectionsStyles() {
    const styleElement = document.createElement('style');
    styleElement.textContent = `
        .recent-selection-btn {
            transition: all 0.2s ease;
        }
        
        .recent-selection-btn:hover {
            background-color: #e5e5e5 !important;
            border-color: #864AF9 !important;
        }
        
        #upload-text span {
            display: inline-block;
            animation: fadeInOut 2s infinite;
        }
        
        @keyframes fadeInOut {
            0%, 100% { opacity: 0.7; }
            50% { opacity: 1; }
        }
    `;
    document.head.appendChild(styleElement);
}

// Add storage management to the close popup function
function enhanceClosePopupHandler() {
    const originalClosePopup = closePopup;
    
    closePopup = function() {
        // Call the original handler
        originalClosePopup();
    };
}

// Initialize local storage enhancements
function initStorageEnhancements() {

    // Enhance popup rendering
    enhancePopupRendering();
    
    // Enhance file change handler
    enhanceFileChangeHandler();
    
    // Enhance topic and video change handlers
    enhanceTopicChangeHandler();
    enhanceVideoClipChangeHandler();
    
    // Enhance popup submit handler
    enhancePopupSubmitHandler();
    
    // Enhance close popup handler
    enhanceClosePopupHandler();
    
    console.log('Scene Editor Storage Enhancements initialized');
}

// Call this function when the page loads
document.addEventListener('DOMContentLoaded', function() {
    // Initialize after a short delay to ensure all other scripts have loaded
    setTimeout(initStorageEnhancements, 500);
});