from pathlib import Path

from app.rag.splitter import split_documents
from app.rag.upload_loader import load_uploaded_documents


BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_FILE = BACKEND_DIR / "data" / "raw" / "school_overview.md"


def main() -> None:
    print(f"测试文件：{TEST_FILE}")

    content = TEST_FILE.read_bytes()

    documents = load_uploaded_documents(
        filename=TEST_FILE.name,
        content=content,
    )

    print(f"解析得到 {len(documents)} 个文档单元")

    chunks = split_documents(documents)

    print(f"切分得到 {len(chunks)} 个片段")

    for index, chunk in enumerate(chunks[:3], start=1):
        print(f"\n===== 切片 {index} =====")
        print("metadata：", chunk.metadata)
        print("content：")
        print(chunk.page_content[:300])


if __name__ == "__main__":
    main()