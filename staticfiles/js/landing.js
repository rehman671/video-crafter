        // Slider state
        const sliderState = {
            tiktok: { index: 0, length: 3 },
            facebook: { index: 0, length: 3 },
            youtube: { index: 0, length: 3 }
        };

        // Update slider position and dots
        function updateSlider(platform) {
            const slider = document.querySelector(`#${platform}-slider .slider-videos`);
            const dots = document.querySelectorAll(`#${platform}-dots .dot`);
            const index = sliderState[platform].index;
            slider.style.transform = `translateX(-${index * 100}%)`;
            dots.forEach((dot, i) => {
                dot.classList.toggle('active', i === index);
            });
        }

        // Move slider (next/prev)
        function moveSlider(platform, direction) {
            const state = sliderState[platform];
            state.index = (state.index + direction + state.length) % state.length;
            updateSlider(platform);
        }

        // Set specific slide index
        function setSliderIndex(platform, index) {
            sliderState[platform].index = index;
            updateSlider(platform);
        }

        // Swipe handling
        function addSwipeListener(platform) {
            const wrapper = document.getElementById(`${platform}-slider`);
            let startX = null;

            wrapper.addEventListener('touchstart', (e) => {
                startX = e.touches[0].clientX;
            });

            wrapper.addEventListener('touchend', (e) => {
                if (!startX) return;
                const endX = e.changedTouches[0].clientX;
                const distance = startX - endX;
                const threshold = 50;
                if (distance > threshold) {
                    moveSlider(platform, 1); // Swipe left
                } else if (distance < -threshold) {
                    moveSlider(platform, -1); // Swipe right
                }
                startX = null;
            });
        }

        // Initialize sliders
        ['tiktok', 'facebook', 'youtube'].forEach(platform => {
            updateSlider(platform);
            addSwipeListener(platform);
        });