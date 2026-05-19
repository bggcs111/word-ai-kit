# WordAiKit

这是一个轻量级的Word文档智能处理工具，通过调用大语言模型 API 对 Word 文档进行智能润色、标题生成、章节重组等处理，帮助用户快速提升文档质量。

## 主要功能

- 智能文字润色：修正语法、错别字，提升语句连贯性
- 文档标题处理：自动识别或生成文档主标题、章节标题、图表标题
- 格式保留：完整保留原文档中的图片、表格、公式
- 风格适配：支持技术方案、学术论文、测试报告等文档类型
- 自定义提示词：用户可指定润色风格、标题要求等
- 多模型支持：支持 DeepSeek、阿里云通义、Kimi 等云端模型，以及 Ollama、LM Studio 等本地模型
- Web 界面：简洁易用的浏览器操作界面

## 软件亮点

- 智能识别文档结构，自动处理标题层级
- 图表标题智能提炼，根据上下文生成准确描述
- 段落格式统一规范（首行缩进2字符，1.5倍行距）
- 支持多文档合并处理
- 本地部署，数据安全可控

## 安装与使用

### 环境要求

- Python 3.8+
- 操作系统：Windows / Linux / macOS

### 方式一：使用 Conda 环境

```bash
conda create -n wordaikit python=3.10
conda activate wordaikit
pip install -r requirements.txt
```

### 方式二：使用 venv 虚拟环境

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate
pip install -r requirements.txt
```

### 运行程序

```bash
python main.py
```

程序启动后会自动打开浏览器访问 <http://localhost:8000>

## 特别说明
- 出于安全考虑，云端API KEY 保存在本地自定义路径。请勿泄露给他人。
- 目前支持的本地大模型工具有Ollama、LM Studio，使用时请参考其官方文档。该功能尚未充分测试，感兴趣的话建议在本地环境先验证。后续会更新相关说明。


### 获取 API Key

| 服务商      | 获取地址                                   |
| -------- | -------------------------------------- |
| DeepSeek | <https://platform.deepseek.com>        |
| 阿里云通义    | <https://dashscope.console.aliyun.com> |
| Kimi     | <https://platform.moonshot.cn>         |

## 许可与联系

- 许可证：MIT License
- QQ交流群：1081856288
- 邮箱：bggcs111@163.com

