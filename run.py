import os
from pathlib import Path

# 必须设置：使用本地下载的模型，不走网络
os.environ["MINERU_MODEL_SOURCE"] = "local"
os.environ["HF_HUB_OFFLINE"] = "1"

from mineru.cli.common import do_parse, read_fn

# 读取 PDF
pdf_path = Path("2.pdf")
print(f"正在解析: {pdf_path} ({pdf_path.stat().st_size / 1024:.0f} KB)")

pdf_bytes = read_fn(pdf_path)

# 解析
do_parse(
    output_dir="./output_new",
    pdf_file_names=[pdf_path.stem],
    pdf_bytes_list=[pdf_bytes],
    p_lang_list=["ch"],
    backend="pipeline",
    parse_method="auto",
    formula_enable=True,
    table_enable=True,
)

# 读取并显示结果
md_path = Path(f"./output/{pdf_path.stem}/auto/{pdf_path.stem}.md")
if md_path.exists():
    content = md_path.read_text(encoding="utf-8")
    print(f"\n解析完成，输出: {md_path}")
    print(f"共 {len(content)} 字符")
else:
    print("解析失败，未生成输出文件")
