let fontSize = 22;
let borderRadius = 26;
let resolution = '1:1';
let apiKeyError = '';
let voiceIdError = '';
let fontError = '';
let dimensionStyles = {
    '1:1': { fontColor: '#ffffff', bgColor: '#000000' },
    '4:5': { fontColor: '#ffffff', bgColor: '#000000' },
    '16:9': { fontColor: '#ffffff', bgColor: '#000000' },
    '9:16': { fontColor: '#000000', bgColor: '#ffffff' }
};
let isProcessing = false;
let processingDots = 0;
let fontSizeDerived = 44;
let selectedFont = '';
let processingInterval = null;

function isValidHex(color) {
    return /^#[0-9A-F]{6}$/i.test(color);
}

function startProcessingAnimation() {
    isProcessing = true;
    const buttonText = document.getElementById('button-text');
    buttonText.textContent = 'Processing';
    processingInterval = setInterval(() => {
        processingDots = (processingDots >= 3) ? 0 : processingDots + 1;
        buttonText.textContent = `Processing${'.'.repeat(processingDots)}`;
    }, 500);
}

function stopProcessingAnimation() {
    isProcessing = false;
    clearInterval(processingInterval);
    processingInterval = null;
    processingDots = 0;
    document.getElementById('button-text').textContent = 'Proceed To Scene Selection';
}

function validateForm() {
    let isValid = true;
    const apiKey = document.getElementById('api_key').value.trim();
    // const voiceId = document.getElementById('voice_id').value.trim();
    const fontSelect = document.getElementById('font_select').value;

    apiKeyError = '';
    voiceIdError = '';
    fontError = '';

    document.getElementById('api_key_error').textContent = '';
    document.getElementById('voice_id_error').textContent = '';
    document.getElementById('font_error').textContent = '';

    if (!apiKey) {
        apiKeyError = 'API key is required.';
        document.getElementById('api_key_error').textContent = apiKeyError;
        document.getElementById('api_key').focus();
        isValid = false;
    }

    // if (!voiceId) {
    //     voiceIdError = 'Voice ID is required.';
    //     document.getElementById('voice_id_error').textContent = voiceIdError;
    //     document.getElementById('voice_id').focus();
    //     isValid = false;
    // }

    if (resolution !== '9:16' && !fontSelect) {
        fontError = 'Please select a font.';
        document.getElementById('font_error').textContent = fontError;
        document.getElementById('font_select').focus();
        isValid = false;
    }

    if (!isValid) {
        const errorElement = document.querySelector('.error-message:not(:empty)');
        if (errorElement) {
            errorElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }

    return isValid;
}

function handleSubmit(event) {
    event.preventDefault();
    
    if (!validateForm()) {
        return false;
    }
    
    startProcessingAnimation();
    
    // Submit the form via AJAX to debug the data being sent
    const form = document.getElementById('text_form');
    const formData = new FormData(form);
    
    // Log form data to console for debugging
    console.log("Submitting form data:");
    for (let pair of formData.entries()) {
        console.log(pair[0] + ': ' + pair[1]);
    }
    
    // Submit the form directly
    form.submit();
    
    return false;
}

function updateSliderBackground(sliderId, value, min, max) {
    const slider = document.getElementById(sliderId);
    if (slider) {
        const percent = ((value - min) / (max - min)) * 100;
        slider.style.background = `linear-gradient(to right, #864AF9 ${percent}%, #D9D9D9 ${percent}%)`;
    }
}

function updateResolutionSettings(selectedResolution) {
    resolution = selectedResolution;
    const previewBox = document.getElementById('preview-box');
    const videoText = document.getElementById('videoText');
    const previewText = document.getElementById('previewText');
    const previewBackground = document.getElementById('previewBackground');
    const tiktokPreview = document.getElementById('tiktokPreview');
    const fontSelectLabel = document.querySelector('.Upload-Font-File-text');
    const fontSelectDropdown = document.querySelector('.Upload-Font-File-Upload');
    const fontSizeLabel = document.querySelector('.Font-Size-text');
    const fontSizeSlider = document.querySelector('.Font-Size-Slider');
    const borderRadiusLabel = document.querySelector('.slider-container label');
    const borderRadiusSliderDiv = document.querySelector('.slider-container');
    const fontSelect = document.getElementById('font_select');
    const preview = document.getElementById('Preview');

    let newFontSize = 22;
    if (selectedResolution === '1:1') {
        previewBox.style.width = '600px';
        previewBox.style.height = '600px';
        videoText.style.fontSize = '48px';
        previewText.style.width = '350px';
        preview.style.marginTop = '0';
        previewBox.style.background = '#EEEEEE';
        videoText.style.display = 'flex';
        previewBackground.style.display = 'flex';
        tiktokPreview.style.display = 'none';
        fontSelectLabel.style.display = 'flex';
        fontSelectDropdown.style.display = 'flex';
        fontSizeLabel.style.display = 'flex';
        fontSizeSlider.style.display = 'block';
        borderRadiusLabel.style.display = 'block';
        borderRadiusSliderDiv.style.display = 'block';
        if (selectedFont && selectedFont !== 'tiktokfont') {
            previewText.style.fontFamily = selectedFont;
        } else {
            fontSelect.value = '';
            previewText.style.fontFamily = '';
        }
        fontError = '';
        document.getElementById('font_error').textContent = '';
    } else if (selectedResolution === '4:5') {
        previewBox.style.width = '480px';
        previewBox.style.height = '600px';
        videoText.style.fontSize = '42px';
        previewText.style.width = '350px';
        preview.style.marginTop = '0';
        previewBox.style.background = '#EEEEEE';
        videoText.style.display = 'flex';
        previewBackground.style.display = 'flex';
        tiktokPreview.style.display = 'none';
        fontSelectLabel.style.display = 'flex';
        fontSelectDropdown.style.display = 'flex';
        fontSizeLabel.style.display = 'flex';
        fontSizeSlider.style.display = 'block';
        borderRadiusLabel.style.display = 'block';
        borderRadiusSliderDiv.style.display = 'block';
        if (selectedFont && selectedFont !== 'tiktokfont') {
            previewText.style.fontFamily = selectedFont;
        } else {
            fontSelect.value = '';
            previewText.style.fontFamily = '';
        }
        fontError = '';
        document.getElementById('font_error').textContent = '';
    } else if (selectedResolution === '16:9') {
        previewBox.style.width = '680px';
        previewBox.style.height = '382px';
        videoText.style.fontSize = '38px';
        previewText.style.width = '350px';
        preview.style.marginTop = '0';
        previewBox.style.background = '#EEEEEE';
        videoText.style.display = 'flex';
        previewBackground.style.display = 'flex';
        tiktokPreview.style.display = 'none';
        fontSelectLabel.style.display = 'flex';
        fontSelectDropdown.style.display = 'flex';
        fontSizeLabel.style.display = 'flex';
        fontSizeSlider.style.display = 'block';
        borderRadiusLabel.style.display = 'block';
        borderRadiusSliderDiv.style.display = 'block';
        if (selectedFont && selectedFont !== 'tiktokfont') {
            previewText.style.fontFamily = selectedFont;
        } else {
            fontSelect.value = '';
            previewText.style.fontFamily = '';
        }
        fontError = '';
        document.getElementById('font_error').textContent = '';
    } else if (selectedResolution === '9:16') {
        previewBox.style.width = '382px';
        previewBox.style.height = '680px';
        previewText.style.width = '300px';
        newFontSize = 16;
        fontSelect.value = 'tiktokfont';
        previewText.style.fontFamily = 'tiktokfont';
        tiktokPreview.style.fontFamily = 'tiktokfont';
        document.querySelectorAll('.text-wrapper2-span').forEach(span => {
            span.style.fontFamily = 'tiktokfont';
            span.style.color = dimensionStyles['9:16'].fontColor;
            span.style.backgroundColor = dimensionStyles['9:16'].bgColor;
        });
        previewBackground.style.display = 'none';
        tiktokPreview.style.display = 'flex';
        fontSelectLabel.style.display = 'none';
        fontSelectDropdown.style.display = 'none';
        fontSizeLabel.style.display = 'none';
        fontSizeSlider.style.display = 'none';
        borderRadiusLabel.style.display = 'none';
        borderRadiusSliderDiv.style.display = 'none';
        videoText.style.display = 'none';
        previewBox.style.background = `url('/images/tiktok.png') center/cover no-repeat`;
        preview.style.marginTop = '-2rem';
        fontError = '';
        document.getElementById('font_error').textContent = '';
    }

    if (selectedResolution !== '9:16' && selectedFont === 'tiktokfont') {
        selectedFont = '';
        fontSelect.value = '';
    }

    fontSize = newFontSize;
    previewText.style.fontSize = `${newFontSize * 0.8}px`;
    const slider = document.getElementById('mySlider');
    if (slider) {
        slider.value = newFontSize;
        updateSliderBackground('mySlider', newFontSize, 16, 25);
    }
    document.getElementById('SliderValue').textContent = newFontSize;
    document.getElementById('recommended-font-size').textContent = `(Recommended Font Size: ${newFontSize})`;
    fontSizeDerived = newFontSize * 2;
    document.getElementById('font_size').value = fontSizeDerived;
    previewBox.style.margin = '0 auto';

    if (previewBackground) {
        previewBackground.style.borderRadius = `${borderRadius}px`;
    }
    updateSliderBackground('subtitleBorderRadiusSlider', borderRadius, 0, 26);

    const fontColor = dimensionStyles[selectedResolution].fontColor;
    const bgColor = dimensionStyles[selectedResolution].bgColor;
    document.getElementById('colorPicker1').value = fontColor;
    document.getElementById('colortext1').value = fontColor;
    document.getElementById('color1').style.backgroundColor = fontColor;
    previewText.style.color = fontColor;

    document.getElementById('colorPicker2').value = bgColor;
    document.getElementById('colortext2').value = bgColor;
    document.getElementById('color2').style.backgroundColor = bgColor;
    previewBackground.style.backgroundColor = bgColor;

    document.querySelectorAll('.box').forEach(box => {
        const res = box.getAttribute('data-resolution');
        if (res === selectedResolution) {
            box.style.border = '1px solid #864AF9';
            const circleOuter = box.querySelector('.circle-outer');
            const circleInner = box.querySelector('.circle-inner');
            if (circleOuter) circleOuter.style.border = '3px solid #864AF9';
            if (circleInner) circleInner.style.backgroundColor = '#864AF9';
        } else {
            box.style.border = '1px solid #88888877';
            const circleOuter = box.querySelector('.circle-outer');
            const circleInner = box.querySelector('.circle-inner');
            if (circleOuter) circleOuter.style.border = '3px solid #D9D9D9';
            if (circleInner) circleInner.style.backgroundColor = '#D9D9D9';
        }
    });
}

function updateSliderBackground(id, value, min, max) {
    const percentage = ((value - min) / (max - min)) * 100;
    const slider = document.getElementById(id);
    slider.style.background = `linear-gradient(to right, #864AF9 ${percentage}%, #D9D9D9 ${percentage}%)`;
}

function handleFontSizeChange(event) {
    const value = parseInt(event.target.value);
    fontSize = value;
    fontSizeDerived = value * 2;
    document.getElementById('SliderValue').textContent = value;
    document.getElementById('font_size').value = fontSizeDerived;

    // Update subtitle preview
    document.getElementById('previewText').style.fontSize = `${value * 0.8}px`;

    updateSliderBackground('mySlider', value, 16, 25);
}

function handleBorderRadiusChange(event) {
    const value = parseInt(event.target.value);
    borderRadius = value;
    document.getElementById('subtitleBorderRadiusValue').textContent = value;

    // Apply to all relevant preview elements
    document.getElementById('previewBackground').style.borderRadius = `${value}px`;
    updateSliderBackground('subtitleBorderRadiusSlider', value, 0, 26);
}

// Attach listeners
document.getElementById('mySlider').addEventListener('input', handleFontSizeChange);
document.getElementById('subtitleBorderRadiusSlider').addEventListener('input', handleBorderRadiusChange);

// On page load (to sync initial states)
window.addEventListener('DOMContentLoaded', () => {
    handleFontSizeChange({ target: document.getElementById('mySlider') });
    handleBorderRadiusChange({ target: document.getElementById('subtitleBorderRadiusSlider') });
});
function handleTopicChange(event) {
    const selectedTopic = event.target.value;
    console.log("Topic selected:", selectedTopic);
    popupTopic = selectedTopic;
    
    // Clear file input when dropdown is used
    const fileInput = document.getElementById('slide_file');
    if (fileInput) {
        fileInput.value = '';
        popupFile = null;
        
        // Reset file upload UI
        const uploadText = document.getElementById("upload-text");
        if (uploadText) {
            uploadText.textContent = "Choose File";
        }
        
        const clearFileBtn = document.getElementById("clear-file");
        if (clearFileBtn) {
            clearFileBtn.style.display = "none";
        }
    }
    
    // Show/hide video clips based on the selected folder
    const videoSelect = document.getElementById('videoSelect');
    if (!videoSelect) return;

    // Clear all options except the default one
    videoSelect.innerHTML = '<option value="" disabled selected>Select A Video Clip</option>';
    
    if (selectedTopic && window.assetFolders && window.assetFolders[selectedTopic]) {
        const videos = window.assetFolders[selectedTopic];
        console.log(`Found ${videos.length} videos for folder: ${selectedTopic}`);
        
        if (videos.length > 0) {
            // Add options directly without optgroup
            videos.forEach(video => {
                const option = document.createElement('option');
                option.value = video.key;
                option.textContent = video.filename;
                option.setAttribute('data-url', video.url);
                videoSelect.appendChild(option);
            });
        }
    }
    
    // Reset selected video
    popupVideoClip = "";
    
    // Update submit button state
    const submitButton = document.getElementById('submit-clip');
    if (submitButton) {
        submitButton.disabled = true;
    }
}
function handleVideoClipChange(event) {
    const selectedVideo = event.target.value;
    console.log("Video selected:", selectedVideo);
    popupVideoClip = selectedVideo;
    
    const fileInput = document.getElementById('slide_file');
    if (fileInput) {
        fileInput.value = '';
        popupFile = null;

        const uploadText = document.getElementById("upload-text");
        if (uploadText) {
            uploadText.textContent = "Choose File";
        }

        const clearFileBtn = document.getElementById("clear-file");
        if (clearFileBtn) {
            clearFileBtn.style.display = "none";
        }
    }

    const submitButton = document.getElementById('submit-clip');
    if (submitButton) {
        submitButton.disabled = false;
    }

    renderPopup();
}

function handlePopupFileChange(e) {
    console.log("File change event triggered");
    const fileInput = document.getElementById('slide_file');

    if (fileInput && fileInput.files && fileInput.files.length > 0) {
        popupFile = fileInput.files[0];
        console.log("Selected file:", popupFile.name);

        // Clear asset selection
        const topicSelect = document.getElementById('selected_topic');
        const videoSelect = document.getElementById('videoSelect');
        if (topicSelect) {
            topicSelect.value = "";
            popupTopic = "";
        }
        if (videoSelect) {
            videoSelect.value = "";
            popupVideoClip = "";
        }

        // Update UI
        const uploadText = document.getElementById("upload-text");
        if (uploadText) {
            const fileName = popupFile.name;
            const lastDotIndex = fileName.lastIndexOf('.');
            const nameWithoutExt = lastDotIndex !== -1 ? fileName.substring(0, lastDotIndex) : '';
            const extension = lastDotIndex !== -1 ? fileName.substring(lastDotIndex) : '';
            const truncatedName = nameWithoutExt.length > 7 ? nameWithoutExt.substring(0, 7) : nameWithoutExt;
            uploadText.textContent = truncatedName + extension;
        }

        // Show clear file button
        const clearFileBtn = document.getElementById("clear-file");
        if (clearFileBtn) {
            clearFileBtn.style.display = "inline";
        }

        // Enable submit button
        const submitButton = document.getElementById("submit-clip");
        if (submitButton) {
            submitButton.disabled = false;
        }

        renderPopup();
    } else {
        console.log("No file selected or file input not found");
        popupFile = null;

        // Reset UI
        const uploadText = document.getElementById("upload-text");
        if (uploadText) {
            uploadText.textContent = "Choose File";
        }

        // Hide clear file button
        const clearFileBtn = document.getElementById("clear-file");
        if (clearFileBtn) {
            clearFileBtn.style.display = "none";
        }

        // Disable submit button if no video clip selected
        const submitButton = document.getElementById("submit-clip");
        if (submitButton) {
            submitButton.disabled = !popupVideoClip;
        }

        renderPopup();
    }
}

function handleResolutionChange(newResolution) {
    document.querySelector(`input[name="resolution"][value="${newResolution}"]`).checked = true;
    updateResolutionSettings(newResolution);
}

document.addEventListener('DOMContentLoaded', () => {
    updateResolutionSettings('1:1');
    updateSliderBackground('mySlider', fontSize, 16, 25);
    updateSliderBackground('subtitleBorderRadiusSlider', borderRadius, 0, 26);
    document.getElementById('previewText').style.fontSize = `${fontSize * 0.8}px`;
    document.getElementById('previewBackground').style.borderRadius = `${borderRadius}px`;
    document.getElementById('font_size').value = fontSizeDerived;

    const apiKeyInput = document.getElementById('api_key');
    const voiceIdInput = document.getElementById('voice_id');
    const fontSelect = document.getElementById('font_select');

    function clearErrors() {
        if (apiKeyInput.value) {
            apiKeyError = '';
            document.getElementById('api_key_error').textContent = '';
        }
        if (voiceIdInput.value) {
            voiceIdError = '';
            document.getElementById('voice_id_error').textContent = '';
        }
        if (fontSelect.value || resolution === '9:16') {
            fontError = '';
            document.getElementById('font_error').textContent = '';
        }
    }

    apiKeyInput.addEventListener('input', clearErrors);
    voiceIdInput.addEventListener('input', clearErrors);
    fontSelect.addEventListener('change', (e) => {
        selectedFont = e.target.value;
        if (resolution !== '9:16' && selectedFont !== 'tiktokfont') {
            document.getElementById('previewText').style.fontFamily = selectedFont;
        }
        clearErrors();
    });

    const colorPicker1 = document.getElementById('colorPicker1');
    const colorPicker2 = document.getElementById('colorPicker2');
    const colortext1 = document.getElementById('colortext1');
    const colortext2 = document.getElementById('colortext2');
    const colorBox1 = document.getElementById('color1');
    const colorBox2 = document.getElementById('color2');
    const previewBackground = document.getElementById('previewBackground');
    const previewText = document.getElementById('previewText');
    const tiktokSpans = document.querySelectorAll('.text-wrapper2-span');

    function handleColor1Change(e) {
        const color = e.target.value;
        if (isValidHex(color)) {
            dimensionStyles[resolution].fontColor = color;
            colortext1.value = color;
            colorBox1.style.backgroundColor = color;
            previewText.style.color = color;
            if (resolution === '9:16') {
                tiktokSpans.forEach(span => span.style.color = color);
            }
        }
    }

    function handleColor2Change(e) {
        const color = e.target.value;
        if (isValidHex(color)) {
            dimensionStyles[resolution].bgColor = color;
            colortext2.value = color;
            colorBox2.style.backgroundColor = color;
            previewBackground.style.backgroundColor = color;
            if (resolution === '9:16') {
                tiktokSpans.forEach(span => span.style.backgroundColor = color);
            }
        }
    }

    colorPicker1.addEventListener('input', handleColor1Change);
    colorPicker2.addEventListener('input', handleColor2Change);
    colortext1.addEventListener('input', handleColor1Change);
    colortext2.addEventListener('input', handleColor2Change);

    document.getElementById('submit_form').addEventListener('click', handleSubmit);

    document.querySelectorAll('.box').forEach(box => {
        box.addEventListener('click', () => {
            const newResolution = box.getAttribute('data-resolution');
            handleResolutionChange(newResolution);
        });
    });

    window.addEventListener('pageshow', (event) => {
        if (event.persisted) {
            stopProcessingAnimation();
            updateSliderBackground('mySlider', fontSize, 16, 25);
        }
    });
});