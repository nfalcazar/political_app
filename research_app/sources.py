from __future__ import annotations

from dataclasses import dataclass
import io
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from pypdf import PdfReader
import requests


PRIMARY_HOST_MARKERS = (
    "congress.gov",
    "gao.gov",
    "bls.gov",
    "census.gov",
    "supremecourt.gov",
    "doi.org",
    "nber.org",
)


@dataclass
class RetrievedDocument:
    content: str
    chunks: list[tuple[str, str]]
    title: str | None
    outbound_links: list[str]


def looks_primary(url: str) -> bool:
    host = urlsplit(url).netloc.lower()
    return (
        host.endswith(".gov")
        or host == "doi.org"
        or any(host == marker or host.endswith(f".{marker}") for marker in PRIMARY_HOST_MARKERS)
    )


def infer_source_type(url: str) -> str:
    lower = url.lower()
    if "doi.org" in lower or "nber.org" in lower:
        return "scientific_study"
    if "congress.gov" in lower:
        return "legislation_or_statute"
    if "court" in lower:
        return "court_ruling"
    if ".gov" in lower:
        return "government_data"
    return "secondary_report"


class SourceRetriever:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.headers = {"User-Agent": "PoliticalResearch/0.1 (+personal research tool)"}

    def retrieve(self, url: str) -> RetrievedDocument:
        response = requests.get(url, headers=self.headers, timeout=self.timeout)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "pdf" in content_type or urlsplit(url).path.lower().endswith(".pdf"):
            document = self._pdf(response.content)
        else:
            document = self._html(response.text, url)
        if not document.chunks:
            raise ValueError(f"No usable text was retrieved from {url}")
        return document

    def _pdf(self, content: bytes) -> RetrievedDocument:
        reader = PdfReader(io.BytesIO(content))
        chunks = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = " ".join((page.extract_text() or "").split())
            if text:
                chunks.extend(self._split_text(text, f"page {page_number}"))
        return RetrievedDocument(
            content="\n\n".join(text for _, text in chunks),
            chunks=chunks,
            title=reader.metadata.title if reader.metadata else None,
            outbound_links=[],
        )

    def _html(self, content: str, base_url: str) -> RetrievedDocument:
        soup = BeautifulSoup(content, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else None
        for element in soup(["script", "style", "nav", "footer", "form", "noscript"]):
            element.decompose()
        paragraphs = [
            " ".join(element.get_text(" ", strip=True).split())
            for element in soup.find_all(["p", "li", "blockquote", "h1", "h2", "h3"])
        ]
        paragraphs = [text for text in paragraphs if len(text) >= 40]
        chunks: list[tuple[str, str]] = []
        buffer: list[str] = []
        start = 1
        size = 0
        for number, paragraph in enumerate(paragraphs, start=1):
            if buffer and size + len(paragraph) > 4000:
                chunks.append((f"paragraphs {start}-{number - 1}", "\n".join(buffer)))
                buffer, start, size = [], number, 0
            buffer.append(paragraph)
            size += len(paragraph)
        if buffer:
            chunks.append((f"paragraphs {start}-{len(paragraphs)}", "\n".join(buffer)))
        links = []
        for anchor in soup.find_all("a", href=True):
            url = urljoin(base_url, anchor["href"])
            if url.startswith(("http://", "https://")):
                links.append(url)
        return RetrievedDocument(
            content="\n\n".join(text for _, text in chunks),
            chunks=chunks,
            title=title,
            outbound_links=list(dict.fromkeys(links)),
        )

    @staticmethod
    def _split_text(text: str, locator: str, limit: int = 4000) -> list[tuple[str, str]]:
        if len(text) <= limit:
            return [(locator, text)]
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks, buffer = [], []
        size = 0
        part = 1
        for sentence in sentences:
            if buffer and size + len(sentence) > limit:
                chunks.append((f"{locator}, part {part}", " ".join(buffer)))
                buffer, size, part = [], 0, part + 1
            buffer.append(sentence)
            size += len(sentence)
        if buffer:
            chunks.append((f"{locator}, part {part}", " ".join(buffer)))
        return chunks
