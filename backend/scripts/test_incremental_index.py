import app.rag.indexer as indexer
from app.rag.loader import load_knowledge_documents
from app.rag.splitter import split_documents


class EmbeddingMustNotRun:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise AssertionError(
            "Unchanged chunks unexpectedly requested new embeddings"
        )


def main() -> None:
    chunks = split_documents(load_knowledge_documents())
    original_get_embedding_model = indexer.get_embedding_model
    indexer.get_embedding_model = lambda: EmbeddingMustNotRun()
    try:
        indexed_count = indexer.rebuild_index(chunks)
    finally:
        indexer.get_embedding_model = original_get_embedding_model

    expected_count = len(
        {indexer.build_chunk_id(chunk) for chunk in chunks}
    )
    assert indexed_count == expected_count
    print(
        {
            "indexed_chunks": indexed_count,
            "embedding_requests": 0,
        }
    )


if __name__ == "__main__":
    main()
