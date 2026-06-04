"""
智能语义切块模块。

策略（按优先级）：
  1. 标题挂载 — 识别 text_level 维护标题链，标题不单独成 chunk，注入后续内容
  2. 短块合并 — 同页相邻短文本合并到接近 MAX 为止
  3. 长块拆分 — 超过 MAX 的单段按句子边界断开
  4. 表格/公式 — 保持完整不切割，挂载标题后独立成 chunk
  5. 图片/图表 — 跳过，保留原结构给下游管线

输出格式：[{type, text, page_idx, bbox, ...}]
"""

import re
from typing import Any, Dict, List, Tuple

from rag.config import ChunkerConfig


# ── HTML 表格转纯文本 ───────────────────────────────────────

_HTML_BR_RE = re.compile(r'<br\s*/?>', re.IGNORECASE)
_HTML_TAG_RE = re.compile(r'<[^>]+>')
_TR_RE = re.compile(r'<tr[^>]*>(.*?)</tr>', re.IGNORECASE | re.DOTALL)
_TD_RE = re.compile(r'<(td|th)[^>]*>(.*?)</\1>', re.IGNORECASE | re.DOTALL)

# 表头中匹配签名/签字列的关键词
_SIGNATURE_KEYWORDS = ('签名', '签字', '签章', '签收')


def _cell_text(cell_html: str) -> str:
    """提取单元格纯文本。"""
    text = _HTML_BR_RE.sub('\n', cell_html)
    text = _HTML_TAG_RE.sub('', text)
    return text.strip()


def _find_signature_columns(rows: list[str], check_rows: int = 3) -> set:
    """在表格前几行中查找含签名关键词的列索引。"""
    sig_cols: set = set()
    for row_html in rows[:check_rows]:
        cells = _TD_RE.findall(row_html)
        for col_idx, (_, inner) in enumerate(cells):
            text = _cell_text(inner)
            if any(kw in text for kw in _SIGNATURE_KEYWORDS):
                sig_cols.add(col_idx)
    return sig_cols


def _html_table_to_text(html: str) -> str:
    """将 HTML 表格转为可读纯文本，签名列替换为占位符。"""
    if not html:
        return ""

    rows = _TR_RE.findall(html)
    if not rows:
        # 回退：原始 HTML，简单去标签
        text = _HTML_BR_RE.sub('\n', html)
        text = _HTML_TAG_RE.sub('', text)
        return text.strip()

    sig_cols = _find_signature_columns(rows)

    lines: list[str] = []
    for row_html in rows:
        cells = _TD_RE.findall(row_html)
        parts: list[str] = []
        for col_idx, (_, inner) in enumerate(cells):
            if col_idx in sig_cols:
                text = _cell_text(inner)
                if text:
                    parts.append(f"[手写:{text}]")
            else:
                text = _cell_text(inner)
                if text:
                    parts.append(text)
        if parts:
            lines.append(' | '.join(parts))

    return '\n'.join(lines)


# ── 工具函数 ──────────────────────────────────────────────

def count_chars(text: str) -> int:
    """估算文本的「有效字符数」（中文 1，英文 0.4，标点 0.6，空格不计）。"""
    n = 0.0
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf':
            n += 1
        elif ch.isascii() and ch.isalpha():
            n += 0.4
        elif ch in (' ', '\t', '\n', '\r'):
            continue
        else:
            n += 0.6
    return max(int(n), 1)


def _is_title(item: Dict) -> bool:
    return bool(item.get("text_level", 0) and item["text_level"] > 0)


def _get_text(item: Dict) -> str:
    t = item.get("type", "text")
    if t == "table":
        parts = []
        caption = " ".join(_as_list(item.get("table_caption")))
        if caption:
            parts.append(caption)
        body = _html_table_to_text(item.get("table_body", ""))
        if body:
            parts.append(body)
        footnote = " ".join(_as_list(item.get("table_footnote")))
        if footnote:
            parts.append(f"注: {footnote}")
        return "\n".join(parts)
    if t == "equation":
        return item.get("text", "") or item.get("text_format", "") or ""
    return (item.get("text") or "").strip()


def _as_list(val) -> List[str]:
    if isinstance(val, list):
        return [str(v) for v in val if v]
    if isinstance(val, str) and val.strip():
        return [val.strip()]
    return []


# ── 句子拆分 ──────────────────────────────────────────────

_SENT_SPLIT_RE = re.compile(r'(?<=[。！？.!?\n])\s*')


def _split_long_text(text: str, max_chars: int) -> List[str]:
    parts: List[str] = []
    sentences = _SENT_SPLIT_RE.split(text)
    current = ""
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        if count_chars(current + sent) <= max_chars:
            current = current + sent if current else sent
        else:
            if current:
                parts.append(current)
            current = sent
    if current:
        parts.append(current)
    if not parts:
        for i in range(0, len(text), max_chars):
            parts.append(text[i:i + max_chars])
    return parts


# ── 标题链 ─────────────────────────────────────────────────

class _TitleStack:
    """维护当前段落所属的标题上下文。"""

    def __init__(self) -> None:
        self._chain: List[Tuple[int, str]] = []

    def push(self, level: int, text: str) -> None:
        tag = "#" * max(1, min(level, 6))
        formatted = f"{tag} {text}"
        while self._chain and self._chain[-1][0] >= level:
            self._chain.pop()
        self._chain.append((level, formatted))

    def prefix(self) -> str:
        if not self._chain:
            return ""
        return "\n\n".join(t for _, t in self._chain)

    def trailing_titles_chunk(self, page_idx: int, bbox: List[int]) -> Dict:
        return {
            "type": "text",
            "text": self.prefix(),
            "page_idx": page_idx,
            "bbox": bbox,
        }


# ── Chunker 类 ─────────────────────────────────────────────

class Chunker:
    """智能语义切块器。"""

    def __init__(self, config: ChunkerConfig = None):
        self.config = config or ChunkerConfig()

    def chunk(self, content_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """对 content_list 执行切块，返回 chunk 列表。"""
        if not content_list:
            return []

        cfg = self.config
        result: List[Dict] = []
        titles = _TitleStack()

        pending_items: List[Dict] = []
        pending_chars: int = 0

        # ── flush helpers ─────────────────────────────────

        def flush() -> None:
            nonlocal pending_items, pending_chars
            if not pending_items:
                return

            merged = ""
            page_idx = pending_items[0].get("page_idx", 0)
            bbox = list(pending_items[0].get("bbox", [0, 0, 0, 0]))

            for item in pending_items:
                merged += _get_text(item) + "\n"
                ibox = item.get("bbox", [0, 0, 0, 0])
                if ibox:
                    bbox[0] = min(bbox[0], ibox[0])
                    bbox[1] = min(bbox[1], ibox[1])
                    bbox[2] = max(bbox[2], ibox[2])
                    bbox[3] = max(bbox[3], ibox[3])

            merged = merged.strip()
            prefix = titles.prefix()
            content = f"{prefix}\n\n{merged}" if prefix else merged

            result.append({
                "type": "text", "text": content,
                "page_idx": page_idx, "bbox": bbox,
            })
            pending_items.clear()
            pending_chars = 0

        def emit_split(text: str, page_idx: int, bbox: List[int]) -> None:
            prefix = titles.prefix()
            for part in _split_long_text(text, cfg.max_chunk_chars):
                part = part.strip()
                if not part:
                    continue
                content = f"{prefix}\n\n{part}" if prefix else part
                result.append({
                    "type": "text", "text": content,
                    "page_idx": page_idx, "bbox": bbox,
                })

        def emit_standalone(item: Dict) -> None:
            body = _get_text(item)
            prefix = titles.prefix()
            content = f"{prefix}\n\n{body}" if prefix else body
            new_item = {
                "type": item.get("type"),
                "text": content,
                "page_idx": item.get("page_idx", 0),
                "bbox": item.get("bbox", [0, 0, 0, 0]),
            }
            for f in ("table_body", "table_caption", "table_footnote",
                       "img_path", "text_format", "html",
                       "code_language", "list_items"):
                if f in item:
                    new_item[f] = item[f]
            result.append(new_item)

        # ── 主循环 ────────────────────────────────────────

        last_title_for_trailing = None

        for item in content_list:
            item_type = item.get("type", "text")
            page_idx = item.get("page_idx", 0)

            # 透传类型
            if item_type in cfg.passthrough_types:
                flush()
                result.append(item)
                last_title_for_trailing = None
                continue

            # 标题
            if _is_title(item):
                flush()
                level = item.get("text_level", 1)
                titles.push(level, _get_text(item))
                last_title_for_trailing = (page_idx, item.get("bbox", [0, 0, 0, 0]))
                continue

            # 独立类型
            if item_type in cfg.standalone_types:
                flush()
                emit_standalone(item)
                last_title_for_trailing = None
                continue

            # 可合并文本
            if item_type in cfg.mergeable_types or item_type == "text":
                text = _get_text(item)
                if not text:
                    continue

                item_chars = count_chars(text)
                last_title_for_trailing = None
                same_page = (pending_items and
                             pending_items[-1].get("page_idx") == page_idx)

                if same_page and pending_chars + item_chars <= cfg.max_chunk_chars:
                    pending_items.append(item)
                    pending_chars += item_chars
                else:
                    flush()
                    if item_chars > cfg.max_chunk_chars:
                        emit_split(text, page_idx, item.get("bbox", [0, 0, 0, 0]))
                    else:
                        pending_items.append(item)
                        pending_chars = item_chars
                continue

            # 兜底：未知类型当文本
            text = _get_text(item)
            if text:
                flush()
                emit_split(text, item.get("page_idx", 0), item.get("bbox", [0, 0, 0, 0]))
                last_title_for_trailing = None

        flush()

        # 文档以标题结尾时输出残留标题链
        if last_title_for_trailing and not any(
            c.get("type") == "text" and titles.prefix() in c.get("text", "")
            for c in result[-3:] if c.get("type") == "text"
        ):
            pg, bb = last_title_for_trailing
            result.append(titles.trailing_titles_chunk(pg, bb))

        return result
