"""
文件解析模块 — 将 PDF/MD 转为统一的 content_list 格式。

职责单一：只负责「文件 → content_list」，不涉及切块或向量化。
可插拔：通过注册新的解析器支持更多文件类型。
"""

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List

from rag.config import ParserConfig


# ── 解析器注册表 ──────────────────────────────────────────

_PARSERS: Dict[str, type] = {}


def register_parser(extensions: List[str]):
    """装饰器：注册文件解析器。"""
    def decorator(cls):
        for ext in extensions:
            _PARSERS[ext.lower()] = cls
        return cls
    return decorator


def get_parser(file_path: Path, config: ParserConfig) -> "BaseParser":
    """根据文件扩展名获取对应解析器实例。"""
    ext = file_path.suffix.lower()
    parser_cls = _PARSERS.get(ext)
    if parser_cls is None:
        raise ValueError(f"不支持的文件类型: {ext}，已注册: {list(_PARSERS.keys())}")
    return parser_cls(config)


# ── 基类 ──────────────────────────────────────────────────

class BaseParser:
    """解析器基类。"""

    def __init__(self, config: ParserConfig):
        self.config = config

    def parse(self, file_path: Path) -> List[Dict[str, Any]]:
        """解析文件，返回 content_list。"""
        raise NotImplementedError


# ── PDF 解析器 ────────────────────────────────────────────

@register_parser([".pdf"])
class PDFParser(BaseParser):
    """使用 MinerU 解析 PDF。"""

    def parse(self, file_path: Path) -> List[Dict[str, Any]]:
        import os
        os.environ.setdefault("MINERU_MODEL_SOURCE", "local")
        os.environ.setdefault("HF_HUB_OFFLINE", "1")

        from mineru.cli.common import do_parse, read_fn

        stem = file_path.stem
        size_kb = file_path.stat().st_size / 1024
        print(f"[Parser] PDF: {file_path.name} ({size_kb:.0f} KB)")

        pdf_bytes = read_fn(file_path)

        print(f"[Parser] MinerU 解析中... ({self.config.backend}/{self.config.parse_method})")
        t0 = time.time()
        do_parse(
            output_dir=self.config.output_dir,
            pdf_file_names=[stem],
            pdf_bytes_list=[pdf_bytes],
            p_lang_list=[self.config.lang],
            backend=self.config.backend,
            parse_method=self.config.parse_method,
            formula_enable=self.config.formula_enable,
            table_enable=self.config.table_enable,
        )
        elapsed = time.time() - t0
        print(f"[Parser] 解析完成 ({elapsed:.1f}s)")

        # 读取 content_list
        content_path = Path(self.config.output_dir) / stem / "auto" / f"{stem}_content_list.json"
        if not content_path.exists():
            raise FileNotFoundError(f"MinerU 未生成: {content_path}")

        content_list = json.loads(content_path.read_text(encoding="utf-8"))
        print(f"[Parser] 输出 {len(content_list)} 个 block")
        return content_list


# ── Markdown 解析器 ───────────────────────────────────────

_HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)


@register_parser([".md", ".markdown", ".txt"])
class MarkdownParser(BaseParser):
    """将 Markdown/文本文件转为 content_list 格式。"""

    def parse(self, file_path: Path) -> List[Dict[str, Any]]:
        size_kb = file_path.stat().st_size / 1024
        print(f"[Parser] MD: {file_path.name} ({size_kb:.0f} KB)")

        md_text = self._read_file(file_path)
        content_list = self._md_to_content_list(md_text)
        print(f"[Parser] 转换为 {len(content_list)} 个 block")
        return content_list

    def _read_file(self, path: Path) -> str:
        """尝试多种编码读取文件。"""
        for enc in ('utf-8', 'gbk', 'gb2312', 'latin-1'):
            try:
                return path.read_text(encoding=enc)
            except UnicodeDecodeError:
                continue
        raise ValueError(f"无法读取文件: {path}")

    def _md_to_content_list(self, md_text: str) -> List[Dict[str, Any]]:
        """将 markdown 文本转为 content_list 格式。"""
        items: List[Dict[str, Any]] = []
        blocks = re.split(r'\n\s*\n', md_text.strip())

        for block in blocks:
            lines = block.strip().split('\n')
            if not lines:
                continue

            first = lines[0].strip()
            m = _HEADING_RE.match(first)
            if m:
                level = len(m.group(1))
                title_text = m.group(2).strip()
                items.append({
                    "type": "text",
                    "text": title_text,
                    "text_level": level,
                    "page_idx": 0,
                    "bbox": [0, 0, 0, 0],
                })
                # 标题行之后的剩余内容作为正文
                rest = '\n'.join(lines[1:]).strip()
                if rest:
                    items.append({
                        "type": "text",
                        "text": rest,
                        "page_idx": 0,
                        "bbox": [0, 0, 0, 0],
                    })
            else:
                items.append({
                    "type": "text",
                    "text": block.strip(),
                    "page_idx": 0,
                    "bbox": [0, 0, 0, 0],
                })

        return items
