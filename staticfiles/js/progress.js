document.addEventListener('DOMContentLoaded', () => {
    const progressFill = document.querySelector('.progress-fill');
    const steps = [
        document.querySelector('.sub-div2'),
        document.querySelector('.sub-div3'),
        document.querySelector('.sub-div4'),
        document.querySelector('.sub-div5')
    ];
    const labels = [
        document.querySelector('.voice-subtitle'),
        document.querySelector('.sceneselection'),
        document.querySelector('.bgmselection'),
        document.querySelector('.download')
    ];

    const pageSteps = {
        'preview': 1,
        'preview.html': 1,
        'scene': 2,
        'scene.html': 2,
        'background-music': 3,
        'background-music.html': 3,
        'download-scene': 4,
        'download-scene.html': 4
      };
      

    function updateProgressBar(step) {
        step = Math.max(1, Math.min(step, steps.length));

        steps.forEach(step => {
            step.classList.remove('completed', 'active');
            step.style.background = '#EEEEEE'; 
        });
        labels.forEach(label => {
            label.classList.remove('active-text');
            label.style.fontWeight = '380'; 
            label.style.color = ''; 
        });

        for (let i = 0; i < step; i++) {
            steps[i].classList.add(i === step - 1 ? 'active' : 'completed');
            steps[i].style.background = '#864AF9'; 
        }
        const progressWidth = ((step - 1) / (steps.length - 1)) * 103;
        progressFill.style.width = `${progressWidth}%`;

        progressFill.style.height = '10px';
        progressFill.style.position = 'absolute';
        progressFill.style.top = '0';
        progressFill.style.left = '0';
        progressFill.style.background = step <= 2 ? '#864AF9' : '#864AF9';
    }

    function getCurrentStep() {
        const page = window.location.pathname.split('/').pop() || 'preview.html';
        return pageSteps[page] || 1; 
    }

    updateProgressBar(getCurrentStep());
    window.addEventListener('popstate', () => {
        updateProgressBar(getCurrentStep());
    });
});