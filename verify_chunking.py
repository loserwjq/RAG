"""验证 chunking 模块效果 —— 使用真实的 MinerU 输出数据。"""
import json
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from chunking import chunk_content_list, _count_chars

DATA = Path("output_new/2/auto/2_content_list.json")

content_list = json.loads(DATA.read_text(encoding="utf-8"))

print(f"Input: {len(content_list)} blocks")

chunks = chunk_content_list(content_list)
text_chunks = [c for c in chunks if c.get("type") == "text"]
chars_list = [_count_chars(c.get("text", "")) for c in text_chunks]

print(f"Output: {len(chunks)} chunks ({len(text_chunks)} text, {len(chunks) - len(text_chunks)} other)")
print(f"Chars: min={min(chars_list)}, max={max(chars_list)}, avg={sum(chars_list)//len(chars_list)}")
print("=" * 70)

for i, chunk in enumerate(chunks):
    text = chunk.get("text", "")
    ctype = chunk.get("type", "?")
    page = chunk.get("page_idx", "?")

    if ctype != "text":
        print(f"\n-- Chunk {i:02d} [{ctype}] page={page} -- (preserved, not chunked)")
        continue

    chars = _count_chars(text)
    flag = " [OK]" if 200 <= chars <= 800 else ""

    print(f"\n-- Chunk {i:02d} | page={page} | chars={chars}{flag}")
    # Show the title prefix and first line of content
    lines = text.split("\n")
    for line in lines[:8]:
        print(f"    {line}")
    if len(lines) > 8:
        print(f"    ... ({len(lines)} lines total)")

print("\n" + "=" * 70)
print(f"Summary: {len(text_chunks)} text chunks, "
      f"min={min(chars_list)}, max={max(chars_list)}, avg={sum(chars_list)//len(chars_list)}")
