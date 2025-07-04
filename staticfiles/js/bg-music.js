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
    const value = parseInt(slider.value);
    console.log(slider.value);
    mp3Templates = mp3Templates.map(template =>
        template.id === id ? { ...template, volume: value } : template
    );
    const container = slider.closest('.uploadmp3');
    container.querySelector('.volume-percentage').textContent = `${value}%`;
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
            const fileName = fileOutput.textContent.trim();
            
            // Get start time and end time
            const startTimeInput = element.querySelector('.startTime');
            const endTimeInput = element.querySelector('.endTime');
            
            // Get volume
            const volumeSlider = element.querySelector('.slider');
            const volumePercentage = element.querySelector('.volume-percentage');
            
            const volumeValue = volumeSlider ? parseInt(volumeSlider.value) : 50;
            
            // Create a template object from server data
            mp3Templates.push({
                id: id,
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
            musicElements.forEach(element => {
                container.removeChild(element);
            });
            
            renderMp3Templates();
            return true;
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
        div.innerHTML = `
            <div class="mp-label bg-text">
                MP3 ${template.id}
                <button type="button" class="delete-btn" onclick="handleDeleteMp3(${template.id})" ${mp3Templates.length > 1 ? '' : 'style="display: none;"'}>Delete</button>
            </div>
            <div class="file-input-container">
                <div class="choose-file-sty">
                    <img src="/static/images/upload-icon.svg" alt="">
                    <input class="fileInput" type="file" accept="audio/mpeg" name="bg_music_${template.id}" onchange="handleFileChange(${template.id}, this)">
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
                    <input type="text" placeholder="00:00" class="time startTime" maxlength="5" name="from_when_${template.id}" value="${template.startTime}" oninput="handleTimeChange(${template.id}, 'startTime', this)">
                </div>
                <div class="start-sub-div">
                    <span class="text start-text">End:</span>
                    <input type="text" placeholder="00:00" class="time endTime" maxlength="5" name="to_when_${template.id}" value="${template.endTime}" oninput="handleTimeChange(${template.id}, 'endTime', this)">
                </div>
            </div>
            <div>
                <div class="Font-Size-text">
                    <div class="mp3-volume">MP3 ${template.id}:</div>
                    <span class="volume-percentage">${template.volume}%</span>
                </div>
                <div class="Font-Size-Slider">
                    <input type="range" min="0" max="100" class="slider" name="bg_level_${template.id}" value="${template.volume}" oninput="handleVolumeChange(${template.id}, this)">
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
        const value = parseInt(slider.value);
        slider.style.setProperty('--value', value);
        // Update the text display as well
        const container = slider.closest('.uploadmp3');
        const percentageEl = container.querySelector('.volume-percentage');
        if (percentageEl) {
            percentageEl.textContent = `${value}%`;
        }
    });
    
    document.getElementById('addMusicBtn').addEventListener('click', handleAddMp3);
    
    // Add form submission interceptor to handle file uploads
    document.getElementById('bg_form').addEventListener('submit', function(event) {
        // Don't submit the form normally yet
        event.preventDefault();
        
        console.log("Form submission intercepted");
        
        // First clear any existing file inputs in the form
        const actualForm = new FormData(this);
        for (let [key, value] of actualForm.entries()) {
            if (key.startsWith('bg_music_')) {
                actualForm.delete(key);
            }
        }
        
        // Now add our stored files to the form
        for (let [key, value] of formDataStorage.entries()) {
            actualForm.append(key, value);
        }
        
        // Debug: Log what's being submitted
        console.log("Files being submitted:");
        for (let [key, value] of actualForm.entries()) {
            if (value instanceof File) {
                console.log(`${key}: File: ${value.name}, Size: ${value.size} bytes`);
            } else {
                console.log(`${key}: ${value}`);
            }
        }
        
        // Submit the form with our custom FormData
        fetch(this.action, {
            method: 'POST',
            body: actualForm,
            // Don't set Content-Type header, let the browser set it with boundary
        })
        .then(response => {
            if (response.ok) {
                // Redirect to the next page or handle success
                window.location.href = `/download/${actualForm.get('video_id')}`;
            } else {
                console.error('Form submission failed');
                // Handle error
            }
        })
        .catch(error => {
            console.error('Error submitting form:', error);
        });
    });
});