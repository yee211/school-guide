import re
from bisect import bisect_right

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.rag.cleaner import document_cleaner
from app.rag.metadata import enrich_document_metadata



_TABLE_SEPARATOR_PATTERN = re.compile(
    r"^\s*\|?(?:\s*:?-+:?\s*\|)+\s*$"
)


def _heading_context(text: str, start_index: int) -> str | None:
    active_headings: dict[int, str] = {}
    for match in re.finditer(r"(?m)^(#{1,6})\s+.+$", text):
        if match.start() > start_index:
            break
        level = len(match.group(1))
        active_headings = {
            heading_level: heading
            for heading_level, heading in active_headings.items()
            if heading_level < level
        }
        active_headings[level] = match.group(0).strip()

    if not active_headings:
        return None
    return "\n".join(
        active_headings[level]
        for level in sorted(active_headings)
    )


def _table_header_before(text: str, start_index: int) -> str | None:
    lines = text.splitlines(keepends=True)
    line_starts: list[int] = []
    offset = 0
    for line in lines:
        line_starts.append(offset)
        offset += len(line)

    latest_header: str | None = None
    for index in range(len(lines) - 1):
        if line_starts[index] > start_index:
            break
        header = lines[index].strip()
        separator = lines[index + 1].strip()
        if (
            header.startswith("|")
            and _TABLE_SEPARATOR_PATTERN.fullmatch(separator)
        ):
            latest_header = f"{header}\n{separator}"
    return latest_header


def _is_heading_only(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return bool(lines) and all(line.startswith("#") for line in lines)


def _add_context(
    chunk: Document,
    heading: str | None,
    table_header: str | None,
) -> Document:
    content = chunk.page_content.strip()
    prefixes: list[str] = []

    if heading and heading not in content:
        prefixes.append(heading)
    if (
        table_header
        and "|" in content
        and table_header not in content
    ):
        prefixes.append(table_header)

    if prefixes:
        content = "\n\n".join([*prefixes, content])

    metadata = dict(chunk.metadata)
    metadata["context_enriched"] = bool(prefixes)
    return Document(page_content=content, metadata=metadata)


def split_documents(
    documents: list[Document],
) -> list[Document]:
    cleaned_documents = document_cleaner.clean_documents(documents)
    if not cleaned_documents:
        return []

    text_splitter = RecursiveCharacterTextSplitter(

        chunk_size=500,
        chunk_overlap=80,
        add_start_index=True,
        separators=[
            "\n# ",
            "\n## ",
            "\n### ",
            "\n\n",
            "\n",
            "。",
            "；",
            "，",
            " ",
            "",
        ],
    )

    chunks: list[Document] = []
    for document in cleaned_documents:
        document_chunks = text_splitter.split_documents([document])
        # Scan each source once; binary search the context at each chunk position.
        heading_offsets, heading_values = [], []
        active = {}
        for match in re.finditer(r"(?m)^(#{1,6})\s+.+$", document.page_content):
            level = len(match.group(1))
            active = {key: value for key, value in active.items() if key < level}
            active[level] = match.group(0).strip()
            heading_offsets.append(match.start())
            heading_values.append("\n".join(active[key] for key in sorted(active)))
        table_offsets, table_values = [], []
        lines = document.page_content.splitlines(keepends=True)
        offset = 0
        in_table = False
        for index, line in enumerate(lines):
            if line.strip().startswith("|") and index + 1 < len(lines) and _TABLE_SEPARATOR_PATTERN.fullmatch(lines[index + 1].strip()):
                table_offsets.append(offset)
                table_values.append(f"{line.strip()}\n{lines[index + 1].strip()}")
                in_table = True
            elif in_table and not line.strip().startswith("|"):
                table_offsets.append(offset)
                table_values.append(None)
                in_table = False
            offset += len(line)
        def context_at(offsets, values, position):
            index = bisect_right(offsets, position) - 1
            return values[index] if index >= 0 else None


        for chunk in document_chunks:
            if len(document_chunks) > 1 and _is_heading_only(
                chunk.page_content
            ):
                continue
            start_index = int(chunk.metadata.get("start_index", 0))
            chunks.append(
                enrich_document_metadata(
                    _add_context(
                        chunk,
                        heading=context_at(heading_offsets, heading_values, start_index),
                        table_header=context_at(table_offsets, table_values, start_index),
                    )
                )
            )

    return chunks
