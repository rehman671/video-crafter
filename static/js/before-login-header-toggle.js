const menu = document.getElementById('menu');
        const topbar = document.getElementById('topbar');
        const hamburger = document.getElementById('hamburger');

        hamburger.addEventListener('click', function (e) {
            e.stopPropagation();
            if (topbar.style.display === 'block') {
                topbar.style.display = 'none';
                hamburger.style.display = 'flex';
            } else {
                hamburger.style.display = 'flex';

                topbar.style.display = 'block';
            }
        });

        // Close menu when clicking outside
        document.addEventListener('click', function (e) {
            if (!topbar.contains(e.target) && e.target !== hamburger) {
                topbar.style.display = 'none';
            }
        });

        // Close menu when clicking a link
        function closeMenu() {
            topbar.style.display = 'none';
        }

        window.closeMenu = closeMenu;