# WordAiKit

<p align="center">
  <img src="https://img.shields.io/badge/version-1.0.0-blue.svg" alt="Version">
  <img src="https://img.shields.io/badge/python-3.8+-green.svg" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-orange.svg" alt="License">
</p>

Word 文档智能处理工具，支持文字润色、保留图片/表格/公式等功能。通过调用大语言模型 API 对 Word 文档进行智能处理，帮助用户快速提升文档质量。

## ✨ 功能特性

- 🔤 **智能润色** - 修正语法、错别字，提升语句连贯性
- 🖼️ **格式保留** - 完整保留原文档中的图片、表格、公式
- 📝 **风格识别** - 自动识别并匹配文档风格（技术方案、学术论文、测试报告等）
- 🤖 **多模型支持** - 支持 DeepSeek、阿里云通义、Kimi 等多种 AI 模型
- 🌐 **Web 界面** - 简洁易用的 Web 操作界面

## 🛠️ 技术栈

- **后端**: Python + FastAPI + Uvicorn
- **AI**: OpenAI API (兼容多家大模型)
- **文档处理**: python-docx
- **前端**: HTML + CSS + JavaScript

## 📁 项目结构

```
WordAiKit-V1.0.0/
├── main.py              # 程序入口
├── requirements.txt     # 依赖配置
├── api/
│   ├── __init__.py
│   └── routes.py        # API 路由
├── src/
│   ├── __init__.py
│   ├── ai_processor.py  # AI 处理模块
│   ├── builder.py       # 文档构建模块
│   ├── cache_manager.py # 缓存管理
│   ├── config.py        # 配置管理
│   ├── constants.py     # 常量定义
│   ├── logger.py        # 日志模块
│   ├── parser.py        # 文档解析模块
│   └── storage.py       # 存储模块
└── static/
    ├── css/
    │   └── style.css
    ├── js/
    │   └── app.js
    └── index.html       # 前端界面
```

## 🚀 快速开始

### 环境要求

- Python 3.8+
- 操作系统：Windows / Linux / macOS

### 创建虚拟环境（推荐）

建议使用虚拟环境安装依赖，避免与系统 Python 环境冲突：

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

**Linux/macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 直接安装（不推荐）

```bash
pip install -r requirements.txt
```

### 运行程序

```bash
python main.py
```

程序启动后会自动打开浏览器访问 `http://localhost:8000`

## 📖 使用说明

### 1. 配置 API Key

首次使用需要配置 AI 服务的 API Key：

1. 点击界面上的「⚙️ 在线配置」按钮
2. 选择要使用的 AI 模型
3. 输入对应的 API Key
4. 点击「🧪 测试配置」验证
5. 点击「💾 保存配置」

**获取 API Key：**
| 服务商 | 获取地址 |
|--------|---------|
| DeepSeek | https://platform.deepseek.com |
| 阿里云通义 | https://dashscope.console.aliyun.com |
| Kimi | https://platform.moonshot.cn |

### 2. 处理文档

1. 上传 Word 文档（.docx 格式）
2. 点击「🚀 开始处理」
3. 下载处理后的文档

**处理限制：**
- 推荐单次处理：≤ 50,000 中文字符（约 25-30 页）
- 最大支持：100,000 中文字符

## ⚙️ 配置文件

- **配置文件位置**: 默认保存在用户文档目录
- **文件名**: `.wordaikit_config.json`
- **日志文件**: `logs/wordaikit.log`

## ⚠️ 注意事项

1. **API Key 安全**: 请勿将配置文件分享给他人
2. **正确退出**: 使用 `Ctrl + C` 退出程序，确保临时文件被正确清理
3. **网络要求**: 需要稳定的网络连接访问 AI API 服务

## 📄 许可证

本项目采用 MIT 许可证

## 🤝 贡献

欢迎提交 Issue 和 Pull Request

## 😉 QQ交流群

WordAiKit交流群：1081856288




---

<p align="center">
  如果这个项目对你有帮助，请给一个 ⭐️ Star 支持一下！
</p>
