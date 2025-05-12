// Predefined video clips for each topic
const videoClips = {
  "745": [
    { id: "622", name: "Surprised Man Sitting on Sofa" },
    { id: "623", name: "Surprised Man Reading Tablet" },
  ],
  "748": [
    { id: "624", name: "A Man in Surprise Shoots Glasses" },
    { id: "625", name: "Surprised Man with Phone" },
  ],
};

// Object to store slide-specific video associations
const slideVideos = {};

// File input change event to update the "Choose File" text and clear dropdowns
document.getElementById('popup-file').addEventListener('change', function () {
  const fileInput = this;
  const fileName = fileInput.files[0]?.name || '';
  const uploadText = document.querySelector('.uploadText');
  const topicSelect = document.getElementById('popup-topic');
  const videoSelect = document.getElementById('popup-video');

  if (fileName) {
    const firstTwoWords = fileName.split(' ').slice(0, 2).join(' '); // Get the first two words
    uploadText.textContent = firstTwoWords; // Display only the first two words
    document.getElementById('delete-icon').style.display = 'block'; // Show delete icon
    uploadText.setAttribute('title', fileName); // Set full name as tooltip

    // Clear topic and video dropdowns
    topicSelect.selectedIndex = 0;
    videoSelect.innerHTML = '<option value="">Select a video</option>';
  } else {
    resetFileUploadText(); // Reset to "Choose File"
  }
});

// Reset the "Choose File" text
function resetFileUploadText() {
  const uploadText = document.querySelector('.uploadText');
  uploadText.textContent = 'Choose File';
  document.getElementById('delete-icon').style.display = 'none';
}

// Handle the delete button click event
document.getElementById('delete-icon').addEventListener('click', () => {
  document.getElementById('popup-file').value = ''; // Clear file input
  resetFileUploadText(); // Reset text
});

// Populate "Select Video" dropdown based on the selected topic
document.getElementById('popup-topic').addEventListener('change', function () {
  const topicId = this.value;
  const videoSelect = document.getElementById('popup-video');
  const fileInput = document.getElementById('popup-file');

  // Reset file input if a topic is selected
  fileInput.value = '';
  resetFileUploadText();

  // Clear existing options in the "Select Video" dropdown
  videoSelect.innerHTML = '<option value="">Select a video</option>';

  // Populate dropdown and auto-select the first video
  if (videoClips[topicId]) {
    videoClips[topicId].forEach((clip, index) => {
      const option = document.createElement('option');
      option.value = clip.id;
      option.textContent = clip.name;
      videoSelect.appendChild(option);

      // Automatically select the first video
      if (index === 0) {
        videoSelect.value = clip.id;
      }
    });
  }
});

// Handle the submit button click event
document.getElementById('popup-submit').addEventListener('click', (event) => {
  event.preventDefault();

  const slideNumber = document.getElementById('popup-submit').getAttribute('data-slide');
  const fileInput = document.getElementById('popup-file');
  const topicSelect = document.getElementById('popup-topic');
  const videoSelect = document.getElementById('popup-video');

  const uploadedFileName = fileInput.files[0]?.name || '';
  const selectedVideo = videoSelect.value;
  const selectedTopic = topicSelect.value;

  // Allow submission if a video is uploaded or a topic and video are selected
  if ((selectedTopic && selectedVideo) || uploadedFileName) {
    // Save the video association for the current slide
    slideVideos[slideNumber] = {
      video: uploadedFileName || selectedVideo,
      displayText: uploadedFileName ? uploadedFileName.split(' ').slice(0, 2).join(' ') : '', // First two words if uploaded
      topic: uploadedFileName ? null : selectedTopic, // Clear topic if a file is uploaded
      dropdownValue: uploadedFileName ? null : selectedVideo, // Clear video dropdown if a file is uploaded
    };

    // Highlight the associated slide-text
    const slideTextElement = document.querySelector(`.slide-text[data-slide="${slideNumber}"]`);
    const spanElement = slideTextElement?.querySelector('span');
    if (spanElement) spanElement.style.backgroundColor = 'yellow';

    // Reset and close the popup modal
    document.getElementById('popup-modal').classList.add('hidden');
    resetPopupFields();
  } else {
    alert('Please select a topic and a video, or upload a video to proceed.');
  }
});

// Reset popup fields
function resetPopupFields() {
  document.getElementById('popup-file').value = '';
  document.getElementById('popup-topic').selectedIndex = 0;
  document.getElementById('popup-video').selectedIndex = 0;
  resetFileUploadText();
}

// Open the popup and prefill data if available
document.querySelectorAll('.slide-text').forEach((text) => {
  text.addEventListener('keydown', (event) => {
    if (event.key === 'Shift') {
      const selection = window.getSelection();
      const selectedText = selection.toString().trim();
      const completeText = text.innerText.trim();

      if (selectedText === completeText) {
        const slideNumber = text.dataset.slide;

        // Open the popup modal
        const popup = document.getElementById('popup-modal');
        popup.classList.remove('hidden');

        // Prefill data for the slide if available
        if (slideVideos[slideNumber]) {
          const { video, displayText, topic, dropdownValue } = slideVideos[slideNumber];
          document.getElementById('popup-topic').value = topic || '';
          document.getElementById('popup-video').value = dropdownValue || ''; // Set dropdown selection

          // Display the previously uploaded video title or reset
          const uploadText = document.querySelector('.uploadText');
          uploadText.textContent = displayText || 'Choose File';
          document.getElementById('delete-icon').style.display = displayText ? 'block' : 'none';
        } else {
          resetPopupFields();
        }

        // Store the current slide number
        document.getElementById('popup-submit').setAttribute('data-slide', slideNumber);
      } else {
        alert('Please select the complete text before pressing Shift.');
      }
    }
  });
});

// Close the popup modal
document.getElementById('close-popup').addEventListener('click', (event) => {
  event.preventDefault();
  document.getElementById('popup-modal').classList.add('hidden');
  resetPopupFields();
});
