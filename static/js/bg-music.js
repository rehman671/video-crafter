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
    console.log("handleDeleteMp3 called with id:", id);
    
    // Find the template to delete
    const templateToDelete = mp3Templates.find(template => template.id === id);
    
    if (!templateToDelete) {
        console.error("Template not found for id:", id);
        return;
    }
    
    // If it has a music ID (existing track), use the server delete endpoint
    if (templateToDelete.musicId) {
        console.log("Deleting existing music track:", templateToDelete.musicId);
        if (confirm('Are you sure you want to delete this background music?')) {
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
    if (mp3Templates.length > 1) {
        removeTemplateFromList(id);
    } else {
        alert("You must have at least one MP3 track.");
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

function handleTimeChange(id, field, value) {
    const formattedValue = formatTimeInput(value);
    mp3Templates = mp3Templates.map(template =>
        template.id === id ? { ...template, [field]: formattedValue } : template
    );
    return formattedValue;
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

function handleVolumeChange(id, value) {
    const volumeValue = parseInt(value) || 50;
    console.log("Volume changed to:", volumeValue);
    mp3Templates = mp3Templates.map(template =>
        template.id === id ? { ...template, volume: volumeValue } : template
    );
    return volumeValue;
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
                <button type="button" class="delete-btn" data-template-id="${template.id}">Delete</button>
            </div>
            <div class="file-input-container">
                <div class="choose-file-sty">
                    <img src="/static/images/upload-icon.svg" alt="">
                    <input class="fileInput" type="file" accept="audio/mpeg" 
                           name="${template.musicId ? `existing_music_${template.musicId}_file` : `bg_music_${template.id}`}">
                    <div class="output">${template.file ? template.file.name : 'Choose File'}</div>
                    ${template.file ? `<button type="button" class="clear-btn">×</button>` : ''}
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
                           value="${template.startTime}">
                </div>
                <div class="start-sub-div">
                    <span class="text start-text">End:</span>
                    <input type="text" placeholder="00:00" class="time endTime" maxlength="5" 
                           name="${template.musicId ? `existing_music_${template.musicId}_to_when` : `to_when_${template.id}`}" 
                           value="${template.endTime}">
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
                           style="--value: ${template.volume}">
                </div>
            </div>
        `;
        container.appendChild(div);
        
        // Set up event listeners after the element is added to DOM
        const deleteBtn = div.querySelector('.delete-btn');
        deleteBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            const templateId = parseInt(this.getAttribute('data-template-id'));
            console.log("Delete button clicked for template:", templateId);
            handleDeleteMp3(templateId);
        });
        
        const fileInput = div.querySelector('.fileInput');
        fileInput.addEventListener('change', function() {
            handleFileChange(template.id, this);
        });
        
        const clearBtn = div.querySelector('.clear-btn');
        if (clearBtn) {
            clearBtn.addEventListener('click', function() {
                handleClearFile(template.id);
            });
        }
        
        const startTimeInput = div.querySelector('.startTime');
        startTimeInput.addEventListener('input', function() {
            this.value = handleTimeChange(template.id, 'startTime', this.value);
        });
        
        const endTimeInput = div.querySelector('.endTime');
        endTimeInput.addEventListener('input', function() {
            this.value = handleTimeChange(template.id, 'endTime', this.value);
        });
        
        const volumeSlider = div.querySelector('.slider');
        volumeSlider.addEventListener('input', function() {
            const newValue = handleVolumeChange(template.id, this.value);
            this.value = newValue;
            this.style.setProperty('--value', newValue);
            const container = this.closest('.uploadmp3');
            const percentageEl = container.querySelector('.volume-percentage');
            if (percentageEl) {
                percentageEl.textContent = `${newValue}%`;
            }
        });
    });

    container.appendChild(addButton);
    container.appendChild(proceedDiv);
    
    // Re-attach listener to the cloned add button
    addButton.addEventListener('click', handleAddMp3);
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
    });
    
    const addMusicBtn = document.getElementById('addMusicBtn');
    if (addMusicBtn) {
        addMusicBtn.addEventListener('click', handleAddMp3);
    }
    
    // Add form submission interceptor to ensure music IDs are included
    const bgForm = document.getElementById('bg_form');
    if (bgForm) {
        bgForm.addEventListener('submit', function(event) {
            event.preventDefault();
            console.log("Form submission intercepted");
            
            const actualForm = new FormData(this);
            
            // Add existing music IDs to the form data explicitly
            mp3Templates.forEach(template => {
                if (template.musicId) {
                    console.log(`Adding music ID ${template.musicId} to form data`);
                    
                    // Add the ID fields for existing music
                    actualForm.append(`bg_music_id_${template.musicId}`, template.musicId);
                    actualForm.append(`existing_music_${template.musicId}_id`, template.musicId);
                    
                    // If there's a new file for this template, add it with the correct name
                    const fileKey = `bg_music_${template.id}`;
                    if (formDataStorage.has(fileKey)) {
                        const file = formDataStorage.get(fileKey);
                        actualForm.append(`existing_music_${template.musicId}_file`, file);
                        console.log(`Added updated file for existing music ${template.musicId}`);
                    }
                } else {
                    // This is a new music track
                    const fileKey = `bg_music_${template.id}`;
                    if (formDataStorage.has(fileKey)) {
                        const file = formDataStorage.get(fileKey);
                        actualForm.append(fileKey, file);
                        console.log(`Added file for new music track ${template.id}`);
                    }
                }
            });

            // Add time seconds values
            document.querySelectorAll('.time').forEach(input => {
                const nameAttr = input.getAttribute('name');
                if (nameAttr) {
                    const timeValue = input.value.trim();
                    let seconds = 0;
                    
                    if (timeValue && timeValue.includes(':')) {
                        const parts = timeValue.split(':');
                        if (parts.length === 2) {
                            const minutes = parseInt(parts[0], 10) || 0;
                            const secs = parseInt(parts[1], 10) || 0;
                            seconds = (minutes * 60) + secs;
                        }
                    } else if (timeValue) {
                        seconds = parseInt(timeValue, 10) || 0;
                    }
                    
                    actualForm.append(nameAttr + '_seconds', seconds.toString());
                }
            });
            
            // Show loading spinner
            const submitButton = document.getElementById('submitBgButton');
            if (submitButton) {
                submitButton.classList.add('loading');
            }

            // Submit the form with our custom FormData
            fetch(this.action || window.location.href, {
                method: 'POST',
                body: actualForm,
            })
            .then(response => {
                if (response.ok) {
                    window.location.href = response.url;
                } else {
                    console.error('Form submission failed');
                    if (submitButton) {
                        submitButton.classList.remove('loading');
                    }
                }
            })
            .catch(error => {
                console.error('Error submitting form:', error);
                if (submitButton) {
                    submitButton.classList.remove('loading');
                }
            });
        });
    }
});