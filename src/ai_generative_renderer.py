"""
AI生成式文档渲染器
渲染AI生成的新文档结构，统一格式（字体、间距）
"""
from typing import Dict, List, Any
from copy import deepcopy
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from src.utils import calculate_max_image_width
import tempfile
import os


class AIGenerativeRenderer:
    """AI生成式文档渲染器"""
    
    def __init__(self):
        """初始化渲染器"""
        self.default_font = "宋体"
        self.default_font_size = Pt(12)
        self.heading_font = "黑体"
        self.heading_sizes = {
            1: Pt(16),
            2: Pt(14),
            3: Pt(12)
        }
        self.line_spacing = 1.5
    
    def render(
        self,
        generated_content: Dict[str, Any],
        output_path: str
    ) -> str:
        """
        渲染AI生成的文档

        Args:
            generated_content: AI生成的内容结构
            output_path: 输出文件路径

        Returns:
            输出文件路径
        """
        structure = generated_content.get('structure', [])
        tables_data = generated_content.get('tables', [])
        images_data = generated_content.get('images', [])
        formulas_data = generated_content.get('formulas', [])
        document_title = generated_content.get('document_title', '')

        if not structure:
            raise ValueError("生成的内容结构为空")

        # 创建新文档
        doc = Document()

        # 设置默认样式
        self._setup_default_styles(doc)

        # 添加文档主标题
        if document_title:
            title_p = doc.add_paragraph()
            title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            title_run = title_p.add_run(document_title)
            title_run.bold = True
            title_run.font.size = Pt(22)
            title_run.font.name = self.heading_font
            title_run._element.rPr.rFonts.set(qn('w:eastAsia'), self.heading_font)

        # 渲染结构
        for item in structure:
            item_type = item.get('type')

            if item_type == 'heading':
                self._render_heading(doc, item)
            elif item_type == 'paragraph':
                self._render_paragraph(doc, item)
            elif item_type == 'table':
                self._render_table(doc, item, tables_data)
            elif item_type == 'image':
                self._render_image(doc, item, images_data)
            elif item_type == 'formula':
                self._render_formula(doc, item, formulas_data)

        # 保存文档
        doc.save(output_path)

        return output_path
    
    def _setup_default_styles(self, doc: Document):
        """设置默认样式"""
        # 设置Normal样式
        normal_style = doc.styles['Normal']
        normal_style.font.name = self.default_font
        normal_style.font.size = self.default_font_size
        normal_style._element.rPr.rFonts.set(qn('w:eastAsia'), self.default_font)
        
        # 设置段落格式
        normal_style.paragraph_format.line_spacing = self.line_spacing
        normal_style.paragraph_format.space_after = Pt(6)
    
    def _render_heading(self, doc: Document, item: Dict):
        """渲染标题"""
        title = item.get('title', '')
        level = item.get('level', 1)
        
        # 添加标题
        heading = doc.add_heading(title, level=level)
        
        # 设置标题样式
        heading.style.font.name = self.heading_font
        heading.style.font.size = self.heading_sizes.get(level, Pt(12))
        heading.style._element.rPr.rFonts.set(qn('w:eastAsia'), self.heading_font)
        
        # 设置标题格式
        heading.paragraph_format.line_spacing = self.line_spacing
        heading.paragraph_format.space_before = Pt(12)
        heading.paragraph_format.space_after = Pt(6)
    
    def _render_paragraph(self, doc: Document, item: Dict):
        """渲染段落"""
        text = item.get('text', '')
        
        if not text:
            return
        
        # 添加段落
        para = doc.add_paragraph(text)
        
        # 设置段落格式：正文两端对齐，首行缩进2字符，行距1.5倍
        para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY  # 两端对齐
        para.paragraph_format.first_line_indent = Pt(24)  # 首行缩进2字符
        para.paragraph_format.line_spacing = self.line_spacing
        para.paragraph_format.space_after = Pt(6)
        
        # 设置字体
        for run in para.runs:
            run.font.name = self.default_font
            run.font.size = self.default_font_size
            run._element.rPr.rFonts.set(qn('w:eastAsia'), self.default_font)
    
    def _render_table(self, doc: Document, item: Dict, tables_data: List[Dict]):
        """渲染表格"""
        table_id = item.get('id')
        
        # 查找表格数据
        table_data = next((t for t in tables_data if t['id'] == table_id), None)
        if not table_data:
            return
        
        content = table_data.get('content')
        if not content:
            return
        
        # 创建表格
        if isinstance(content, list) and len(content) > 0:
            rows = len(content)
            cols = len(content[0]) if content[0] else 1
            
            table = doc.add_table(rows=rows, cols=cols)
            table.style = 'Table Grid'
            
            # 填充表格内容
            for i, row_data in enumerate(content):
                row = table.rows[i]
                for j, cell_data in enumerate(row_data):
                    cell = row.cells[j]
                    cell.text = str(cell_data) if cell_data else ''
                    
                    # 设置单元格字体
                    for paragraph in cell.paragraphs:
                        paragraph.paragraph_format.line_spacing = self.line_spacing
                        for run in paragraph.runs:
                            run.font.name = self.default_font
                            run.font.size = Pt(10)  # 表格字体稍小
                            run._element.rPr.rFonts.set(qn('w:eastAsia'), self.default_font)
            
            # 表格居中
            table.alignment = WD_ALIGN_PARAGRAPH.CENTER

            # 表格简单美化：标题行加底纹、外框加粗
            self._beautify_table(table, rows, cols)
        
        # 添加空行
        doc.add_paragraph()
    
    def _beautify_table(self, table, rows: int, cols: int):
        """对表格做简单美化：标题行加底纹、外框加粗、标题加粗"""
        if rows == 0 or cols == 0:
            return

        # 1. 标题行（首行）加底纹 + 加粗
        header_cells = table.rows[0].cells
        for cell in header_cells:
            tc_pr = cell._tc.get_or_add_tcPr()
            shd = OxmlElement('w:shd')
            shd.set(qn('w:val'), 'clear')
            shd.set(qn('w:color'), 'auto')
            shd.set(qn('w:fill'), 'D9E2F3')  # 浅蓝底纹
            tc_pr.append(shd)
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.bold = True

        # 2. 外框加粗（通过表级 tblBorders，但全表加粗会过重，这里给表格设置单线外框+内细线）
        tbl = table._tbl
        tbl_pr = tbl.tblPr
        if tbl_pr is not None:
            existing = tbl_pr.find(qn('w:tblBorders'))
            if existing is not None:
                tbl_pr.remove(existing)
            borders = OxmlElement('w:tblBorders')
            for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
                el = OxmlElement(f'w:{edge}')
                el.set(qn('w:val'), 'single')
                el.set(qn('w:sz'), '8' if edge in ('top', 'bottom') else '4')
                el.set(qn('w:space'), '0')
                el.set(qn('w:color'), 'auto')
                borders.append(el)
            tbl_pr.append(borders)
    
    def _render_image(self, doc: Document, item: Dict, images_data: List[Dict]):
        """渲染图片"""
        image_id = item.get('id')
        
        # 查找图片数据
        image_data = next((i for i in images_data if i['id'] == image_id), None)
        if not image_data:
            return
        
        content = image_data.get('content')
        if not content:
            return
        
        # 创建临时文件保存图片
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
            tmp_file.write(content)
            tmp_path = tmp_file.name
        
        try:
            # 添加图片（居中）
            para = doc.add_paragraph()
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = para.add_run()
            inline_shape = run.add_picture(tmp_path)

            # 自动调整：若图片宽度超过允许的最大宽度，则等比缩小（保留宽高比，避免单边拉伸）
            max_width = calculate_max_image_width(doc, char_margin=4)
            if inline_shape.width > max_width:
                ratio = max_width / float(inline_shape.width)
                inline_shape.width = max_width
                inline_shape.height = int(inline_shape.height * ratio)

            # 添加空行
            doc.add_paragraph()
        finally:
            # 删除临时文件
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def _render_formula(self, doc: Document, item: Dict, formulas_data: List[Dict]):
        """渲染公式"""
        formula_id = item.get('id')
        formula_data = next((f for f in formulas_data if f['id'] == formula_id), None)
        if not formula_data:
            return

        para = doc.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER

        kind = formula_data.get('kind', 'standalone')

        if kind == 'inline':
            omath = formula_data.get('omath')
            if omath is not None:
                try:
                    para._element.append(deepcopy(omath))
                except Exception:
                    run = para.add_run("[公式]")
                    run.italic = True
        else:
            content = formula_data.get('content')
            if content is not None:
                try:
                    new_run = para.add_run('')
                    new_run._element.append(deepcopy(content._element))
                except Exception:
                    run = para.add_run("[公式]")
                    run.italic = True
            else:
                run = para.add_run("[公式]")
                run.italic = True