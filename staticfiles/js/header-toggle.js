let isDropdownVisible = false;

function toggleDropdown() {
    isDropdownVisible = !isDropdownVisible;
    const dropdown = document.getElementById('pfpdropdown');
    dropdown.className = isDropdownVisible ? 'present' : 'not-present';
}

document.addEventListener('click', (event) => {
    const pfp = document.getElementById('pfp');
    const dropdown = document.getElementById('pfpdropdown');
    if (pfp && dropdown && !dropdown.contains(event.target) && !pfp.contains(event.target)) {
        isDropdownVisible = false;
        dropdown.className = 'not-present';
    }
});