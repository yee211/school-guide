from app.rag.loader import load_knowledge_documents
from app.rag.splitter import split_documents


def main() -> None:
    documents = load_knowledge_documents()

    print(f"读取到 {len(documents)} 个文档单元")

    for index, document in enumerate(documents, start=1):
        print(f"\n===== 文档单元 {index} =====")
        print(document.metadata)
        print(document.page_content[:100])

    chunks = split_documents(documents)

    print(f"\n总共切分成 {len(chunks)} 个片段")


if __name__ == "__main__":
    main()