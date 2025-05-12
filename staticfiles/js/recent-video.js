let activeMenuId = null;
let files = [
    {
        id: 347,
        name: "Id: 347 - If you're struggling to wake up because of back pain,",
        clips: 0,
        created: "Feb. 23, 2025, 12:37 p.m."
    }
];

function toggleMenu(event, fileId) {
    event.stopPropagation();
    const menu = document.getElementById(`actions-${fileId}`);
    if (activeMenuId === fileId) {
        menu.style.display = 'none';
        activeMenuId = null;
    } else {
        if (activeMenuId) {
            document.getElementById(`actions-${activeMenuId}`).style.display = 'none';
        }
        menu.style.display = 'block';
        activeMenuId = fileId;
    }
}

function deleteFile(fileId) {
    if (confirm("Are you sure you want to delete this file?")) {
        files = files.filter(file => file.id !== fileId);
        renderFiles();
        alert("File deleted successfully!");
    }
    if (activeMenuId === fileId) {
        document.getElementById(`actions-${fileId}`).style.display = 'none';
        activeMenuId = null;
    }
}

// function renderFiles() {
//     const log = document.querySelector('.log');
//     log.innerHTML = `
//         <div>
//             <div>
//                 <input type="checkbox" name="selectall" id="selectall" style="opacity: 0;">
//                 <div>Text Files</div>
//             </div>
//             <div>Clips</div>
//             <div>Created At</div>
//         </div>
//     `;
//     files.forEach(file => {
//         const logItem = document.createElement('div');
//         logItem.className = 'log-item';
//         logItem.dataset.fileId = file.id;
//         logItem.innerHTML = `
//             <div>
//                 <input type="checkbox" name="selectall" id="selectall" style="opacity: 0;">
//                 <div>
//                     <a href="/text/download_video/${file.id}/" class="link-tag">
//                         ${file.name}
//                     </a>
//                 </div>
//             </div>
//             <div>${file.clips}</div>
//             <div>${file.created}</div>
//             <img
//                 src="/images/dots.svg"
//                 class="menu"
//                 alt="Menu options"
//                 style="cursor: pointer;"
//                 onclick="toggleMenu(event, ${file.id})"
//             >
//             <div class="actions" id="actions-${file.id}" style="display: none; position: absolute; right: 20px; background: white; border: 1px solid #ddd; border-radius: 4px; padding: 5px;">
//                 <div>
//                     <a href="#" class="link-tag" onclick="deleteFile(${file.id})">
//                         <img src="/images/delete-icn.svg" alt="Delete Icon" style="width: 20px;">
//                         Delete
//                     </a>
//                 </div>
//             </div>
//         `;
//         log.appendChild(logItem);
//     });
// }

document.addEventListener('DOMContentLoaded', () => {
    renderFiles();
});