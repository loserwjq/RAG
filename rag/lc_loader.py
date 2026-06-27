"""
LangChain Document Loader 适配器 — 将现有解析器封装为 BaseLoader 接口。

支持所有现有文件格式: PDF, PPTX, PPT, DOCX, XLSX, XLS, MD, TXT, Markdown。

用法:
    from rag.lc_loader import RAGDocumentLoader
    from rag.config import ParserConfig
    from pathlib import Path

    loader = RAGDocumentLoader(Path("doc.pdf"), ParserConfig())
    for doc in loader.lazy_load():
        print(doc.page_content[:100])
"""

from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

from rag.config import ParserConfig
from rag.parser import get_parser


class RAGDocumentLoader(BaseLoader):
    """LangChain Document Loader，封装 NeuralKB 的现有解析器。

    委托给 rag.parser.get_parser() 获取格式匹配的解析器，
    将 content_list 转换为 LangChain Document 对象。

    每个 content_list 项 → 一个 Document:
        - page_content: block.get("text", "")
        - metadata: 所有其他字段（type, page_idx, bbox, text_level, ...）
    """

    # 标准 metadata 字段（会放入 Document.metadata）
    STANDARD_META_KEYS = {"type", "page_idx", "bbox", "text_level"}

    def __init__(
        self,
        file_path: Path,
        config: Optional[ParserConfig] = None,
        doc_name: str = "",
    ):
        """
        参数:
            file_path: 文件路径
            config: 解析器配置（默认 ParserConfig()）
            doc_name: 文档名称（默认取文件名 stem）
        """
        self.file_path = file_path
        self.config = config or ParserConfig()
        self.doc_name = doc_name or file_path.stem

    def lazy_load(self) -> Iterator[Document]:
        """惰性解析文件，逐个产出 LangChain Document。

        每个 Document 对应 content_list 中的一个 block。
        """
        if not self.file_path.exists():
            raise FileNotFoundError(f"文件不存在: {self.file_path}")

        # 使用现有解析器
        parser = get_parser(self.file_path, self.config)
        content_list = parser.parse(self.file_path)

        for i, block in enumerate(content_list):
            text = block.get("text", "")
            if not text and block.get("type", "text") not in ("image", "chart", "seal"):
                # 非透传类型且无文本，跳过
                continue

            # 构建 metadata：标准字段 + 所有扩展字段
            metadata: Dict[str, Any] = {
                "source": str(self.file_path),
                "doc_name": self.doc_name,
                "block_idx": i,
            }

            # 标准字段
            for key in self.STANDARD_META_KEYS:
                if key in block:
                    metadata[key] = block[key]

            # 扩展字段（table_body, table_caption, img_path, text_format, html, ...）
            for key, value in block.items():
                if key not in self.STANDARD_META_KEYS and key != "text":
                    metadata[key] = value

            yield Document(
                page_content=text,
                metadata=metadata,
            )
