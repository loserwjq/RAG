"""
RAG Pipeline CLI 入口。

用法:
    python main.py ingest test.md                  # 入库文档
    python main.py ingest 2.pdf                    # 入库 PDF
    python main.py search "加班费怎么算"            # 检索
    python main.py ask "请假流程是什么"             # 问答（待接入 LLM）
    python main.py info                            # 查看向量库状态
"""

import sys
import io
import os

# Windows 控制台 UTF-8
try:
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
except Exception:
    pass

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def cmd_ingest(args):
    """入库文档。"""
    from rag import Pipeline

    pipe = Pipeline()
    for file_path in args:
        try:
            result = pipe.ingest(file_path)
            print(f"\n✓ {result['doc_name']}: "
                  f"{result['n_stored']} chunks 入库 ({result['elapsed']}s)")
        except Exception as e:
            print(f"\n✗ {file_path}: {e}")


def cmd_search(args):
    """检索。"""
    from rag import Pipeline

    if not args:
        print("用法: python main.py search <query>")
        return

    query = " ".join(args)
    pipe = Pipeline()

    print(f"查询: {query}\n")
    results = pipe.search(query, top_k=5)

    if not results:
        print("未找到相关结果。请先使用 ingest 命令入库文档。")
        return

    for i, r in enumerate(results, 1):
        lines = r["content"].split("\n")
        headings = [l.strip("# ").strip() for l in lines if l.startswith("#")]
        section = " > ".join(headings[-2:]) if headings else r["content"][:80]
        print(f"  [{i}] {r['score']:+.3f}  {section[:70]}")
        print(f"       doc={r['metadata'].get('doc_name', '?')} "
              f"page={r['metadata'].get('page_idx', '?')}")


def cmd_ask(args):
    """问答。"""
    from rag import Pipeline

    if not args:
        print("用法: python main.py ask <question>")
        return

    question = " ".join(args)
    pipe = Pipeline()

    print(f"问题: {question}\n")
    result = pipe.ask(question)

    print(f"回答:\n{result['answer']}\n")
    if result["sources"]:
        print(f"参考来源 ({len(result['sources'])} 条):")
        for i, s in enumerate(result["sources"], 1):
            print(f"  [{i}] score={s['score']:.3f} "
                  f"doc={s['metadata'].get('doc_name', '?')}")


def cmd_info(args):
    """查看向量库状态。"""
    from rag import Pipeline

    pipe = Pipeline()
    print(f"向量库路径: {pipe._config.store.persist_dir}")
    print(f"Collection: {pipe._config.store.collection_name}")
    print(f"文档数: {pipe.doc_count}")
    print(f"Collections: {pipe.store.list_collections()}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1].lower()
    args = sys.argv[2:]

    commands = {
        "ingest": cmd_ingest,
        "search": cmd_search,
        "ask": cmd_ask,
        "info": cmd_info,
    }

    if cmd in commands:
        commands[cmd](args)
    else:
        print(f"未知命令: {cmd}")
        print(f"可用命令: {', '.join(commands.keys())}")


if __name__ == "__main__":
    main()
