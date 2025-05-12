// Initialize with empty templates that will be replaced if backend data exists
let mp3Templates = [];
let existingBgMusic = false;

// Store actual File objects in a FormData object that will persist
const formDataStorage = new FormData();

function handleAddMp3() {
    const newId = mp3Templates.length + 1;
    mp3Templates.push({
        id: newId,
        file: null,
        startTime: "",
        endTime: "",
        volume: 50
    });
    renderMp3Templates();
}

function handleDeleteMp3(id) {
    if (mp3Templates.length > 1) {
        // Find the template being deleted
        const templateToDelete = mp3Templates.find(template => template.id === id);
        
        // If it has a music ID (existing track), we need to handle it differently
        if (templateToDelete && templateToDelete.musicId) {
            console.log("WARNING: Attempting to delete an existing music track:", templateToDelete.musicId);
            // We should use the actual delete API endpoint for this
            if (confirm('Are you sure you want to delete this background music?')) {
                console.log(`Sending delete request for music ID: ${templateToDelete.musicId}`);
                
                // Make the actual API call
                fetch('/delete-background-music/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                    },
                    body: JSON.stringify({
                        bg_music_id: templateToDelete.musicId
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        removeTemplateFromList(id);
                    } else {
                        console.error("Failed to delete background music:", data.error);
                        alert("Failed to delete background music: " + data.error);
                    }
                })
                .catch(error => {
                    console.error("Error during delete:", error);
                    alert("An error occurred while deleting: " + error);
                });
            }
            return;
        }
        
        // For new tracks, just remove locally
        removeTemplateFromList(id);
    }
}

function removeTemplateFromList(id) {
    // Remove the file from storage
    formDataStorage.delete(`bg_music_${id}`);
    
    mp3Templates = mp3Templates
        .filter(template => template.id !== id)
        .map((template, index) => {
            // Update ID and rename in form data if needed
            const newId = index + 1;
            if (template.id !== newId && template.file) {
                const file = formDataStorage.get(`bg_music_${template.id}`);
                formDataStorage.delete(`bg_music_${template.id}`);
                if (file) formDataStorage.append(`bg_music_${newId}`, file);
            }
            return { ...template, id: newId };
        });
    renderMp3Templates();
}

function handleClearFile(id) {
    mp3Templates = mp3Templates.map(template =>
        template.id === id ? { ...template, file: null } : template
    );
    // Remove from storage
    formDataStorage.delete(`bg_music_${id}`);
    renderMp3Templates();
}

function formatTimeInput(value) {
    let cleaned = value.replace(/\D/g, "");
    cleaned = cleaned.slice(0, 4);
    if (cleaned.length > 2) {
        return `${cleaned.slice(0, 2)}:${cleaned.slice(2)}`;
    }
    return cleaned;
}

function handleTimeChange(id, field, element) {
    const formattedValue = formatTimeInput(element.value);
    element.value = formattedValue;
    mp3Templates = mp3Templates.map(template =>
        template.id === id ? { ...template, [field]: formattedValue } : template
    );
}

function handleFileChange(id, input) {
    const file = input.files[0];
    if (file) {
        mp3Templates = mp3Templates.map(template =>
            template.id === id ? { ...template, file: { name: file.name } } : template
        );
        
        // Store the actual file in our FormData storage
        formDataStorage.set(`bg_music_${id}`, file);
        renderMp3Templates();
    }
}

function handleVolumeChange(id, slider) {
    const value = parseInt(slider.value) || 50; // Default to 50 if NaN
    console.log("Volume changed to:", value);
    mp3Templates = mp3Templates.map(template =>
        template.id === id ? { ...template, volume: value } : template
    );
    const container = slider.closest('.uploadmp3');
    if (container) {
        const percentageEl = container.querySelector('.volume-percentage');
        if (percentageEl) {
            percentageEl.textContent = `${value}%`;
        }
    }
    
    // Ensure the value is properly set
    slider.value = value;
    slider.setAttribute('value', value);
    slider.style.setProperty('--value', value);
}

function convertTimeToString(seconds) {
    if (seconds === null || seconds === undefined) return "";
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`;
}

function initializeFromServerData() {
    // Get all existing music items
    const musicElements = document.querySelectorAll('.uploadmp3');
    
    // If we have server-rendered music elements
    if (musicElements.length > 0) {
        mp3Templates = [];
        let id = 1;
        
        // Process each music element from the server
        musicElements.forEach(element => {
            // Get the file name from the output element
            const fileOutput = element.querySelector('.output');
            const fileName = fileOutput ? fileOutput.textContent.trim() : 'Choose File';
            
            // Get start time and end time
            const startTimeInput = element.querySelector('.startTime');
            const endTimeInput = element.querySelector('.endTime');
            
            // Get volume
            const volumeSlider = element.querySelector('.slider');
            const volumePercentage = element.querySelector('.volume-percentage');
            
            const volumeValue = volumeSlider ? parseInt(volumeSlider.value) : 50;
            
            // Get music ID from data attribute
            const musicId = element.getAttribute('data-music-id');
            console.log("Found music track with ID:", musicId);
            
            // Only treat as valid ID if it's not empty
            const validMusicId = musicId && musicId !== 'None' && musicId !== 'null' && musicId !== 'undefined' ? musicId : null;
            if (validMusicId) {
                console.log("Found valid music ID:", validMusicId);
            }
            
            // Create a template object from server data
            mp3Templates.push({
                id: id,
                musicId: validMusicId, // Store the actual background music ID for existing tracks
                file: fileName !== 'Choose File' ? { name: fileName } : null,
                startTime: startTimeInput ? startTimeInput.value : "",
                endTime: endTimeInput ? endTimeInput.value : "",
                volume: volumeValue
            });
            
            id++;
        });
        
        existingBgMusic = mp3Templates.length > 0;
        
        // If we found existing data, render with it
        if (existingBgMusic) {
            // Remove the default elements
            const container = document.getElementById('musicContainer');
            if (container) {
                musicElements.forEach(element => {
                    if (container.contains(element)) {
                        container.removeChild(element);
                    }
                });
                
                renderMp3Templates();
                return true;
            }
        }
    }
    
    // If we have no server data, initialize with defaults
    if (mp3Templates.length === 0) {
        mp3Templates = [
            { id: 1, file: null, startTime: "", endTime: "", volume: 50 },
            { id: 2, file: null, startTime: "", endTime: "", volume: 50 }
        ];
    }
    
    return false;
}

function renderMp3Templates() {
    const container = document.getElementById('musicContainer');
    if (!container) {
        console.error("Music container element not found");
        return;
    }
    
    // Clone buttons to preserve event listeners
    const addButton = document.getElementById('addMusicBtn')?.cloneNode(true);
    const proceedDiv = document.getElementById('proceed')?.cloneNode(true);
    
    if (!addButton || !proceedDiv) {
        console.error("Required elements not found");
        return;
    }
    
    container.innerHTML = '';

    mp3Templates.forEach(template => {
        const div = document.createElement('div');
        div.className = 'uploadmp3';
        // Set data-music-id attribute from the stored musicId (if it exists)
        div.setAttribute('data-music-id', template.musicId || '');
        
        // Add hidden input for music ID if it exists
        const hiddenInputs = template.musicId ? 
        `<input type="hidden" name="bg_music_id_${template.musicId}" value="${template.musicId}">
        <input type="hidden" name="existing_music_${template.musicId}_id" value="${template.musicId}">` : '';
        
        div.innerHTML = `
            ${hiddenInputs}
            <div class="mp-label bg-text">
                MP3 ${template.id}
                <button type="button" class="delete-btn">Delete</button>
            </div>
            <div class="file-input-container">
                <div class="choose-file-sty">
                    <img src="/static/images/upload-icon.svg" alt="">
                    <input class="fileInput" type="file" accept="audio/mpeg" 
                           name="${template.musicId ? `existing_music_${template.musicId}_file` : `bg_music_${template.id}`}" 
                           onchange="handleFileChange(${template.id}, this)">
                    <div class="output">${template.file ? template.file.name : 'Choose File'}</div>
                    ${template.file ? `<button type="button" class="clear-btn" onclick="handleClearFile(${template.id})">×</button>` : ''}
                </div>
            </div>
            <div class="bg-text">
                <span>What Second Should This MP3 Play From? <span class="text-span">In Minutes</span></span>
            </div>
            <div class="start-main-div">
                <div class="start-sub-div">
                    <span class="text start-text">Start:</span>
                    <input type="text" placeholder="00:00" class="time startTime" maxlength="5" 
                           name="${template.musicId ? `existing_music_${template.musicId}_from_when` : `from_when_${template.id}`}" 
                           value="${template.startTime}" oninput="handleTimeChange(${template.id}, 'startTime', this)">
                </div>
                <div class="start-sub-div">
                    <span class="text start-text">End:</span>
                    <input type="text" placeholder="00:00" class="time endTime" maxlength="5" 
                           name="${template.musicId ? `existing_music_${template.musicId}_to_when` : `to_when_${template.id}`}" 
                           value="${template.endTime}" oninput="handleTimeChange(${template.id}, 'endTime', this)">
                </div>
            </div>
            <div>
                <div class="Font-Size-text">
                    <div class="mp3-volume">MP3 ${template.id}:</div>
                    <span class="volume-percentage">${template.volume}%</span>
                </div>
                <div class="Font-Size-Slider">
                    <input type="range" min="0" max="100" class="slider" 
                           name="${template.musicId ? `existing_music_${template.musicId}_bg_level` : `bg_level_${template.id}`}" 
                           value="${template.volume}" 
                           style="--value: ${template.volume}" oninput="handleVolumeChange(${template.id}, this)">
                </div>
            </div>
        `;
        container.appendChild(div);
    });

    container.appendChild(addButton);
    container.appendChild(proceedDiv);
    container.querySelector('#addMusicBtn').addEventListener('click', handleAddMp3);
}

document.addEventListener('DOMContentLoaded', () => {
    // Try to initialize from server data first
    const hasServerData = initializeFromServerData();
    
    if (!hasServerData) {
        // If no server data, render with defaults
        renderMp3Templates();
    }
    
    // Initialize all sliders for proper visual display
    document.querySelectorAll('.slider').forEach(slider => {
        const value = parseInt(slider.value) || 50;
        slider.value = value;
        slider.setAttribute('value', value);
        slider.style.setProperty('--value', value);
        
        // Update the text display as well
        const container = slider.closest('.uploadmp3');
        if (container) {
            const percentageEl = container.querySelector('.volume-percentage');
            if (percentageEl) {
                percentageEl.textContent = `${value}%`;
            }
        }
        
        // Add input event listener to each slider
        slider.addEventListener('input', function() {
            // Find the MP3 ID from the slider's name (bg_level_X)
            const nameMatch = this.name?.match(/bg_level_(\d+)/);
            if (nameMatch && nameMatch[1]) {
                const id = parseInt(nameMatch[1]);
                handleVolumeChange(id, this);
            }
        });
    });
    
    const addMusicBtn = document.getElementById('addMusicBtn');
    if (addMusicBtn) {
        addMusicBtn.addEventListener('click', handleAddMp3);
    }
    
    // Add form submission interceptor to ensure music IDs are included
    const bgForm = document.getElementById('bg_form');
    if (bgForm) {
        bgForm.addEventListener('submit', function(event) {
            // We'll handle the form submission ourselves, but let's make sure all IDs are included
            event.preventDefault();
            
            console.log("Form submission intercepted - ensuring background music IDs are included");
            
            // Add existing music IDs to the form data explicitly
            mp3Templates.forEach(template => {
                if (template.musicId) {
                    console.log(`Ensuring music ID ${template.musicId} is included in form data`);
                    
                    // Double check if we already have this ID in the form
                    const input1Name = `bg_music_id_${template.musicId}`;
                    const input2Name = `existing_music_${template.musicId}_id`;
                    
                    // Check if these inputs exist in the form
                    const input1 = this.querySelector(`input[name="${input1Name}"]`);
                    const input2 = this.querySelector(`input[name="${input2Name}"]`);
                    
                    if (!input1) {
                        const hiddenInput = document.createElement('input');
                        hiddenInput.type = 'hidden';
                        hiddenInput.name = input1Name;
                        hiddenInput.value = template.musicId;
                        this.appendChild(hiddenInput);
                        console.log(`Added hidden input for bg_music_id_${template.musicId}`);
                    }
                    
                    if (!input2) {
                        const hiddenInput = document.createElement('input');
                        hiddenInput.type = 'hidden';
                        hiddenInput.name = input2Name;
                        hiddenInput.value = template.musicId;
                        this.appendChild(hiddenInput);
                        console.log(`Added hidden input for existing_music_${template.musicId}_id`);
                    }
                }
            });
            
            // Also add time seconds values
            document.querySelectorAll('.time').forEach(input => {
                const nameAttr = input.getAttribute('name');
                if (nameAttr) {
                    // Convert the time value to seconds
                    const timeValue = input.value.trim();
                    let seconds = 0;
                    
                    if (timeValue) {
                        if (timeValue.includes(':')) {
                            const parts = timeValue.split(':');
                            if (parts.length === 2) {
                                const minutes = parseInt(parts[0], 10) || 0;
                                const secs = parseInt(parts[1], 10) || 0;
                                seconds = (minutes * 60) + secs;
                            }
                        } else {
                            seconds = parseInt(timeValue, 10) || 0;
                        }
                    }
                    
                    // Create a hidden input with _seconds suffix
                    const hiddenInput = document.createElement('input');
                    hiddenInput.type = 'hidden';
                    hiddenInput.name = nameAttr + '_seconds';
                    hiddenInput.value = seconds.toString();
                    this.appendChild(hiddenInput);
                }
            });
            
            // Create a FormData from the form with all our additions
            const formData = new FormData(this);
            
            // Add stored files to the form data
            for (let [key, value] of formDataStorage.entries()) {
                formData.set(key, value);
            }
            
            // Debug: Log what's being submitted
            console.log("Form data being submitted:");
            for (let [key, value] of formData.entries()) {
                if (value instanceof File) {
                    console.log(`${key}: File: ${value.name}, Size: ${value.size} bytes`);
                } else {
                    console.log(`${key}: ${value}`);
                }
            }
            
            // Show loading spinner
            const submitButton = document.getElementById('submitBgButton');
            if (submitButton) {
                submitButton.classList.add('loading');
            }
            
            // Instead of using fetch, we'll do a regular form submission
            // This ensures all form data is properly processed by Django
            
            // Log that we're about to submit
            console.log("Submitting form directly to preserve Django form handling");
            
            // Make sure our custom form will be processed properly
            const formElement = this;
            
            // Create hidden inputs for all FormData entries that aren't in the form
            for (let [key, value] of formData.entries()) {
                // Skip if it's already in the form
                if (formElement.querySelector(`[name="${key}"]`)) {
                    continue;
                }
                
                // Special handling for files
                if (value instanceof File) {
                    // Files can't be added this way, they'll be handled by the default form submission
                    console.log(`Note: File ${key} will be handled by browser form submission`);
                    continue;
                }
                
                // Add as hidden input
                const input = document.createElement('input');
                input.type = 'hidden';
                input.name = key;
                input.value = value;
                formElement.appendChild(input);
                console.log(`Added hidden input for ${key}: ${value}`);
            }
            
            // Now submit the form directly
            console.log("Submitting form normally");
            
            // Allow the normal form submission to happen
            setTimeout(() => {
                formElement.submit();
            }, 10); // Small timeout to ensure all our changes are processed
            
            // Don't proceed with fetch
            return;
                } else {
                    console.error("Form submission failed with status:", response.status);
                    alert("There was an error submitting the form. Please try again.");
                    
                    // Remove loading spinner
                    if (submitButton) {
                        submitButton.classList.remove('loading');
                    }
                }
            })
            .catch(error => {
                console.error("Form submission error:", error);
                alert("There was an error submitting the form: " + error);
                
                // Remove loading spinner
                if (submitButton) {
                    submitButton.classList.remove('loading');
                }
            });
        });
    }
});
