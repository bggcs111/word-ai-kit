// WordAiKit - Main JavaScript Application

// Global Variables
let selectedFile = null;
let resultFileName = null;
let currentTab = 'deepseek';

// Initialize Application
window.addEventListener('DOMContentLoaded', () => {
    checkServiceStatus();
    loadModels();
    loadConfigStatus();
    setupEventListeners();
});

// Event Listeners Setup
function setupEventListeners() {
    // File input listener
    const fileInput = document.getElementById('fileInput');
    fileInput.addEventListener('change', handleFileSelect);
    
    // Drag and drop listeners - setup on the drop zone only
    const dropZone = document.getElementById('fileLabel');
    
    // Prevent default drag behaviors on drop zone
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });
    
    // Prevent default on document to stop browser from opening file
    ['dragover', 'drop'].forEach(eventName => {
        document.addEventListener(eventName, preventDefaults, false);
    });
    
    // Highlight drop area when dragging over
    dropZone.addEventListener('dragenter', highlight, false);
    dropZone.addEventListener('dragover', highlight, false);
    dropZone.addEventListener('dragleave', unhighlight, false);
    dropZone.addEventListener('drop', handleDrop, false);
    
    // Model selector listener
    document.getElementById('modelSelect').addEventListener('change', handleModelChange);
    
    // Modal close on outside click
    window.onclick = handleModalOutsideClick;
}

// Prevent default drag behaviors - VERY IMPORTANT to stop browser from opening file
function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
    return false;
}

// Highlight drop area
function highlight(e) {
    e.preventDefault();
    e.stopPropagation();
    document.getElementById('fileLabel').classList.add('drag-over');
}

// Remove highlight
function unhighlight(e) {
    e.preventDefault();
    e.stopPropagation();
    document.getElementById('fileLabel').classList.remove('drag-over');
}

// Handle dropped files
function handleDrop(e) {
    // MUST prevent default here!
    e.preventDefault();
    e.stopPropagation();
    
    unhighlight(e);
    
    const dt = e.dataTransfer;
    const files = dt.files;
    
    if (files.length > 0) {
        const file = files[0];
        // Check if file is .docx
        if (file.name.endsWith('.docx')) {
            selectedFile = file;
            updateFileLabel(file.name);
            document.getElementById('processBtn').disabled = false;
            addLog(`📄 通过拖拽选择文件：${file.name}`);
        } else {
            showAlert('请上传 .docx 格式的 Word 文档', 'error');
            addLog(`❌ 不支持的文件格式：${file.name}`);
        }
    }
    
    return false;
}

// File Selection Handler
function handleFileSelect(e) {
    const file = e.target.files[0];
    if (file) {
        selectedFile = file;
        updateFileLabel(file.name);
        document.getElementById('processBtn').disabled = false;
    }
}

// Model Change Handler
async function handleModelChange(e) {
    const modelName = e.target.value;
    if (modelName) {
        await switchModel(modelName);
    }
}

// Modal Outside Click Handler
function handleModalOutsideClick(event) {
    const modal = document.getElementById('configModal');
    if (event.target === modal) {
        closeConfigModal();
    }
}

// Service Status
async function checkServiceStatus() {
    try {
        const response = await fetch('/api/');
        const data = await response.json();
        
        document.getElementById('currentModel').textContent = data.current_model || '未知';
        document.getElementById('serviceStatus').textContent = '✅ 正常运行';
        document.getElementById('serviceStatus').style.color = '#28a745';
        
        return data;
    } catch (error) {
        document.getElementById('serviceStatus').textContent = '❌ 无法连接';
        document.getElementById('serviceStatus').style.color = '#dc3545';
        showAlert('无法连接到服务，请确保后端服务已启动', 'error');
        return null;
    }
}

// Load Models
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
                }
                select.appendChild(option);
            });
        }
    } catch (error) {
        console.error('加载模型列表失败:', error);
    }
}

// Switch Model
async function switchModel(modelName) {
    try {
        addLog('🔄 正在切换模型：' + modelName);
        const response = await fetch(`/api/switch/${modelName}`);
        const data = await response.json();
        
        if (data.error) {
            addLog('❌ 切换失败：' + data.error);
            showAlert(data.error, 'warning');
        } else {
            addLog('✅ 模型已切换：' + modelName);
            document.getElementById('currentModel').textContent = modelName;
            await checkServiceStatus();
        }
    } catch (error) {
        addLog('❌ 切换失败：' + error.message);
        showAlert(`切换模型失败：${error.message}`, 'error');
    }
}

// Process Document
async function processDocument() {
    if (!selectedFile) {
        showAlert('请先选择要处理的文档', 'warning');
        return;
    }

    clearPreviousState();

    const processBtn = document.getElementById('processBtn');
    const progressContainer = document.getElementById('progressContainer');
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');

    try {
        processBtn.disabled = true;
        processBtn.innerHTML = '<span class="loading-spinner"></span> 处理中...';
        progressContainer.classList.add('show');
        progressFill.style.width = '30%';
        progressText.textContent = '正在上传文档...';
        addLog('📤 开始上传文档：' + selectedFile.name);

        const formData = new FormData();
        formData.append('file', selectedFile);

        progressFill.style.width = '50%';
        progressText.textContent = '正在处理文档...';
        addLog('🔄 正在处理文档...');

        const response = await fetch('/api/process', {
            method: 'POST',
            body: formData
        });

        progressFill.style.width = '80%';
        progressText.textContent = '正在生成结果...';
        addLog('📝 正在生成结果...');

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || '处理失败');
        }

        const blob = await response.blob();
        resultFileName = `processed_${selectedFile.name}`;
        window.resultBlob = blob;
        
        // 获取文档类型并显示（简单的 ASCII 标识）
        const docType = response.headers.get('X-Doc-Type');
        
        if (docType) {
            console.log('文档类型:', docType);
            
            // 文档类型映射（英文标识 -> 中文显示）
            const typeMap = {
                'Technical Design': '📊 文档类型：技术方案/设计文档',
                'Academic Paper': '📊 文档类型：学术论文',
                'Test Report': '📊 文档类型：测试报告',
                'Survey Report': '📊 文档类型：调研报告',
                'Project Document': '📊 文档类型：项目文档',
                'Other': '📊 文档类型：其他类型'
            };
            
            const typeText = typeMap[docType] || `📊 文档类型：${docType}`;
            addLog(typeText);
        }
        
        progressFill.style.width = '100%';
        progressText.textContent = '处理完成！';
        addLog('✅ 文档处理成功：' + resultFileName);
        addLog('💾 结果已准备下载');
        
        showResult(selectedFile.name, resultFileName);

    } catch (error) {
        const errorMsg = `处理失败：${error.message}`;
        addLog('❌ ' + errorMsg);
        showAlert(errorMsg, 'error');
        progressContainer.classList.remove('show');
    } finally {
        processBtn.disabled = false;
        processBtn.innerHTML = '🚀 开始处理';
        
        setTimeout(() => {
            progressContainer.classList.remove('show');
            progressFill.style.width = '0%';
        }, 2000);
    }
}

// Show Result
function showResult(inputFile, outputFile) {
    const resultSection = document.getElementById('resultSection');
    const resultTitle = document.getElementById('resultTitle');
    const resultDesc = document.getElementById('resultDesc');

    resultTitle.textContent = '✅ 处理成功';
    resultDesc.textContent = `原始文件：${inputFile}\n处理后文件：${outputFile}`;
    resultSection.classList.add('show');
}

// Download Result
function downloadResult() {
    if (!window.resultBlob) {
        showAlert('没有可下载的文件', 'warning');
        return;
    }

    const url = window.URL.createObjectURL(window.resultBlob);
    const a = document.createElement('a');
    a.href = url;
    a.download = resultFileName || 'processed_document.docx';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);

    showAlert('下载已开始', 'success');
}

// Update File Label
function updateFileLabel(fileName) {
    const label = document.getElementById('fileLabel');
    label.classList.add('has-file');
    label.innerHTML = `
        <div class="file-icon">📄</div>
        <div class="file-name">${fileName}</div>
        <div class="file-hint">文件大小：${formatFileSize(selectedFile.size)}</div>
    `;
}

// Format File Size
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
}

// Show Alert
function showAlert(message, type) {
    const container = document.getElementById('alertContainer');
    const alert = document.createElement('div');
    alert.className = `alert alert-${type} show`;
    
    const icons = {
        success: '✅',
        error: '❌',
        warning: '⚠️',
        info: 'ℹ️'
    };

    alert.innerHTML = `
        <span style="font-size: 20px;">${icons[type]}</span>
        <span style="flex: 1;">${message.replace(/\n/g, '<br>')}</span>
        <span class="alert-close" onclick="this.parentElement.remove()" title="关闭">✖</span>
    `;

    container.appendChild(alert);

    if (type !== 'error') {
        setTimeout(() => {
            alert.classList.remove('show');
            setTimeout(() => alert.remove(), 300);
        }, 5000);
    }
}

// Add Log
function addLog(message) {
    const logBox = document.getElementById('logBox');
    const timestamp = new Date().toLocaleTimeString('zh-CN');
    const logEntry = `[${timestamp}] ${message}\n`;
    logBox.value += logEntry;
    logBox.scrollTop = logBox.scrollHeight;
}

// Clear Logs
function clearLogs() {
    const logBox = document.getElementById('logBox');
    logBox.value = '';
    addLog('🗑️ 日志已清除');
}

// Clear Previous State
function clearPreviousState() {
    const resultSection = document.getElementById('resultSection');
    resultSection.classList.remove('show');
    
    const logBox = document.getElementById('logBox');
    logBox.value = '';
    addLog('🔄 开始新的处理任务');
    
    const alertContainer = document.getElementById('alertContainer');
    alertContainer.innerHTML = '';
}

// Configuration Management
function openConfigModal() {
    document.getElementById('configModal').style.display = 'flex';
    loadConfigStatus();
}

function closeConfigModal() {
    document.getElementById('configModal').style.display = 'none';
    hideTestResult();
}

// Save Storage Path
async function saveStoragePath() {
    const dirPath = document.getElementById('storagePath').value.trim();
    
    if (!dirPath) {
        showAlert('请输入配置文件保存路径', 'warning');
        return;
    }
    
    const confirmMsg = `确定要将配置文件保存到以下目录吗？\n\n${dirPath}\n\n注意：配置文件不能保存在项目目录中。`;
    if (!confirm(confirmMsg)) {
        return;
    }
    
    try {
        const response = await fetch('/api/config/path', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                storage_path: dirPath
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            document.getElementById('storagePath').value = data.storage_path;
            showAlert('配置文件路径更改成功！', 'success');
            addLog(`✅ 配置文件路径已更改：${data.storage_path}`);
        } else {
            const errorMsg = data.detail || '路径更改失败';
            showAlert(errorMsg, 'error');
            addLog(`❌ 配置文件路径更改失败：${errorMsg}`);
        }
    } catch (error) {
        showAlert('网络请求异常：' + error.message, 'error');
        addLog(`❌ 配置文件路径更改失败：${error.message}`);
    }
}

// Tab Management
function openTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    document.getElementById(tabName).classList.add('active');
    document.querySelector(`.tab-btn[onclick="openTab('${tabName}')"]`).classList.add('active');
    
    currentTab = tabName;
}

// Load Config Status
async function loadConfigStatus() {
    try {
        const response = await fetch('/api/config/status');
        const data = await response.json();
        
        if (response.ok) {
            updateConfigStatus(data.config_status);
            
            for (const [modelName, config] of Object.entries(data.config_status)) {
                if (config.has_config) {
                    document.getElementById(`${modelName}ApiKey`).value = '********';
                    document.getElementById(`${modelName}BaseUrl`).value = config.base_url;
                    document.getElementById(`${modelName}Model`).value = config.model;
                }
            }
            
            if (data.storage_path) {
                document.getElementById('storagePath').value = data.storage_path;
            }
        }
    } catch (error) {
        console.error('加载配置状态失败:', error);
    }
}

// Update Config Status
function updateConfigStatus(configStatus) {
    for (const [modelName, status] of Object.entries(configStatus)) {
        const statusElement = document.getElementById(`${modelName}Status`);
        if (statusElement) {
            if (status.has_config) {
                statusElement.textContent = '已配置';
                statusElement.className = 'status-badge configured';
            } else {
                statusElement.textContent = '未配置';
                statusElement.className = 'status-badge not-configured';
            }
        }
    }
}

// Save Current Config
async function saveCurrentConfig() {
    const modelName = currentTab;
    const apiKey = document.getElementById(`${modelName}ApiKey`).value;
    const baseUrl = document.getElementById(`${modelName}BaseUrl`).value;
    const model = document.getElementById(`${modelName}Model`).value;

    if (!apiKey || apiKey === '********') {
        showAlert('请输入有效的 API Key', 'warning');
        return;
    }

    try {
        const response = await fetch('/api/config/save', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                model_name: modelName,
                api_key: apiKey,
                base_url: baseUrl,
                model: model
            })
        });

        const data = await response.json();
        
        if (response.ok) {
            showAlert('配置保存成功', 'success');
            addLog(`✅ 配置保存成功：${modelName}`);
            await loadConfigStatus();
            await loadModels();
        } else {
            showAlert(data.detail || '配置保存失败', 'error');
            addLog(`❌ 配置保存失败：${data.detail || '未知错误'}`);
        }
    } catch (error) {
        showAlert(`配置保存失败：${error.message}`, 'error');
        addLog(`❌ 配置保存失败：${error.message}`);
    }
}

// Test Result Display
function showTestResult(type, title, content) {
    const resultDiv = document.getElementById('testResult');
    const titleDiv = document.getElementById('testResultTitle');
    const contentDiv = document.getElementById('testResultContent');
    
    resultDiv.classList.remove('success', 'error', 'warning');
    resultDiv.classList.add(type);
    resultDiv.classList.add('show');
    
    titleDiv.textContent = title;
    contentDiv.textContent = content;
}

function hideTestResult() {
    const resultDiv = document.getElementById('testResult');
    resultDiv.classList.remove('show');
}

// Test Current Config
async function testCurrentConfig() {
    const modelName = currentTab;
    const apiKey = document.getElementById(`${modelName}ApiKey`).value;
    const baseUrl = document.getElementById(`${modelName}BaseUrl`).value;
    const model = document.getElementById(`${modelName}Model`).value;

    if (!apiKey || apiKey === '********') {
        showTestResult('warning', '⚠️ 请输入 API Key', '请在当前模型的 API Key 输入框中填写有效的 API Key 后再进行测试。');
        return;
    }

    showTestResult('warning', '🔄 正在测试...', `正在测试 ${modelName} 的配置，请稍候...`);

    try {
        const response = await fetch('/api/config/test', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                model_name: modelName,
                api_key: apiKey,
                base_url: baseUrl,
                model: model
            })
        });

        const data = await response.json();
        
        if (response.ok) {
            showTestResult('success', '✅ 配置测试成功', `${modelName} 配置正确，AI 服务响应正常。\n\n模型回复：${data.result}`);
            addLog(`✅ 配置测试成功：${modelName} - ${data.result}`);
        } else {
            let errorMsg = data.detail || '配置测试失败';
            let userFriendlyMsg = errorMsg;
            
            if (errorMsg.includes('认证') || errorMsg.includes('API Key') || errorMsg.includes('401')) {
                userFriendlyMsg = 'API Key 无效或已过期，请检查 API Key 是否正确。';
            } else if (errorMsg.includes('模型') || errorMsg.includes('model')) {
                userFriendlyMsg = '模型名称无效，请检查模型名称是否正确。';
            } else if (errorMsg.includes('网络') || errorMsg.includes('连接') || errorMsg.includes('timeout')) {
                userFriendlyMsg = '网络连接问题，请检查网络连接和 Base URL 是否正确。';
            }
            
            showTestResult('error', '❌ 配置测试失败', `${userFriendlyMsg}\n\n详细错误：${errorMsg}`);
            addLog(`❌ 配置测试失败：${errorMsg}`);
        }
    } catch (error) {
        showTestResult('error', '❌ 配置测试失败', `网络请求异常，请检查：\n1. 后端服务是否正常运行\n2. 网络连接是否正常\n\n详细错误：${error.message}`);
        addLog(`❌ 配置测试失败：${error.message}`);
    }
}
