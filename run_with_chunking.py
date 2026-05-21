"""
MinerU 本地解析 + 智能语义切块 一体化脚本。

用法:
    python run_with_chunking.py                  # 默认 2.pdf
    python run_with_chunking.py myfile.pdf       # PDF 文件 → MinerU 解析 → 切块
    python run_with_chunking.py myfile.md        # MD 文件 → 直接切块

输出:
    output/<文件名>/auto/<文件名>_chunks.json      切块结果
    (PDF) output/<文件名>/auto/                    MinerU 完整输出
"""

import os
import sys
import io
import json
import re
import time
from pathlib import Path

try:
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
except Exception:
    pass
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["MINERU_MODEL_SOURCE"] = "local"
os.environ["HF_HUB_OFFLINE"] = "1"


# ── MD → content_list 转换 ───────────────────────────────

_HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)


def _md_to_content_list(md_text: str) -> list:
    """将 markdown 文本转为 MinerU content_list 格式，复用同一套切块逻辑。"""
    items = []
    # 按空行分隔段落
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


# ── 文件类型判断 ──────────────────────────────────────────

PDF_EXTS  = {".pdf"}
MD_EXTS   = {".md", ".markdown", ".txt"}


def _detect_type(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    if ext in PDF_EXTS:
        return "pdf"
    if ext in MD_EXTS:
        return "md"
    raise ValueError(f"不支持的文件类型: {ext}")


# ── 处理入口 ──────────────────────────────────────────────

def process_file(file_path: str, output_dir: str = "./output") -> Path:
    """自动识别文件类型，解析并切块。"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    file_type = _detect_type(path)
    file_stem = path.stem

    if file_type == "pdf":
        return _process_pdf(path, file_stem, output_dir)
    else:
        return _process_md(path, file_stem, output_dir)


def _process_pdf(path: Path, stem: str, output_dir: str) -> Path:
    """PDF: MinerU 解析 → content_list → 切块。"""
    from mineru.cli.common import do_parse, read_fn

    size_kb = path.stat().st_size / 1024
    print(f"[PDF] 解析: {path.name} ({size_kb:.0f} KB)")

    pdf_bytes = read_fn(path)

    print(f"      MinerU 解析中... (pipeline/auto)")
    t0 = time.time()
    do_parse(
        output_dir=output_dir,
        pdf_file_names=[stem],
        pdf_bytes_list=[pdf_bytes],
        p_lang_list=["ch"],
        backend="pipeline",
        parse_method="auto",
        formula_enable=True,
        table_enable=True,
    )
    print(f"      耗时 {time.time() - t0:.1f}s")

    parse_dir = Path(output_dir) / stem / "auto"
    content_path = parse_dir / f"{stem}_content_list.json"
    if not content_path.exists():
        raise FileNotFoundError(f"MinerU 未生成: {content_path}")

    content_list = json.loads(content_path.read_text(encoding="utf-8"))
    return _chunk_and_save(content_list, parse_dir, stem)


def _process_md(path: Path, stem: str, output_dir: str) -> Path:
    """MD: 直接读取 → 转为 content_list → 切块。"""
    size_kb = path.stat().st_size / 1024
    print(f"[MD]  解析: {path.name} ({size_kb:.0f} KB)")

    md_text = None
    for enc in ('utf-8', 'gbk', 'gb2312', 'latin-1'):
        try:
            md_text = path.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    if md_text is None:
        raise ValueError(f"无法读取文件: {path}")

    content_list = _md_to_content_list(md_text)
    print(f"      转换为 {len(content_list)} 个 block")

    parse_dir = Path(output_dir) / stem / "auto"
    parse_dir.mkdir(parents=True, exist_ok=True)
    return _chunk_and_save(content_list, parse_dir, stem)


# ── 切块 & 保存（PDF / MD 共用） ───────────────────────────

def _chunk_and_save(content_list: list, parse_dir: Path, stem: str) -> Path:
    from chunking import chunk_content_list

    print(f"      切块前: {len(content_list)} 个 block")
    chunks = chunk_content_list(content_list)
    print(f"      切块后: {len(chunks)} 个 chunk")

    chunk_path = parse_dir / f"{stem}_chunks.json"
    chunk_path.write_text(
        json.dumps(chunks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"      已保存: {chunk_path}")

    _print_summary(chunks)
    return chunk_path


def _print_summary(chunks: list) -> None:
    from chunking import _count_chars

    print("\n" + "=" * 60)
    for i, chunk in enumerate(chunks):
        ctype = chunk.get("type", "?")
        page = chunk.get("page_idx", "?")
        text = chunk.get("text", "")

        if ctype != "text":
            print(f"\n[{i}] [{ctype}] page={page}  (保留下游处理)")
            continue

        chars = _count_chars(text)
        preview = text[:100].replace("\n", " | ")
        print(f"\n[{i}] page={page} chars~{chars}")
        print(f"    {preview}...")

    text_chunks = [c for c in chunks if c.get("type") == "text"]
    chars_l = [_count_chars(c.get("text", "")) for c in text_chunks]
    print(f"\n{'=' * 60}")
    print(f"共 {len(text_chunks)} 个文本 chunk, "
          f"min={min(chars_l)}, max={max(chars_l)}, avg={sum(chars_l)//len(chars_l)} chars")


# ── CLI ────────────────────────────────────────────────────

if __name__ == "__main__":
    file = sys.argv[1] if len(sys.argv) > 1 else "2.pdf"

    # 支持拖拽/通配符等多文件输入
    files = sys.argv[1:] if len(sys.argv) > 1 else ["2.pdf"]
    for f in files:
        try:
            process_file(f)
        except Exception as e:
            print(f"错误 [{f}]: {e}")
