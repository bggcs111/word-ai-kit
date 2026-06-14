<h1 align="center">WordAiKit</h1>


WordAiKit是一个轻量级的Word文档智能处理工具，通过调用大语言模型 API 对 Word 文档(docx格式)进行文字润色、标题生成、参考模板输出等处理，帮助用户快速提升文档质量。

<img width="550" height="610" alt="image" src="https://github.com/user-attachments/assets/5d89b799-85a9-4e99-9770-98ff089ef606" />

## 更新
2026-6-14: V2.0.0 (当前版本)
- 新增参考模板输出模式: 上传docx格式参考模板和需要整合的docx格式原始文档, WordAiKit可输出符合模板的最终文档
- 新增本地大模型接口: 支持ollama和LM Studio, 功能正在验证中
- 优化润色模式: 可选文章类型或自定义文章类型, WordAiKit润色文章时将适应相应的风格; 输入自定义提示词, WordAiKit将根据提示词进行修改和润色

## 后续计划
- [] 优化前端, UI更简洁
- [] 验证本地模型接入的效果
- [] 进一步提示自定义指令编辑的精准性

2026-3-15：V1.0.0 (初始版本)
- 基础的智能文字润色和复杂元素(图 表 公式)保留功能

## 主要亮点
- 智能文字润色：修正语法、错别字，提升语句连贯性, 并自动生成文档图表标题
- 复杂元素保留：完整保留原文档中的图片、表格、公式 
- 多风格选择：预设技术方案、学术论文、测试报告等文章类型, 或自定义类型
- 自定义提示词：用户可自行编写提示词
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
- 出于安全考虑，云端API KEY配置信息保存在本地自定义的且非项目文件的路径。请勿泄露给他人。
- 本地大模型接口尚未充分测试，感兴趣的话建议参考其官方文档, 我会尽快更新相关说明。


### 获取 API Key

| 服务商      | 获取地址                                   |
| -------- | -------------------------------------- |
| DeepSeek | <https://platform.deepseek.com>        |
| 阿里云通义    | <https://dashscope.console.aliyun.com> |
| Kimi     | <https://platform.moonshot.cn>         |


## 许可与联系

- 许可证：MIT License
- 联系邮箱：bggcs111@163.com

