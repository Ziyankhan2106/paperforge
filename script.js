// ========== State Management ==========
const appState = {
    currentProject: null,
    projectName: null,
    paperType: null,
    content: null,
    selectedElement: null,
};

// ========== API Configuration ==========
const API_BASE = 'http://localhost:8000';

// ========== DOM Elements ==========
const loginPage = document.getElementById('loginPage');
const editorPage = document.getElementById('editorPage');
const projectNameInput = document.getElementById('projectName');
const paperTypeSelect = document.getElementById('paperType');
const startBlankBtn = document.getElementById('startBlankBtn');
const uploadDocxBtn = document.getElementById('uploadDocxBtn');
const docxFile = document.getElementById('docxFile');
const loginError = document.getElementById('loginError');
const loginLoading = document.getElementById('loginLoading');
const logoutBtn = document.getElementById('logoutBtn');

// Editor elements
const editorTitle = document.getElementById('editorTitle');
const projectInfo = document.getElementById('projectInfo');
const titleInput = document.getElementById('titleInput');
const abstractInput = document.getElementById('abstractInput');
const authorsContainer = document.getElementById('authorsContainer');
const addAuthorBtn = document.getElementById('addAuthorBtn');
const referencesContainer = document.getElementById('referencesContainer');
const addReferenceBtn = document.getElementById('addReferenceBtn');
const sectionsContainer = document.getElementById('sectionsContainer');
const documentStructure = document.getElementById('documentStructure');

// Toolbar buttons
const addSectionBtn = document.getElementById('addSectionBtn');
const addSubsectionBtn = document.getElementById('addSubsectionBtn');
const addSubsubsectionBtn = document.getElementById('addSubsubsectionBtn');
const compileBtn = document.getElementById('compileBtn');
const reviewBtn = document.getElementById('reviewBtn');
const saveBtn = document.getElementById('saveBtn');
const rephraseBtn = document.getElementById('rephraseBtn');

// Modal elements
const addSectionModal = document.getElementById('addSectionModal');
const addSubsectionModal = document.getElementById('addSubsectionModal');
const rephraseModal = document.getElementById('rephraseModal');
const reviewModal = document.getElementById('reviewModal');
const compilationModal = document.getElementById('compilationModal');

// ========== Event Listeners ==========
startBlankBtn.addEventListener('click', handleStartBlank);
uploadDocxBtn.addEventListener('click', () => docxFile.click());
docxFile.addEventListener('change', handleDocxUpload);
logoutBtn.addEventListener('click', handleLogout);
addSectionBtn.addEventListener('click', () => openModal(addSectionModal));
addSubsectionBtn.addEventListener('click', () => openModal(addSubsectionModal));
addAuthorBtn.addEventListener('click', addAuthorField);
addReferenceBtn.addEventListener('click', addReferenceField);
saveBtn.addEventListener('click', handleSaveProject);
compileBtn.addEventListener('click', handleCompile);
reviewBtn.addEventListener('click', handleReview);
rephraseBtn.addEventListener('click', handleRephrase);

// Modal close listeners
document.querySelectorAll('.close').forEach(closeBtn => {
    closeBtn.addEventListener('click', (e) => {
        e.target.closest('.modal').classList.remove('show');
    });
});

document.querySelectorAll('.cancel-btn').forEach(cancelBtn => {
    cancelBtn.addEventListener('click', (e) => {
        e.target.closest('.modal').classList.remove('show');
    });
});

// Modal confirm buttons
document.getElementById('confirmAddSection')?.addEventListener('click', confirmAddSection);
document.getElementById('confirmAddSubsection')?.addEventListener('click', confirmAddSubsection);
document.getElementById('confirmRephrase')?.addEventListener('click', confirmRephrase);
document.getElementById('generateRephrase')?.addEventListener('click', generateRephrase);

// ========== Event Handlers ==========
async function handleStartBlank() {
    const projectName = projectNameInput.value.trim();
    const paperType = paperTypeSelect.value;

    if (!projectName || !paperType) {
        showError('Please enter project name and select paper type');
        return;
    }

    try {
        showLoading(true);
        const response = await fetch(`${API_BASE}/create-project`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_name: projectName,
                paper_type: parseInt(paperType)
            })
        });

        if (!response.ok) throw new Error('Failed to create project');

        const data = await response.json();
        initializeEditor(projectName, paperType, data);
        transitionToEditor();
    } catch (error) {
        showError('Error creating project: ' + error.message);
    } finally {
        showLoading(false);
    }
}

async function handleDocxUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    const projectName = projectNameInput.value.trim();
    const paperType = paperTypeSelect.value;

    if (!projectName || !paperType) {
        showError('Please enter project name and select paper type');
        return;
    }

    try {
        showLoading(true);
        const formData = new FormData();
        formData.append('file', file);
        formData.append('project_name', projectName);
        formData.append('project_type', parseInt(paperType));

        const response = await fetch(`${API_BASE}/convert-paper`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) throw new Error('Failed to upload document');

        const data = await response.json();
        initializeEditor(projectName, paperType, data);
        transitionToEditor();
    } catch (error) {
        showError('Error uploading document: ' + error.message);
    } finally {
        showLoading(false);
    }
}

function handleLogout() {
    appState.currentProject = null;
    appState.projectName = null;
    appState.paperType = null;
    appState.content = null;

    projectNameInput.value = '';
    paperTypeSelect.value = '';
    loginError.classList.remove('show');

    transitionToLogin();
}

async function handleSaveProject() {
    if (!appState.projectName || !appState.content) return;

    try {
        saveBtn.disabled = true;
        const response = await fetch(`${API_BASE}/update-project`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_name: appState.projectName,
                content: appState.content
            })
        });

        if (!response.ok) throw new Error('Failed to save project');

        showNotification('Project saved successfully!', 'success');
    } catch (error) {
        showNotification('Error saving project: ' + error.message, 'error');
    } finally {
        saveBtn.disabled = false;
    }
}

async function handleCompile() {
    if (!appState.projectName || !appState.content) return;

    try {
        compilationModal.classList.add('show');
        const response = await fetch(`${API_BASE}/compile`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_name: appState.projectName,
                content: appState.content
            })
        });

        if (!response.ok) throw new Error('Compilation failed');

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${appState.projectName}.pdf`;
        a.click();

        compilationModal.classList.remove('show');
        showNotification('PDF compiled successfully!', 'success');
    } catch (error) {
        compilationModal.classList.remove('show');
        showNotification('Error compiling PDF: ' + error.message, 'error');
    }
}

async function handleReview() {
    if (!appState.projectName || !appState.content) return;

    try {
        compilationModal.classList.add('show');
        const response = await fetch(`${API_BASE}/review`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_name: appState.projectName,
                content: appState.content
            })
        });

        if (!response.ok) throw new Error('Review failed');

        const reviewData = await response.json();
        compilationModal.classList.remove('show');
        displayReview(reviewData);
    } catch (error) {
        compilationModal.classList.remove('show');
        showNotification('Error reviewing paper: ' + error.message, 'error');
    }
}

function handleRephrase() {
    const selectedText = window.getSelection().toString();
    if (!selectedText) {
        showNotification('Please select text to rephrase', 'warning');
        return;
    }

    document.getElementById('originalText').textContent = selectedText;
    document.getElementById('rephrasedText').value = '';
    openModal(rephraseModal);
}

async function generateRephrase() {
    const selectedText = document.getElementById('originalText').textContent;
    const style = document.getElementById('rephraseStyle').value;

    try {
        const response = await fetch(`${API_BASE}/rephrase`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: selectedText,
                style: style
            })
        });

        if (!response.ok) throw new Error('Rephrase failed');

        const data = await response.json();
        document.getElementById('rephrasedText').value = data.rephrased_text || data.text;
    } catch (error) {
        showNotification('Error generating rephrase: ' + error.message, 'error');
    }
}

function confirmRephrase() {
    const rephrasedText = document.getElementById('rephrasedText').value;
    if (!rephrasedText) {
        showNotification('No rephrased text to insert', 'warning');
        return;
    }

    document.execCommand('insertText', false, rephrasedText);
    rephraseModal.classList.remove('show');
}

function confirmAddSection() {
    const title = document.getElementById('sectionTitle').value.trim();
    const content = document.getElementById('sectionContent').value.trim();

    if (!title) {
        showNotification('Please enter section title', 'warning');
        return;
    }

    const section = {
        title: title,
        content: content,
        subsections: [],
        paragraphs: content ? [{ text: content }] : []
    };

    if (!appState.content.sections) {
        appState.content.sections = [];
    }

    appState.content.sections.push(section);

    document.getElementById('sectionTitle').value = '';
    document.getElementById('sectionContent').value = '';
    addSectionModal.classList.remove('show');

    renderSections();
    updateStructure();
    showNotification('Section added successfully!', 'success');
}

function confirmAddSubsection() {
    const parentIndex = document.getElementById('parentSection').value;
    const title = document.getElementById('subsectionTitle').value.trim();
    const content = document.getElementById('subsectionContent').value.trim();

    if (!title || parentIndex === '') {
        showNotification('Please select parent section and enter subsection title', 'warning');
        return;
    }

    const subsection = {
        title: title,
        content: content,
        paragraphs: content ? [{ text: content }] : []
    };

    if (!appState.content.sections[parentIndex].subsections) {
        appState.content.sections[parentIndex].subsections = [];
    }

    appState.content.sections[parentIndex].subsections.push(subsection);

    document.getElementById('subsectionTitle').value = '';
    document.getElementById('subsectionContent').value = '';
    addSubsectionModal.classList.remove('show');

    renderSections();
    updateStructure();
    showNotification('Subsection added successfully!', 'success');
}

// ========== Editor Functions ==========
function initializeEditor(projectName, paperType, content) {
    appState.projectName = projectName;
    appState.paperType = paperType;
    appState.content = content;

    editorTitle.textContent = projectName;
    projectInfo.textContent = `Type: ${paperType === '1' ? 'Single Column (NeurIPS)' : 'Double Column (CVPR)'}`;

    // Populate content
    if (content.title) titleInput.value = content.title;
    if (content.abstract) abstractInput.value = content.abstract;
    if (content.authors) renderAuthors();
    if (content.references) renderReferences();
    if (content.sections) renderSections();

    updateStructure();
}

function renderAuthors() {
    authorsContainer.innerHTML = '';
    appState.content.authors?.forEach((author, idx) => {
        const authorDiv = document.createElement('div');
        authorDiv.className = 'author-item';
        authorDiv.innerHTML = `
            <div class="author-inputs">
                <input type="text" value="${author.name || ''}" placeholder="Name" 
                       data-idx="${idx}" data-field="name" class="author-input">
                <input type="text" value="${author.affiliation || ''}" placeholder="Affiliation" 
                       data-idx="${idx}" data-field="affiliation" class="author-input">
            </div>
            <button class="author-remove" onclick="removeAuthor(${idx})">Remove</button>
        `;
        authorsContainer.appendChild(authorDiv);
    });
}

function renderReferences() {
    referencesContainer.innerHTML = '';
    appState.content.references?.forEach((ref, idx) => {
        const refDiv = document.createElement('div');
        refDiv.className = 'reference-item';
        refDiv.innerHTML = `
            <div class="reference-id">[${idx + 1}]</div>
            <div class="reference-citation">${ref.citation || ref.text || ''}</div>
            <button class="reference-remove" onclick="removeReference(${idx})">Remove</button>
        `;
        referencesContainer.appendChild(refDiv);
    });
}

function renderSections() {
    sectionsContainer.innerHTML = '';
    appState.content.sections?.forEach((section, sIdx) => {
        const sectionDiv = document.createElement('div');
        sectionDiv.className = 'section-block';

        let subsectionsHTML = '';
        if (section.subsections) {
            section.subsections.forEach((subsection, ssIdx) => {
                subsectionsHTML += `
                    <div class="subsection-block">
                        <div class="section-header">
                            <div class="section-title">${subsection.title}</div>
                            <div class="section-actions">
                                <button class="section-action-btn" onclick="editSubsection(${sIdx}, ${ssIdx})">Edit</button>
                                <button class="section-action-btn" onclick="removeSubsection(${sIdx}, ${ssIdx})">Delete</button>
                            </div>
                        </div>
                        <div class="section-content">${subsection.content || subsection.paragraphs?.map(p => p.text).join(' ') || ''}</div>
                    </div>
                `;
            });
        }

        sectionDiv.innerHTML = `
            <div class="section-header">
                <div class="section-title">${section.title}</div>
                <div class="section-actions">
                    <button class="section-action-btn" onclick="editSection(${sIdx})">Edit</button>
                    <button class="section-action-btn" onclick="removeSection(${sIdx})">Delete</button>
                </div>
            </div>
            <div class="section-content">${section.content || section.paragraphs?.map(p => p.text).join(' ') || ''}</div>
            ${subsectionsHTML}
        `;

        sectionsContainer.appendChild(sectionDiv);
    });
}

function updateStructure() {
    documentStructure.innerHTML = '';

    // Add title
    const titleNode = document.createElement('div');
    titleNode.className = 'tree-node';
    titleNode.innerHTML = '<div class="tree-node-label"><span class="icon">📄</span><span>Title</span></div>';
    documentStructure.appendChild(titleNode);

    // Add abstract
    const abstractNode = document.createElement('div');
    abstractNode.className = 'tree-node';
    abstractNode.innerHTML = '<div class="tree-node-label"><span class="icon">📝</span><span>Abstract</span></div>';
    documentStructure.appendChild(abstractNode);

    // Add sections
    appState.content.sections?.forEach((section, idx) => {
        const sectionNode = document.createElement('div');
        sectionNode.className = 'tree-node';
        sectionNode.innerHTML = `<div class="tree-node-label"><span class="icon">📋</span><span>${section.title}</span></div>`;

        if (section.subsections && section.subsections.length > 0) {
            const childrenDiv = document.createElement('div');
            childrenDiv.className = 'tree-children';

            section.subsections.forEach(subsection => {
                const subNode = document.createElement('div');
                subNode.className = 'tree-node';
                subNode.innerHTML = `<div class="tree-node-label"><span class="icon">└─</span><span>${subsection.title}</span></div>`;
                childrenDiv.appendChild(subNode);
            });

            sectionNode.appendChild(childrenDiv);
        }

        documentStructure.appendChild(sectionNode);
    });

    // Add references
    const refNode = document.createElement('div');
    refNode.className = 'tree-node';
    refNode.innerHTML = '<div class="tree-node-label"><span class="icon">📚</span><span>References</span></div>';
    documentStructure.appendChild(refNode);
}

// ========== Content Modification Functions ==========
function addAuthorField() {
    if (!appState.content.authors) {
        appState.content.authors = [];
    }
    appState.content.authors.push({ name: '', affiliation: '' });
    renderAuthors();
}

function removeAuthor(idx) {
    appState.content.authors.splice(idx, 1);
    renderAuthors();
}

function addReferenceField() {
    if (!appState.content.references) {
        appState.content.references = [];
    }
    appState.content.references.push({ citation: '' });
    renderReferences();
}

function removeReference(idx) {
    appState.content.references.splice(idx, 1);
    renderReferences();
}

function removeSection(idx) {
    appState.content.sections.splice(idx, 1);
    renderSections();
    updateStructure();
}

function removeSubsection(sIdx, ssIdx) {
    appState.content.sections[sIdx].subsections.splice(ssIdx, 1);
    renderSections();
    updateStructure();
}

function editSection(idx) {
    const section = appState.content.sections[idx];
    document.getElementById('sectionTitle').value = section.title;
    document.getElementById('sectionContent').value = section.content || '';

    const modal = document.getElementById('addSectionModal');
    const confirmBtn = document.getElementById('confirmAddSection');

    confirmBtn.onclick = () => {
        section.title = document.getElementById('sectionTitle').value;
        section.content = document.getElementById('sectionContent').value;
        document.getElementById('sectionTitle').value = '';
        document.getElementById('sectionContent').value = '';
        modal.classList.remove('show');
        renderSections();
        updateStructure();
    };

    openModal(modal);
}

function editSubsection(sIdx, ssIdx) {
    const subsection = appState.content.sections[sIdx].subsections[ssIdx];
    document.getElementById('subsectionTitle').value = subsection.title;
    document.getElementById('subsectionContent').value = subsection.content || '';

    const modal = document.getElementById('addSubsectionModal');
    const confirmBtn = document.getElementById('confirmAddSubsection');

    confirmBtn.onclick = () => {
        subsection.title = document.getElementById('subsectionTitle').value;
        subsection.content = document.getElementById('subsectionContent').value;
        document.getElementById('subsectionTitle').value = '';
        document.getElementById('subsectionContent').value = '';
        modal.classList.remove('show');
        renderSections();
        updateStructure();
    };

    openModal(modal);
}

// Update content fields on input
titleInput?.addEventListener('input', (e) => {
    appState.content.title = e.target.value;
});

abstractInput?.addEventListener('input', (e) => {
    appState.content.abstract = e.target.value;
});

document.addEventListener('change', (e) => {
    if (e.target.classList.contains('author-input')) {
        const idx = parseInt(e.target.dataset.idx);
        const field = e.target.dataset.field;
        appState.content.authors[idx][field] = e.target.value;
    }
});

// ========== Modal Functions ==========
function openModal(modal) {
    modal.classList.add('show');
}

function closeModal(modal) {
    modal.classList.remove('show');
}

// ========== Display Functions ==========
function displayReview(reviewData) {
    const reviewContent = document.getElementById('reviewContent');
    reviewContent.innerHTML = '';

    // Overall score
    if (reviewData.overall_score !== undefined) {
        const scoreDiv = document.createElement('div');
        scoreDiv.className = 'score-item';
        scoreDiv.innerHTML = `
            <div class="score-header">
                <span>Overall Score</span>
                <span>${reviewData.overall_score}/10</span>
            </div>
            <div class="score-bar">
                <div class="score-fill" style="width: ${reviewData.overall_score * 10}%"></div>
            </div>
        `;
        reviewContent.appendChild(scoreDiv);
    }

    // Strengths
    if (reviewData.strengths) {
        const strengthsDiv = document.createElement('div');
        strengthsDiv.className = 'review-section';
        strengthsDiv.innerHTML = '<h4>Strengths</h4>';
        const ul = document.createElement('ul');
        ul.className = 'recommendation-list';
        reviewData.strengths.forEach(strength => {
            const li = document.createElement('li');
            li.className = 'recommendation-item';
            li.textContent = strength;
            ul.appendChild(li);
        });
        strengthsDiv.appendChild(ul);
        reviewContent.appendChild(strengthsDiv);
    }

    // Weaknesses
    if (reviewData.weaknesses) {
        const weaknessesDiv = document.createElement('div');
        weaknessesDiv.className = 'review-section';
        weaknessesDiv.innerHTML = '<h4>Areas for Improvement</h4>';
        const ul = document.createElement('ul');
        ul.className = 'recommendation-list';
        reviewData.weaknesses.forEach(weakness => {
            const li = document.createElement('li');
            li.className = 'recommendation-item';
            li.textContent = weakness;
            ul.appendChild(li);
        });
        weaknessesDiv.appendChild(ul);
        reviewContent.appendChild(weaknessesDiv);
    }

    // Recommendations
    if (reviewData.recommendations) {
        const recsDiv = document.createElement('div');
        recsDiv.className = 'review-section';
        recsDiv.innerHTML = '<h4>Recommendations</h4>';
        const ul = document.createElement('ul');
        ul.className = 'recommendation-list';
        reviewData.recommendations.forEach(rec => {
            const li = document.createElement('li');
            li.className = 'recommendation-item';
            li.textContent = rec;
            ul.appendChild(li);
        });
        recsDiv.appendChild(ul);
        reviewContent.appendChild(recsDiv);
    }

    openModal(reviewModal);
}

// ========== UI Helper Functions ==========
function transitionToEditor() {
    loginPage.classList.remove('active');
    editorPage.classList.add('active');
}

function transitionToLogin() {
    loginPage.classList.add('active');
    editorPage.classList.remove('active');
}

function showError(message) {
    loginError.textContent = message;
    loginError.classList.add('show');
    setTimeout(() => {
        loginError.classList.remove('show');
    }, 5000);
}

function showLoading(show) {
    loginLoading.style.display = show ? 'flex' : 'none';
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 16px 20px;
        border-radius: 6px;
        background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#f59e0b'};
        color: white;
        font-weight: 600;
        z-index: 2000;
        animation: slideIn 0.3s ease;
    `;
    notification.textContent = message;
    document.body.appendChild(notification);

    setTimeout(() => {
        notification.remove();
    }, 3000);
}

// ========== Initialization ==========
document.addEventListener('DOMContentLoaded', () => {
    console.log('IdeaOverflow Editor loaded');
});
