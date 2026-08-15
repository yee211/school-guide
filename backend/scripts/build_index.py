
from app.rag.indexer import rebuild_index
from app.rag.loader import load_knowledge_documents
from app.rag.splitter import split_documents


def main() -> None:
    print("开始读取学校资料……")
    documents = load_knowledge_documents()

    print(f"读取到 {len(documents)} 个文档")

    chunks = split_documents(documents)
    print(f"切分成 {len(chunks)} 个片段")

    indexed_count = rebuild_index(chunks)

    print(f"成功写入 {indexed_count} 个向量")
    print("知识库构建完成")


if __name__ == "__main__":
    main()