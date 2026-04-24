from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from langchain_core.documents import Document


@dataclass
class ParsedDocument:
    text: str
    metadata: dict


def _parse_with_docling(file_path: Path) -> str:
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    result = converter.convert(str(file_path))
    return result.document.export_to_markdown()


def _parse_with_pypdf(file_path: Path) -> list[Document]:
    from langchain_community.document_loaders import PyPDFLoader

    loader = PyPDFLoader(str(file_path))
    docs = loader.load()
    for d in docs:
        d.metadata["source"] = file_path.name
    return docs


def parse_pdf(file_path: str | Path, patient_id: str | None = None) -> list[Document]:
    path = Path(file_path)

    try:
        text = _parse_with_docling(path)
        return [
            Document(
                page_content=text,
                metadata={
                    "source": path.name,
                    "document_type": "medical_report",
                    "patient_id": patient_id or "unknown",
                    "page": 1,
                },
            )
        ]
    except Exception:
        # Fallback to robust page-level PDF parsing if Docling fails.
        docs = _parse_with_pypdf(path)
        for d in docs:
            d.metadata["document_type"] = d.metadata.get("document_type", "medical_report")
            d.metadata["patient_id"] = patient_id or d.metadata.get("patient_id", "unknown")
        return docs
