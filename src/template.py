"""
模板定义模块 - 智能 Word 模板系统
负责从 Word 模板文档提取样式、结构和生成模板定义
"""
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum


class ElementType(Enum):
    """元素类型枚举"""
    TITLE = "title"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    LIST = "list"
    IMAGE = "image"
    FORMULA = "formula"


class HeadingLevel(Enum):
    """标题级别"""
    H1 = 1
    H2 = 2
    H3 = 3
    H4 = 4
    H5 = 5
    H6 = 6


@dataclass
class FontDefinition:
    """字体定义"""
    name: str = "宋体"
    size: str = "12pt"
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "size": self.size,
            "bold": self.bold,
            "italic": self.italic,
            "underline": self.underline,
            "color": self.color
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'FontDefinition':
        return cls(
            name=data.get("name", "宋体"),
            size=data.get("size", "12pt"),
            bold=data.get("bold", False),
            italic=data.get("italic", False),
            underline=data.get("underline", False),
            color=data.get("color")
        )


@dataclass
class ParagraphStyle:
    """段落样式"""
    alignment: str = "left"
    line_spacing: float = 1.5
    space_before: str = "0pt"
    space_after: str = "0pt"
    indent_left: str = "0cm"
    indent_right: str = "0cm"
    first_line_indent: str = "0cm"
    
    def to_dict(self) -> Dict:
        return {
            "alignment": self.alignment,
            "line_spacing": self.line_spacing,
            "space_before": self.space_before,
            "space_after": self.space_after,
            "indent_left": self.indent_left,
            "indent_right": self.indent_right,
            "first_line_indent": self.first_line_indent
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ParagraphStyle':
        return cls(
            alignment=data.get("alignment", "left"),
            line_spacing=data.get("line_spacing", 1.5),
            space_before=data.get("space_before", "0pt"),
            space_after=data.get("space_after", "0pt"),
            indent_left=data.get("indent_left", "0cm"),
            indent_right=data.get("indent_right", "0cm"),
            first_line_indent=data.get("first_line_indent", "0cm")
        )


@dataclass
class StyleDefinition:
    """样式定义"""
    style_name: str
    font: FontDefinition = field(default_factory=FontDefinition)
    paragraph: ParagraphStyle = field(default_factory=ParagraphStyle)
    is_heading: bool = False
    heading_level: Optional[int] = None
    is_title: bool = False
    numbering_format: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "style_name": self.style_name,
            "font": self.font.to_dict(),
            "paragraph": self.paragraph.to_dict(),
            "is_heading": self.is_heading,
            "heading_level": self.heading_level,
            "is_title": self.is_title,
            "numbering_format": self.numbering_format
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'StyleDefinition':
        return cls(
            style_name=data.get("style_name", "Normal"),
            font=FontDefinition.from_dict(data.get("font", {})),
            paragraph=ParagraphStyle.from_dict(data.get("paragraph", {})),
            is_heading=data.get("is_heading", False),
            heading_level=data.get("heading_level"),
            is_title=data.get("is_title", False),
            numbering_format=data.get("numbering_format")
        )


@dataclass
class TemplateElement:
    """模板元素"""
    element_type: ElementType
    style_name: str
    heading_level: Optional[int] = None
    numbering: Optional[str] = None
    placeholder_text: str = ""
    description: str = ""
    order: int = 0
    
    def to_dict(self) -> Dict:
        return {
            "element_type": self.element_type.value,
            "style_name": self.style_name,
            "heading_level": self.heading_level,
            "numbering": self.numbering,
            "placeholder_text": self.placeholder_text,
            "description": self.description,
            "order": self.order
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'TemplateElement':
        return cls(
            element_type=ElementType(data.get("element_type", "paragraph")),
            style_name=data.get("style_name", "Normal"),
            heading_level=data.get("heading_level"),
            numbering=data.get("numbering"),
            placeholder_text=data.get("placeholder_text", ""),
            description=data.get("description", ""),
            order=data.get("order", 0)
        )


@dataclass
class TemplateDefinition:
    """模板定义"""
    template_id: str
    name: str
    description: str = ""
    version: str = "1.0"
    styles: Dict[str, StyleDefinition] = field(default_factory=dict)
    structure: List[TemplateElement] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "template_id": self.template_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "styles": {name: style.to_dict() for name, style in self.styles.items()},
            "structure": [elem.to_dict() for elem in self.structure],
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'TemplateDefinition':
        template = cls(
            template_id=data.get("template_id", ""),
            name=data.get("name", "未命名模板"),
            description=data.get("description", ""),
            version=data.get("version", "1.0"),
            metadata=data.get("metadata", {})
        )
        
        for style_name, style_data in data.get("styles", {}).items():
            template.styles[style_name] = StyleDefinition.from_dict(style_data)
        
        for elem_data in data.get("structure", []):
            template.structure.append(TemplateElement.from_dict(elem_data))
        
        return template
    
    def to_json(self) -> Dict:
        return self.to_dict()
    
    def get_heading_structure(self) -> List[Dict]:
        """获取标题结构（用于 AI 理解文档布局）"""
        headings = []
        for elem in self.structure:
            if elem.element_type == ElementType.HEADING:
                headings.append({
                    "level": elem.heading_level or 1,
                    "numbering": elem.numbering,
                    "placeholder": elem.placeholder_text,
                    "description": elem.description
                })
        return headings
    
    def get_content_requirements(self) -> str:
        """生成内容要求提示词"""
        parts = [
            f"## 模板：{self.name}",
            f"\n{self.description}",
            "\n## 文档结构要求：",
        ]
        
        for elem in self.structure:
            if elem.element_type == ElementType.HEADING:
                level = elem.heading_level or 1
                numbering = f"{elem.numbering} " if elem.numbering else ""
                parts.append(f"\n{'#' * level} {numbering}{elem.placeholder_text or '（标题）'}")
                if elem.description:
                    parts.append(f"   {elem.description}")
            elif elem.element_type == ElementType.PARAGRAPH:
                parts.append(f"\n   [正文内容]")
                if elem.description:
                    parts.append(f"   {elem.description}")
            elif elem.element_type == ElementType.TABLE:
                parts.append(f"\n   [表格]")
            elif elem.element_type == ElementType.IMAGE:
                parts.append(f"\n   [图片]")
        
        return "\n".join(parts)
