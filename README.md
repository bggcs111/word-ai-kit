# WordAiKit

这是一个轻量级的Word文档智能处理工具，通过调用大语言模型 API 对 Word 文档(docx格式)进行文字润色、标题生成、参考模板输出等处理，帮助用户快速提升文档质量。

<img width="550" height="610" alt="image" src="https://github.com/user-attachments/assets/5d89b799-85a9-4e99-9770-98ff089ef606" />

## 更新
2026-6-14: V2.0.0 (当前版本)
- 新增文档合并输出模式: 只需要提前上传一个或多个docx格式参考模板, 之后上传多篇原始文档, AI智能合成后按选定的模板输出最终文档
- 优化润色模式: 可以选择文档类型或自定义文档类型, AI输出符合该类型的文字风格; 也可以输入自定义提示词, AI按提示词要求润色原文并输出

2026-3-15：V1.0.0
- 初始版本, 具有基础的智能文字润色和复杂元素(图 表 公式)保留功能

## 主要亮点
- 智能文字润色：修正语法、错别字，提升语句连贯性
- 图表标题生成：自动生成文档图表标题
- 复杂元素保留：完整保留原文档中的图片、表格、公式 
- 风格适配：支持技术方案、学术论文、测试报告等文档类型, 或者自定义类型
- 自定义提示词：用户可指定文章风格、标题生成等要求
- 文档合并与模板套用: 支持多文档合并与重排, 并按照自定义模板输出
- 多模型支持：支持云端模型和本地模型接入
- 隐私保护: API KEY配置信息保存在本地非项目路径, 首次配置下次直接使用 


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
- 出于安全考虑，云端API KEY 保存在本地自定义的且非项目文件的路径。请勿泄露给他人。
- 目前支持的本地大模型工具有Ollama、LM Studio，使用时请参考其官方文档。该功能尚未充分测试，感兴趣的话建议在本地环境先验证。后续我会更新相关说明。


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

