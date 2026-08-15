from functools import lru_cache
from threading import Lock

import torch
from langchain_core.documents import Document
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
)

from app.core.config import (
    RERANK_BATCH_SIZE,
    RERANK_MAX_LENGTH,
    RERANK_MODEL_ID,
)


class CrossEncoderReranker:
    def __init__(self) -> None:
        self._lock = Lock()

    @staticmethod
    @lru_cache(maxsize=1)
    def _load_model():
        tokenizer = AutoTokenizer.from_pretrained(
            RERANK_MODEL_ID,
        )
        model = AutoModelForSequenceClassification.from_pretrained(
            RERANK_MODEL_ID,
        )
        device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )
        model.to(device)
        model.eval()
        return tokenizer, model, device

    def _score(
        self,
        query: str,
        documents: list[Document],
    ) -> list[float]:
        tokenizer, model, device = self._load_model()
        scores: list[float] = []

        for start in range(0, len(documents), RERANK_BATCH_SIZE):
            batch = documents[start:start + RERANK_BATCH_SIZE]
            inputs = tokenizer(
                [query] * len(batch),
                [document.page_content for document in batch],
                padding=True,
                truncation=True,
                max_length=RERANK_MAX_LENGTH,
                return_tensors="pt",
            )
            inputs = {
                key: value.to(device)
                for key, value in inputs.items()
            }

            with torch.inference_mode():
                logits = model(**inputs).logits

            scores.extend(
                logits.reshape(-1).float().cpu().tolist()
            )

        return scores

    def rerank(
        self,
        query: str,
        documents: list[Document],
        top_k: int,
    ) -> list[Document]:
        if not documents or top_k <= 0:
            return []

        with self._lock:
            scores = self._score(query, documents)

        ranked = sorted(
            zip(documents, scores),
            key=lambda item: item[1],
            reverse=True,
        )
        return [document for document, _ in ranked[:top_k]]


cross_encoder_reranker = CrossEncoderReranker()
