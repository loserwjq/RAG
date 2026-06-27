"""
LangChain TextSplitter 适配器 — 将智能语义切块器封装为标准接口。

保留所有现有切块逻辑：
    - 标题挂载（title-grafting）
    - 短块合并（smart merge）
    - 长块拆分（sentence-boundary split）
    - 表格/公式独立处理
    - 图片/图表透传

用法:
    from rag.lc_splitter import HybridChunkTextSplitter
    from rag.config import ChunkerConfig

    splitter = HybridChunkTextSplitter(ChunkerConfig())
    chunk_docs = splitter.split_documents(documents)
"""

from typing import Any, Dict, List

from langchain_core.documents import Document
from langchain_text_splitters import TextSplitter

from rag.chunker import Chunker
from rag.config import ChunkerConfig


class HybridChunkTextSplitter(TextSplitter):
    """LangChain TextSplitter，封装 NeuralKB 的智能语义切块器。

    流程: Document → content_list → Chunker.chunk() → Document
    """

    # content_list 项中的非标准 metadata 字段（会透传到 chunker）
    _CONTENT_META_KEYS = {
        "table_body", "table_caption", "table_footnote",
        "img_path", "text_format", "html",
        "code_language", "list_items",
    }

    def __init__(self, config: ChunkerConfig = None, **kwargs):
        """
        参数:
            config: 切块配置（默认 ChunkerConfig()）
        """
        super().__init__(**kwargs)
        self._config = config or ChunkerConfig()
        self._chunker = Chunker(self._config)

    def split_text(self, text: str) -> List[str]:
        """LangChain TextSplitter 抽象方法实现。

        对纯文本执行简单的句子边界拆分。完整的语义切块（标题挂载、
        表格处理等）请使用 split_documents()。

        参数:
            text: 输入文本

        返回: 切分后的文本块列表
        """
        from rag.chunker import count_chars, _split_long_text

        if not text:
            return []

        return _split_long_text(text, self._config.max_chunk_chars)

    def split_documents(self, documents: List[Document]) -> List[Document]:
        """对 Document 列表执行智能语义切块。

        参数:
            documents: LangChain Document 列表（通常来自 RAGDocumentLoader）

        返回: 切块后的 Document 列表
        """
        if not documents:
            return []

        # Step 1: Document → content_list
        content_list = []
        for doc in documents:
            item: Dict[str, Any] = {
                "type": doc.metadata.get("type", "text"),
                "text": doc.page_content,
                "page_idx": doc.metadata.get("page_idx", 0),
                "bbox": doc.metadata.get("bbox", [0, 0, 0, 0]),
                "text_level": doc.metadata.get("text_level", 0),
            }
            # 透传扩展字段（table_body, img_path, html, ...）
            for key in self._CONTENT_META_KEYS:
                if key in doc.metadata:
                    item[key] = doc.metadata[key]
            content_list.append(item)

        # Step 2: 运行现有切块器
        chunks = self._chunker.chunk(content_list)

        # Step 3: chunk → Document
        chunk_docs = []
        for i, chunk in enumerate(chunks):
            meta = {
                "type": chunk.get("type", "text"),
                "page_idx": chunk.get("page_idx", 0),
                "bbox": chunk.get("bbox", [0, 0, 0, 0]),
                "chunk_idx": i,
            }

            # 保留原始文档的 source/doc_name
            if documents:
                first_doc = documents[0]
                meta["source"] = first_doc.metadata.get("source", "")
                meta["doc_name"] = first_doc.metadata.get("doc_name", "")

            # 透传扩展字段
            for key in self._CONTENT_META_KEYS:
                if key in chunk:
                    meta[key] = chunk[key]

            chunk_docs.append(Document(
                page_content=chunk.get("text", ""),
                metadata=meta,
            ))

        return chunk_docs
