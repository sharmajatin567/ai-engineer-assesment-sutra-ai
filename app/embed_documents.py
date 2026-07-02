import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pdfplumber
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.base.read_config import read_config
from app.base.knowledge.knowledge import KnowledgeBankClientFactory
from app.utils import parse_sections

DOCS_DIR = Path("app/docs")
PDFS = ["Leave_Policy.pdf", "Procurement_Process_SOP.pdf"]


def _page_texts(path):
    with pdfplumber.open(path) as pdf:
        return [page.extract_text() or "" for page in pdf.pages]


async def embed():
    config = read_config()
    default_kb_provider = config["KNOWLEDGE_CONFIG"]["DEFAULT_PROVIDER"]
    kb = KnowledgeBankClientFactory(config).client
    knowledge_config = config["KNOWLEDGE_CONFIG"]["PROVIDERS"][default_kb_provider]
    section_index = knowledge_config["SECTION_INDEX_NAME"]
    chunk_index = knowledge_config["CHUNK_INDEX_NAME"]
    splitter = RecursiveCharacterTextSplitter(chunk_size=200, chunk_overlap=20)

    for name in PDFS:
        pages = _page_texts(DOCS_DIR / name)

        # Index sections
        sections = parse_sections(pages, name)
        section_docs = [section["document"] for section in sections]
        section_metas = [section["metadata"] for section in sections]
        count = await kb.bulk_insert(section_docs, section_metas, section_index)
        print(f"{count} Sections indexed for document {name}")

        # Index chunks
        chunk_docs = []
        chunk_metas = []
        for page_number, text in enumerate(pages, start=1):
            for piece in splitter.split_text(text):
                chunk_docs.append(piece)
                chunk_metas.append({"document_name": name, "page_number": page_number})
        count = await kb.bulk_insert(chunk_docs, chunk_metas, chunk_index)
        print(f"{count} chunks indexed for document {name}")


if __name__ == "__main__":
    asyncio.run(embed())
