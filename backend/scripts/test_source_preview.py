"""Source preview boundaries and content preservation, without external services."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from langchain_core.documents import Document
from app.api.knowledge import preview_source


class SourcePreviewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.backend = Path(self.temp.name)
        self.raw = self.backend / "data/raw"
        self.raw.mkdir(parents=True)
        self.one = patch("app.api.knowledge.BACKEND_DIR", self.backend)
        self.two = patch("app.api.knowledge.RAW_DATA_DIR", self.raw)
        self.one.start()
        self.two.start()
        self.addCleanup(self.one.stop)
        self.addCleanup(self.two.stop)

    async def test_preserves_markdown_table_and_accepts_both_path_formats(self):
        text = "# 招生计划\n| 专业 | 学费 |\n|---|---|\n| 软件工程 | 4800 |\n"
        (self.raw / "plans.md").write_text(text, encoding="utf-8")
        for source in ("data/raw/plans.md", "backend/data/raw/plans.md"):
            result = await preview_source(source)
            self.assertEqual(result["content"], (self.raw / "plans.md").read_bytes().decode("utf-8"))
            self.assertEqual(result["source"], "data/raw/plans.md")
            self.assertFalse(result["truncated"])

    async def test_blocks_traversal_absolute_paths_and_secrets(self):
        for source in ("data/raw/../../.env", "backend/.env", "C:/secret.txt", "data/raw/../plans.md", "data/raw//plans.md"):
            with self.subTest(source=source), self.assertRaises(HTTPException) as exc:
                await preview_source(source)
            self.assertEqual(exc.exception.status_code, 400)

    async def test_missing_source_returns_not_found(self):
        with self.assertRaises(HTTPException) as exc:
            await preview_source("data/raw/missing.md")
        self.assertEqual(exc.exception.status_code, 404)

    async def test_large_content_reports_truncation(self):
        (self.raw / "long.md").write_text("x" * 70000, encoding="utf-8")
        result = await preview_source("data/raw/long.md")
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["content"]), 60000)

    async def test_oversized_file_is_rejected_before_read(self):
        (self.raw / "big.md").write_text("x" * 30, encoding="utf-8")
        with patch("app.api.knowledge.MAX_FILE_SIZE", 20), self.assertRaises(HTTPException) as exc:
            await preview_source("data/raw/big.md")
        self.assertEqual(exc.exception.status_code, 413)

    async def test_attachment_uses_existing_converter(self):
        (self.raw / "one.pdf").write_bytes(b"test fixture")
        with patch("app.api.knowledge.load_uploaded_documents", return_value=[Document(page_content="附件正文")]) as loader:
            result = await preview_source("data/raw/one.pdf")
        loader.assert_called_once_with("one.pdf", b"test fixture")
        self.assertEqual(result["content"], "附件正文")


if __name__ == "__main__":
    unittest.main()
