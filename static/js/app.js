// WordAiKit - Main JavaScript Application

// Global Variables
let selectedFiles = [];
let resultFileName = null;
let currentTab = 'deepseek';
let selectedTemplateId = null;
let customTemplateJson = null;
let processMode = 'normal'; // 'normal' or 'template'

// Initialize Application
window.addEventListener('DOMContentLoaded', () => {
    checkServiceStatus();
    loadModels();
    loadConfigStatus();
    loadTemplates();
    setupEventListeners();
});

// Event Listeners Setup
function setupEventListeners() {
    const fileInput = document.getElementById('fileInput');
    fileInput.addEventListener('change', handleFileSelect);
    
    const dropZone = document.getElementById('fileLabel');
    
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });
    
    ['dragover', 'drop'].forEach(eventName => {
        document.addEventListener(eventName, preventDefaults, false);
    });
    
    dropZone.addEventListener('dragenter', highlight, false);
    dropZone.addEventListener('dragover', highlight, false);
    dropZone.addEventListener('dragleave', unhighlight, false);
    dropZone.addEventListener('drop', handleDrop, false);
    
    document.getElementById('modelSelect').addEventListener('change', handleModelChange);
    
    window.onclick = handleModalOutsideClick;
}

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
    return false;
}

function highlight(e) {
    e.preventDefault();
    e.stopPropagation();
    document.getElementById('fileLabel').classList.add('drag-over');
}

function unhighlight(e) {
    e.preventDefault();
    e.stopPropagation();
    document.getElementById('fileLabel').classList.remove('drag-over');
}

function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    
    unhighlight(e);
    
    const dt = e.dataTransfer;
    const files = dt.files;
    
    if (files.length > 0) {
        const validFiles = [];
        for (const file of files) {
            if (file.name.endsWith('.docx')) {
                validFiles.push(file);
            }
        }
        
        if (validFiles.length > 0) {
            selectedFiles = validFiles;
            updateFileList();
            document.getElementById('processBtn').disabled = false;
            addLog(`📄 通过拖拽选择 ${validFiles.length} 个文件`);
        } else {
            showAlert('请上传 .docx 格式的 Word 文档', 'error');
            addLog(`❌ 不支持的文件格式`);
        }
    }
    
    return false;
}

function handleFileSelect(e) {
    const files = e.target.files;
    if (files.length > 0) {
        selectedFiles = Array.from(files);
        updateFileList();
        document.getElementById('processBtn').disabled = false;
    }
}

async function handleModelChange(e) {
    const modelName = e.target.value;
    if (modelName) {
        await switchModel(modelName);
    }
}

function handleModalOutsideClick(event) {
    const modal = document.getElementById('configModal');
    if (event.target === modal) {
        closeConfigModal();
    }
    
    const templateModal = document.getElementById('templateUploadModal');
    if (templateModal && event.target === templateModal) {
        closeTemplateUploadModal();
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
    if (selectedFiles.length === 0) {
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
        addLog(`📤 开始上传 ${selectedFiles.length} 个文档`);

        const formData = new FormData();
        for (const file of selectedFiles) {
            formData.append('files', file);
        }

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
        resultFileName = `processed_${selectedFiles[0].name}`;
        window.resultBlob = blob;
        
        const docType = response.headers.get('X-Doc-Type');
        
        if (docType) {
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
        
        const fileNames = selectedFiles.map(f => f.name).join(', ');
        showResult(fileNames, resultFileName);

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

// Update File List
function updateFileList() {
    const label = document.getElementById('fileLabel');
    const fileListDiv = document.getElementById('fileList');
    
    if (selectedFiles.length === 0) {
        label.classList.remove('has-file');
        label.innerHTML = `
            <div class="file-icon">📄</div>
            <div class="file-name">点击上传文档</div>
            <div class="file-hint">支持 .docx 格式，可同时选择多个文档</div>
        `;
        fileListDiv.style.display = 'none';
        return;
    }
    
    label.classList.add('has-file');
    label.innerHTML = `
        <div class="file-icon">📄</div>
        <div class="file-name">已选择 ${selectedFiles.length} 个文档</div>
        <div class="file-hint">点击可重新选择</div>
    `;
    
    fileListDiv.style.display = 'block';
    let html = '<div style="background: #f8f9fa; border-radius: 5px; padding: 8px; font-size: 13px;">';
    for (let i = 0; i < selectedFiles.length; i++) {
        html += `<div style="padding: 3px 0; display: flex; justify-content: space-between; align-items: center;">
            <span>📄 ${selectedFiles[i].name}</span>
            <span style="color: #6c757d; font-size: 12px;">${formatFileSize(selectedFiles[i].size)}</span>
        </div>`;
    }
    html += '</div>';
    fileListDiv.innerHTML = html;
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

// ========== 模板处理相关功能 ==========

// 加载模板列表
async function loadTemplates() {
    try {
        const response = await fetch('/api/templates');
        const data = await response.json();
        
        const select = document.getElementById('templateSelect');
        
        if (data.templates && data.templates.length > 0) {
            select.innerHTML = '<option value="">-- 请选择模板 --</option>';
            
            data.templates.forEach(template => {
                const option = document.createElement('option');
                option.value = template.template_id;
                option.textContent = `${template.name} (${template.structure_count} 个元素, ${template.styles_count} 个样式)`;
                select.appendChild(option);
            });
            
            select.addEventListener('change', (e) => {
                selectedTemplateId = e.target.value;
                customTemplateJson = null;
                if (selectedTemplateId) {
                    addLog(`📋 已选择模板：${selectedTemplateId}`);
                    showTemplateInfo(selectedTemplateId);
                }
            });
            
            addLog(`📋 已加载 ${data.templates.length} 个模板`);
        } else {
            select.innerHTML = '<option value="">-- 暂无模板，请先上传 --</option>';
        }
    } catch (error) {
        console.error('加载模板列表失败:', error);
        addLog(`❌ 加载模板列表失败：${error.message}`);
    }
}

// 显示模板信息
async function showTemplateInfo(templateId) {
    try {
        const response = await fetch(`/api/templates/${templateId}`);
        const data = await response.json();
        
        if (data.template) {
            const template = data.template;
            const infoDiv = document.getElementById('templateInfo');
            infoDiv.style.display = 'block';
            infoDiv.innerHTML = `
                <strong>${template.name}</strong><br>
                ${template.description || '无描述'}<br>
                <small>样式数：${Object.keys(template.styles || {}).length} | 
                       元素数：${(template.structure || []).length}</small>
            `;
        }
    } catch (error) {
        console.error('获取模板详情失败:', error);
    }
}

// 切换处理模式
function toggleProcessMode() {
    const modeRadios = document.getElementsByName('processMode');
    for (const radio of modeRadios) {
        if (radio.checked) {
            processMode = radio.value;
            break;
        }
    }
    
    const templateSelection = document.getElementById('templateSelection');
    const docTypeSection = document.getElementById('docTypeSection');
    const userPromptSection = document.getElementById('userPromptSection');
    if (processMode === 'template') {
        templateSelection.style.display = 'block';
        docTypeSection.style.display = 'none';
        userPromptSection.style.display = 'none';
        addLog('📋 已切换到模板输出模式');
    } else {
        templateSelection.style.display = 'none';
        docTypeSection.style.display = 'block';
        userPromptSection.style.display = 'block';
        addLog('📝 已切换到普通润色模式');
    }
}

// 文档类型选择变化
document.addEventListener('DOMContentLoaded', () => {
    const docTypeSelect = document.getElementById('docTypeSelect');
    const customDocTypeDiv = document.getElementById('customDocTypeDiv');
    
    if (docTypeSelect) {
        docTypeSelect.addEventListener('change', () => {
            if (docTypeSelect.value === 'custom') {
                customDocTypeDiv.style.display = 'block';
            } else {
                customDocTypeDiv.style.display = 'none';
            }
        });
    }
});

// 打开模板上传模态框
function openTemplateUploadModal() {
    document.getElementById('templateUploadModal').style.display = 'flex';
    document.getElementById('templateUploadProgress').style.display = 'none';
    document.getElementById('templateUploadResult').style.display = 'none';
    document.getElementById('templateDocInput').value = '';
}

// 关闭模板上传模态框
function closeTemplateUploadModal() {
    document.getElementById('templateUploadModal').style.display = 'none';
}

// 上传模板文档
async function uploadTemplateDocument() {
    const fileInput = document.getElementById('templateDocInput');
    const file = fileInput.files[0];
    
    if (!file) {
        showAlert('请先选择模板文档', 'warning');
        return;
    }
    
    if (!file.name.endsWith('.docx')) {
        showAlert('请上传 .docx 格式的 Word 文档', 'error');
        return;
    }
    
    const progressDiv = document.getElementById('templateUploadProgress');
    const progressFill = document.getElementById('templateProgressFill');
    const progressText = document.getElementById('templateProgressText');
    const resultDiv = document.getElementById('templateUploadResult');
    
    progressDiv.style.display = 'block';
    resultDiv.style.display = 'none';
    progressFill.style.width = '30%';
    progressText.textContent = '正在上传模板文档...';
    
    try {
        const formData = new FormData();
        formData.append('file', file);
        
        progressFill.style.width = '50%';
        progressText.textContent = '正在解析模板...';
        
        const response = await fetch('/api/templates/parse', {
            method: 'POST',
            body: formData
        });
        
        progressFill.style.width = '80%';
        progressText.textContent = '正在保存模板...';
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || '模板解析失败');
        }
        
        const data = await response.json();
        
        progressFill.style.width = '100%';
        progressText.textContent = '模板解析完成！';
        
        resultDiv.style.display = 'block';
        resultDiv.innerHTML = `
            <div style="color: #28a745; font-weight: bold;">✅ 模板解析成功</div>
            <div style="margin-top: 10px;">
                <strong>模板名称：</strong>${data.template.name}<br>
                <strong>样式数量：</strong>${Object.keys(data.template.styles || {}).length}<br>
                <strong>元素数量：</strong>${(data.template.structure || []).length}<br>
                <strong>保存路径：</strong>${data.saved_path}
            </div>
        `;
        
        addLog(`✅ 模板解析成功：${data.template.name}`);
        
        // 刷新模板列表
        setTimeout(() => {
            loadTemplates();
            closeTemplateUploadModal();
            showAlert('模板解析成功，已添加到模板列表', 'success');
        }, 1500);
        
    } catch (error) {
        progressText.textContent = '解析失败';
        progressFill.style.width = '100%';
        progressFill.style.background = '#dc3545';
        
        resultDiv.style.display = 'block';
        resultDiv.innerHTML = `<div style="color: #dc3545;">❌ ${error.message}</div>`;
        
        addLog(`❌ 模板解析失败：${error.message}`);
        showAlert(`模板解析失败：${error.message}`, 'error');
    }
}

// 处理文档（支持模板模式）
async function processDocument() {
    if (selectedFiles.length === 0) {
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
        
        if (processMode === 'template') {
            processBtn.innerHTML = '<span class="loading-spinner"></span> 模板处理中...';
        } else {
            processBtn.innerHTML = '<span class="loading-spinner"></span> 处理中...';
        }
        
        progressContainer.classList.add('show');
        progressFill.style.width = '30%';
        progressText.textContent = '正在上传文档...';
        addLog(`📤 开始上传 ${selectedFiles.length} 个文档`);

        const formData = new FormData();
        for (const file of selectedFiles) {
            formData.append('files', file);
        }

        // 普通模式下传递用户自定义提示词和文档类型
        if (processMode === 'normal') {
            // 文档类型处理
            const docTypeSelect = document.getElementById('docTypeSelect');
            let docType = docTypeSelect ? docTypeSelect.value : '';
            if (docType === 'custom') {
                const customDocType = document.getElementById('customDocType').value.trim();
                if (customDocType) {
                    docType = customDocType;
                    addLog(`📚 已使用自定义文档类型：${docType}`);
                } else {
                    docType = '';
                    addLog('📚 文档类型未设置，将保持原文风格');
                }
            } else if (docType) {
                addLog(`📚 已选择文档类型：${docType}`);
            } else {
                addLog('📚 文档类型未设置，将保持原文风格');
            }
            
            if (docType) {
                formData.append('doc_type', docType);
            }
            
            // 用户自定义提示词（可以包含任何要求，如风格、章节标题、内容要求等）
            const userPrompt = document.getElementById('userPrompt').value.trim();
            if (userPrompt) {
                formData.append('user_prompt', userPrompt);
                addLog('💡 已使用用户自定义要求，AI 会智能识别并执行');
            } else {
                addLog('📝 将使用默认自动润色');
            }
        }

        if (processMode === 'template') {
            progressFill.style.width = '40%';
            progressText.textContent = '准备模板参数...';
            
            if (!selectedTemplateId && !customTemplateJson) {
                throw new Error('请先选择模板或上传自定义模板文件');
            }
            
            if (selectedTemplateId) {
                formData.append('template_id', selectedTemplateId);
                addLog(`📋 使用模板：${selectedTemplateId}`);
            }
            
            if (customTemplateJson) {
                formData.append('template_json', JSON.stringify(customTemplateJson));
                addLog(`📋 使用自定义模板`);
            }
        }

        progressFill.style.width = '50%';
        progressText.textContent = '正在处理文档...';
        addLog('🔄 正在处理文档...');
        
        // 根据处理模式选择API路由
        let apiUrl;
        if (processMode === 'template') {
            apiUrl = '/api/process-with-template-generative';
            addLog('🚀 使用AI生成式策略');
        } else {
            apiUrl = '/api/process';
        }
        
        const response = await fetch(apiUrl, {
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
        resultFileName = processMode === 'template' 
            ? `template_${selectedFiles[0].name}` 
            : `processed_${selectedFiles[0].name}`;
        window.resultBlob = blob;
        
        const docType = response.headers.get('X-Doc-Type');
        const templateName = response.headers.get('X-Template-Name');
        
        if (templateName) {
            addLog(`📋 使用模板：${templateName}`);
        }
        
        if (docType) {
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
        progressText.textContent = processMode === 'template' ? '模板处理完成！' : '处理完成！';
        addLog('✅ 文档处理成功：' + resultFileName);
        addLog('💾 结果已准备下载');
        
        const fileNames = selectedFiles.map(f => f.name).join(', ');
        showResult(fileNames, resultFileName);

    } catch (error) {
        const errorMsg = `处理失败：${error.message}`;
        addLog('❌ ' + errorMsg);
        showAlert(errorMsg, 'error');
        progressContainer.classList.remove('show');
    } finally {
        processBtn.disabled = false;
        
        if (processMode === 'template') {
            processBtn.innerHTML = '🚀 开始模板处理';
        } else {
            processBtn.innerHTML = '🚀 开始处理';
        }
        
        setTimeout(() => {
            progressContainer.classList.remove('show');
            progressFill.style.width = '0%';
        }, 2000);
    }
}

// 监听自定义模板文件上传
const templateFileInput = document.getElementById('templateFileInput');
if (templateFileInput) {
    templateFileInput.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (file) {
            try {
                const text = await file.text();
                customTemplateJson = JSON.parse(text);
                selectedTemplateId = null;
                addLog(`📋 已加载自定义模板：${customTemplateJson.name || '未命名模板'}`);
                showAlert('自定义模板加载成功', 'success');
            } catch (error) {
                addLog(`❌ 模板文件解析失败：${error.message}`);
                showAlert('模板文件格式错误，请确保是有效的 JSON 文件', 'error');
                customTemplateJson = null;
            }
        }
    });
}
