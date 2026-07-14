from research_app.repository import canonicalize_url
from research_app.sources import SourceRetriever, infer_source_type, looks_primary


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
