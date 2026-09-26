// WordAiKit - Chat UI Application

const STORAGE_KEY = 'wordaikit_tasks';
const DEFAULT_PROMPT = '';

let tasks = [];
let currentTaskId = null;
let selectedFiles = [];
let currentModel = '';
let resultBlob = null;
let resultFileName = null;
let isProcessing = false;
let currentTab = 'deepseek';

// Initialize
window.addEventListener('DOMContentLoaded', () => {
    initTasks();
    setupEventListeners();
    loadModels();
    checkServiceStatus();
    autoResizeTextarea();
});

// ========== Task Management ==========

function initTasks() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
        try {
            tasks = JSON.parse(saved);
        } catch (e) {
            tasks = [];
        }
    }

    if (!Array.isArray(tasks) || tasks.length === 0) {
        tasks = [createTaskObject('新任务', DEFAULT_PROMPT)];
    }

    currentTaskId = tasks[0].id;
    renderTaskList();
    loadCurrentTask();
}

function createTaskObject(name, prompt) {
    return {
        id: 'task_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9),
        name: name || '新任务',
        prompt: prompt || '',
        createdAt: Date.now()
    };
}

function saveTasks() {
    // 只保存任务名称和提示词，不保存聊天记录与文件
    const toSave = tasks.map(t => ({
        id: t.id,
        name: t.name,
        prompt: t.prompt,
        createdAt: t.createdAt
    }));
    localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
}

function createNewTask() {
    const newTask = createTaskObject('新任务 ' + (tasks.length + 1), DEFAULT_PROMPT);
    tasks.unshift(newTask);
    currentTaskId = newTask.id;
    saveTasks();
    renderTaskList();
    loadCurrentTask();
}

function switchTask(taskId) {
    if (isProcessing) return;
    // 保存当前提示词
    saveCurrentPrompt();
    currentTaskId = taskId;
    renderTaskList();
    loadCurrentTask();
}

function deleteTask(taskId, event) {
    event.stopPropagation();
    if (isProcessing) return;
    if (tasks.length <= 1) {
        showToast('至少保留一个任务', 'warning');
        return;
    }
    tasks = tasks.filter(t => t.id !== taskId);
    if (currentTaskId === taskId) {
        currentTaskId = tasks[0].id;
    }
    saveTasks();
    renderTaskList();
    loadCurrentTask();
}

function getCurrentTask() {
    return tasks.find(t => t.id === currentTaskId) || tasks[0];
}

function saveCurrentPrompt() {
    const task = getCurrentTask();
    if (task) {
        const prompt = document.getElementById('promptInput').value.trim();
        task.prompt = prompt;
        saveTasks();
    }
}

function loadCurrentTask() {
    const task = getCurrentTask();
    if (!task) return;

    document.getElementById('currentTaskName').textContent = task.name;
    document.getElementById('promptInput').value = task.prompt || '';
    autoResizeTextarea();

    // 切换任务时清空当前文件和结果（文件不跨任务保存）
    selectedFiles = [];
    resultBlob = null;
    resultFileName = null;
    updateFilePreview();

    // 如果没有聊天记录，显示欢迎页
    const messages = document.getElementById('messages');
    const welcome = document.getElementById('welcomeView');
    messages.innerHTML = '';

    if (!task.messages || task.messages.length === 0) {
        messages.style.display = 'none';
        welcome.style.display = 'block';
    } else {
        welcome.style.display = 'none';
        messages.style.display = 'flex';
        task.messages.forEach(msg => appendMessageToDOM(msg));
        scrollToBottom();
    }
}

function renderTaskList() {
    const list = document.getElementById('taskList');
    list.innerHTML = '';

    tasks.forEach(task => {
        const item = document.createElement('div');
        item.className = 'task-item' + (task.id === currentTaskId ? ' active' : '');
        item.onclick = () => switchTask(task.id);

        const name = document.createElement('span');
        name.className = 'task-item-name';
        name.textContent = task.name;

        const delBtn = document.createElement('button');
        delBtn.className = 'task-item-delete';
        delBtn.textContent = '×';
        delBtn.onclick = (e) => deleteTask(task.id, e);

        item.appendChild(name);
        item.appendChild(delBtn);
        list.appendChild(item);
    });
}

// ========== Chat Messages ==========

function ensureMessagesVisible() {
    const welcome = document.getElementById('welcomeView');
    const messages = document.getElementById('messages');
    welcome.style.display = 'none';
    messages.style.display = 'flex';
}

function addMessage(role, content, options = {}) {
    const task = getCurrentTask();
    if (!task.messages) {
        task.messages = [];
    }

    const msg = {
        id: 'msg_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9),
        role,
        content,
        files: options.files || [],
        status: options.status || null,
        hasDownload: options.hasDownload || false,
        timestamp: Date.now()
    };

    task.messages.push(msg);
    saveTasks();
    ensureMessagesVisible();
    appendMessageToDOM(msg);
    scrollToBottom();
    return msg;
}

function updateMessage(msgId, updates) {
    const task = getCurrentTask();
    if (!task.messages) return;
    const msg = task.messages.find(m => m.id === msgId);
    if (!msg) return;

    Object.assign(msg, updates);
    saveTasks();

    // 更新 DOM
    const el = document.querySelector(`[data-msg-id="${msgId}"]`);
    if (el) {
        renderMessageContent(el, msg);
    }
}

function appendMessageToDOM(msg) {
    const messages = document.getElementById('messages');
    const el = document.createElement('div');
    el.className = 'message ' + msg.role;
    el.dataset.msgId = msg.id;

    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = msg.role === 'user' ? '我' : 'AI';

    const content = document.createElement('div');
    content.className = 'message-content';
    renderMessageContent(content, msg);

    el.appendChild(avatar);
    el.appendChild(content);
    messages.appendChild(el);
}

function renderMessageContent(container, msg) {
    container.innerHTML = '';

    // 文本内容
    const text = document.createElement('div');
    text.textContent = msg.content;
    container.appendChild(text);

    // 附件
    if (msg.files && msg.files.length > 0) {
        const filesDiv = document.createElement('div');
        filesDiv.className = 'message-files';
        msg.files.forEach(file => {
            const tag = document.createElement('span');
            tag.className = 'message-file-tag';
            tag.textContent = '📄 ' + file.name;
            filesDiv.appendChild(tag);
        });
        container.appendChild(filesDiv);
    }

    // 状态或下载
    if (msg.status || msg.hasDownload) {
        const actions = document.createElement('div');
        actions.className = 'message-actions';

        if (msg.status) {
            const status = document.createElement('div');
            status.className = 'message-status';
            if (msg.status === 'processing') {
                status.innerHTML = '<span class="spinner"></span> 正在处理...';
            } else {
                status.textContent = msg.status;
            }
            actions.appendChild(status);
        }

        if (msg.hasDownload) {
            const downloadBtn = document.createElement('button');
            downloadBtn.className = 'btn btn-success';
            downloadBtn.textContent = '⬇ 下载处理后的文档';
            downloadBtn.onclick = downloadResult;
            actions.appendChild(downloadBtn);
        }

        container.appendChild(actions);
    }
}

function scrollToBottom() {
    const container = document.getElementById('chatContainer');
    container.scrollTop = container.scrollHeight;
}

// ========== Event Listeners ==========

function setupEventListeners() {
    // 新建任务
    document.getElementById('newTaskBtn').addEventListener('click', createNewTask);

    // 任务名称编辑
    const taskNameEl = document.getElementById('currentTaskName');
    taskNameEl.addEventListener('blur', () => {
        const task = getCurrentTask();
        if (task) {
            const newName = taskNameEl.textContent.trim();
            task.name = newName || '新任务';
            saveTasks();
            renderTaskList();
        }
    });
    taskNameEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            taskNameEl.blur();
        }
    });

    // 文件上传
    document.getElementById('attachFileBtn').addEventListener('click', () => {
        document.getElementById('fileInput').click();
    });
    document.getElementById('fileInput').addEventListener('change', handleFileSelect);
    document.getElementById('filePreviewRemove').addEventListener('click', () => {
        selectedFiles = [];
        document.getElementById('fileInput').value = '';
        updateFilePreview();
    });

    // 输入框
    const promptInput = document.getElementById('promptInput');
    promptInput.addEventListener('input', () => {
        autoResizeTextarea();
        saveCurrentPrompt();
    });
    promptInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    });

    // 发送
    document.getElementById('sendBtn').addEventListener('click', handleSend);

    // 快捷按钮
    document.querySelectorAll('.quick-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            promptInput.value = btn.dataset.prompt;
            autoResizeTextarea();
            saveCurrentPrompt();
            promptInput.focus();
        });
    });

    // 模型切换
    document.getElementById('modelSelect').addEventListener('change', handleModelChange);

    // 配置模态框
    document.getElementById('openConfigBtn').addEventListener('click', openConfigModal);
    document.getElementById('closeConfigModal').addEventListener('click', closeConfigModal);
    document.getElementById('saveConfigBtn').addEventListener('click', saveCurrentConfig);
    document.getElementById('testConfigBtn').addEventListener('click', testCurrentConfig);
    document.getElementById('saveStoragePathBtn').addEventListener('click', saveStoragePath);

    // Tab 切换
    document.querySelectorAll('#configTabs .tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            openTab(btn.dataset.tab);
        });
    });

    // 点击模态框外部关闭
    document.getElementById('configModal').addEventListener('click', (e) => {
        if (e.target.id === 'configModal') {
            closeConfigModal();
        }
    });
}

function autoResizeTextarea() {
    const textarea = document.getElementById('promptInput');
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 160) + 'px';
}

function handleFileSelect(e) {
    const files = Array.from(e.target.files);
    const validFiles = files.filter(f => f.name.endsWith('.docx'));
    if (validFiles.length !== files.length) {
        showToast('仅支持 .docx 格式', 'warning');
    }
    if (validFiles.length > 0) {
        selectedFiles = validFiles;
        updateFilePreview();
    }
}

function updateFilePreview() {
    const preview = document.getElementById('filePreview');
    const nameEl = document.getElementById('filePreviewName');

    if (selectedFiles.length === 0) {
        preview.style.display = 'none';
        return;
    }

    preview.style.display = 'flex';
    if (selectedFiles.length === 1) {
        nameEl.textContent = '📄 ' + selectedFiles[0].name;
    } else {
        nameEl.textContent = `📄 已选择 ${selectedFiles.length} 个文档`;
    }
}

async function handleSend() {
    if (isProcessing) return;

    const promptInput = document.getElementById('promptInput');
    const prompt = promptInput.value.trim();

    if (!prompt && selectedFiles.length === 0) {
        showToast('请输入要求或上传文档', 'warning');
        return;
    }

    // 保存提示词
    saveCurrentPrompt();

    // 添加用户消息
    const userContent = prompt || '（未输入要求，直接处理文档）';
    addMessage('user', userContent, { files: selectedFiles.map(f => ({ name: f.name, size: f.size })) });

    // 清空输入
    promptInput.value = '';
    autoResizeTextarea();

    // 开始处理
    await processDocument(prompt, selectedFiles);
}

// ========== Processing ==========

async function processDocument(prompt, files) {
    isProcessing = true;
    const sendBtn = document.getElementById('sendBtn');
    sendBtn.disabled = true;

    const statusMsg = addMessage('system', '已收到请求，开始处理...', { status: 'processing' });

    try {
        if (files.length === 0) {
            throw new Error('请先上传要处理的文档');
        }

        updateMessage(statusMsg.id, { content: '正在上传文档...' });

        const formData = new FormData();
        files.forEach(file => formData.append('files', file));
        formData.append('user_prompt', prompt);

        updateMessage(statusMsg.id, { content: '正在调用 AI 进行自然语言润色，请稍候...' });

        const response = await fetch('/api/process-natural', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || '处理失败');
        }

        resultBlob = await response.blob();
        const contentDisposition = response.headers.get('Content-Disposition') || '';
        const match = contentDisposition.match(/filename\*=UTF-8''(.+)$/);
        resultFileName = match ? decodeURIComponent(match[1]) : 'nl_processed.docx';

        updateMessage(statusMsg.id, {
            content: '处理完成，文档已生成。',
            status: null,
            hasDownload: true
        });

        // 处理完成后清空已选文件
        selectedFiles = [];
        document.getElementById('fileInput').value = '';
        updateFilePreview();

    } catch (error) {
        updateMessage(statusMsg.id, {
            content: '处理失败：' + error.message,
            status: null,
            hasDownload: false
        });
        showToast('处理失败：' + error.message, 'error');
    } finally {
        isProcessing = false;
        sendBtn.disabled = false;
    }
}

function downloadResult() {
    if (!resultBlob) {
        showToast('没有可下载的文件', 'warning');
        return;
    }

    const url = window.URL.createObjectURL(resultBlob);
    const a = document.createElement('a');
    a.href = url;
    a.download = resultFileName || 'nl_processed.docx';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
    showToast('下载已开始', 'success');
}

// ========== Service & Models ==========

async function checkServiceStatus() {
    const dot = document.getElementById('serviceStatusDot');
    try {
        const response = await fetch('/api/');
        const data = await response.json();
        if (response.ok) {
            dot.className = 'status-dot online';
            dot.title = '服务正常运行';
            return data;
        }
        throw new Error('服务异常');
    } catch (error) {
        dot.className = 'status-dot offline';
        dot.title = '无法连接到服务';
        showToast('无法连接到后端服务', 'error');
        return null;
    }
}

async function loadModels() {
    try {
        const data = await checkServiceStatus();
        if (data && data.可用模型) {
            const select = document.getElementById('modelSelect');
            select.innerHTML = '';
            data.可用模型.forEach(model => {
                const option = document.createElement('option');
                option.value = model;
                option.textContent = model;
                if (model === data.current_model) {
                    option.selected = true;
                    currentModel = model;
                }
                select.appendChild(option);
            });
        }
    } catch (error) {
        console.error('加载模型列表失败:', error);
    }
}

async function handleModelChange(e) {
    const modelName = e.target.value;
    if (!modelName || modelName === currentModel) return;

    try {
        const response = await fetch(`/api/switch/${modelName}`);
        const data = await response.json();
        if (data.error) {
            showToast(data.error, 'error');
            e.target.value = currentModel;
        } else {
            currentModel = modelName;
            showToast(`已切换到模型：${modelName}`, 'success');
        }
    } catch (error) {
        showToast('切换模型失败', 'error');
        e.target.value = currentModel;
    }
}

// ========== Config Modal ==========

function openConfigModal() {
    document.getElementById('configModal').style.display = 'flex';
    loadConfigStatus();
    hideTestResult();
}

function closeConfigModal() {
    document.getElementById('configModal').style.display = 'none';
    hideTestResult();
}

function openTab(tabName) {
    document.querySelectorAll('#configTabs .tab-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));

    document.querySelector(`#configTabs .tab-btn[data-tab="${tabName}"]`).classList.add('active');
    document.getElementById(tabName).classList.add('active');
    currentTab = tabName;
}

async function loadConfigStatus() {
    try {
        const response = await fetch('/api/config/status');
        const data = await response.json();

        if (response.ok) {
            renderConfigStatus(data.config_status);

            Object.entries(data.config_status).forEach(([modelName, config]) => {
                if (config.has_config) {
                    document.getElementById(`${modelName}ApiKey`).value = '********';
                    document.getElementById(`${modelName}BaseUrl`).value = config.base_url;
                    document.getElementById(`${modelName}Model`).value = config.model;
                }
            });

            if (data.storage_path) {
                document.getElementById('storagePath').value = data.storage_path;
            }
        }
    } catch (error) {
        console.error('加载配置状态失败:', error);
    }
}

function renderConfigStatus(configStatus) {
    const container = document.getElementById('configStatus');
    container.innerHTML = '';

    const modelNames = {
        deepseek: 'DeepSeek',
        aliyun: '阿里百炼',
        kimi: 'Kimi',
        ollama: 'Ollama',
        lmstudio: 'LM Studio'
    };

    Object.entries(configStatus).forEach(([modelName, status]) => {
        const row = document.createElement('div');
        row.className = 'status-row';

        const label = document.createElement('span');
        label.textContent = modelNames[modelName] || modelName;

        const badge = document.createElement('span');
        badge.className = 'status-badge ' + (status.has_config ? 'configured' : 'not-configured');
        badge.textContent = status.has_config ? '已配置' : '未配置';

        row.appendChild(label);
        row.appendChild(badge);
        container.appendChild(row);
    });
}

async function saveCurrentConfig() {
    const apiKey = document.getElementById(`${currentTab}ApiKey`).value;
    const baseUrl = document.getElementById(`${currentTab}BaseUrl`).value;
    const model = document.getElementById(`${currentTab}Model`).value;

    if (!apiKey || apiKey === '********') {
        showToast('请输入有效的 API Key', 'warning');
        return;
    }

    try {
        const response = await fetch('/api/config/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model_name: currentTab,
                api_key: apiKey,
                base_url: baseUrl,
                model: model
            })
        });

        const data = await response.json();
        if (response.ok) {
            showToast('配置保存成功', 'success');
            await loadConfigStatus();
            await loadModels();
        } else {
            showToast(data.detail || '配置保存失败', 'error');
        }
    } catch (error) {
        showToast('配置保存失败：' + error.message, 'error');
    }
}

async function testCurrentConfig() {
    const apiKey = document.getElementById(`${currentTab}ApiKey`).value;
    const baseUrl = document.getElementById(`${currentTab}BaseUrl`).value;
    const model = document.getElementById(`${currentTab}Model`).value;

    if (!apiKey || apiKey === '********') {
        showTestResult('warning', '请输入 API Key', '请在当前模型的 API Key 输入框中填写有效的 API Key 后再进行测试。');
        return;
    }

    showTestResult('warning', '正在测试...', `正在测试 ${currentTab} 的配置，请稍候...`);

    try {
        const response = await fetch('/api/config/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model_name: currentTab,
                api_key: apiKey,
                base_url: baseUrl,
                model: model
            })
        });

        const data = await response.json();
        if (response.ok) {
            showTestResult('success', '配置测试成功', `${currentTab} 配置正确，AI 回复：${data.result}`);
        } else {
            showTestResult('error', '配置测试失败', data.detail || '未知错误');
        }
    } catch (error) {
        showTestResult('error', '配置测试失败', '网络请求异常：' + error.message);
    }
}

async function saveStoragePath() {
    const dirPath = document.getElementById('storagePath').value.trim();
    if (!dirPath) {
        showToast('请输入配置文件保存路径', 'warning');
        return;
    }

    try {
        const response = await fetch('/api/config/path', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ storage_path: dirPath })
        });

        const data = await response.json();
        if (response.ok) {
            document.getElementById('storagePath').value = data.storage_path;
            showToast('配置文件路径更改成功', 'success');
        } else {
            showToast(data.detail || '路径更改失败', 'error');
        }
    } catch (error) {
        showToast('网络请求异常：' + error.message, 'error');
    }
}

function showTestResult(type, title, content) {
    const resultDiv = document.getElementById('testResult');
    resultDiv.className = 'test-result ' + type + ' show';
    document.getElementById('testResultTitle').textContent = title;
    document.getElementById('testResultContent').textContent = content;
}

function hideTestResult() {
    document.getElementById('testResult').className = 'test-result';
}

// ========== Toast ==========

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        left: 50%;
        transform: translateX(-50%);
        padding: 10px 18px;
        border-radius: 8px;
        font-size: 13px;
        z-index: 2000;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        animation: fadeIn 0.2s ease;
    `;

    const colors = {
        success: { bg: '#dcfce7', color: '#166534', border: '#bbf7d0' },
        error: { bg: '#fee2e2', color: '#991b1b', border: '#fecaca' },
        warning: { bg: '#fef3c7', color: '#92400e', border: '#fde68a' },
        info: { bg: '#e0e7ff', color: '#3730a3', border: '#c7d2fe' }
    };

    const c = colors[type] || colors.info;
    toast.style.background = c.bg;
    toast.style.color = c.color;
    toast.style.border = `1px solid ${c.border}`;
    toast.textContent = message;

    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}
