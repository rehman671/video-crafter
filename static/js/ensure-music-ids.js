document.addEventListener('DOMContentLoaded', function() {
    // Find form and add special handler
    const bgForm = document.getElementById('bg_form');
    if (bgForm) {
        console.log("Found background music form, adding ID preservation");
        
        bgForm.addEventListener('submit', function(e) {
            console.log("Form submission intercepted");
            
            // First, find all existing music IDs in the form
            const musicContainers = document.querySelectorAll('.uploadmp3[data-music-id]');
            musicContainers.forEach(container => {
                const musicId = container.getAttribute('data-music-id');
                if (musicId && musicId !== "" && musicId !== "None") {
                    console.log(`Processing music container with ID: ${musicId}`);
                    
                    // Double check if we already have this ID in the form
                    const existingInputBgMusicId = document.querySelector(`input[name="bg_music_id_${musicId}"]`);
                    if (!existingInputBgMusicId) {
                        // Create hidden input for music ID
                        const hiddenInput = document.createElement('input');
                        hiddenInput.type = 'hidden';
                        hiddenInput.name = `bg_music_id_${musicId}`;
                        hiddenInput.value = musicId;
                        this.appendChild(hiddenInput);
                        console.log(`Added hidden input for bg_music_id_${musicId}`);
                    }
                    
                    // Check for existing_music_ID_id field too
                    const existingInputExistingMusicId = document.querySelector(`input[name="existing_music_${musicId}_id"]`);
                    if (!existingInputExistingMusicId) {
                        // Create hidden input for existing_music_ID_id
                        const hiddenInput = document.createElement('input');
                        hiddenInput.type = 'hidden';
                        hiddenInput.name = `existing_music_${musicId}_id`;
                        hiddenInput.value = musicId;
                        this.appendChild(hiddenInput);
                        console.log(`Added hidden input for existing_music_${musicId}_id`);
                    }
                }
            });
            
            // Convert time fields to seconds and add hidden fields
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
                    
                    // Find or create a hidden input with _seconds suffix
                    let hiddenInput = document.querySelector(`input[name="${nameAttr}_seconds"]`);
                    if (!hiddenInput) {
                        hiddenInput = document.createElement('input');
                        hiddenInput.type = 'hidden';
                        hiddenInput.name = nameAttr + '_seconds';
                        input.parentNode.appendChild(hiddenInput);
                    }
                    
                    // Set the value
                    hiddenInput.value = seconds.toString();
                    console.log(`Added time in seconds for ${nameAttr}: ${seconds}`);
                }
            });
            
            // Verify form data before submission
            const formData = new FormData(this);
            console.log("Form data being submitted:");
            for (let [key, value] of formData.entries()) {
                console.log(`${key}: ${value}`);
            }
            
            // Add loading spinner
            const submitButton = document.getElementById('submitBgButton');
            if (submitButton) {
                submitButton.classList.add('loading');
            }
            
            // Allow normal form submission
            return true;
        });
    }
});
