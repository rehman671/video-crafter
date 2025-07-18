let pendingUploads = new Set(); // Track highlights that are still uploading
let uploadQueue = new Map(); // Track upload promises
let scriptFile = null;
// Add these after the existing variables at the top
let scriptFileName = "No file chosen";
let folderFiles = null;
// Add these new variables for split/merge functionality
let subtitleOperationHistory = [];
let maxSubtitleHistorySize = 10;
let folderFileName = "No folder chosen";
let slides = [
    {
        id: -1, // Use negative ID for new slides
        subtitle: "Slide 1",
        text: "",
        markedText: "",
        originalText: "",
        isEditing: true,
        sequence: 1
    }
];
let slideCount = 1;
let isPfpDropdownOpen = false;
let popupOpen = false;
let selectedSlideId = null;
let selectedText = "";
let activeSlideIds = new Set([-1]); // Update this to match
let isProcessing = false;
let dotCount = 0;
let popupFile = null;
let popupTopic = "";
let popupVideoClip = "";
let popupErrorMessage = "";

// Make this constant globally available by adding it to the window object
const MAX_SUBTITLE_LENGTH = window.VIDEOTYPE === "9:16" ? 50 : 100;

window.MAX_SUBTITLE_LENGTH = MAX_SUBTITLE_LENGTH;
console.log("MAX_SUBTITLE_LENGTH:", MAX_SUBTITLE_LENGTH);
console.log("Video Type:", window.VIDEOTYPE);
// Initialize on page load
function getCleanTextContent(htmlText) {
    if (!htmlText) return "";
    
    // Create a temporary div to parse HTML and extract clean text
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = htmlText;
    
    // Get clean text content without any HTML tags
    const cleanText = tempDiv.textContent || tempDiv.innerText || "";
    
    return cleanText.trim();
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

document.addEventListener('DOMContentLoaded', () => {
    // Attach event listeners
    document.getElementById('pfp')?.addEventListener('click', togglePfpDropdown);
    document.getElementById('fileUpload')?.addEventListener('change', handleScriptFileChange);
    document.getElementById('fileInput')?.addEventListener('change', handleFolderFileChange);
    document.getElementById('videoUploadButton')?.addEventListener('click', handleFolderUpload);
    document.getElementById('createLeadBtn')?.addEventListener('click', addSlide);
    document.querySelector('.button-container-btn')?.addEventListener('click', handleProceedWithValidation);

    // Initialize drag and move functionality
    // initializeDragAndMove();

    // Initialize instruction sections
    document.querySelectorAll('.section-header').forEach(header => {
        header.addEventListener('click', () => toggleContent(header));
    });
    document.querySelectorAll('.section-content a').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            openModal('upload-video');
        });
    });

    // Load JSZip library dynamically if it's not already loaded
    if (typeof JSZip === 'undefined') {
        loadJSZip().catch(err => console.error("Failed to load JSZip:", err));
    }

    // Initial render
    renderSlides(false); // Don't update on first render

    // Send initial slide to backend if it's new (not loaded from database)
    if (slides.length > 0 && slides[0].id < 0) {
        // Send the first slide to the backend, using the actual ID from the slides array
        setTimeout(() => {
            const firstSlide = slides[0];
            console.log("Sending initial slide to backend with ID:", firstSlide.id);
            updateClipOnServer(firstSlide.id, firstSlide.text || "");
        }, 500);
    }

});

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
    document.getElementById('progressBar').style.width = `${percent}%`;
    document.getElementById('progressPercent').textContent = `${percent}%`;
    console.log(message);
}

// Function to create a ZIP file from the selected folder
async function createZipFromFolder(files) {
    // Define video extensions to accept
    const videoExtensions = ['.mp4', '.webm', '.ogg', '.mov', '.avi', '.wmv', '.flv', '.mkv', '.m4v', '.mpg', '.mpeg', '.3gp', '.3g2'];

    // Filter to include only video files and log what's being excluded
    const allFiles = Array.from(files);
    const videoFiles = [];
    const excludedFiles = [];
    // Add this after filtering video files but before creating the zip
    // Check if total video file size exceeds limit
    let totalSize = 0;
    for (const file of videoFiles) {
        totalSize += file.size;
    }

    if (totalSize > MAX_UPLOAD_SIZE) {
        console.error(`⚠️ Total video size (${formatFileSize(totalSize)}) exceeds the 10 GB limit!`);
        alert(`Total video size (${formatFileSize(totalSize)}) exceeds the 10 GB limit. Please select a smaller folder or fewer video files.`);
        return null;
    }

    // Also add this to the logs
    console.log(`Total video size: ${formatFileSize(totalSize)}`);
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

    // Rest of the function remains the same...
    // Load JSZip dynamically if it's not already loaded
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
// // Folder upload
// function handleFolderFileChange(event) {
//     folderFiles = event.target.files;
//     const folderName = folderFiles?.[0]?.webkitRelativePath.split("/")[0];
//     folderFileName = folderName ? folderName.slice(0, 15) : "No folder chosen";
//     document.getElementById('fileName2').textContent = folderFileName;
//     document.getElementById('fileName2').style.color = '#00000080';
// }

// // Handle folder upload and processing
// async function handleFolderUpload() {
//     // Check if user is on a free plan and show overlay if needed
//     if (typeof isFreePlan !== 'undefined' && isFreePlan) {
//         document.getElementById('freeUserOverlay').style.display = 'flex';
//         return;
//     }

//     if (!folderFiles || folderFiles.length === 0) {
//         alert('Please choose a folder to upload');
//         return;
//     }

//     // Change button text to "Uploading..."
//     const uploadButton = document.getElementById('videoUploadButton');
//     if (uploadButton) {
//         uploadButton.textContent = "Uploading...";
//         uploadButton.disabled = true;
//     }

//     // Show the upload form that was hidden but hide the percentage display
//     const uploadForm = document.getElementById('uploadForm');
//     if (uploadForm) {
//         uploadForm.style.display = 'block';
//     }

//     // Hide the percentage text to show only one progress indicator
//     document.getElementById('progressPercent').style.display = 'none';

//     // Show progress elements
//     document.getElementById('progressBar').style.width = '0%';
//     document.getElementById('uploadStatus').style.display = 'none'; // Hide status text

//     // Create a ZIP file from the selected folder
//     const zipFile = await createZipFromFolder(folderFiles);
//     if (!zipFile) {
//         // Reset button on error
//         if (uploadButton) {
//             uploadButton.textContent = "Upload and Process";
//             uploadButton.disabled = false;
//         }
//         return;
//     }

//     // Prepare directories info
//     const directories = {};
//     for (let i = 0; i < folderFiles.length; i++) {
//         const file = folderFiles[i];
//         const pathParts = file.webkitRelativePath.split('/');
//         const mainFolder = pathParts[0];
//         const subFolder = pathParts.length > 2 ? pathParts[1] : 'uncategorized';

//         if (!directories[subFolder]) {
//             directories[subFolder] = [];
//         }

//         directories[subFolder].push(file.name);
//     }

//     // Store directories info in the hidden input
//     if (document.getElementById('directories')) {
//         document.getElementById('directories').value = JSON.stringify(directories);
//     }

//     // Get CSRF token from cookie
//     function getCookie(name) {
//         let cookieValue = null;
//         if (document.cookie && document.cookie !== '') {
//             const cookies = document.cookie.split(';');
//             for (let i = 0; i < cookies.length; i++) {
//                 const cookie = cookies[i].trim();
//                 if (cookie.substring(0, name.length + 1) === (name + '=')) {
//                     cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
//                     break;
//                 }
//             }
//         }
//         return cookieValue;
//     }

//     const csrftoken = getCookie('csrftoken');

//     // Create a FormData object to send the files
//     const formData = new FormData(uploadForm);

//     // Remove any existing files and add the ZIP file
//     if (formData.has('folder')) {
//         formData.delete('folder');
//     }
//     formData.append('zip_file', zipFile);

//     // Add the folder name
//     const mainFolder = folderFiles[0].webkitRelativePath.split('/')[0];
//     formData.append('main_folder_name', mainFolder);

//     // Track upload progress
//     let lastProgress = 0;
//     const xhr = new XMLHttpRequest();
//     xhr.upload.addEventListener('progress', (event) => {
//         if (event.lengthComputable) {
//             const percentComplete = Math.round((event.loaded / event.total) * 100);

//             // Only update UI when progress changes by at least 1%
//             if (percentComplete > lastProgress) {
//                 lastProgress = percentComplete;
//                 document.getElementById('progressBar').style.width = percentComplete + '%';

//                 // If progress reaches 100%, prepare for page reload
//                 if (percentComplete >= 100) {
//                     uploadButton.textContent = "Processing...";
//                 }
//             }
//         }
//     });

//     xhr.addEventListener('load', function() {
//         if (xhr.status === 200) {
//             try {
//                 const response = JSON.parse(xhr.responseText);
//                 if (response.success) {
//                     // Set progress to 100% if not already
//                     document.getElementById('progressBar').style.width = '100%';

//                     // Reload page or redirect
//                     if (response.redirect_url) {
//                         window.location.href = response.redirect_url;
//                     } else {
//                         window.location.reload();
//                     }
//                 } else {
//                     // Reset button on error
//                     if (uploadButton) {
//                         uploadButton.textContent = "Upload and Process";
//                         uploadButton.disabled = false;
//                     }
//                     alert('Upload failed: ' + (response.error || 'Unknown error'));
//                 }
//             } catch (e) {
//                 // Reset button on error
//                 if (uploadButton) {
//                     uploadButton.textContent = "Upload and Process";
//                     uploadButton.disabled = false;
//                 }
//                 window.location.reload();

//             }
//         } else {
//             // Reset button on error
//             if (uploadButton) {
//                 uploadButton.textContent = "Upload and Process";
//                 uploadButton.disabled = false;
//             }
//             alert('Upload failed: Server returned ' + xhr.status);
//         }
//     });

//     xhr.addEventListener('error', function() {
//         // Reset button on error
//         if (uploadButton) {
//             uploadButton.textContent = "Upload and Process";
//             uploadButton.disabled = false;
//         }
//         alert('Upload failed: Network error');
//     });

//     xhr.addEventListener('abort', function() {
//         // Reset button on error
//         if (uploadButton) {
//             uploadButton.textContent = "Upload and Process";
//             uploadButton.disabled = false;
//         }
//         alert('Upload aborted');
//     });

//     xhr.open('POST', uploadForm.action);
//     xhr.setRequestHeader('X-CSRFToken', csrftoken);
//     xhr.send(formData);
// }

// Drag and Move with Auto-Scroll Functionality
// function initializeDragAndMove() {
//     if (!window.$ || !$('#leadsTable tbody').length) return;

//     let scrollSpeed = 50;
//     let scrollInterval;

//     $('#leadsTable tbody').sortable({
//         axis: "y",
//         containment: "parent",
//         handle: "td:first-child",
//         placeholder: "ui-sortable-placeholder",
//         forcePlaceholderSize: true,
//         tolerance: "pointer",
//         cursorAt: { top: 10 },
//         helper: function (e, tr) {
//             const $original = tr.children();
//             const $helper = tr.clone();
//             $helper.children().each(function (index) {
//                 $(this).width($original.eq(index).width());
//             });
//             return $helper;
//         },
//         start: function (event, ui) {
//             scrollInterval = setInterval(function () {
//                 autoScrollDuringDrag(ui.helper);
//             }, 20);
//             ui.item.data("scrollInterval", scrollInterval);
//         },
//         update: function (event, ui) {
//             const newOrder = $(this).sortable("toArray", { attribute: "data-id" });
//             const updatedSlides = newOrder.map((id, index) => {
//                 const slideId = parseInt(id);
//                 const slide = slides.find(s => s.id === slideId);
//                 return {
//                     ...slide,
//                     subtitle: `Subtitle ${index + 1}`,
//                     sequence: index + 1
//                 };
//             });
//             slides = updatedSlides;
//             renderSlides();

//         },
//         stop: function (event, ui) {
//             clearInterval(ui.item.data("scrollInterval"));
//             $(this).sortable("refreshPositions");
//         }
//     });

//     const style = document.createElement('style');
//     style.textContent = `
//         .ui-sortable-placeholder {
//             background: #f0f0f0;
//             border-left: 2px solid purple;
//             visibility: visible !important;
//             height: 50px;
//         }
//         td[title]:hover::after {
//             content: attr(title);
//             position: absolute;
//             top: -30px;
//             left: 50%;
//             transform: translateX(-50%);
//             background: #333;
//             color: white;
//             padding: 4px 8px;
//             border-radius: 4px;
//             font-size: 12px;
//             white-space: nowrap;
//             z-index: 1000;
//         }
//         .slide-last.active {
//             background-color: rgb(211, 211, 211);
//         }
//     `;
//     document.head.appendChild(style);
// }

function autoScrollDuringDrag(draggedElement) {  // Fixed parameter name
    const scrollThreshold = 50;
    const elementRect = draggedElement[0].getBoundingClientRect();

    if (elementRect.top < scrollThreshold) {
        window.scrollBy({ top: -10, behavior: 'smooth' });
    } else if (elementRect.bottom > window.innerHeight - scrollThreshold) {
        window.scrollBy({ top: 10, behavior: 'smooth' });
    }
}


// Processing dots
let processingInterval = null;
function startProcessing() {
    isProcessing = true;
    processingInterval = setInterval(() => {
        dotCount = (dotCount + 1) % 4;
        renderButton();
    }, 500);
}
function stopProcessing() {
    isProcessing = false;
    clearInterval(processingInterval);
    renderButton();
}


// Pfp dropdown
function togglePfpDropdown() {
    isPfpDropdownOpen = !isPfpDropdownOpen;
    const dropdown = document.getElementById('pfpdropdown');
    if (dropdown) {
        dropdown.className = isPfpDropdownOpen ? 'present' : 'not-present';
    }
}

// Script file upload
async function handleScriptFileChange(event) {
    const file = event.target.files[0];
    scriptFile = file;
    if (file) {
        const text = await file.text();
        // Check file size
        // if (text.length <= 5000) {
            // Check each line's character count
            const lines = text.split('\n');
            const longLines = lines.filter(line => line.trim().length > MAX_SUBTITLE_LENGTH);

            if (longLines.length > 0) {
                alert(`Some lines in your file exceed the ${MAX_SUBTITLE_LENGTH} character limit per subtitle. Please edit your file before uploading.`);
                scriptFileName = "No file chosen";
                scriptFile = null;
                event.target.value = "";
            } else {
                scriptFileName = file.name.slice(0, 15);
            }
        // } 
        // else {
        //     alert("The text file exceeds the 5000-character limit!");
        //     scriptFileName = "No file chosen";
        //     scriptFile = null;
        //     event.target.value = "";
        // }
    } else {
        scriptFileName = "No file chosen";
    }
    document.getElementById('fileName').textContent = scriptFileName;
    document.getElementById('fileName').style.color = '#00000080';
}

// Initialize highlighting with subclips data
function processInitialSubclips(subclips) {
    console.log("Processing initial subclips:", subclips);

    // Group subclips by clip_id
    const subclipsByClip = {};
    subclips.forEach(subclip => {
        if (!subclipsByClip[subclip.clip_id]) {
            subclipsByClip[subclip.clip_id] = [];
        }
        subclipsByClip[subclip.clip_id].push(subclip);
    });

    // Apply highlights to each clip
    slides = slides.map(slide => {
        const clipSubclips = subclipsByClip[slide.id] || [];

        if (clipSubclips.length > 0) {
            let markedText = slide.text;

            // Sort subclips by text length (longest first) to avoid nested replacement issues
            clipSubclips.sort((a, b) => b.text.length - a.text.length);

            // Apply highlighting for each subclip
            clipSubclips.forEach(subclip => {
                const highlightId = `highlight_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
                const regex = new RegExp(`(${escapeRegExp(subclip.text)})(?![^<]*>)`, "i");

                // Store existing file information in the mark element
                markedText = markedText.replace(
                    regex,
                    `<mark class="handlePopupSubmit" data-highlight-id="${highlightId}" data-video-file="${subclip.video_file}">${subclip.text}</mark>`
                );
            });

            return {
                ...slide,
                markedText: markedText
            };
        }

        return slide;
    });

    // Re-render slides with highlights without sending updates to server
    renderSlides(false);
}

// Helper function to escape special characters in regex
function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Load script into slides
async function loadScript(clips) {
    console.log(clips);

    if (clips && clips.length > 0) {
        // Validate all clips for character limits
        const excessiveLengthClips = clips.filter(clip =>
            clip.text && clip.text.length > MAX_SUBTITLE_LENGTH
        );

        if (excessiveLengthClips.length > 0) {
            alert(`${excessiveLengthClips.length} subtitle(s) exceed the ${MAX_SUBTITLE_LENGTH} character limit. These will be highlighted in red.`);
        }

        const isDefaultUnchanged = slides.length === 1 && slides[0].id === -1 &&
            (slides[0].text === "" || slides[0].text === "Type Your Script Here");

        let newSlides = clips.map((clip, index) => ({
            id: clip.id,
            subtitle: `Slide ${index + 1}`,
            text: clip.text,
            markedText: clip.text, // Will be updated if subclips exist
            originalText: clip.text,
            isEditing: false,
            sequence: clip.sequence,
            exceedsLimit: clip.text && clip.text.length > MAX_SUBTITLE_LENGTH
        }));

        slideCount = clips.length;
        slides = isDefaultUnchanged ? newSlides : [...slides, ...newSlides];
        activeSlideIds = new Set();
        renderSlides();
    }
}

// Function to create a zip file and upload it
function createAndUploadZip(files) {
    // Show progress elements
    document.getElementById('progressBar').style.width = '0%';
    document.getElementById('progressPercent').textContent = '0%';
    document.getElementById('uploadStatus').textContent = 'Creating zip file...';
    document.getElementById('uploadStatus').style.display = 'block';

    // Get CSRF token from cookie
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    const csrftoken = getCookie('csrftoken');

    // Create a FormData object to send the files
    const formData = new FormData(document.getElementById('uploadForm'));

    // Append each file to the FormData
    const mainFolder = files[0].webkitRelativePath.split('/')[0];
    formData.append('main_folder_name', mainFolder);

    // Track upload progress
    let lastProgress = 0;
    const xhr = new XMLHttpRequest();
    xhr.upload.addEventListener('progress', (event) => {
        if (event.lengthComputable) {
            const percentComplete = Math.round((event.loaded / event.total) * 100);

            // Only update UI when progress changes by at least 1%
            if (percentComplete > lastProgress) {
                lastProgress = percentComplete;
                document.getElementById('progressBar').style.width = percentComplete + '%';
                document.getElementById('progressPercent').textContent = percentComplete + '%';
            }
        }
    });

    xhr.addEventListener('load', function () {
        if (xhr.status === 200) {
            try {
                const response = JSON.parse(xhr.responseText);
                if (response.success) {
                    document.getElementById('uploadStatus').textContent = 'Upload completed successfully!';
                    document.getElementById('progressBar').style.width = '100%';
                    document.getElementById('progressPercent').textContent = '100%';

                    // Redirect if provided in response
                    if (response.redirect_url) {
                        window.location.href = response.redirect_url;
                    }
                } else {
                    document.getElementById('uploadStatus').textContent = 'Upload failed: ' + (response.error || 'Unknown error');
                }
            } catch (e) {
                document.getElementById('uploadStatus').textContent = 'Error processing server response';
            }
        } else {
            document.getElementById('uploadStatus').textContent = 'Upload failed: Server returned ' + xhr.status;
        }
    });

    xhr.addEventListener('error', function () {
        document.getElementById('uploadStatus').textContent = 'Upload failed: Network error';
    });

    xhr.addEventListener('abort', function () {
        document.getElementById('uploadStatus').textContent = 'Upload aborted';
    });

    xhr.open('POST', document.getElementById('uploadForm').action);
    xhr.setRequestHeader('X-CSRFToken', csrftoken);
    xhr.send(formData);
}

// Slides management
function addSlide(e) {
    e.preventDefault();
    const newId = (-1 * slides.length) - 1;
    const slideNumber = slides.length + 1; // Keep track of the display number separately
    const newSlide = {
        id: newId,
        subtitle: `Slide ${slideNumber}`, // Use positive number for display
        text: "",
        markedText: "",
        originalText: "",
        isEditing: true,
        sequence: slideNumber
    };
    slides.push(newSlide);
    slideCount = newId;
    // Don't add to activeSlideIds here - let the slide be displayed without being active
    renderSlides();

    // Send the new slide to the backend to create a clip
    updateClipOnServer(newId, "");
    updateProceedButtonState();
}

function deleteSlide(id) {
    slides = slides
        .filter(slide => slide.id !== id)
        .map((slide, index) => ({
            ...slide,
            subtitle: `Slide ${index + 1}`,
            sequence: index + 1
        }));
    slideCount = slides.length > 0 ? Math.max(...slides.map(s => s.id)) : 0;
    console.log("Deleted slide with ID:", id);
    deleteClipFromServer(id);
    activeSlideIds.delete(id);
    renderSlides();
    if(isFreePlan){
        checkSubtitleLimit()
    }
    updateProceedButtonState();
}

function toggleEdit(slideId) {
    const slide = slides.find(slide => slide.id === slideId);
    const wasEditing = slide.isEditing;

    slides = slides.map(slide =>
        slide.id === slideId ? { ...slide, isEditing: !slide.isEditing } : slide
    );

    // If slide was in edit mode and now it's not, update the server
    if (wasEditing && !slides.find(slide => slide.id === slideId).isEditing) {
        const slideText = slides.find(slide => slide.id === slideId).text;
        updateClipOnServer(slideId, slideText);
    }

    if (slides.find(slide => slide.id === slideId).isEditing) {
        console.log("Editing slide:", slideId);
        activeSlideIds.add(slideId);
    } else {
        console.log("Editing slide:", slideId);
        activeSlideIds.delete(slideId);
    }
    renderSlides();
    updateProceedButtonState();
}

function handleKeyPress(e, slideId) {
    if (e.key === "Enter") {
        e.preventDefault();
        const textarea = e.target;

        // Check if the text exceeds the character limit
        if (textarea.value.length > MAX_SUBTITLE_LENGTH) {
            const errorMessage = document.getElementById(`error-message_${slideId}`);
            if (errorMessage) {
                errorMessage.textContent = `Subtitle text cannot exceed ${MAX_SUBTITLE_LENGTH} characters`;
                errorMessage.style.display = "block";
            }
            return;
        }

        slides = slides.map(slide =>
            slide.id === slideId ? {
                ...slide,
                text: textarea.value,
                markedText: textarea.value,
                isEditing: false
            } : slide
        );

        // Update clip on server when user presses Enter
        updateClipOnServer(slideId, textarea.value);

        activeSlideIds.delete(slideId);
        renderSlides(false); // Pass false to avoid double update
        textarea.blur();
    }
}

// Function to update clip on the server
function updateClipOnServer(slideId, text) {
    // Validate subtitle length first
    if (!validateSubtitleLength(text)) {
        const slide = slides.find(s => s.id === slideId);
        if (slide) {
            const errorMessage = document.getElementById(`error-message_${slideId}`);
            if (errorMessage) {
                errorMessage.textContent = `Subtitle text cannot exceed ${MAX_SUBTITLE_LENGTH} characters`;
                errorMessage.style.display = "block";
            }
        }
        return false;
    }

    // Get video ID from the URL
    const path = window.location.pathname;
    const videoId = path.split('/')[2];

    // Get CSRF token from cookie
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    const csrftoken = getCookie('csrftoken');

    // Get the slide to retrieve its sequence number
    const slide = slides.find(s => s.id === slideId);

    // Prepare data for the request
    const data = {
        clip_id: slideId,
        text: text,
        video_id: videoId,
        sequence: slide.sequence // Add sequence number to the data sent to server
    };

    // Send AJAX request
    fetch('/update-clip/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrftoken,
        },
        body: JSON.stringify(data),
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                console.log('Clip updated successfully:', data);
                // If a new clip was created, update the slide ID
                if (data.clip_id && slideId < 0) {
                    slides = slides.map(slide =>
                        slide.id === slideId ? { ...slide, id: data.clip_id } : slide
                    );
                    activeSlideIds.delete(slideId);
                    // activeSlideIds.add(data.clip_id);
                    renderSlides(send_update = false);
                }
            } else {
                console.error('Error updating clip:', data.error);
            }
        })
        .catch(error => {
            console.error('Error:', error);
        });
}

// Function to delete clip from the server
function deleteClipFromServer(slideId) {
    // Get video ID from the URL
    const path = window.location.pathname;

    // Get CSRF token from cookie
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    const csrftoken = getCookie('csrftoken');

    // Prepare data for the request
    const data = {
        clip_id: slideId,
    };

    // Only send delete request if the slideId is positive (existing in database)
    if (slideId > 0) {
        // Send AJAX request
        fetch('/delete-clip/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken,
            },
            body: JSON.stringify(data),
        })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    console.log('Clip deleted successfully:', data);
                } else {
                    console.error('Error deleting clip:', data.error);
                }
            })
            .catch(error => {
                console.error('Error:', error);
            });
    } else {
        console.log('Skipping server delete for temporary slide ID:', slideId);
    }
}

function handleUndo(slideId) {
    if (confirm("Are You Sure You Want To Reset This Sentence?")) {
        slides = slides.map(slide => {
            if (slide.id === slideId) {
                let cleanText = "";
                
                if (!slide.originalText || slide.originalText.trim() === "") {
                    // If no original text, extract clean text from markedText
                    cleanText = getCleanTextContent(slide.markedText || slide.text || "");
                    console.log("Undo: No original text, cleaning marked text:", {
                        markedText: slide.markedText,
                        cleanedText: cleanText,
                        cleanedLength: cleanText.length
                    });
                } else {
                    // Use original text, but make sure it's clean too
                    cleanText = getCleanTextContent(slide.originalText);
                    console.log("Undo: Using original text:", {
                        originalText: slide.originalText,
                        cleanedText: cleanText,
                        cleanedLength: cleanText.length
                    });
                }
                
                return {
                    ...slide,
                    text: cleanText,
                    markedText: cleanText, // Reset marked text to clean text
                    isEditing: false
                };
            }
            return slide;
        });
        
        activeSlideIds.delete(slideId);
        renderSlides();
    }
    updateProceedButtonState();
}

// function handleUndo(slideId) {
//     if (confirm("Are You Sure You Want To Reset This Sentence?")) {
//         slides = slides.map(slide => {
//             if (slide.id === slideId) {
//                 if (!slide.originalText || slide.originalText.trim() === "") {
//                     const cleanedText = slide.markedText.replace(
//                         /<mark class="handlePopupSubmit">([^<]+)<\/mark>/gi,
//                         "$1"
//                     );
//                     return {
//                         ...slide,
//                         text: cleanedText,
//                         markedText: cleanedText,
//                         isEditing: false
//                     };
//                 }
//                 return {
//                     ...slide,
//                     text: slide.originalText,
//                     markedText: slide.originalText,
//                     isEditing: false
//                 };
//             }
//             return slide;
//         });
//         activeSlideIds.delete(slideId);
//         renderSlides();
//     }
// }

// function handleTextSelection(slideId) {
//     const slide = slides.find(s => s.id === slideId);
//     if (slide.isEditing) return;

//     const selection = window.getSelection();
//     const selected = selection.toString().trim();

//     if (selected && /\b\w+\b/.test(selected) && selected.length > 1) {
//         const markedText = slide.markedText || slide.text || "";

//         // Create a temporary div to parse the HTML content properly
//         const tempDiv = document.createElement('div');
//         tempDiv.innerHTML = markedText;

//         // Get the DOM representation of the text
//         const nodes = Array.from(tempDiv.childNodes);

//         // Get the raw text content
//         const textContent = tempDiv.textContent;

//         // Check if the selected text exists in the text content at all
//         if (textContent.includes(selected)) {
//             // Extract all existing highlights
//             const highlights = Array.from(tempDiv.querySelectorAll('mark.handlePopupSubmit'))
//                 .map(mark => mark.textContent);

//             // Check if the selection is already highlighted
//             const isAlreadyHighlighted = highlights.some(highlight => 
//                 highlight.includes(selected) || selected.includes(highlight)
//             );

//             // Check if selected text overlaps with existing highlights
//             let selectionOverlapsHighlight = false;

//             // Find the position of the selected text in the full text
//             const selectionIndex = textContent.indexOf(selected);

//             // Check if this position overlaps with any existing highlight
//             highlights.forEach(highlight => {
//                 const highlightIndex = textContent.indexOf(highlight);
//                 const highlightEnd = highlightIndex + highlight.length;

//                 // Check for overlap
//                 if ((selectionIndex >= highlightIndex && selectionIndex < highlightEnd) ||
//                     (selectionIndex + selected.length > highlightIndex && selectionIndex + selected.length <= highlightEnd)) {
//                     selectionOverlapsHighlight = true;
//                 }
//             });

//             const errorMessage = document.querySelector(`#error-message_${slideId}`);

//             if (!isAlreadyHighlighted && !selectionOverlapsHighlight) {
//                 // Selection is valid, proceed with the popup
//                 if (errorMessage) {
//                     errorMessage.textContent = "";
//                     errorMessage.style.display = "none";
//                 }

//                 selectedSlideId = slideId;
//                 selectedText = selected;
//                 popupOpen = true;
//                 renderPopup();
//             } else {
//                 // Display appropriate error message
//                 if (errorMessage) {
//                     errorMessage.textContent = isAlreadyHighlighted ? 
//                         "This text is already assigned to a video clip." : 
//                         "Selection overlaps with existing highlights. Please select unassigned text only.";
//                     errorMessage.style.display = "block";
//                 }
//             }
//         } else {
//             const errorMessage = document.querySelector(`#error-message_${slideId}`);
//             if (errorMessage) {
//                 errorMessage.textContent = "Selected text not found in subtitle.";
//                 errorMessage.style.display = "block";
//             }
//         }

//         selection.removeAllRanges();
//     }
// }


function handleTextSelection(slideId) {
    const slide = slides.find(s => s.id === slideId);
    if (slide.isEditing) return;

    const selection = window.getSelection();
    let selected = selection.toString().trim();

    // Ignore empty selections
    if (!selected || selected.length <= 1) return;

    const markedText = slide.markedText || slide.text || "";

    // Create a temporary div to parse the HTML content properly
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = markedText;

    // Get the plain text content (without HTML tags)
    const textContent = tempDiv.textContent;

    // Check if the selection exists in the text content
    if (!textContent.includes(selected)) {
        const errorMessage = document.querySelector(`#error-message_${slideId}`);
        if (errorMessage) {
            errorMessage.textContent = "Selected text not found in subtitle.";
            errorMessage.style.display = "block";
        }
        selection.removeAllRanges();
        return;
    }

    // Find the position of the selection in the text
    const selectionIndex = textContent.indexOf(selected);

    // Check if the selection starts at word boundary
    const isStartWordBoundary = selectionIndex === 0 ||
        !isWordChar(textContent[selectionIndex - 1]);

    // Check if the selection ends at word boundary
    const selectionEnd = selectionIndex + selected.length;
    const isEndWordBoundary = selectionEnd === textContent.length ||
        !isWordChar(textContent[selectionEnd]);

    // If not at word boundaries, show error and exit
    if (!isStartWordBoundary || !isEndWordBoundary) {
        const errorMessage = document.querySelector(`#error-message_${slideId}`);
        showErrorMessage(slideId, "Please select whole words only.");
        selection.removeAllRanges();
        return;
    }

    // Extract all existing highlights
    const highlights = Array.from(tempDiv.querySelectorAll('mark.handlePopupSubmit'))
        .map(mark => mark.textContent);

    // Check if the selection is already highlighted
    const isAlreadyHighlighted = highlights.some(highlight =>
        highlight.includes(selected) || selected.includes(highlight)
    );

    // Check if selected text overlaps with existing highlights
    let selectionOverlapsHighlight = false;

    // Check for overlap with existing highlights
    highlights.forEach(highlight => {
        const highlightIndex = textContent.indexOf(highlight);
        const highlightEnd = highlightIndex + highlight.length;

        // Check for overlap
        if ((selectionIndex >= highlightIndex && selectionIndex < highlightEnd) ||
            (selectionEnd > highlightIndex && selectionEnd <= highlightEnd) ||
            (selectionIndex <= highlightIndex && selectionEnd >= highlightEnd)) {
            selectionOverlapsHighlight = true;
        }
    });

    const errorMessage = document.querySelector(`#error-message_${slideId}`);

    if (!isAlreadyHighlighted && !selectionOverlapsHighlight) {
        // Selection is valid, proceed with the popup
        if (errorMessage) {
            errorMessage.textContent = "";
            errorMessage.style.display = "none";
        }

        selectedSlideId = slideId;
        selectedText = selected;
        popupOpen = true;
        renderPopup();
    } else {
        // Display appropriate error message
        if (errorMessage) {
            errorMessage.textContent = isAlreadyHighlighted ?
                "This text is already assigned to a video clip." :
                "Selection overlaps with existing highlights. Please select unassigned text only.";
            errorMessage.style.display = "block";
        }
    }

    selection.removeAllRanges();
}

// Helper function to show an error message with animation
function showErrorMessage(slideId, message) {
    const errorElement = document.getElementById(`error-message_${slideId}`);
    if (!errorElement) return;

    errorElement.textContent = message;
    errorElement.style.display = 'block';

    // Create shake animation
    errorElement.style.animation = 'none';
    setTimeout(() => {
        errorElement.style.animation = 'shake 0.5s ease-in-out';
    }, 10);
}

// Helper function to determine if a character is part of a word
function isWordChar(char) {
    if (!char) return false;
    return /\w/.test(char) || char === "'" || char === "-"; // Include apostrophes and hyphens as part of words
}
// function handleHighlightedTextClick(slideId, markedText) {
//     const match = markedText.match(/<mark class="handlePopupSubmit">([^<]+)<\/mark>/);
//     if (match) {
//         selectedSlideId = slideId;
//         selectedText = match[1]; // The highlighted text
//         popupOpen = true;
//         renderPopup();
//     }
// }



function areAllTextareasHidden() {
    return slides.every(slide => !slide.isEditing);
}

async function fetchNoSubclipIds() {
    console.log("Checking for unassigned text in slides...");

    return slides
        .filter(slide => {
            // Skip empty slides
            if (!slide.text || slide.text.trim() === "") {
                return false;
            }

            // Extract all highlighted text from the marked text
            const markedText = slide.markedText || slide.text || "";

            // Create a temporary div to properly parse the HTML
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = markedText;

            // Get all mark elements
            const markElements = tempDiv.querySelectorAll('mark.handlePopupSubmit');

            // If there are no mark elements but there is text, it means no text is assigned
            if (markElements.length === 0) {
                console.log(`Slide ${slide.id} has no highlights at all`);
                return true;
            }

            // Get the raw text without any HTML
            const fullText = tempDiv.textContent.trim();

            // Collect all the highlighted text
            let highlightedText = '';
            markElements.forEach(mark => {
                highlightedText += mark.textContent;
            });

            // Remove all spaces from both strings for comparison
            const normalizedFullText = fullText.replace(/\s+/g, '');
            const normalizedHighlightedText = highlightedText.replace(/\s+/g, '');

            // Check if all text is highlighted by comparing after removing spaces
            const isAllHighlighted = normalizedHighlightedText === normalizedFullText;

            if (!isAllHighlighted) {
                console.log(`Slide ${slide.id} has unassigned text: "${normalizedFullText}" vs highlighted: "${normalizedHighlightedText}"`);
            }

            return !isAllHighlighted;
        })
        .map(slide => slide.id);
}

// async function handleProceedWithValidation(event) {
//     event.preventDefault(); // Prevent default navigation
//     startProcessing();
//     if (areAllTextareasHidden()) {
//         // Check for excessive character counts in all slides
//         const exceededLimitSlides = slides.filter(slide => 
//             slide.text && slide.text.length > MAX_SUBTITLE_LENGTH
//         );

//         if (exceededLimitSlides.length > 0) {
//             exceededLimitSlides.forEach(slide => {
//                 const errorMessage = document.querySelector(`#error-message_${slide.id}`);
//                 if (errorMessage) {
//                     errorMessage.textContent = `Subtitle text cannot exceed ${MAX_SUBTITLE_LENGTH} characters (current: ${slide.text.length})`;
//                     errorMessage.style.display = "block";
//                 }
//             });

//             alert(`${exceededLimitSlides.length} subtitle(s) exceed the ${MAX_SUBTITLE_LENGTH} character limit. Please edit them before proceeding.`);
//             stopProcessing();
//             return;
//         }

//         const idsWithoutClips = await fetchNoSubclipIds();
//         if (idsWithoutClips.length > 0) {
//             idsWithoutClips.forEach(id => {
//                 const errorMessage = document.querySelector(`#error-message_${id}`);
//                 if (errorMessage) {
//                     const slide = slides.find(s => s.id === id);
//                     errorMessage.textContent = !slide.markedText || slide.markedText.trim() === ""
//                         ? "Please Enter Subtitle Text"
//                         : "Assign Clips To All Of The Subtitle Text";
//                     errorMessage.style.display = "block";
//                 }
//             });
//             stopProcessing();
//         } else {
//             console.log("Updating backend order with slides:", slides);

//             // Get video ID from the URL
//             const path = window.location.pathname;
//             const videoId = path.split('/')[2];

//             // Get CSRF token from cookie
//             function getCookie(name) {
//                 let cookieValue = null;
//                 if (document.cookie && document.cookie !== '') {
//                     const cookies = document.cookie.split(';');
//                     for (let i = 0; i < cookies.length; i++) {
//                         const cookie = cookies[i].trim();
//                         if (cookie.substring(0, name.length + 1) === (name + '=')) {
//                             cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
//                             break;
//                         }
//                     }
//                 }
//                 return cookieValue;
//             }

//             const csrftoken = getCookie('csrftoken');

//             // Create FormData to send all data including files
//             const formData = new FormData();
//             formData.append('video_id', videoId);

//             // Track if we're only uploading new files (not changing existing structure)
//             const newFiles = window.videoFiles ? Object.keys(window.videoFiles).length : 0;
//             formData.append('new_files_only', newFiles > 0 ? 'true' : 'false');

//             // Process slides and extract file data
//             const processedSlides = slides.map(slide => {
//                 const slideData = {
//                     id: slide.id,
//                     text: slide.text,
//                     markedText: slide.markedText,
//                     sequence: slide.sequence,
//                     highlights: []
//                 };

//                 // Extract highlight information if exists in markedText
//                 if (slide.markedText) {
//                     // Match all mark elements with their attributes and content
//                     const markRegex = /<mark class="handlePopupSubmit"([^>]*)>([^<]+)<\/mark>/g;
//                     let match;

//                     // Iterate through all matches in the marked text
//                     while ((match = markRegex.exec(slide.markedText)) !== null) {
//                         const attributes = match[1]; // All attributes inside the mark tag
//                         const text = match[2]; // The text content of the mark

//                         // Extract the highlight ID
//                         const highlightIdMatch = attributes.match(/data-highlight-id="([^"]*)"/);
//                         const highlightId = highlightIdMatch ? highlightIdMatch[1] : null;

//                         // Extract the video file if present
//                         const videoFileMatch = attributes.match(/data-video-file="([^"]*)"/);
//                         const videoFile = videoFileMatch ? videoFileMatch[1] : null;

//                         // Extract asset folder and video key if present
//                         const topicMatch = attributes.match(/data-topic="([^"]*)"/);
//                         const videoKeyMatch = attributes.match(/data-video-key="([^"]*)"/);
//                         const topic = topicMatch ? topicMatch[1] : null;
//                         const videoKey = videoKeyMatch ? videoKeyMatch[1] : null;

//                         console.log(`Extracted highlight: ID=${highlightId}, text=${text}, topic=${topic}, videoKey=${videoKey}, videoFile=${videoFile}`);

//                         // Store highlight information
//                         if (highlightId) {
//                             const highlightData = {
//                                 text: text,
//                                 highlightId: highlightId
//                             };

//                             // Add videoFile if available
//                             if (videoFile) {
//                                 highlightData.videoFile = videoFile;
//                             }

//                             // Add topic and videoKey if available (for asset selection)
//                             if (topic && videoKey) {
//                                 highlightData.topic = topic;
//                                 highlightData.videoKey = videoKey;
//                             }

//                             slideData.highlights.push(highlightData);
//                         }
//                     }
//                 }

//                 return slideData;
//             });

//             // Add processed slides to FormData
//             formData.append('slides_data', JSON.stringify(processedSlides));

//             // Add only new files from window.videoFiles
//             if (window.videoFiles) {
//                 Object.entries(window.videoFiles).forEach(([highlightId, file]) => {
//                     formData.append(`file_${highlightId}`, file);
//                     console.log(`Adding file: ${highlightId} = ${file.name}`);
//                 });
//             }

//             // Log the request data to console for debugging
//             console.log("Sending slides data:", processedSlides);

//             // Send data to server
//             fetch('/save-slides-data/', {
//                 method: 'POST',
//                 headers: {
//                     'X-CSRFToken': csrftoken,
//                 },
//                 body: formData
//             })
//             .then(response => {
//                 console.log("Response status:", response.status);

//                 // Check if the response is a redirect
//                 if (response.redirected) {
//                     console.log('Server redirected to:', response.url);
//                     window.location.href = response.url;
//                     return { success: true, redirected: true };
//                 }

//                 return response.json();
//             })
//             .then(data => {
//                 // Skip further processing if we were redirected
//                 if (data.redirected) return;

//                 console.log("Response data:", data);
//                 if (data.success) {
//                     console.log('Slides data saved successfully');
//                     // If the server didn't redirect us, manually go to background music page
//                     window.location.href = `/background-music/${videoId}/`;
//                 } else {
//                     console.error('Error saving slides data:', data.error);
//                     alert('Error saving slides data. Please try again.');
//                     stopProcessing();
//                 }
//             })
//             .catch(error => {
//                 console.error('Error:', error);
//                 alert('An error occurred. Please try again.');
//                 stopProcessing();
//             });
//         }
//     } else {
//         alert("You Need To Save or Delete The Current Text");
//         stopProcessing();
//     }
// }

async function handleProceedWithValidation(event) {
    event.preventDefault(); // Prevent default navigation
    
    // First check critical issues that prevent proceeding
    if (!areAllTextareasHidden()) {
        alert("You Need To Save or Delete The Current Text");
        return;
    }
    
    if (pendingUploads.size > 0) {
        return; // Still uploading
    }
    
    // Check for excessive character counts and show them with shake animation
    const exceededLimitSlides = slides.filter(slide => 
        slide.text && slide.text.length > MAX_SUBTITLE_LENGTH
    );
    
    if (exceededLimitSlides.length > 0) {
        // Scroll to the first slide with exceeded limit and shake it
        const firstExceededSlide = exceededLimitSlides[0];
        scrollToSlideWithShake(firstExceededSlide.id, 
            `Subtitle text cannot exceed ${MAX_SUBTITLE_LENGTH} characters (current: ${firstExceededSlide.text.length})`);
        
        // Show alert with count
        alert(`${exceededLimitSlides.length} subtitle(s) exceed the ${MAX_SUBTITLE_LENGTH} character limit. Please edit them before proceeding.`);
        return;
    }
    
    // Check for unassigned text and show with shake animation
    const unassignedSlides = findUnassignedSlides();
    if (unassignedSlides.length > 0) {
        // Scroll to the first unassigned slide and shake it
        const firstUnassignedSlide = unassignedSlides[0];
        const errorMessage = !firstUnassignedSlide.markedText || firstUnassignedSlide.markedText.trim() === ""
            ? "Please Enter Subtitle Text"
            : "Assign Clips To All Of The Subtitle Text";
            
        scrollToSlideWithShake(firstUnassignedSlide.id, errorMessage);
        
        // Show alert with count
        alert(`${unassignedSlides.length} subtitle(s) have unassigned text. Please assign video clips to all text before proceeding.`);
        return;
    }
    
    // If we get here, everything is valid - proceed with the original logic
    startProcessing();
    
    console.log("Updating backend order with slides:", slides);

    // Get video ID from the URL
    const path = window.location.pathname;
    const videoId = path.split('/')[2];

    // Get CSRF token from cookie
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    const csrftoken = getCookie('csrftoken');

    // Create FormData to send all data including files
    const formData = new FormData();
    formData.append('video_id', videoId);

    // Check if we're using assets or uploading new files
    const hasAssetSelections = slides.some(slide =>
        slide.markedText && slide.markedText.includes('data-topic=') && slide.markedText.includes('data-video-key=')
    );

    const newFiles = window.videoFiles ? Object.keys(window.videoFiles).length : 0;

    // Add a flag to indicate whether we're processing assets or new files or both
    formData.append('processing_assets', hasAssetSelections ? 'true' : 'false');
    formData.append('new_files_only', newFiles > 0 ? 'true' : 'false');

    // Process slides and extract file data
    const processedSlides = slides.map(slide => {
        const slideData = {
            id: slide.id,
            text: slide.text,
            markedText: slide.markedText,
            sequence: slide.sequence,
            highlights: []
        };

        // Extract highlight information if exists in markedText
        if (slide.markedText) {
            // Match all mark elements with their attributes and content
            const markRegex = /<mark class="handlePopupSubmit"([^>]*)>([^<]+)<\/mark>/g;
            let match;

            // Iterate through all matches in the marked text
            while ((match = markRegex.exec(slide.markedText)) !== null) {
                const attributes = match[1]; // All attributes inside the mark tag
                const text = match[2]; // The text content of the mark

                // Extract highlight attributes
                const highlightIdMatch = attributes.match(/data-highlight-id="([^"]*)"/);
                const highlightId = highlightIdMatch ? highlightIdMatch[1] : null;

                const videoFileMatch = attributes.match(/data-video-file="([^"]*)"/);
                const videoFile = videoFileMatch ? videoFileMatch[1] : null;

                const topicMatch = attributes.match(/data-topic="([^"]*)"/);
                const videoKeyMatch = attributes.match(/data-video-key="([^"]*)"/);
                const topic = topicMatch ? topicMatch[1] : null;
                const videoKey = videoKeyMatch ? videoKeyMatch[1] : null;

                console.log(`Extracted highlight: ID=${highlightId}, text=${text}, topic=${topic}, videoKey=${videoKey}, videoFile=${videoFile}`);

                // Store highlight information
                if (highlightId) {
                    const highlightData = {
                        text: text,
                        highlightId: highlightId
                    };

                    // Add videoFile if available
                    if (videoFile) {
                        highlightData.videoFile = videoFile;
                    }

                    // Add topic and videoKey if available (for asset selection)
                    if (topic && videoKey) {
                        highlightData.topic = topic;
                        highlightData.videoKey = videoKey;
                    }

                    slideData.highlights.push(highlightData);
                }
            }
        }

        return slideData;
    });

    // Add processed slides to FormData
    formData.append('slides_data', JSON.stringify(processedSlides));

    // Add only new files from window.videoFiles
    if (window.videoFiles) {
        Object.entries(window.videoFiles).forEach(([highlightId, file]) => {
            formData.append(`file_${highlightId}`, file);
            console.log(`Adding file: ${highlightId} = ${file.name}`);
        });
    }

    // Log the request data to console for debugging
    console.log("Sending slides data:", processedSlides);

    // Add waiting status
    document.getElementById('button-text').textContent = "Processing assets...";

    // Send data to server
    try {
        const response = await fetch('/save-slides-data/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrftoken,
            },
            body: formData
        });

        console.log("Response status:", response.status);

        // Check if the response is a redirect
        if (response.redirected) {
            console.log('Server redirected to:', response.url);
            window.location.href = response.url;
            return;
        }

        const data = await response.json();
        console.log("Response data:", data);

        if (data.success) {
            console.log('Slides data saved successfully');
            // If the server didn't redirect us, manually go to background music page
            // Wait a little longer if asset processing was needed
            if (hasAssetSelections) {
                document.getElementById('button-text').textContent = "Asset processing complete!";
                setTimeout(() => {
                    window.location.href = `/background-music/${videoId}/`;
                }, 1000);
            } else {
                window.location.href = `/background-music/${videoId}/`;
            }
        } else {
            console.error('Error saving slides data:', data.error);
            alert('Error saving slides data: ' + (data.error || 'Unknown error'));
            stopProcessing();
        }
    } catch (error) {
        console.error('Error:', error);
        alert('An error occurred. Please try again.');
        stopProcessing();
    }
}
// async function handleProceedWithValidation(event) {
//     event.preventDefault(); // Prevent default navigation
//     startProcessing();

//     if (!areAllTextareasHidden()) {
//         alert("You Need To Save or Delete The Current Text");
//         stopProcessing();
//         return;
//     }

//     // Check for excessive character counts
//     const exceededLimitSlides = slides.filter(slide =>
//         slide.text && slide.text.length > MAX_SUBTITLE_LENGTH
//     );

//     if (exceededLimitSlides.length > 0) {
//         // Show error messages and exit
//         exceededLimitSlides.forEach(slide => {
//             const errorMessage = document.querySelector(`#error-message_${slide.id}`);
//             if (errorMessage) {
//                 errorMessage.textContent = `Subtitle text cannot exceed ${MAX_SUBTITLE_LENGTH} characters (current: ${slide.text.length})`;
//                 errorMessage.style.display = "block";
//             }
//         });

//         alert(`${exceededLimitSlides.length} subtitle(s) exceed the ${MAX_SUBTITLE_LENGTH} character limit. Please edit them before proceeding.`);
//         stopProcessing();
//         return;
//     }

//     const idsWithoutClips = await fetchNoSubclipIds();
//     if (idsWithoutClips.length > 0) {
//         // Show error messages for unassigned text
//         idsWithoutClips.forEach(id => {
//             const errorMessage = document.querySelector(`#error-message_${id}`);
//             if (errorMessage) {
//                 const slide = slides.find(s => s.id === id);
//                 errorMessage.textContent = !slide.markedText || slide.markedText.trim() === ""
//                     ? "Please Enter Subtitle Text"
//                     : "Assign Clips To All Of The Subtitle Text";
//                 errorMessage.style.display = "block";
//             }
//         });
//         stopProcessing();
//         return;
//     }

//     console.log("Updating backend order with slides:", slides);

//     // Get video ID from the URL
//     const path = window.location.pathname;
//     const videoId = path.split('/')[2];

//     // Get CSRF token from cookie
//     function getCookie(name) {
//         let cookieValue = null;
//         if (document.cookie && document.cookie !== '') {
//             const cookies = document.cookie.split(';');
//             for (let i = 0; i < cookies.length; i++) {
//                 const cookie = cookies[i].trim();
//                 if (cookie.substring(0, name.length + 1) === (name + '=')) {
//                     cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
//                     break;
//                 }
//             }
//         }
//         return cookieValue;
//     }

//     const csrftoken = getCookie('csrftoken');

//     // Create FormData to send all data including files
//     const formData = new FormData();
//     formData.append('video_id', videoId);

//     // Check if we're using assets or uploading new files
//     const hasAssetSelections = slides.some(slide =>
//         slide.markedText && slide.markedText.includes('data-topic=') && slide.markedText.includes('data-video-key=')
//     );

//     const newFiles = window.videoFiles ? Object.keys(window.videoFiles).length : 0;

//     // Add a flag to indicate whether we're processing assets or new files or both
//     formData.append('processing_assets', hasAssetSelections ? 'true' : 'false');
//     formData.append('new_files_only', newFiles > 0 ? 'true' : 'false');

//     // Process slides and extract file data
//     const processedSlides = slides.map(slide => {
//         const slideData = {
//             id: slide.id,
//             text: slide.text,
//             markedText: slide.markedText,
//             sequence: slide.sequence,
//             highlights: []
//         };

//         // Extract highlight information if exists in markedText
//         if (slide.markedText) {
//             // Match all mark elements with their attributes and content
//             const markRegex = /<mark class="handlePopupSubmit"([^>]*)>([^<]+)<\/mark>/g;
//             let match;

//             // Iterate through all matches in the marked text
//             while ((match = markRegex.exec(slide.markedText)) !== null) {
//                 const attributes = match[1]; // All attributes inside the mark tag
//                 const text = match[2]; // The text content of the mark

//                 // Extract highlight attributes
//                 const highlightIdMatch = attributes.match(/data-highlight-id="([^"]*)"/);
//                 const highlightId = highlightIdMatch ? highlightIdMatch[1] : null;

//                 const videoFileMatch = attributes.match(/data-video-file="([^"]*)"/);
//                 const videoFile = videoFileMatch ? videoFileMatch[1] : null;

//                 const topicMatch = attributes.match(/data-topic="([^"]*)"/);
//                 const videoKeyMatch = attributes.match(/data-video-key="([^"]*)"/);
//                 const topic = topicMatch ? topicMatch[1] : null;
//                 const videoKey = videoKeyMatch ? videoKeyMatch[1] : null;

//                 console.log(`Extracted highlight: ID=${highlightId}, text=${text}, topic=${topic}, videoKey=${videoKey}, videoFile=${videoFile}`);

//                 // Store highlight information
//                 if (highlightId) {
//                     const highlightData = {
//                         text: text,
//                         highlightId: highlightId
//                     };

//                     // Add videoFile if available
//                     if (videoFile) {
//                         highlightData.videoFile = videoFile;
//                     }

//                     // Add topic and videoKey if available (for asset selection)
//                     if (topic && videoKey) {
//                         highlightData.topic = topic;
//                         highlightData.videoKey = videoKey;
//                     }

//                     slideData.highlights.push(highlightData);
//                 }
//             }
//         }

//         return slideData;
//     });

//     // Add processed slides to FormData
//     formData.append('slides_data', JSON.stringify(processedSlides));

//     // Add only new files from window.videoFiles
//     if (window.videoFiles) {
//         Object.entries(window.videoFiles).forEach(([highlightId, file]) => {
//             formData.append(`file_${highlightId}`, file);
//             console.log(`Adding file: ${highlightId} = ${file.name}`);
//         });
//     }

//     // Log the request data to console for debugging
//     console.log("Sending slides data:", processedSlides);

//     // Add waiting status
//     document.getElementById('button-text').textContent = "Processing assets...";

//     // Send data to server
//     try {
//         const response = await fetch('/save-slides-data/', {
//             method: 'POST',
//             headers: {
//                 'X-CSRFToken': csrftoken,
//             },
//             body: formData
//         });

//         console.log("Response status:", response.status);

//         // Check if the response is a redirect
//         if (response.redirected) {
//             console.log('Server redirected to:', response.url);
//             window.location.href = response.url;
//             return;
//         }

//         const data = await response.json();
//         console.log("Response data:", data);

//         if (data.success) {
//             console.log('Slides data saved successfully');
//             // If the server didn't redirect us, manually go to background music page
//             // Wait a little longer if asset processing was needed
//             if (hasAssetSelections) {
//                 document.getElementById('button-text').textContent = "Asset processing complete!";
//                 setTimeout(() => {
//                     window.location.href = `/background-music/${videoId}/`;
//                 }, 1000);
//             } else {
//                 window.location.href = `/background-music/${videoId}/`;
//             }
//         } else {
//             console.error('Error saving slides data:', data.error);
//             alert('Error saving slides data: ' + (data.error || 'Unknown error'));
//             stopProcessing();
//         }
//     } catch (error) {
//         console.error('Error:', error);
//         alert('An error occurred. Please try again.');
//         stopProcessing();
//     }
// }


function validateSubtitleLength(text) {
    return text.length <= MAX_SUBTITLE_LENGTH;
}

function handlePopupFileChange(e) {
    console.log("File change event triggered");
    const fileInput = document.getElementById('slide_file');
    
    if (fileInput && fileInput.files && fileInput.files.length > 0) {
        popupFile = fileInput.files[0];
        const fileName = popupFile.name;
        const fileSizeMB = popupFile.size / (1024 * 1024); // convert bytes to MB

        // 500 MB size limit
        if (fileSizeMB > 500) {
            alert("File size exceeds 500MB. Please choose a smaller file.");
            fileInput.value = ''; // Reset the file input
            popupFile = null;

            // Reset UI
            const uploadText = document.getElementById("upload-text");
            if (uploadText) {
                uploadText.textContent = "Choose or Drag File";
            }

            const clearFileBtn = document.getElementById("clear-file");
            if (clearFileBtn) {
                clearFileBtn.style.display = "none";
            }

            const submitButton = document.getElementById("submit-clip");
            if (submitButton) {
                submitButton.disabled = true;
            }

            return;
        }

        console.log("File selected:", fileName);
        
        // Clear dropdown selections when file is chosen
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
        
        // Update upload text UI
        const uploadText = document.getElementById("upload-text");
        if (uploadText) {
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
    } else {
        console.log("No file selected or file input not found");
        popupFile = null;
        
        // Reset UI
        const uploadText = document.getElementById("upload-text");
        if (uploadText) {
            uploadText.textContent = "Choose or Drag File";
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
    }
}


function clearPopupFile() {
    popupFile = null;
    popupErrorMessage = "";
    document.getElementById("upload-text").textContent = "Choose or Drag File";
    document.getElementById("clear-file").style.display = "none";
    const submitButton = document.getElementById("submit-clip");
    submitButton.disabled = !popupVideoClip;
    renderPopup();
}

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
            uploadText.textContent = "Choose or Drag File";
        }

        const clearFileBtn = document.getElementById("clear-file");
        if (clearFileBtn) {
            clearFileBtn.style.display = "none";
        }
    }

    // Rebuild video select dropdown with only the selected folder's videos
    const videoSelect = document.getElementById('videoSelect');
    if (!videoSelect) return;

    // Clear all options except the default one
    videoSelect.innerHTML = '<option value="" disabled selected>Select A Video Clip</option>';

    if (selectedTopic && window.assetFolders && window.assetFolders[selectedTopic]) {
        const videos = window.assetFolders[selectedTopic];

        if (videos.length > 0) {
            // Create optgroup for the selected folder only
            const optgroup = document.createElement('optgroup');
            optgroup.label = selectedTopic;
            optgroup.setAttribute('data-folder', selectedTopic);

            // Add options for each video
            videos.forEach(video => {
                const option = document.createElement('option');
                option.value = video.key;
                option.textContent = video.filename;
                option.setAttribute('data-url', video.url);
                optgroup.appendChild(option);
            });

            videoSelect.appendChild(optgroup);
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
function handleVideoClipChange(e) {
    popupVideoClip = e.target.value;
    popupFile = null;
    popupErrorMessage = "";
    document.getElementById("upload-text").textContent = "Choose or Drag File";
    document.getElementById("clear-file").style.display = "none";
    const submitButton = document.getElementById("submit-clip");
    submitButton.disabled = !popupVideoClip;
    renderPopup();
}

// function handlePopupSubmit(e) {
//     e.preventDefault();
//     console.log("Submitting popup form...");
//     console.log("FROM JS ")

//     // Check if file is selected
//     const fileInput = document.getElementById('slide_file');
//     const hasFile = fileInput && fileInput.files && fileInput.files.length > 0;

//     console.log("File input exists:", !!fileInput);
//     console.log("Files array exists:", !!(fileInput && fileInput.files));
//     console.log("Files length:", fileInput && fileInput.files ? fileInput.files.length : 0);
//     console.log("Has file:", hasFile);
//     console.log("popupFile:", popupFile);

//     // Check if asset is selected
//     const selectedTopic = document.getElementById('selected_topic')?.value;
//     const selectedVideo = document.getElementById('videoSelect')?.value;
//     const hasVideoSelection = selectedTopic && selectedVideo;

//     console.log("Selected topic:", selectedTopic);
//     console.log("Selected video:", selectedVideo);
//     console.log("Has video selection:", hasVideoSelection);

//     // Validate that we have either a file or an asset selected
//     if (!hasFile && !hasVideoSelection) {
//         popupErrorMessage = "Please select a video file or choose a video from your assets.";
//         console.log("Validation error:", popupErrorMessage);
//         renderPopup();
//         return;
//     }

//     // Get CSRF token from cookie
//     function getCookie(name) {
//         let cookieValue = null;
//         if (document.cookie && document.cookie !== '') {
//             const cookies = document.cookie.split(';');
//             for (let i = 0; i < cookies.length; i++) {
//                 const cookie = cookies[i].trim();
//                 if (cookie.substring(0, name.length + 1) === (name + '=')) {
//                     cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
//                     break;
//                 }
//             }
//         }
//         return cookieValue;
//     }

//     const csrftoken = getCookie('csrftoken');
//     console.log("CSRF Token obtained:", !!csrftoken);

//     // Process file upload
//     if (hasFile) {
//         console.log("Processing file upload");
//         // Get the file from the input element directly to ensure we have the latest
//         const file = fileInput.files[0];
//         console.log("File to upload:", file.name, file.size, file.type);

//         // Create FormData for file upload
//         const formData = new FormData();
//         formData.append('slide_file', file);
//         formData.append('slide_text', selectedText);
//         formData.append('clipId', selectedSlideId);

//         console.log("FormData created with:", {
//             slide_text: selectedText,
//             clipId: selectedSlideId,
//             file_name: file.name
//         });

//         // Send API request - using Promise.catch to ensure we see any errors
//         console.log("Sending API request to /handle-clip-assignment/");
//         fetch('/handle-clip-assignment/', {
//             method: 'POST',
//             headers: {
//                 'X-CSRFToken': csrftoken
//             },
//             body: formData
//         })
//         .then(response => {
//             console.log("API Response received:", response.status, response.statusText);
//             return response.json();
//         })
//         .then(data => {
//             console.log("API Response data:", data);

//             if (data.success) {
//                 console.log("File upload successful:", data);

//                 // Store file in window object for later processing
//                 if (!window.videoFiles) window.videoFiles = {};
//                 const highlightId = `highlight_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
//                 window.videoFiles[highlightId] = file;

//                 // Create a temporary URL for the file
//                 const fileUrl = data.file_url || URL.createObjectURL(file);
//                 console.log("File URL for highlight:", fileUrl);

//                 // Update highlighted text with video file
//                 slides = slides.map(slide => {
//                     if (slide.id === selectedSlideId) {
//                         let newMarkedText = slide.markedText || slide.text || "";

//                         // Check if this text is already highlighted
//                         const isAlreadyHighlighted = newMarkedText.includes(`<mark class="handlePopupSubmit">${selectedText}</mark>`) || 
//                                                    new RegExp(`<mark class="handlePopupSubmit"[^>]*>${escapeRegExp(selectedText)}</mark>`, 'i').test(newMarkedText);

//                         // If it's already highlighted, remove the existing highlight first
//                         if (isAlreadyHighlighted) {
//                             // Remove the existing highlight for this text
//                             const regex = new RegExp(`<mark class="handlePopupSubmit"[^>]*>${escapeRegExp(selectedText)}</mark>`, 'i');
//                             newMarkedText = newMarkedText.replace(regex, selectedText);
//                         }

//                         // Now add the new highlight with video file reference
//                         const regex = new RegExp(`(${escapeRegExp(selectedText)})(?![^<]*>)`, "i");
//                         newMarkedText = newMarkedText.replace(
//                             regex,
//                             `<mark class="handlePopupSubmit" data-highlight-id="${highlightId}" data-video-file="${fileUrl}">${selectedText}</mark>`
//                         );

//                         return {
//                             ...slide,
//                             markedText: newMarkedText,
//                             isEditing: false
//                         };
//                     }
//                     return slide;
//                 });

//                 console.log("Updated slide with file highlight, ID:", highlightId);
//             } else {
//                 console.error("File upload failed:", data.error);
//                 popupErrorMessage = data.error || "Failed to upload the file. Please try again.";
//                 renderPopup();
//                 return;
//             }

//             // Close popup and reset state
//             popupOpen = false;
//             popupFile = null;
//             popupTopic = "";
//             popupVideoClip = "";
//             selectedText = "";
//             selectedSlideId = null;

//             // Update UI
//             renderSlides();
//             closePopup();

//             console.log("Popup submitted successfully");
//         })
//         .catch(error => {
//             console.error("API error:", error);
//             console.error("Error details:", error.message, error.stack);
//             popupErrorMessage = "An error occurred. Please try again.";
//             renderPopup();
//         });
//     } 
//     // Process asset selection
//     else if (hasVideoSelection) {
//         console.log("Processing asset selection");

//         // Get the URL from the selected option's data-url attribute
//         let fileUrl = "";
//         const videoSelectElement = document.getElementById('videoSelect');
//         if (videoSelectElement && videoSelectElement.selectedIndex >= 0) {
//             const selectedOption = videoSelectElement.options[videoSelectElement.selectedIndex];
//             fileUrl = selectedOption.dataset.url;
//             console.log("Selected video URL:", fileUrl);
//         }

//         // Prepare data for the API request
//         const data = {
//             slide_text: selectedText,
//             clipId: selectedSlideId,
//             selected_topic: selectedTopic,
//             selected_video: selectedVideo
//         };

//         console.log("Sending JSON data to API:", data);

//         // Send API request
//         fetch('/handle-clip-assignment/', {
//             method: 'POST',
//             headers: {
//                 'Content-Type': 'application/json',
//                 'X-CSRFToken': csrftoken
//             },
//             body: JSON.stringify(data)
//         })
//         .then(response => {
//             console.log("API Response received:", response.status, response.statusText);
//             return response.json();
//         })
//         .then(data => {
//             console.log("API Response data:", data);

//             if (data.success) {
//                 console.log("Asset selection successful:", data);

//                 // Update highlighted text with asset reference
//                 slides = slides.map(slide => {
//                     if (slide.id === selectedSlideId) {
//                         let newMarkedText = slide.markedText || slide.text || "";

//                         // Check if this text is already highlighted
//                         const isAlreadyHighlighted = newMarkedText.includes(`<mark class="handlePopupSubmit">${selectedText}</mark>`) || 
//                                                    new RegExp(`<mark class="handlePopupSubmit"[^>]*>${escapeRegExp(selectedText)}</mark>`, 'i').test(newMarkedText);

//                         // If it's already highlighted, remove the existing highlight first
//                         if (isAlreadyHighlighted) {
//                             // Remove the existing highlight for this text
//                             const regex = new RegExp(`<mark class="handlePopupSubmit"[^>]*>${escapeRegExp(selectedText)}</mark>`, 'i');
//                             newMarkedText = newMarkedText.replace(regex, selectedText);
//                         }

//                         // Now add the new highlight with asset reference
//                         const regex = new RegExp(`(${escapeRegExp(selectedText)})(?![^<]*>)`, "i");
//                         newMarkedText = newMarkedText.replace(
//                             regex,
//                             `<mark class="handlePopupSubmit" data-topic="${selectedTopic}" data-video-key="${selectedVideo}" data-video-file="${data.file_url}">${selectedText}</mark>`
//                         );

//                         return {
//                             ...slide,
//                             markedText: newMarkedText,
//                             isEditing: false
//                         };
//                     }
//                     return slide;
//                 });

//                 console.log("Updated slide with asset highlight");
//             } else {
//                 console.error("Asset selection failed:", data.error);
//                 popupErrorMessage = data.error || "Failed to assign the asset. Please try again.";
//                 renderPopup();
//                 return;
//             }

//             // Close popup and reset state
//             popupOpen = false;
//             popupFile = null;
//             popupTopic = "";
//             popupVideoClip = "";
//             selectedText = "";
//             selectedSlideId = null;

//             // Update UI
//             renderSlides();
//             closePopup();

//             console.log("Popup submitted successfully");
//         })
//         .catch(error => {
//             console.error("API error:", error);
//             console.error("Error details:", error.message, error.stack);
//             popupErrorMessage = "An error occurred. Please try again.";
//             renderPopup();
//         });
//     }
// }


// Helper function to update the UI with highlighted text
function updateHighlightedText(slideId, text, fileUrl) {
    slides = slides.map(slide => {
        if (slide.id === slideId) {
            let newMarkedText = slide.markedText || slide.text || "";
            if (!newMarkedText.includes(`<mark class="handlePopupSubmit">${text}</mark>`)) {
                const regex = new RegExp(`(${text})(?![^<]*>)`, "i");
                newMarkedText = newMarkedText.replace(
                    regex,
                    `<mark class="handlePopupSubmit" data-video-url="${fileUrl}">${text}</mark>`
                );
            }
            return {
                ...slide,
                markedText: newMarkedText,
                isEditing: false
            };
        }
        return slide;
    });
    activeSlideIds.delete(slideId);
    renderSlides();
}

function closePopup() {
    popupOpen = false;
    popupFile = null;
    popupTopic = "";
    popupVideoClip = "";
    popupErrorMessage = "";
    selectedText = "";
    selectedSlideId = null;
    renderPopup();
}

// Instruction modals
let tutorialModalOpen = false;
let uploadModalOpen = false;

function openModal(modalId) {
    tutorialModalOpen = modalId === "tutorial-video";
    uploadModalOpen = modalId === "upload-video";
    renderModals();
}

function closeModal() {
    tutorialModalOpen = false;
    uploadModalOpen = false;
    renderModals();
}

function toggleContent(header) {
    const contentId = header.textContent.includes("How To Upload Files To The Asset Folde") ? "tutorial-video" : "tips";
    console.log("Toggling content for:", contentId);
    console.log(header.textContent);
    const content = document.getElementById(contentId);
    const span = header.querySelector("span");
    document.querySelectorAll(".section").forEach(section => {
        const h = section.querySelector(".section-header");
        h.style.backgroundColor = "#fff";
        h.style.color = "#6c25be";
    });
    content.classList.toggle("open");
    if (content.classList.contains("open")) {
        span.classList.add("rotate");
        header.style.backgroundColor = "#6c25be";
        header.style.color = "#fff";
        if (contentId === "tutorial-video") {
            content.style.maxHeight = "1100px";
        }
    } else {
        span.classList.remove("rotate");
        if (contentId === "tutorial-video") {
            content.style.maxHeight = "0px";
        }
    }
}


// function renderSlides(send_update = true) {
//     const tbody = document.querySelector('#leadsTable tbody');
//     if (!tbody) return;
//     tbody.innerHTML = '';
//     slides.forEach(slide => {
//         const tr = document.createElement('tr');
//         tr.dataset.id = slide.id;
//         tr.style.height = "5rem";
//         if (send_update === true) {
//             updateClipOnServer(slide.id, slide.text);
//         }

//         const charCount = slide.text ? getCleanTextContent(slide.text).length : 0;
//         const charCountClass = charCount > MAX_SUBTITLE_LENGTH ? 'char-count-exceeded' : 'char-count';

//         tr.innerHTML = `
//             <td class="slide-first" style="font-size: 1.4rem; position: relative;" title="Drag to move">
//                 <div style="display: flex; align-items: center;">
                  
//                     ${slide.subtitle}
//                 </div>
//             </td>
//             <td id="highlightable_${slide.id}">
//                 <div class="highlight-sub">
//                     ${slide.isEditing ? `
//                         <textarea
//                             class="textarea-class"
//                             id="slide_text_${slide.id}"
//                             name="slide_text"
//                             placeholder="Type Your Script Here And Press Enter (Max ${MAX_SUBTITLE_LENGTH} Characters)"
//                             onkeydown="handleKeyPress(event, ${slide.id})"
//                             ${charCount > MAX_SUBTITLE_LENGTH ? 'style="border: 1px solid red;"' : ''}
//                         >${getCleanTextContent(slide.text)}</textarea>
//                         <div class="${charCountClass}">${charCount}/${MAX_SUBTITLE_LENGTH}</div>
//                     ` : `
//                         <span>${slide.markedText || slide.text || ""}</span>
//                     `}
//                     <div id="error-message_${slide.id}" class="error-message" style="display: ${charCount > MAX_SUBTITLE_LENGTH ? 'block' : 'none'};">
//                         ${charCount > MAX_SUBTITLE_LENGTH ? `Subtitle text cannot exceed ${MAX_SUBTITLE_LENGTH} characters (current: ${charCount})` : ''}
//                     </div>
//                 </div>
//             </td>

//             <td class="slide-last ${activeSlideIds.has(slide.id) ? 'active' : ''}">
//                 <a href="#" class="above-del" onclick="handleUndo(${slide.id}); event.preventDefault();">
//                     <img src="/static/images/undo.svg" alt="Undo" style="width: 1.2rem; height: 3rem; cursor: pointer;">
//                 </a>
//             </td>

//         `;
//         tbody.appendChild(tr);

//         if (!slide.isEditing) {
//             const highlightable = document.getElementById(`highlightable_${slide.id}`);
//             highlightable.addEventListener('mouseup', () => handleTextSelection(slide.id));

//             const marks = highlightable.querySelectorAll('mark.handlePopupSubmit');
//             marks.forEach(mark => {
//                 mark.addEventListener('click', () => {
//                     selectedSlideId = slide.id;
//                     selectedText = mark.textContent;
//                     popupOpen = true;
//                     renderPopup();
//                 });
//             });
//         }

//         if (slide.isEditing) {
//             const textarea = document.getElementById(`slide_text_${slide.id}`);

//             // Add keydown event listener to prevent typing at limit
//             textarea.addEventListener('keydown', (e) => {
//                 const maxLength = window.MAX_SUBTITLE_LENGTH || 100;
//                 const currentLength = textarea.value.length;
//                 const selectedText = textarea.value.substring(textarea.selectionStart, textarea.selectionEnd);
//                 const isTextSelected = selectedText.length > 0;

//                 // Allow backspace, delete, arrow keys, home, end, etc.
//                 const allowedKeys = [8, 9, 37, 38, 39, 40, 46, 36, 35, 33, 34];

//                 // Allow Ctrl+A, Ctrl+C, Ctrl+V, Ctrl+X
//                 if (e.ctrlKey && [65, 67, 86, 88].includes(e.keyCode)) {
//                     return;
//                 }

//                 // If we're at the limit and trying to add more characters
//                 if (currentLength >= maxLength && !allowedKeys.includes(e.keyCode) && !isTextSelected) {
//                     e.preventDefault();

//                     // Show error message
//                     const errorMessage = document.getElementById(`error-message_${slide.id}`);
//                     if (errorMessage) {
//                         errorMessage.textContent = `Subtitle text cannot exceed ${maxLength} characters`;
//                         errorMessage.style.display = "block";
//                     }

//                     // Add shake animation to the textarea
//                     textarea.style.animation = 'shake 0.5s ease-in-out';
//                     setTimeout(() => {
//                         textarea.style.animation = '';
//                     }, 500);

//                     return false;
//                 }
//             });

//             // Add paste event listener to handle pasted content
//             textarea.addEventListener('paste', (e) => {
//                 e.preventDefault();

//                 const maxLength = window.MAX_SUBTITLE_LENGTH || 100;
//                 const pastedText = (e.clipboardData || window.clipboardData).getData('text');
//                 const currentText = textarea.value;
//                 const selectionStart = textarea.selectionStart;
//                 const selectionEnd = textarea.selectionEnd;

//                 // Calculate new text after paste
//                 const newText = currentText.substring(0, selectionStart) + pastedText + currentText.substring(selectionEnd);

//                 if (newText.length > maxLength) {
//                     // Calculate how much we can paste
//                     const remainingLength = maxLength - currentText.length + (selectionEnd - selectionStart);
//                     const truncatedPaste = pastedText.substring(0, Math.max(0, remainingLength));

//                     // Insert truncated text
//                     textarea.value = currentText.substring(0, selectionStart) + truncatedPaste + currentText.substring(selectionEnd);

//                     // Update cursor position
//                     const newCursorPos = selectionStart + truncatedPaste.length;
//                     textarea.setSelectionRange(newCursorPos, newCursorPos);

//                     // Show error message
//                     const errorMessage = document.getElementById(`error-message_${slide.id}`);
//                     if (errorMessage) {
//                         errorMessage.textContent = `Subtitle text cannot exceed ${maxLength} characters. Pasted text was truncated.`;
//                         errorMessage.style.display = "block";
//                     }

//                     // Trigger input event to update UI
//                     textarea.dispatchEvent(new Event('input', { bubbles: true }));
//                 } else {
//                     // Allow normal paste
//                     textarea.value = newText;
//                     const newCursorPos = selectionStart + pastedText.length;
//                     textarea.setSelectionRange(newCursorPos, newCursorPos);
//                     textarea.dispatchEvent(new Event('input', { bubbles: true }));
//                 }
//             });

//             // Original input event listener with modification to hard-limit length
//             textarea.addEventListener('input', (e) => {
//                 const newText = e.target.value;
//                 const maxLength = window.MAX_SUBTITLE_LENGTH || 100;

//                 // Hard limit - truncate if somehow exceeds
//                 if (newText.length > maxLength) {
//                     e.target.value = newText.substring(0, maxLength);
//                     return;
//                 }

//                 slides = slides.map(s =>
//                     s.id === slide.id ? { ...s, text: newText, markedText: newText } : s
//                 );

//                 // Update character count
//                 const charCount = e.target.value.length;
//                 const charCountElement = e.target.parentElement.querySelector(`.char-count, .char-count-exceeded`);
//                 if (charCountElement) {
//                     charCountElement.textContent = `${charCount}/${maxLength}`;
//                     charCountElement.className = charCount >= maxLength ? 'char-count-exceeded' : 'char-count';
//                 }

//                 // Show/hide error message
//                 const errorMessage = document.getElementById(`error-message_${slide.id}`);
//                 if (errorMessage) {
//                     if (charCount >= maxLength) {
//                         errorMessage.textContent = `Subtitle text cannot exceed ${maxLength} characters`;
//                         errorMessage.style.display = 'block';
//                         textarea.style.border = '1px solid red';
//                     } else {
//                         errorMessage.style.display = 'none';
//                         textarea.style.border = '';
//                     }
//                 }
//             });
//         }
//     });

//     document.getElementById('no_of_slides').value = slideCount;
//     renderButton();

//     // Reinitialize drag functionality after rendering
//     if (window.$ && $('#leadsTable tbody').length) {
//         // initializeDragAndMove();
//     }
//     updateProceedButtonState();

// }


function renderButton() {
    const btn = document.querySelector('.button-container-btn');
    if (btn) {
        btn.className = `button-container-btn ${isProcessing ? 'processing' : ''}`;
        btn.disabled = isProcessing;
        btn.querySelector('#button-text').textContent =
            isProcessing ? `Processing${'.'.repeat(dotCount)}` : "Proceed To Background Music Selection";
        btn.querySelector('#proceed-svg').style.display = isProcessing ? 'none' : 'inline-block';
    }
}

// function renderPopup() {
//     let popup = document.querySelector('.popup-modal');
//     if (!popup) {
//         popup = document.createElement('div');
//         popup.className = 'popup-modal';
//         document.body.appendChild(popup);
//     }
//     popup.style.display = popupOpen ? 'flex' : 'none';
//     if (popupOpen) {
//         popup.innerHTML = `
//             <div class="popup-container">
//                 <div class="close-btnx close-btn">
//                     <button class="close-popup" onclick="closePopup()">X</button>
//                 </div>
//                 <div id="modal-cont">
//                     <form class="popup-content" style="grid-template-columns: 0.7fr 1fr; width: 100%;" onsubmit="handlePopupSubmit(event)">
//                         <br>
//                         <input type="hidden" name="csrfmiddlewaretoken" value="">
//                         <div id="submit-cont">
//                         <div class="form-group" style=" padding-left: 0px; padding-right: 0px;">
//                         <h4 style="margin-bottom: 15px; margin-top: 0px; color: rgb(51, 51, 51);">Selected Text:</h4>
//                         <div style="margin-bottom: 15px; padding: 7px; background: rgb(240, 240, 240); border-radius: 6px; border: 1px solid rgb(224, 224, 224); font-size: 18px; color: rgb(25, 25, 25);">${selectedText}</div></div>
//                             <div class="form-group">
//                                 <input id="slide_text" hidden name="slide_text" value="${selectedText}" readonly class="form-input">
//                             </div>
//                             <input id="clipId" type="number" hidden name="clipId" value="2298" readonly>
//                             <input type="text" hidden id="remaining" name="remaining" value="starting with a tingling sensation in my back." readonly>
//                             <div style="display: grid; grid-template-columns: 0.7fr 1fr; border-radius: 8px; border: 1px solid #00000080; overflow: hidden;" class="form-grid-cont">
//                                 <div class="grid-item title form-grid-item begin column-1">
//                                     <span style="height: 50px; align-items: center;">Upload Scene</span>
//                                 </div>
//                                 <div class="grid-item title form-grid-item end column-2">
//                                     <span style="height: 50px; align-items: center; margin-left: -18px;">Upload Scene From Assets Folder</span>
//                                 </div>
//                                 <div class="form-grid-item main-item">
//                                     <div class="form-group" style="height: 100%;">
//                                         <div class="upload-container">
//                                             <label for="slide_file" class="upload-label">
//                                                 <img src="/images/upload.svg" alt="" class="uploadSvg">
//                                                 <span id="upload-text">${popupFile ? popupFile.name.slice(0, 7) + (popupFile.name.includes('.') ? popupFile.name.slice(popupFile.name.lastIndexOf('.')) : '') : 'Choose File'}</span>
//                                             </label>
//                                             <i id="clear-file" style="display: ${popupFile ? 'inline' : 'none'};" onclick="clearPopupFile()" class="ri-close-circle-line"></i>
//                                             <input type="file" id="slide_file" name="slide_file" class="upload-input" accept="video/*" onchange="handlePopupFileChange(event)">
//                                         </div>
//                                     </div>
//                                 </div>
//                                 <div style="border-left: 0.8px solid #864AF9;" class="form-grid-item">
//                                     <div class="form-group">
//                                         <select id="selected_topic" name="selected_topic" class="form-select" onchange="handleTopicChange(event)">
//                                             <option value="" ${!popupTopic ? 'selected' : ''}>Select Topic</option>
//                                             <option value="17" ${popupTopic === "17" ? 'selected' : ''}>Male Thinking Clips</option>
//                                             <option value="18" ${popupTopic === "18" ? 'selected' : ''}>Male Crying Clips</option>
//                                             <option value="19" ${popupTopic === "19" ? 'selected' : ''}>Male Desperation Clips</option>
//                                         </select>
//                                     </div>
//                                     <div class="form-group">
//                                         <select id="videoSelect" name="selected_video" class="form-select" onchange="handleVideoClipChange(event)">
//                                             <option value="" disabled ${!popupVideoClip ? 'selected' : ''}>Select A Video Clip</option>
//                                             ${popupTopic ? `
//                                                 <option value="clip1" ${popupVideoClip === "clip1" ? 'selected' : ''}>Clip 1</option>
//                                                 <option value="clip2" ${popupVideoClip === "clip2" ? 'selected' : ''}>Clip 2</option>
//                                             ` : ''}
//                                         </select>
//                                         <p style="color: red; font-size: 13px; margin-top: 5px;" id="error-slide">${popupErrorMessage}</p>
//                                     </div>
//                                     <input type="number" hidden id="is_tiktok" name="is_tiktok" value="0" readonly>
//                                 </div>
//                             </div>
//                         </div>
//                         <div style="align-items: end;" class="form-group ai-form">
//                         <a href="https://chatgpt.com/" target="_blank" id="ai-clip" >Click For AI Scene Suggestions</a>
//                             <button type="submit" id="submit-clip" class="submit-btn" ${popupFile || (popupTopic && popupVideoClip) ? '' : 'disabled'}>
//                                 Submit
//                             </button>
//                         </div>
//                     </form>
//                 </div>
//             </div>
//         `;
//     }
// }

function renderModals() {
    let tutorialModal = document.getElementById('tutorial-modal');
    let uploadModal = document.getElementById('upload-modal');
    if (!tutorialModal) {
        tutorialModal = document.createElement('div');
        tutorialModal.id = 'tutorial-modal';
        tutorialModal.className = 'modal';
        document.body.appendChild(tutorialModal);
    }
    if (!uploadModal) {
        uploadModal = document.createElement('div');
        uploadModal.id = 'upload-modal';
        uploadModal.className = 'modal';
        document.body.appendChild(uploadModal);
    }
    tutorialModal.style.display = tutorialModalOpen ? 'block' : 'none';
    uploadModal.style.display = uploadModalOpen ? 'block' : 'none';
    if (tutorialModalOpen || uploadModalOpen) {
        const modal = tutorialModalOpen ? tutorialModal : uploadModal;
        modal.innerHTML = `
            <div class="modal-content">
                <span class="close" onclick="closeModal()">×</span>
                <iframe src="/public/videos/youtube/youtube1.mp4" frameborder="0" allow="accelerometer; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
            </div>
        `;
    }
}




// // Modified handleFolderUpload function to process each subfolder individually
// async function handleFolderUpload() {
//     // Check if user is on a free plan and show overlay if needed
//     if (typeof isFreePlan !== 'undefined' && isFreePlan) {
//         document.getElementById('freeUserOverlay').style.display = 'flex';
//         return;
//     }

//     if (!folderFiles || folderFiles.length === 0) {
//         alert('Please choose a folder to upload');
//         return;
//     }

//     // Change button text to "Uploading..."
//     const uploadButton = document.getElementById('videoUploadButton');
//     if (uploadButton) {
//         uploadButton.textContent = "Uploading...";
//         uploadButton.disabled = true;
//     }

//     // Show the upload form that was hidden but hide the percentage display initially
//     const uploadForm = document.getElementById('uploadForm');
//     if (uploadForm) {
//         uploadForm.style.display = 'block';
//     }

//     // Get CSRF token from cookie
//     function getCookie(name) {
//         let cookieValue = null;
//         if (document.cookie && document.cookie !== '') {
//             const cookies = document.cookie.split(';');
//             for (let i = 0; i < cookies.length; i++) {
//                 const cookie = cookies[i].trim();
//                 if (cookie.substring(0, name.length + 1) === (name + '=')) {
//                     cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
//                     break;
//                 }
//             }
//         }
//         return cookieValue;
//     }

//     const csrftoken = getCookie('csrftoken');

//     // Get the root folder name
//     const rootFolder = folderFiles[0].webkitRelativePath.split('/')[0];

//     // Organize files by subfolder
//     const subfolders = {};
//     for (const file of folderFiles) {
//         const pathParts = file.webkitRelativePath.split('/');

//         // Skip files directly in the root folder (we want only subfolders)
//         if (pathParts.length <= 2) continue;

//         const subfolder = pathParts[1];
//         if (!subfolders[subfolder]) {
//             subfolders[subfolder] = [];
//         }
//         subfolders[subfolder].push(file);
//     }

//     // If no subfolders found, fall back to zipping the whole folder
//     if (Object.keys(subfolders).length === 0) {
//         console.log("No subfolders found, zipping entire folder");
//         const zipFile = await createZipFromFolder(folderFiles);
//         if (!zipFile) {
//             // Reset button on error
//             if (uploadButton) {
//                 uploadButton.textContent = "Upload and Process";
//                 uploadButton.disabled = false;
//             }
//             return;
//         }

//         await uploadZipFile(zipFile, rootFolder, csrftoken, uploadForm, uploadButton);
//         return;
//     }

//     // Display status
//     document.getElementById('uploadStatus').textContent = `Found ${Object.keys(subfolders).length} subfolders to process`;
//     document.getElementById('uploadStatus').style.display = 'block';

//     // Initialize progress tracking
//     const totalSubfolders = Object.keys(subfolders).length;
//     let completedSubfolders = 0;
//     let successCount = 0;

//     // Process each subfolder in parallel
//     const uploadPromises = Object.entries(subfolders).map(async ([subfolderName, files], index) => {
//         try {
//             // Update status
//             document.getElementById('uploadStatus').textContent = `Processing subfolder: ${subfolderName} (${index + 1}/${totalSubfolders})`;

//             // Create ZIP for this subfolder
//             const zipFile = await createZipFromSubfolder(files, subfolderName);
//             if (!zipFile) {
//                 throw new Error(`Failed to create ZIP for subfolder: ${subfolderName}`);
//             }

//             // Upload the ZIP file
//             const result = await uploadZipFile(zipFile, subfolderName, csrftoken, uploadForm, null, false);

//             // Update progress
//             completedSubfolders++;
//             if (result.success) {
//                 successCount++;
//             }

//             // Update progress bar
//             const progressPercent = Math.round((completedSubfolders / totalSubfolders) * 100);
//             document.getElementById('progressBar').style.width = `${progressPercent}%`;
//             document.getElementById('progressPercent').textContent = `${progressPercent}%`;
//             document.getElementById('uploadStatus').textContent = 
//                 `Processed ${completedSubfolders}/${totalSubfolders} subfolders (${successCount} successful)`;

//             return result;
//         } catch (error) {
//             console.error(`Error processing subfolder ${subfolderName}:`, error);
//             completedSubfolders++;
//             // Update progress bar even on error
//             const progressPercent = Math.round((completedSubfolders / totalSubfolders) * 100);
//             document.getElementById('progressBar').style.width = `${progressPercent}%`;
//             document.getElementById('progressPercent').textContent = `${progressPercent}%`;
//             return { success: false, error: error.message };
//         }
//     });

//     // Wait for all uploads to complete
//     const results = await Promise.all(uploadPromises);

//     // Process results
//     const allSuccessful = results.every(result => result.success);

//     if (allSuccessful) {
//         document.getElementById('uploadStatus').textContent = 'All subfolders uploaded successfully!';
//         document.getElementById('progressBar').style.width = '100%';
//         document.getElementById('progressPercent').textContent = '100%';

//         // Reload page or redirect after a brief delay
//         setTimeout(() => {
//             window.location.reload();
//         }, 2000);
//     } else {
//         // Some uploads failed
//         const successCount = results.filter(result => result.success).length;
//         document.getElementById('uploadStatus').textContent = 
//             `Completed with ${successCount}/${totalSubfolders} subfolders uploaded successfully. Please check failed folders.`;

//         // Reset button to allow retry
//         if (uploadButton) {
//             uploadButton.textContent = "Upload and Process";
//             uploadButton.disabled = false;
//         }
//     }
// }

// Modified handleFolderUpload function to process each subfolder individually
async function handleFolderUpload() {

    // Add this code after the first few checks in handleFolderUpload
    // Double-check the folder size before proceeding
    let totalSize = 0;
    for (const file of folderFiles) {
        totalSize += file.size;
    }

    if (totalSize > MAX_UPLOAD_SIZE) {
        alert(`Folder size (${formatFileSize(totalSize)}) exceeds the 10 GB limit. Please select a smaller folder.`);
        return;
    }

    // Continue with the rest of the function...
    // Check if user is on a free plan and show overlay if needed
    if (typeof isFreePlan !== 'undefined' && isFreePlan) {
        document.getElementById('freeUserOverlay').style.display = 'flex';
        return;
    }

    if (!folderFiles || folderFiles.length === 0) {
        alert('Please choose a folder to upload');
        return;
    }

    // Filter to get only video files
    const allVideoFiles = Array.from(folderFiles).filter(file => isVideoFile(file));

    if (allVideoFiles.length === 0) {
        alert('No video files found in the selected folder');
        return;
    }

    console.log(`Found ${allVideoFiles.length} video files out of ${folderFiles.length} total files`);

    // Change button text to "Uploading..."
    const uploadButton = document.getElementById('videoUploadButton');
    if (uploadButton) {
        uploadButton.textContent = "Uploading...";
        uploadButton.disabled = true;
    }

    // Show the upload form that was hidden but hide the percentage display initially
    const uploadForm = document.getElementById('uploadForm');
    if (uploadForm) {
        uploadForm.style.display = 'block';
    }

    // Initialize progress display
    document.getElementById('progressBar').style.width = '0%';
    document.getElementById('progressPercent').textContent = '0%';
    document.getElementById('progressPercent').style.display = 'block';
    document.getElementById('uploadStatus').style.display = 'block';
    document.getElementById('uploadStatus').textContent = 'Analyzing video files...';

    // Get CSRF token from cookie
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    const csrftoken = getCookie('csrftoken');

    // Get the root folder name from video files only
    const rootFolder = allVideoFiles[0].webkitRelativePath.split('/')[0];
    console.log("Root folder:", rootFolder);

    // Organize video files by subfolder
    const subfolders = {};
    for (const file of allVideoFiles) {
        const pathParts = file.webkitRelativePath.split('/');

        // Skip files directly in the root folder (we want only subfolders)
        if (pathParts.length <= 2) continue;

        const subfolder = pathParts[1];
        if (!subfolders[subfolder]) {
            subfolders[subfolder] = [];
        }
        subfolders[subfolder].push(file);
    }

    console.log("Subfolders with video files:", Object.keys(subfolders));

    // If no subfolders found, fall back to zipping the whole folder with video files only
    if (Object.keys(subfolders).length === 0) {
        console.log("No subfolders found, zipping entire folder with video files only");
        document.getElementById('uploadStatus').textContent = 'No subfolders found, processing video files...';

        // Use allVideoFiles instead of folderFiles
        const zipFile = await createZipFromFolder(allVideoFiles);
        if (!zipFile) {
            // Reset button on error
            if (uploadButton) {
                uploadButton.textContent = "Upload and Process";
                uploadButton.disabled = false;
            }
            document.getElementById('uploadStatus').textContent = 'Failed to create ZIP file';
            return;
        }

        await uploadZipFile(zipFile, rootFolder, csrftoken, uploadForm, uploadButton);
        return;
    }

    // Display status
    document.getElementById('uploadStatus').textContent = `Found ${Object.keys(subfolders).length} subfolders with video files to process`;

    // Initialize progress tracking
    const totalSubfolders = Object.keys(subfolders).length;
    let completedSubfolders = 0;
    let successCount = 0;

    try {
        // Process each subfolder in sequence (not parallel to avoid overwhelming the server)
        for (const [subfolderName, videoFiles] of Object.entries(subfolders)) {
            try {
                // Skip empty subfolders (this shouldn't happen since we're already filtering)
                if (videoFiles.length === 0) {
                    console.log(`Skipping empty subfolder: ${subfolderName}`);
                    completedSubfolders++;
                    continue;
                }

                // Update status
                const folderIndex = completedSubfolders + 1;
                document.getElementById('uploadStatus').textContent =
                    `Processing subfolder: ${subfolderName} (${folderIndex}/${totalSubfolders}) - ${videoFiles.length} video files`;

                console.log(`Creating ZIP for subfolder: ${subfolderName} with ${videoFiles.length} video files`);

                // Create ZIP for this subfolder - pass only video files
                const zipFile = await createZipFromSubfolder(videoFiles, subfolderName);
                if (!zipFile) {
                    throw new Error(`Failed to create ZIP for subfolder: ${subfolderName}`);
                }

                console.log(`Uploading ZIP for subfolder: ${subfolderName}`);

                // Upload the ZIP file
                const result = await uploadZipFile(zipFile, subfolderName, csrftoken, uploadForm, null, false);

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
                document.getElementById('progressBar').style.width = `${progressPercent}%`;
                document.getElementById('progressPercent').textContent = `${progressPercent}%`;
                document.getElementById('uploadStatus').textContent =
                    `Processed ${completedSubfolders}/${totalSubfolders} subfolders (${successCount} successful)`;

            } catch (error) {
                console.error(`Error processing subfolder ${subfolderName}:`, error);
                completedSubfolders++;

                // Update progress bar even on error
                const progressPercent = Math.round((completedSubfolders / totalSubfolders) * 100);
                document.getElementById('progressBar').style.width = `${progressPercent}%`;
                document.getElementById('progressPercent').textContent = `${progressPercent}%`;
                document.getElementById('uploadStatus').textContent =
                    `Error on subfolder ${subfolderName}: ${error.message}`;
            }
        }

        // Process results
        if (successCount === totalSubfolders) {
            document.getElementById('uploadStatus').textContent = 'All video files uploaded successfully!';
            document.getElementById('progressBar').style.width = '100%';
            document.getElementById('progressPercent').textContent = '100%';

            // Reload page after a brief delay
            setTimeout(() => {
                window.location.reload();
            }, 2000);
        } else if (successCount > 0) {
            // Some uploads successful
            document.getElementById('uploadStatus').textContent =
                `Completed with ${successCount}/${totalSubfolders} subfolders uploaded successfully.`;

            // Reload page after a brief delay
            setTimeout(() => {
                window.location.reload();
            }, 3000);
        } else {
            // All uploads failed
            document.getElementById('uploadStatus').textContent =
                `Failed to upload any subfolders. Please try again.`;

            // Reset button to allow retry
            if (uploadButton) {
                uploadButton.textContent = "Upload and Process";
                uploadButton.disabled = false;
            }
        }
    } catch (error) {
        console.error("Error in folder upload process:", error);
        document.getElementById('uploadStatus').textContent = `Error: ${error.message}`;

        // Reset button
        if (uploadButton) {
            uploadButton.textContent = "Upload and Process";
            uploadButton.disabled = false;
        }
    }
}

async function createZipFromSubfolder(files, subfolderName) {
    // Define video extensions to accept
    const videoExtensions = ['.mp4', '.webm', '.ogg', '.mov', '.avi', '.wmv', '.flv', '.mkv', '.m4v', '.mpg', '.mpeg', '.3gp', '.3g2'];

    console.log(`\n🗂️ Processing subfolder: ${subfolderName}`);
    console.log(`Files passed to function: ${files.length}`);

    // Since files passed are already filtered, we should only have video files
    // but let's double-check and log what we find
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
        console.warn(`⚠️ Found ${unexpectedFiles.length} unexpected non-video files in pre-filtered list`);
    }

    if (videoFiles.length === 0) {
        console.log(`❌ No video files in subfolder: ${subfolderName}`);
        return null;
    }

    const progressText = `Creating ZIP for subfolder: ${subfolderName}`;
    document.getElementById('uploadStatus').textContent = `${progressText} (${videoFiles.length} video files)`;

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
            document.getElementById('uploadStatus').textContent =
                `${progressText} - Adding video file ${processedCount} of ${totalFiles}`;
        }

        // Generate the ZIP file
        document.getElementById('uploadStatus').textContent = `${progressText} - Compressing video files...`;
        const content = await zip.generateAsync({
            type: "blob",
            compression: "DEFLATE",
            compressionOptions: { level: 6 }
        }, (metadata) => {
            document.getElementById('uploadStatus').textContent =
                `${progressText} - Compressing: ${metadata.percent.toFixed(1)}%`;
        });

        // Create a File object from the Blob
        const zipFile = new File([content], `${subfolderName}.zip`, { type: "application/zip" });

        document.getElementById('uploadStatus').textContent = `${progressText} - ZIP file ready for upload`;
        console.log(`✅ Subfolder ZIP created successfully with ${videoFiles.length} video files`);
        return zipFile;
    } catch (error) {
        console.error(`❌ Error creating ZIP for subfolder ${subfolderName}:`, error);
        document.getElementById('uploadStatus').textContent =
            `Error creating ZIP for subfolder ${subfolderName}: ${error.message}`;
        return null;
    }
}
// Function to upload a single ZIP file to the server
// function uploadZipFile(zipFile, folderName, csrftoken, uploadForm, uploadButton, shouldReload = true) {
//     return new Promise((resolve, reject) => {
//         // Prepare directories info - simplified for single folder
//         const directories = {};
//         directories[folderName] = []; // Just use the folder name as the key

//         // Create a FormData object for this upload
//         const formData = new FormData();

//         // Add the ZIP file
//         formData.append('zip_file', zipFile);

//         // Add the folder name
//         formData.append('main_folder_name', folderName);

//         // Add directories info
//         formData.append('directories', JSON.stringify(directories));

//         // Create an XHR request
//         const xhr = new XMLHttpRequest();

//         xhr.upload.addEventListener('progress', (event) => {
//             if (event.lengthComputable) {
//                 const percentComplete = Math.round((event.loaded / event.total) * 100);
//                 document.getElementById('uploadStatus').textContent = 
//                     `Uploading ${folderName}: ${percentComplete}%`;
//             }
//         });

//         xhr.addEventListener('load', function() {
//             if (xhr.status === 200) {
//                 try {
//                     const response = JSON.parse(xhr.responseText);
//                     if (response.success) {
//                         // Success
//                         document.getElementById('uploadStatus').textContent = 
//                             `Uploaded ${folderName} successfully!`;

//                         // Reload page or redirect if requested
//                         if (shouldReload) {
//                             if (response.redirect_url) {
//                                 window.location.href = response.redirect_url;
//                             } else {
//                                 window.location.reload();
//                             }
//                         }

//                         resolve({ success: true, response });
//                     } else {
//                         // Server error
//                         document.getElementById('uploadStatus').textContent = 
//                             `Upload failed for ${folderName}: ${response.error || 'Unknown error'}`;

//                         // Reset button on error if provided
//                         if (uploadButton && shouldReload) {
//                             uploadButton.textContent = "Upload and Process";
//                             uploadButton.disabled = false;
//                         }

//                         resolve({ success: false, error: response.error || 'Unknown error' });
//                     }
//                 } catch (e) {
//                     // JSON parse error
//                     document.getElementById('uploadStatus').textContent = 
//                         `Error processing response for ${folderName}`;

//                     // Reset button on error if provided
//                     if (uploadButton && shouldReload) {
//                         uploadButton.textContent = "Upload and Process";
//                         uploadButton.disabled = false;
//                     }

//                     resolve({ success: false, error: 'Error processing response' });
//                 }
//             } else {
//                 // HTTP error
//                 document.getElementById('uploadStatus').textContent = 
//                     `Upload failed for ${folderName}: Server returned ${xhr.status}`;

//                 // Reset button on error if provided
//                 if (uploadButton && shouldReload) {
//                     uploadButton.textContent = "Upload and Process";
//                     uploadButton.disabled = false;
//                 }

//                 resolve({ success: false, error: `Server returned ${xhr.status}` });
//             }
//         });

//         xhr.addEventListener('error', function() {
//             // Network error
//             document.getElementById('uploadStatus').textContent = 
//                 `Upload failed for ${folderName}: Network error`;

//             // Reset button on error if provided
//             if (uploadButton && shouldReload) {
//                 uploadButton.textContent = "Upload and Process";
//                 uploadButton.disabled = false;
//             }

//             resolve({ success: false, error: 'Network error' });
//         });

//         xhr.addEventListener('abort', function() {
//             // Upload aborted
//             document.getElementById('uploadStatus').textContent = 
//                 `Upload aborted for ${folderName}`;

//             // Reset button on error if provided
//             if (uploadButton && shouldReload) {
//                 uploadButton.textContent = "Upload and Process";
//                 uploadButton.disabled = false;
//             }

//             resolve({ success: false, error: 'Upload aborted' });
//         });

//         // Send the request
//         xhr.open('POST', uploadForm.action);
//         xhr.setRequestHeader('X-CSRFToken', csrftoken);
//         xhr.send(formData);
//     });
// }

// Function to upload a single ZIP file to the server
function uploadZipFile(zipFile, folderName, csrftoken, uploadForm, uploadButton, shouldReload = true) {
    return new Promise((resolve, reject) => {
        // Prepare directories info - simplified for single folder
        const directories = {};
        directories[folderName] = []; // Just use the folder name as the key

        // Create a FormData object for this upload
        const formData = new FormData();

        // Add the ZIP file
        formData.append('zip_file', zipFile);

        // Add the folder name
        formData.append('main_folder_name', folderName);

        // Add directories info
        formData.append('directories', JSON.stringify(directories));

        // Create an XHR request
        const xhr = new XMLHttpRequest();

        xhr.upload.addEventListener('progress', (event) => {
            if (event.lengthComputable) {
                const percentComplete = Math.round((event.loaded / event.total) * 100);
                document.getElementById('uploadStatus').textContent =
                    `Uploading ${folderName}: ${percentComplete}%`;
            }
        });

        xhr.addEventListener('load', function () {
            if (xhr.status === 200) {
                try {
                    // Some APIs may return empty response with 200 status - treat this as success
                    if (!xhr.responseText || xhr.responseText.trim() === '') {
                        document.getElementById('uploadStatus').textContent =
                            `Uploaded ${folderName} successfully!`;

                        // Handle reload if needed
                        if (shouldReload) {
                            setTimeout(() => {
                                window.location.reload();
                            }, 1000);
                        }

                        resolve({ success: true });
                        return;
                    }

                    // Try to parse JSON response
                    const response = JSON.parse(xhr.responseText);

                    // Consider 200 status as success even if response doesn't have a success field
                    if (response.success === undefined || response.success) {
                        document.getElementById('uploadStatus').textContent =
                            `Uploaded ${folderName} successfully!`;

                        // Reload page or redirect if requested
                        if (shouldReload) {
                            if (response.redirect_url) {
                                window.location.href = response.redirect_url;
                            } else {
                                setTimeout(() => {
                                    window.location.reload();
                                }, 1000);
                            }
                        }

                        resolve({ success: true, response });
                    } else {
                        // Server explicitly returned success: false
                        document.getElementById('uploadStatus').textContent =
                            `Upload failed for ${folderName}: ${response.error || 'Unknown error'}`;

                        // Reset button on error if provided
                        if (uploadButton && shouldReload) {
                            uploadButton.textContent = "Upload and Process";
                            uploadButton.disabled = false;
                        }

                        resolve({ success: false, error: response.error || 'Unknown error' });
                    }
                } catch (e) {
                    // If JSON parsing fails but status is 200, still treat as success
                    console.log(`JSON parsing error for ${folderName}, but status is 200. Treating as success.`);
                    document.getElementById('uploadStatus').textContent =
                        `Uploaded ${folderName} successfully!`;

                    if (shouldReload) {
                        setTimeout(() => {
                            window.location.reload();
                        }, 1000);
                    }

                    resolve({ success: true });
                }
            } else {
                // HTTP error
                document.getElementById('uploadStatus').textContent =
                    `Upload failed for ${folderName}: Server returned ${xhr.status}`;

                // Reset button on error if provided
                if (uploadButton && shouldReload) {
                    uploadButton.textContent = "Upload and Process";
                    uploadButton.disabled = false;
                }

                resolve({ success: false, error: `Server returned ${xhr.status}` });
            }
        });

        xhr.addEventListener('error', function () {
            // Network error
            document.getElementById('uploadStatus').textContent =
                `Upload failed for ${folderName}: Network error`;

            // Reset button on error if provided
            if (uploadButton && shouldReload) {
                uploadButton.textContent = "Upload and Process";
                uploadButton.disabled = false;
            }

            resolve({ success: false, error: 'Network error' });
        });

        xhr.addEventListener('abort', function () {
            // Upload aborted
            document.getElementById('uploadStatus').textContent =
                `Upload aborted for ${folderName}`;

            // Reset button on error if provided
            if (uploadButton && shouldReload) {
                uploadButton.textContent = "Upload and Process";
                uploadButton.disabled = false;
            }

            resolve({ success: false, error: 'Upload aborted' });
        });

        // Send the request
        xhr.open('POST', uploadForm.action);
        xhr.setRequestHeader('X-CSRFToken', csrftoken);
        xhr.send(formData);
    });
}
// Update the folder file change handler to display the main folder name
function handleFolderFileChange(event) {
    folderFiles = event.target.files;
    const folderName = folderFiles?.[0]?.webkitRelativePath.split("/")[0];
    folderFileName = folderName ? folderName.slice(0, 15) : "No folder chosen";
    document.getElementById('fileName2').textContent = folderFileName;
    document.getElementById('fileName2').style.color = '#00000080';

    // Calculate total folder size
    let totalSize = 0;
    if (folderFiles && folderFiles.length > 0) {
        console.log(`\n📁 FOLDER SELECTED: ${folderName}`);
        console.log(`Total files in folder: ${folderFiles.length}`);

        // Calculate total size and filter video files
        const allFiles = Array.from(folderFiles);
        const videoFiles = [];
        const nonVideoFiles = [];

        for (const file of allFiles) {
            totalSize += file.size;

            if (isVideoFile(file)) {
                videoFiles.push(file);
            } else {
                nonVideoFiles.push(file);
            }
        }

        // Log size information
        console.log(`Total folder size: ${formatFileSize(totalSize)}`);
        console.log(`Video files found: ${videoFiles.length}`);
        console.log(`Non-video files found: ${nonVideoFiles.length}`);

        // Check if folder exceeds the size limit
        const isSizeExceeded = updateFolderSizeIndicator(totalSize);

        if (isSizeExceeded) {
            // Create or update error message
            let sizeErrorElement = document.getElementById('folder-size-error');
            if (!sizeErrorElement) {
                sizeErrorElement = document.createElement('div');
                sizeErrorElement.id = 'folder-size-error';
                sizeErrorElement.className = 'folder-size-error';

                const filenameElement = document.getElementById('fileName2');
                if (filenameElement && filenameElement.parentNode) {
                    filenameElement.parentNode.appendChild(sizeErrorElement);
                }
            }

            sizeErrorElement.textContent = `Folder size (${formatFileSize(totalSize)}) exceeds the 10 GB limit`;
            sizeErrorElement.classList.add('shake-animation');
            setTimeout(() => {
                sizeErrorElement.classList.remove('shake-animation');
            }, 500);

            // Disable upload button
            const uploadButton = document.getElementById('videoUploadButton');
            if (uploadButton) {
                uploadButton.disabled = true;
                uploadButton.style.opacity = '0.5';
                uploadButton.title = "Folder exceeds 10 GB size limit";
            }
        } else {
            // Remove error message if it exists
            const sizeErrorElement = document.getElementById('folder-size-error');
            if (sizeErrorElement) {
                sizeErrorElement.remove();
            }

            // Enable upload button
            const uploadButton = document.getElementById('videoUploadButton');
            if (uploadButton) {
                uploadButton.disabled = false;
                uploadButton.style.opacity = '1';
                uploadButton.title = "";
            }

            // Display folder info
            const fileTypes = {};
            allFiles.forEach(file => {
                const ext = file.name.split('.').pop() || 'no-extension';
                fileTypes[ext] = (fileTypes[ext] || 0) + 1;
            });

            console.log(`\n📄 FILE TYPE BREAKDOWN:`);
            Object.entries(fileTypes).forEach(([ext, count]) => {
                console.log(`  .${ext}: ${count} file(s)`);
            });

            // Get unique subfolders containing video files
            const subfolders = new Set();
            let totalVideoCount = 0;

            for (const file of videoFiles) {
                const pathParts = file.webkitRelativePath.split('/');
                if (pathParts.length > 2) { // Main folder / subfolder / file
                    subfolders.add(pathParts[1]);
                }
                totalVideoCount++;
            }

            if (subfolders.size > 0 || totalVideoCount > 0) {
                const subfoldersText = document.createElement('div');
                subfoldersText.className = 'subfolders-info';
                subfoldersText.innerHTML = `
                    <div>Contains ${subfolders.size} subfolder${subfolders.size > 1 ? 's' : ''}</div>
                    <div>Total video files: ${totalVideoCount}</div>
                `;
                subfoldersText.style.fontSize = '12px';
                subfoldersText.style.color = '#666';
                subfoldersText.style.marginTop = '5px';

                // Add or update subfolder info
                const existingInfo = document.querySelector('.subfolders-info');
                if (existingInfo) {
                    existingInfo.replaceWith(subfoldersText);
                } else {
                    const filenameElement = document.getElementById('fileName2');
                    if (filenameElement && filenameElement.parentNode) {
                        filenameElement.parentNode.appendChild(subfoldersText);
                    }
                }
            }
        }
    }
}

// Define the maximum file size constant in bytes
const MAX_UPLOAD_SIZE = 10 * 1024 * 1024 * 1024; // 10 GB in bytes

// Helper function to format file size in human-readable format
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    else if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + " KB";
    else if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(2) + " MB";
    else return (bytes / (1024 * 1024 * 1024)).toFixed(2) + " GB";
}

// Function to create and update the folder size indicator
function updateFolderSizeIndicator(totalSize) {
    const maxSize = MAX_UPLOAD_SIZE;
    const percentage = Math.min((totalSize / maxSize) * 100, 100);

    // Create container if it doesn't exist
    let sizeIndicatorContainer = document.getElementById('size-indicator-container');
    if (!sizeIndicatorContainer) {
        sizeIndicatorContainer = document.createElement('div');
        sizeIndicatorContainer.id = 'size-indicator-container';
        sizeIndicatorContainer.style.marginTop = '8px';

        const filenameElement = document.getElementById('fileName2');
        if (filenameElement && filenameElement.parentNode) {
            filenameElement.parentNode.appendChild(sizeIndicatorContainer);
        }
    }

    // Determine color based on percentage
    let statusClass = 'size-ok';
    let statusIcon = 'ri-check-line';

    if (percentage > 90) {
        statusClass = 'size-danger';
        statusIcon = 'ri-error-warning-line';
    } else if (percentage > 70) {
        statusClass = 'size-warning';
        statusIcon = 'ri-alert-line';
    }

    // Create HTML for the indicator


    return percentage >= 100; // Return true if size exceeds limit
}


// Add CSS styles for size indicator
document.addEventListener('DOMContentLoaded', function () {
    const style = document.createElement('style');
    style.textContent = `
        .folder-size-error {
            color: #FF5050;
            margin-top: 5px;
            font-weight: bold;
            transition: all 0.3s ease;
        }
        
        @keyframes shake {
            0%, 100% { transform: translateX(0); }
            25% { transform: translateX(-5px); }
            75% { transform: translateX(5px); }
        }
        
        .shake-animation {
            animation: shake 0.5s ease-in-out;
        }
        
        .size-warning {
            display: flex;
            align-items: center;
            margin-top: 5px;
            font-size: 12px;
        }
        
        .size-warning i {
            color: #FF5050;
            margin-right: 5px;
        }
        
        .size-warning.size-ok i {
            color: #4CAF50;
        }
        
        .size-progress-container {
            margin-top: 5px;
            width: 100%;
            height: 6px;
            background-color: #f0f0f0;
            border-radius: 3px;
            overflow: hidden;
        }
        
        .size-progress-bar {
            height: 100%;
            border-radius: 3px;
            transition: width 0.3s ease;
        }
        
        .size-progress-bar.size-ok {
            background-color: #4CAF50;
        }
        
        .size-progress-bar.size-warning {
            background-color: #FFC107;
        }
        
        .size-progress-bar.size-danger {
            background-color: #FF5050;
        }
    `;
    document.head.appendChild(style);
});


// Function to scroll to a slide and show shake animation
function scrollToSlideWithShake(slideId, errorMessage) {
    const slideElement = document.querySelector(`tr[data-id="${slideId}"]`);
    if (slideElement) {
        // Scroll to the slide
        slideElement.scrollIntoView({ 
            behavior: 'smooth', 
            block: 'center' 
        });
        
        // Add shake animation to the entire row
        slideElement.style.animation = 'shake 0.6s ease-in-out';
        slideElement.style.backgroundColor = '#ffebee';
        
        // Show error message
        const errorMessageElement = document.getElementById(`error-message_${slideId}`);
        if (errorMessageElement) {
            errorMessageElement.textContent = errorMessage;
            errorMessageElement.style.display = 'block';
            errorMessageElement.style.animation = 'shake 0.6s ease-in-out';
        }
        
        // Remove animations after they complete
        setTimeout(() => {
            slideElement.style.animation = '';
            slideElement.style.backgroundColor = '';
            if (errorMessageElement) {
                errorMessageElement.style.animation = '';
            }
        }, 600);
    }
}

// Function to find unassigned slides
function findUnassignedSlides() {
    return slides.filter(slide => {
        // Skip empty slides
        if (!slide.text || slide.text.trim() === "") {
            return false;
        }

        // Extract all highlighted text from the marked text
        const markedText = slide.markedText || slide.text || "";
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = markedText;
        
        // Get all mark elements
        const markElements = tempDiv.querySelectorAll('mark.handlePopupSubmit');
        
        // If there are no mark elements but there is text, it means no text is assigned
        if (markElements.length === 0) {
            return true;
        }
        
        // Get the raw text without any HTML
        const fullText = tempDiv.textContent.trim();
        
        // Collect all the highlighted text
        let highlightedText = '';
        markElements.forEach(mark => {
            highlightedText += mark.textContent;
        });
        
        // Remove all spaces from both strings for comparison
        const normalizedFullText = fullText.replace(/\s+/g, '');
        const normalizedHighlightedText = highlightedText.replace(/\s+/g, '');
        
        // Check if all text is highlighted
        return normalizedHighlightedText !== normalizedFullText;
    });
}

function shouldEnableProceedButton() {
    // Check if all textareas are hidden (not in editing mode)
    if (!areAllTextareasHidden()) {
        return false;
    }
    
    // Check if there are any pending uploads
    if (pendingUploads.size > 0) {
        return false;
    }
    
    // Always enable the button - we'll handle validation in the click handler
    return true;
}


// ADD these functions to your existing scene.js file (paste.txt)



// Function to split a subtitle at cursor position
function splitSubtitleAtCursor(slideId, cursorPosition) {
    const slideIndex = slides.findIndex(s => s.id === slideId);
    if (slideIndex === -1) return false;

    const slide = slides[slideIndex];
    const fullText = getCleanTextContent(slide.text);
    
    // Validate cursor position
    if (cursorPosition <= 0 || cursorPosition >= fullText.length) {
        console.log('Invalid cursor position for splitting');
        return false;
    }

    // Find word boundary near cursor position
    const splitPosition = findNearestWordBoundaryForSplit(fullText, cursorPosition);
    if (splitPosition === -1) {
        console.log('No valid word boundary found for splitting');
        return false;
    }

    // Split the text
    const firstPartText = fullText.substring(0, splitPosition).trim();
    const secondPartText = fullText.substring(splitPosition).trim();

    if (!firstPartText || !secondPartText) {
        console.log('Split would result in empty subtitle');
        return false;
    }

    // Check character limits
    if (firstPartText.length > MAX_SUBTITLE_LENGTH || secondPartText.length > MAX_SUBTITLE_LENGTH) {
        alert(`Split would create subtitle(s) exceeding ${MAX_SUBTITLE_LENGTH} character limit`);
        return false;
    }

    // Check free plan restrictions
    if (typeof isFreePlan !== 'undefined' && isFreePlan && slides.length >= 10) {
        alert('Free plan users are limited to 10 subtitles. Please upgrade your subscription.');
        return false;
    }

    // Save current state for undo
    saveSubtitleOperationToHistory();

    // Split highlighted text assignments
    const { firstPartMarked, secondPartMarked } = splitMarkedText(slide.markedText || slide.text, splitPosition);

    // Create new slide for second part
    const newSlideId = generateNewSlideId();
    const newSlide = {
        id: newSlideId,
        subtitle: `Slide ${slideIndex + 2}`,
        text: secondPartText,
        markedText: secondPartMarked,
        originalText: secondPartText,
        isEditing: false,
        sequence: slide.sequence + 1
    };

    // Update current slide with first part
    slides[slideIndex] = {
        ...slide,
        text: firstPartText,
        markedText: firstPartMarked,
        isEditing: false
    };

    // Insert new slide after current one
    slides.splice(slideIndex + 1, 0, newSlide);

    // Update sequence numbers for slides after the split
    updateSequenceNumbers(slideIndex + 2);

    // Send split request to server
    sendSplitToServer(slideId, splitPosition, firstPartText, secondPartText, firstPartMarked, secondPartMarked);

    // Re-render slides
    renderSlides(false);
    
    console.log(`Split subtitle ${slideId} at position ${splitPosition}`);
    return true;
}

// Function to merge a subtitle with the previous one
function mergeWithPreviousSubtitle(slideId) {
    const slideIndex = slides.findIndex(s => s.id === slideId);
    if (slideIndex <= 0) {
        console.log('Cannot merge: no previous subtitle');
        return false;
    }

    const currentSlide = slides[slideIndex];
    const previousSlide = slides[slideIndex - 1];

    // Combine texts
    const combinedText = getCleanTextContent(previousSlide.text) + ' ' + getCleanTextContent(currentSlide.text);

    // Check character limit
    if (combinedText.length > MAX_SUBTITLE_LENGTH) {
        alert(`Merged subtitle would exceed ${MAX_SUBTITLE_LENGTH} character limit (${combinedText.length} characters)`);
        return false;
    }

    // Save current state for undo
    saveSubtitleOperationToHistory();

    // Combine marked text preserving highlights
    // Combine marked text and reset all video assignments
    const combinedMarkedText = combineMarkedTexts(previousSlide.markedText || previousSlide.text, currentSlide.markedText || currentSlide.text);
    console.log('Merged subtitles - all video assignments reset for combined text');

    // Send merge request to server
    sendMergeToServer(currentSlide.id, previousSlide.id, combinedText, combinedMarkedText);

    // Update previous slide with combined content
    slides[slideIndex - 1] = {
        ...previousSlide,
        text: combinedText,
        markedText: combinedMarkedText,
        isEditing: false
    };

    // Remove current slide
    const removedSlide = slides.splice(slideIndex, 1)[0];

    // Update sequence numbers
    updateSequenceNumbers(slideIndex);

    // Re-render slides
    renderSlides(false);

    console.log(`Merged subtitle ${slideId} with previous subtitle`);
    return true;
}

// Function to send split request to server
function sendSplitToServer(clipId, splitPosition, firstPartText, secondPartText, firstPartMarked, secondPartMarked) {
    // Get CSRF token
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    const csrftoken = getCookie('csrftoken');
    
    const data = {
        clip_id: clipId,
        split_position: splitPosition,
        first_part_text: firstPartText,
        second_part_text: secondPartText,
        first_part_marked: firstPartMarked,
        second_part_marked: secondPartMarked
    };

    fetch('/split-subtitle/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrftoken,
        },
        body: JSON.stringify(data),
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log('Split request successful:', data);
            // Update the new slide ID if needed
            const newSlideIndex = slides.findIndex(s => s.id < 0 && s.text === secondPartText);
            if (newSlideIndex !== -1 && data.new_clip_id) {
                slides[newSlideIndex].id = data.new_clip_id;
                renderSlides(false);
            }
        } else {
            console.error('Split request failed:', data.error);
        }
    })
    .catch(error => {
        console.error('Error sending split request:', error);
    });
}

// Function to send merge request to server
function sendMergeToServer(currentClipId, previousClipId, mergedText, mergedMarkedText) {
    // Get CSRF token
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    const csrftoken = getCookie('csrftoken');
    
    const data = {
    current_clip_id: currentClipId,
    previous_clip_id: previousClipId,
    merged_text: mergedText,
    merged_marked_text: mergedMarkedText,
    reset_video_assignments: true  // Add this flag to inform backend
};

    fetch('/merge-subtitles/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrftoken,
        },
        body: JSON.stringify(data),
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log('Merge request successful:', data);
        } else {
            console.error('Merge request failed:', data.error);
        }
    })
    .catch(error => {
        console.error('Error sending merge request:', error);
    });
}

// Function to split marked text while removing highlights from split text
function splitMarkedText(markedText, splitPosition) {
    if (!markedText || !markedText.includes('<mark')) {
        // No highlights to preserve
        const cleanText = getCleanTextContent(markedText || '');
        return {
            firstPartMarked: cleanText.substring(0, splitPosition).trim(),
            secondPartMarked: cleanText.substring(splitPosition).trim()
        };
    }

    // Create a mapping of character positions to track highlights
    const cleanText = getCleanTextContent(markedText);
    const characterHighlightMap = new Array(cleanText.length).fill(null);
    
    // Parse the HTML to map each character to its highlight information
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = markedText;
    
    let charIndex = 0;
    
    function mapHighlights(node, currentHighlight = null) {
        if (node.nodeType === Node.TEXT_NODE) {
            const text = node.textContent;
            for (let i = 0; i < text.length; i++) {
                if (charIndex < characterHighlightMap.length) {
                    characterHighlightMap[charIndex] = currentHighlight;
                    charIndex++;
                }
            }
        } else if (node.nodeType === Node.ELEMENT_NODE && node.tagName === 'MARK') {
            // Extract all attributes from the mark element
            const highlightInfo = {
                attributes: {},
                text: node.textContent
            };
            
            for (let attr of node.attributes) {
                highlightInfo.attributes[attr.name] = attr.value;
            }
            
            // Process children with this highlight info
            for (let child of node.childNodes) {
                mapHighlights(child, highlightInfo);
            }
        } else {
            // Process other elements
            for (let child of node.childNodes) {
                mapHighlights(child, currentHighlight);
            }
        }
    }
    
    // Build the character highlight map
    for (let child of tempDiv.childNodes) {
        mapHighlights(child);
    }
    
    // Find highlights that cross the split boundary and should be removed
    const highlightsToRemove = new Set();
    
    // Check for highlights that span across the split position
    for (let i = Math.max(0, splitPosition - 50); i < Math.min(characterHighlightMap.length, splitPosition + 50); i++) {
        const highlight = characterHighlightMap[i];
        if (highlight) {
            const highlightText = highlight.text;
            const highlightStart = cleanText.indexOf(highlightText);
            const highlightEnd = highlightStart + highlightText.length;
            
            // If this highlight crosses the split boundary, mark it for removal
            if (highlightStart < splitPosition && highlightEnd > splitPosition) {
                // Create a unique identifier for this highlight
                const highlightId = JSON.stringify(highlight.attributes);
                highlightsToRemove.add(highlightId);
                console.log(`Marking highlight for removal: "${highlightText}" (crosses split boundary)`);
            }
        }
    }
    
    // Now reconstruct the HTML for both parts, excluding removed highlights
    function reconstructHTML(startPos, endPos) {
        let html = '';
        let currentHighlight = null;
        let markOpen = false;
        
        for (let i = startPos; i < endPos && i < characterHighlightMap.length; i++) {
            const char = cleanText[i];
            const highlight = characterHighlightMap[i];
            
            // Check if this highlight should be removed
            let shouldRemoveHighlight = false;
            if (highlight) {
                const highlightId = JSON.stringify(highlight.attributes);
                shouldRemoveHighlight = highlightsToRemove.has(highlightId);
            }
            
            // Treat removed highlights as no highlight
            const effectiveHighlight = shouldRemoveHighlight ? null : highlight;
            
            // Check if highlight state changed
            if (!areHighlightsEqual(currentHighlight, effectiveHighlight)) {
                // Close current mark if open
                if (markOpen) {
                    html += '</mark>';
                    markOpen = false;
                }
                
                // Open new mark if needed
                if (effectiveHighlight) {
                    const attrs = Object.entries(effectiveHighlight.attributes)
                        .map(([key, value]) => `${key}="${value}"`)
                        .join(' ');
                    html += `<mark ${attrs}>`;
                    markOpen = true;
                }
                
                currentHighlight = effectiveHighlight;
            }
            
            // Add the character (escape HTML entities)
            html += char.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        }
        
        // Close any open mark
        if (markOpen) {
            html += '</mark>';
        }
        
        return html.trim();
    }
    
    function areHighlightsEqual(h1, h2) {
        if (h1 === h2) return true;
        if (!h1 || !h2) return false;
        
        // Compare attributes
        const attrs1 = h1.attributes || {};
        const attrs2 = h2.attributes || {};
        
        const keys1 = Object.keys(attrs1);
        const keys2 = Object.keys(attrs2);
        
        if (keys1.length !== keys2.length) return false;
        
        for (let key of keys1) {
            if (attrs1[key] !== attrs2[key]) return false;
        }
        
        return true;
    }
    
    const result = {
        firstPartMarked: reconstructHTML(0, splitPosition),
        secondPartMarked: reconstructHTML(splitPosition, cleanText.length)
    };
    
    console.log('Split removing crossed highlights:', {
        original: markedText,
        splitAt: splitPosition,
        removedHighlights: highlightsToRemove.size,
        firstPart: result.firstPartMarked,
        secondPart: result.secondPartMarked
    });
    
    return result;
}

// Function to combine marked texts while preserving highlights
// Function to combine marked texts while REMOVING all highlights (reset videos)
function combineMarkedTexts(firstMarkedText, secondMarkedText) {
    const firstClean = getCleanTextContent(firstMarkedText || '').trim();
    const secondClean = getCleanTextContent(secondMarkedText || '').trim();

    if (!firstClean) return secondClean;
    if (!secondClean) return firstClean;

    // Return plain text without any highlights - this resets all assigned videos
    return firstClean + ' ' + secondClean;
}
// Function to find word boundary for splitting
function findNearestWordBoundaryForSplit(text, position) {
    // Word boundary characters
    const wordBoundaryRegex = /[\s\.,!?;:\-\(\)\[\]{}""'']/;
    
    // Look for word boundaries before and after the position
    let beforeBoundary = -1;
    let afterBoundary = -1;
    
    // Search backwards for word boundary
    for (let i = position - 1; i >= 0; i--) {
        if (wordBoundaryRegex.test(text[i])) {
            beforeBoundary = i + 1; // Position after the boundary character
            break;
        }
    }
    
    // Search forwards for word boundary
    for (let i = position; i < text.length; i++) {
        if (wordBoundaryRegex.test(text[i])) {
            afterBoundary = i;
            break;
        }
    }
    
    // Choose the closest boundary
    if (beforeBoundary === -1 && afterBoundary === -1) {
        return -1; // No word boundary found
    } else if (beforeBoundary === -1) {
        return afterBoundary;
    } else if (afterBoundary === -1) {
        return beforeBoundary;
    } else {
        // Choose the closer one
        const distanceBefore = position - beforeBoundary;
        const distanceAfter = afterBoundary - position;
        return distanceBefore <= distanceAfter ? beforeBoundary : afterBoundary;
    }
}

// Function to generate new slide ID
function generateNewSlideId() {
    // Use negative IDs for new slides (similar to existing pattern)
    const existingNegativeIds = slides
        .filter(s => s.id < 0)
        .map(s => s.id);
    
    if (existingNegativeIds.length === 0) {
        return -1;
    }
    
    return Math.min(...existingNegativeIds) - 1;
}

// Function to update sequence numbers after operations
function updateSequenceNumbers(startIndex = 0) {
    for (let i = startIndex; i < slides.length; i++) {
        slides[i].subtitle = `Slide ${i + 1}`;
        slides[i].sequence = i + 1;
    }
}

// Function to save operation to history for undo
function saveSubtitleOperationToHistory() {
    const currentState = {
        slides: JSON.parse(JSON.stringify(slides)), // Deep clone
        timestamp: Date.now()
    };
    
    subtitleOperationHistory.push(currentState);
    
    // Limit history size
    if (subtitleOperationHistory.length > maxSubtitleHistorySize) {
        subtitleOperationHistory.shift();
    }
}

// Function to undo last operation
function undoLastSubtitleOperation() {
    if (subtitleOperationHistory.length === 0) {
        console.log('No operations to undo');
        return false;
    }
    
    const lastState = subtitleOperationHistory.pop();
    slides = lastState.slides;
    
    // Re-render slides
    renderSlides(false);
    
    console.log('Undid last subtitle operation');
    return true;
}

// Function to handle keyboard and mouse events for splitting and merging
function handleSubtitleInteraction(event, slideId) {
    const slide = slides.find(s => s.id === slideId);
    if (!slide || slide.isEditing) {
        return; // Don't handle interactions for editing slides
    }

    // Ctrl/Cmd + Click for splitting
    if ((event.ctrlKey || event.metaKey) && event.type === 'click') {
        event.preventDefault();
        
        // Get cursor position in the text
        const selection = window.getSelection();
        if (selection.rangeCount === 0) return;
        
        const range = selection.getRangeAt(0);
        const cursorPosition = getCursorPositionInText(range, slideId);
        
        if (cursorPosition !== -1) {
            splitSubtitleAtCursor(slideId, cursorPosition);
        }
    }
    
    // Shift + Click for merging with previous
    else if (event.shiftKey && event.type === 'click') {
        event.preventDefault();
        mergeWithPreviousSubtitle(slideId);
    }
}

// Function to get cursor position in clean text
function getCursorPositionInText(range, slideId) {
    const slideElement = document.querySelector(`#highlightable_${slideId} span`);
    if (!slideElement) return -1;
    
    // Create a temporary element to get clean text
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = slideElement.innerHTML;
    
    // Get the clean text
    const cleanText = tempDiv.textContent || '';
    
    // Try to find the position by walking through the DOM
    const walker = document.createTreeWalker(
        slideElement,
        NodeFilter.SHOW_TEXT,
        null,
        false
    );
    
    let position = 0;
    let node;
    
    while (node = walker.nextNode()) {
        if (node === range.startContainer) {
            return position + range.startOffset;
        }
        position += node.textContent.length;
    }
    
    return -1;
}

// CSS styles for split/merge functionality
const splitMergeStyles = `
    .subtitle-split-merge-hint {
        font-size: 11px;
        color: #666;
        margin-top: 4px;
        opacity: 0;
        transition: opacity 0.2s ease;
        width: fit-content;
    }
    
    .highlight-sub:hover .subtitle-split-merge-hint {
        opacity: 1;
    }
    
    .subtitle-operation-success {
        background-color: #e8f5e8 !important;
        transition: background-color 0.3s ease;
    }
    
    .subtitle-operation-error {
        background-color: #ffebee !important;
        animation: subtitleShake 0.5s ease-in-out;
    }
    
    @keyframes subtitleShake {
        0%, 100% { transform: translateX(0); }
        25% { transform: translateX(-3px); }
        75% { transform: translateX(3px); }
    }
    
    .highlightable-interactive {
        cursor: text;
        position: relative;
    }
    
    .highlightable-interactive:hover {
        background-color: #f8f9fa;
    }
    
    .split-merge-tooltip {
        position: absolute;
        bottom: 100%;
        left: 50%;
        transform: translateX(-50%);
        background: rgba(0, 0, 0, 0.8);
        color: white;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 11px;
        white-space: nowrap;
        opacity: 0;
        pointer-events: none;
        transition: opacity 0.2s ease;
        z-index: 1000;
    }
    
    .highlightable-interactive:hover .split-merge-tooltip {
        opacity: 1;
    }
`;

// Add styles to document
function addSplitMergeStyles() {
    const styleElement = document.createElement('style');
    styleElement.textContent = splitMergeStyles;
    document.head.appendChild(styleElement);
}

// MODIFY the existing renderSlides function to add split/merge event listeners
// REPLACE the existing renderSlides function with this updated version:

function renderSlides(send_update = true) {
    const tbody = document.querySelector('#leadsTable tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    slides.forEach(slide => {
        const tr = document.createElement('tr');
        tr.dataset.id = slide.id;
        tr.style.height = "5rem";
        if (send_update === true) {
            updateClipOnServer(slide.id, slide.text);
        }

        const charCount = slide.text ? getCleanTextContent(slide.text).length : 0;
        const charCountClass = charCount > MAX_SUBTITLE_LENGTH ? 'char-count-exceeded' : 'char-count';

        tr.innerHTML = `
            <td class="slide-first" style="font-size: 1.4rem; position: relative;" title="Drag to move">
                <div style="display: flex; align-items: center;">
                     ${slide.subtitle}
                </div>
            </td>
            <td id="highlightable_${slide.id}" style="user-select:text;">
                <div class="highlight-sub">
                    ${slide.isEditing ? `
                     
                    ` : `
                        <div class="highlightable-interactive" style="user-select: text;">
                            <span>${slide.markedText || slide.text || ""}</span>
                            <div class="split-merge-tooltip" style="user-select: none;">
    Ctrl+Click (⌘+Click on Mac) to split • Shift+Click to merge with previous
                            </div>
                        </div>
                        <div class="subtitle-split-merge-hint" style="user-select: none;">
    💡 Ctrl+Click (⌘+Click on Mac) to split • Shift+Click to merge with previous
                        </div>
                    `}
                    <div id="error-message_${slide.id}" class="error-message" style="display: ${charCount > MAX_SUBTITLE_LENGTH ? 'block' : 'none'};">
                        ${charCount > MAX_SUBTITLE_LENGTH ? `Subtitle text cannot exceed ${MAX_SUBTITLE_LENGTH} characters (current: ${charCount})` : ''}
                    </div>
                </div>
            </td>
            <td class="slide-last ${activeSlideIds.has(slide.id) ? 'active' : ''}">
                <a href="#" class="above-del" onclick="handleUndo(${slide.id}); event.preventDefault();">
                    <img src="/static/images/undo.svg" alt="Undo" style="width: 1.2rem; height: 3rem; cursor: pointer;">
                </a>
            </td>
        `;
        tbody.appendChild(tr);

        if (!slide.isEditing) {
            const highlightable = document.getElementById(`highlightable_${slide.id}`);
            
            // Add existing text selection handler
            highlightable.addEventListener('mouseup', () => handleTextSelection(slide.id));

            // Add split/merge event listeners
            const interactiveDiv = highlightable.querySelector('.highlightable-interactive');
            if (interactiveDiv) {
                interactiveDiv.addEventListener('click', (e) => {
                    handleSubtitleInteraction(e, slide.id);
                });
            }

            // Add existing mark click handlers
            const marks = highlightable.querySelectorAll('mark.handlePopupSubmit');
            marks.forEach(mark => {
                mark.addEventListener('click', () => {
                    selectedSlideId = slide.id;
                    selectedText = mark.textContent;
                    popupOpen = true;
                    renderPopup();
                });
            });
        }

        if (slide.isEditing) {
            const textarea = document.getElementById(`slide_text_${slide.id}`);

            // Add existing textarea event listeners (keydown, paste, input)
            textarea.addEventListener('keydown', (e) => {
                const maxLength = window.MAX_SUBTITLE_LENGTH || 100;
                const currentLength = textarea.value.length;
                const selectedText = textarea.value.substring(textarea.selectionStart, textarea.selectionEnd);
                const isTextSelected = selectedText.length > 0;

                const allowedKeys = [8, 9, 37, 38, 39, 40, 46, 36, 35, 33, 34];

                if (e.ctrlKey && [65, 67, 86, 88].includes(e.keyCode)) {
                    return;
                }

                if (currentLength >= maxLength && !allowedKeys.includes(e.keyCode) && !isTextSelected) {
                    e.preventDefault();

                    const errorMessage = document.getElementById(`error-message_${slide.id}`);
                    if (errorMessage) {
                        errorMessage.textContent = `Subtitle text cannot exceed ${maxLength} characters`;
                        errorMessage.style.display = "block";
                    }

                    textarea.style.animation = 'shake 0.5s ease-in-out';
                    setTimeout(() => {
                        textarea.style.animation = '';
                    }, 500);

                    return false;
                }
            });

            // Add paste event listener
            textarea.addEventListener('paste', (e) => {
                e.preventDefault();

                const maxLength = window.MAX_SUBTITLE_LENGTH || 100;
                const pastedText = (e.clipboardData || window.clipboardData).getData('text');
                const currentText = textarea.value;
                const selectionStart = textarea.selectionStart;
                const selectionEnd = textarea.selectionEnd;

                const newText = currentText.substring(0, selectionStart) + pastedText + currentText.substring(selectionEnd);

                if (newText.length > maxLength) {
                    const remainingLength = maxLength - currentText.length + (selectionEnd - selectionStart);
                    const truncatedPaste = pastedText.substring(0, Math.max(0, remainingLength));

                    textarea.value = currentText.substring(0, selectionStart) + truncatedPaste + currentText.substring(selectionEnd);

                    const newCursorPos = selectionStart + truncatedPaste.length;
                    textarea.setSelectionRange(newCursorPos, newCursorPos);

                    const errorMessage = document.getElementById(`error-message_${slide.id}`);
                    if (errorMessage) {
                        errorMessage.textContent = `Subtitle text cannot exceed ${maxLength} characters. Pasted text was truncated.`;
                        errorMessage.style.display = "block";
                    }

                    textarea.dispatchEvent(new Event('input', { bubbles: true }));
                } else {
                    textarea.value = newText;
                    const newCursorPos = selectionStart + pastedText.length;
                    textarea.setSelectionRange(newCursorPos, newCursorPos);
                    textarea.dispatchEvent(new Event('input', { bubbles: true }));
                }
            });

            // Add input event listener
            textarea.addEventListener('input', (e) => {
                const newText = e.target.value;
                const maxLength = window.MAX_SUBTITLE_LENGTH || 100;

                if (newText.length > maxLength) {
                    e.target.value = newText.substring(0, maxLength);
                    return;
                }

                slides = slides.map(s =>
                    s.id === slide.id ? { ...s, text: newText, markedText: newText } : s
                );

                const charCount = e.target.value.length;
                const charCountElement = e.target.parentElement.querySelector(`.char-count, .char-count-exceeded`);
                if (charCountElement) {
                    charCountElement.textContent = `${charCount}/${maxLength}`;
                    charCountElement.className = charCount >= maxLength ? 'char-count-exceeded' : 'char-count';
                }

                const errorMessage = document.getElementById(`error-message_${slide.id}`);
                if (errorMessage) {
                    if (charCount >= maxLength) {
                        errorMessage.textContent = `Subtitle text cannot exceed ${maxLength} characters`;
                        errorMessage.style.display = 'block';
                        textarea.style.border = '1px solid red';
                    } else {
                        errorMessage.style.display = 'none';
                        textarea.style.border = '';
                    }
                }
            });
        }
    });

    document.getElementById('no_of_slides').value = slideCount;
    renderButton();
    updateProceedButtonState();
}

// Initialize split/merge functionality
document.addEventListener('DOMContentLoaded', () => {
    addSplitMergeStyles();
    
    // Add global keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Ctrl/Cmd + Shift + Z for undo operations
        if ((e.ctrlKey || e.metaKey) && e.key === 'z' && e.shiftKey) {
            e.preventDefault();
            undoLastSubtitleOperation();
        }
    });
});

// Export functions for use in other parts of the application
window.splitSubtitleAtCursor = splitSubtitleAtCursor;
window.mergeWithPreviousSubtitle = mergeWithPreviousSubtitle;
window.undoLastSubtitleOperation = undoLastSubtitleOperation;