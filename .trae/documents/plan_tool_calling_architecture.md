# 工具化架构改造与图表匹配优化计划

## Context

当前 WordAiKit 的图表插入位置不够准确，主要原因是：
1. AI 只能被动接收固定的 1-2 段上文，无法主动查询更多上下文
2. 所有逻辑集中在 `NaturalLanguageProcessor` 一个类中，难以扩展和复用
3. 图表上下文提取规则固定，无法根据实际文档结构调整

用户希望将图表公式识别、理解、提取等功能做成工具供模型调用，提升可扩展性和工具复用性。

## 解决方案

引入 OpenAI Function Calling 机制，将文档处理能力封装为工具，让 AI 可以主动查询文档结构、理解图表上下文，从而更准确地放置图表。

## 实现步骤

### 1. 创建 DocumentTools 类 (src/document_tools.py)

封装 5 个文档访问工具：

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `get_document_structure` | 获取文档整体结构概览 | 无 |
| `get_chart_context` | 获取指定图表的上下文 | `chart_id`, `paragraphs_before=2`, `paragraphs_after=1` |
| `get_paragraph_text` | 获取指定段落的完整文本 | `paragraph_id` |
| `get_chart_description` | 获取图表的 AI 生成描述 | `chart_id` |
| `get_element_order` | 获取文档元素的原始顺序 | 无 |

关键设计：
- `get_chart_context` 支持前后查看，比当前只能看上文更灵活
- 预生成图表描述，避免重复调用 AI
- 统一 `execute_tool` 入口，简化调用逻辑

### 2. 创建 ToolCallingProcessor 类 (src/tool_calling_processor.py)

实现工具调用循环：

```
1. 初始化对话，传入系统提示和用户要求
2. AI 可调用工具查询文档结构
3. 执行工具，返回结果给 AI
4. 重复 2-3，直到 AI 生成最终结构
5. 解析并验证结构
```

关键设计：
- `max_tool_calls=15` 防止无限循环
- 失败时回退到传统模式
- 复用 `_extract_elements` 和 `_validate_and_fix_structure` 逻辑

### 3. 重构 NaturalLanguageProcessor (src/natural_language_processor.py)

添加 `use_tool_calling` 参数：

```python
def __init__(self, client: OpenAI, model_name: str, use_tool_calling: bool = True):
    self.use_tool_calling = use_tool_calling
    if use_tool_calling:
        self.tool_processor = ToolCallingProcessor(client, model_name)
```

当 `use_tool_calling=True` 时委托给 `ToolCallingProcessor`，否则使用原有逻辑。

### 4. 更新 OpenAI 版本 (requirements.txt)

将 `openai==1.6.1` 升级到 `openai>=1.10.0`，确保完整支持 function calling。

### 5. 更新配置 (src/config.py)

在 `ConfigManager` 中添加 `use_tool_calling` 配置项，默认启用。

## 关键文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/document_tools.py` | 新建 | DocumentTools 类，封装 5 个工具 |
| `src/tool_calling_processor.py` | 新建 | ToolCallingProcessor 类，处理工具调用循环 |
| `src/natural_language_processor.py` | 修改 | 添加 use_tool_calling 参数，委托给新处理器 |
| `src/config.py` | 修改 | 添加 use_tool_calling 配置项 |
| `requirements.txt` | 修改 | 升级 openai 版本 |

## 图表匹配优化效果

**当前流程**：
```
提取上下文(固定1-2段) → AI被动接收 → 生成结构 → 修复缺失
```

**改进后流程**：
```
AI主动查询文档结构 → 按需查询图表上下文 → 验证理解 → 生成准确结构
```

AI 可以：
- 先调用 `get_document_structure()` 了解文档全貌
- 对每个图表调用 `get_chart_context()` 灵活查询前后文
- 调用 `get_paragraph_text()` 验证特定段落内容
- 基于充分理解后再生成结构

## 验证方法

1. 准备包含多个图表的测试文档
2. 分别用传统模式和工具调用模式处理
3. 对比输出文档中图表的位置准确性
4. 检查工具调用日志，确认 AI 正确使用了工具

## 向后兼容

- 保留原有 `NaturalLanguageProcessor` 逻辑
- 通过配置开关切换模式
- Streamlit UI 和 API 路由无需修改
