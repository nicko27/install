// Documentation interactivity

// Smooth scrolling for anchor links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        document.querySelector(this.getAttribute('href')).scrollIntoView({
            behavior: 'smooth'
        });
    });
});

// Copy code blocks
document.querySelectorAll('pre code').forEach((block) => {
    const button = document.createElement('button');
    button.className = 'copy-button';
    button.textContent = 'Copy';
    
    block.parentNode.style.position = 'relative';
    block.parentNode.appendChild(button);
    
    button.addEventListener('click', async () => {
        try {
            await navigator.clipboard.writeText(block.textContent);
            button.textContent = 'Copied!';
            button.classList.add('copied');
            
            setTimeout(() => {
                button.textContent = 'Copy';
                button.classList.remove('copied');
            }, 2000);
        } catch (err) {
            console.error('Failed to copy text: ', err);
            button.textContent = 'Error';
            button.classList.add('error');
        }
    });
});

// Search functionality
const searchInput = document.getElementById('search');
const searchResults = document.getElementById('search-results');

if (searchInput && searchResults) {
    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase();
        const sections = document.querySelectorAll('section');
        const results = [];
        
        sections.forEach(section => {
            const title = section.querySelector('h2').textContent.toLowerCase();
            const content = section.textContent.toLowerCase();
            
            if (title.includes(query) || content.includes(query)) {
                results.push({
                    title: section.querySelector('h2').textContent,
                    id: section.id
                });
            }
        });
        
        displaySearchResults(results);
    });
}

function displaySearchResults(results) {
    searchResults.innerHTML = '';
    
    if (results.length === 0) {
        searchResults.innerHTML = '<p class="text-gray-600 p-4">No results found</p>';
        return;
    }
    
    const ul = document.createElement('ul');
    ul.className = 'divide-y';
    
    results.forEach(result => {
        const li = document.createElement('li');
        li.innerHTML = `
            <a href="#${result.id}" class="block p-4 hover:bg-gray-50">
                <h4 class="font-medium">${result.title}</h4>
            </a>
        `;
        ul.appendChild(li);
    });
    
    searchResults.appendChild(ul);
}

// Dark mode toggle
const darkModeToggle = document.getElementById('dark-mode-toggle');
if (darkModeToggle) {
    darkModeToggle.addEventListener('click', () => {
        document.documentElement.classList.toggle('dark');
        localStorage.setItem('darkMode', 
            document.documentElement.classList.contains('dark')
        );
    });
}

// Initialize dark mode from preference
if (localStorage.getItem('darkMode') === 'true' ||
    (localStorage.getItem('darkMode') === null && 
     window.matchMedia('(prefers-color-scheme: dark)').matches)) {
    document.documentElement.classList.add('dark');
}

// Mobile menu
const menuButton = document.getElementById('menu-button');
const sidebar = document.querySelector('.sidebar');

if (menuButton && sidebar) {
    menuButton.addEventListener('click', () => {
        sidebar.classList.toggle('show');
    });
}

// Version selector
const versionSelect = document.getElementById('version-select');
if (versionSelect) {
    versionSelect.addEventListener('change', (e) => {
        window.location.href = e.target.value;
    });
}

// API playground
const playground = document.getElementById('api-playground');
if (playground) {
    const editor = CodeMirror(playground, {
        mode: 'python',
        theme: 'monokai',
        lineNumbers: true,
        autoCloseBrackets: true,
        matchBrackets: true,
        indentUnit: 4
    });
    
    const runButton = document.getElementById('run-code');
    if (runButton) {
        runButton.addEventListener('click', () => {
            const code = editor.getValue();
            // Add code execution logic here
        });
    }
}
