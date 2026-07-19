from research_app.utils import canonicalize_url
import pytest
import requests

from research_app.sources import (
    HostAdapterRegistry,
    InteractiveResult,
    RestrictedSourceError,
    RetrievalFailure,
    SourceRetriever,
    infer_source_type,
    looks_primary,
    validate_public_url,
)
from research_app.content_policy import TokenCounter, classify_rights


def test_url_canonicalization_removes_tracking_parameters():
    assert canonicalize_url(
        "HTTPS://Example.COM/report/?utm_source=x&year=2024#section"
    ) == "https://example.com/report?year=2024"


def test_primary_source_classification():
    assert looks_primary("https://www.bls.gov/news.release/union2.htm")
    assert infer_source_type("https://doi.org/10.1234/example") == "scientific_study"
    assert not looks_primary("https://example.com/news")
    assert not looks_primary("https://bls.gov.example.com/fake")


def test_html_retrieval_creates_stable_locators():
    document = SourceRetriever()._html(
        """
        <html><head><title>Study</title></head><body>
        <nav>Ignore navigation content that is deliberately long.</nav>
        <h1>Union outcomes research heading with enough useful content</h1>
        <p>This paragraph contains a sufficiently detailed description of the research finding.</p>
        <a href="https://www.bls.gov/report.pdf">Primary report</a>
        </body></html>
        """,
        "https://example.com/article",
    )
    assert document.title == "Study"
    assert document.chunks[0][0].startswith("paragraphs ")
    assert "research finding" in document.content
    assert document.outbound_links == ["https://www.bls.gov/report.pdf"]


def test_oversized_unpunctuated_html_is_split_by_model_tokens():
    document = SourceRetriever()._html(
        f"<html><body><p>{'occupation evidence ' * 20000}</p></body></html>",
        "https://example.com/long",
    )
    counter = TokenCounter()
    assert len(document.chunks) > 10
    assert max(counter.count(text) for _, text in document.chunks) <= 1024


def test_rights_classification_is_conservative():
    assert classify_rights("https://history.state.gov/report")[0] == "public_domain"
    assert classify_rights("https://www.gov.il/report")[0] == "unknown"
    assert classify_rights("https://example.com/report")[0] == "unknown"
    assert classify_rights(
        "https://example.com/report", "https://creativecommons.org/licenses/by/4.0/"
    )[0] == "open_license"


def test_private_network_urls_are_rejected_before_retrieval():
    with pytest.raises(RestrictedSourceError):
        validate_public_url("http://127.0.0.1/private")


def test_host_adapter_finds_public_document_and_json_ld_links():
    links = HostAdapterRegistry().candidates(
        "https://documents.un.org/page",
        """
        <a href="/download/report.pdf">Download report</a>
        <script type="application/ld+json">{"contentUrl": "/files/data.pdf"}</script>
        """,
    )
    assert links == [
        "https://documents.un.org/download/report.pdf",
        "https://documents.un.org/files/data.pdf",
    ]


def test_static_document_adapter_runs_before_browser(monkeypatch):
    monkeypatch.setattr("research_app.sources.validate_public_url", lambda _url: None)

    class Resolver:
        timeout = 10
        def resolve(self, _url):
            return []

    class Session:
        def get(self, url, **_kwargs):
            response = requests.Response()
            response.url = url
            if url.endswith("robots.txt"):
                response.status_code = 404
                response._content = b""
            elif url == "https://example.gov/report":
                response.status_code = 200
                response.headers["content-type"] = "text/html"
                response._content = b'<a href="/download/report">Download report</a>'
            else:
                response.status_code = 200
                response.headers["content-type"] = "text/html"
                response._content = b"<p>The official document contains enough public evidence for extraction and review.</p>"
            return response

    class Browser:
        enabled = True
        timeout = 10
        calls = 0
        def render(self, _url):
            self.calls += 1
            return InteractiveResult("", _url, [])

    browser = Browser()
    document = SourceRetriever(
        session=Session(), resolver=Resolver(), interactive=browser
    ).retrieve("https://example.gov/report")
    assert "official document" in document.content
    assert browser.calls == 0
    assert any(item["method"] == "host_adapter" for item in document.retrieval_attempts)


def test_browser_is_not_used_for_access_denial(monkeypatch):
    monkeypatch.setattr("research_app.sources.validate_public_url", lambda _url: None)

    class Resolver:
        timeout = 10
        def resolve(self, _url):
            return []

    class Session:
        def get(self, url, **_kwargs):
            response = requests.Response()
            response.url = url
            response.status_code = 404 if url.endswith("robots.txt") else 403
            response._content = b""
            return response

    class Browser:
        enabled = True
        timeout = 10
        calls = 0
        def render(self, _url):
            self.calls += 1
            raise AssertionError("browser must not run")

    browser = Browser()
    with pytest.raises(RestrictedSourceError):
        SourceRetriever(
            session=Session(), resolver=Resolver(), interactive=browser
        ).retrieve("https://example.gov/denied")
    assert browser.calls == 0


def test_failed_pdf_is_marked_as_needing_ocr():
    assert SourceRetriever()._pdf(b"not a valid PDF").needs_ocr


def test_authentication_forms_are_classified_as_restricted_content():
    assert SourceRetriever._looks_restricted_page(
        '<form action="/login"><input type="password"></form>'
    )


def test_declared_oversized_download_is_rejected_before_body_read():
    response = requests.Response()
    response.headers["content-length"] = str(2 * 1024 * 1024)
    retriever = SourceRetriever(max_download_mb=1)
    with pytest.raises(RetrievalFailure, match="size limit"):
        retriever._read_bounded(response)
