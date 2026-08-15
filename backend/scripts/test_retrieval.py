import asyncio

from app.rag.retriever import retriever_service


async def main() -> None:
    question = "学校有哪些特色专业？"

    documents = await retriever_service.search(
        query=question,
        top_k=2,
    )

    print(f"检索到 {len(documents)} 个片段")

    for index, document in enumerate(documents, start=1):
        print(f"\n===== 检索结果 {index} =====")
        print(f"来源：{document.metadata.get('source')}")
        print(f"起始位置：{document.metadata.get('start_index')}")
        print(document.page_content)


if __name__ == "__main__":
    asyncio.run(main())