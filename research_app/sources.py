from __future__ import annotations

from dataclasses import dataclass
import io
import ipaddress
import json
import re
import socket
import time
from typing import Protocol
from urllib.parse import quote, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup
from pypdf import PdfReader
import requests

from .content_policy import TokenChunker


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
    detected_license: str | None = None
    retrieval_permission: str = "public_http"
    robots_status: str = "not_checked"
    terms_status: str = "not_checked"
    resolved_url: str | None = None
    retrieval_attempts: list[dict] | None = None
    alternate_urls: list[str] | None = None
    needs_ocr: bool = False


@dataclass
class InteractiveResult:
    html: str
    url: str
    actions: list[dict]
    download: bytes | None = None
    download_content_type: str | None = None


class InteractiveRetriever(Protocol):
    enabled: bool

    def render(self, url: str) -> InteractiveResult: ...


class DisabledInteractiveRetriever:
    enabled = False

    def render(self, url: str) -> InteractiveResult:
        raise RuntimeError("Interactive retrieval is disabled")


class RetrievalFailure(ValueError):
    def __init__(
        self,
        message: str,
        *,
        outcome_code: str = "retrieval_failed",
        attempts: list[dict] | None = None,
        needs_ocr: bool = False,
    ):
        super().__init__(message)
        self.outcome_code = outcome_code
        self.attempts = attempts or []
        self.needs_ocr = needs_ocr


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


class RestrictedSourceError(RetrievalFailure):
    pass


def validate_public_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise RestrictedSourceError(
            f"Unsafe source URL: {url}", outcome_code="unsafe_url"
        )
    host = parts.hostname.rstrip(".").casefold()
    if host == "localhost" or host.endswith(".localhost"):
        raise RestrictedSourceError(
            f"Private-network source URL is not allowed: {url}",
            outcome_code="private_network",
        )
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(item[4][0])
                for item in socket.getaddrinfo(host, parts.port or 443, type=socket.SOCK_STREAM)
            }
        except socket.gaierror as exc:
            raise RetrievalFailure(
                f"Source hostname could not be resolved: {host}",
                outcome_code="dns_failure",
            ) from exc
    if any(not address.is_global for address in addresses):
        raise RestrictedSourceError(
            f"Private-network source URL is not allowed: {url}",
            outcome_code="private_network",
        )


class AlternateLocationResolver:
    def __init__(self, email: str | None = None, timeout: int = 15, session=None):
        self.email = email
        self.timeout = timeout
        self.session = session or requests.Session()

    @staticmethod
    def doi_from_url(url: str) -> str | None:
        lower = url.casefold()
        if "doi.org/" not in lower:
            return None
        return url[lower.index("doi.org/") + len("doi.org/"):].split("?", 1)[0].strip("/")

    def resolve(self, url: str) -> list[str]:
        doi = self.doi_from_url(url)
        if not doi:
            return []
        locations: list[str] = []
        if self.email:
            try:
                response = self.session.get(
                    f"https://api.unpaywall.org/v2/{quote(doi, safe='')}",
                    params={"email": self.email}, timeout=self.timeout,
                )
                response.raise_for_status()
                payload = response.json()
                for item in [payload.get("best_oa_location"), *(payload.get("oa_locations") or [])]:
                    if item:
                        locations.extend(filter(None, [item.get("url_for_pdf"), item.get("url")]))
            except (requests.RequestException, ValueError, TypeError):
                pass
        try:
            work_id = quote(f"https://doi.org/{doi}", safe="")
            response = self.session.get(
                f"https://api.openalex.org/works/{work_id}", timeout=self.timeout
            )
            response.raise_for_status()
            payload = response.json()
            for item in [payload.get("best_oa_location"), *(payload.get("locations") or [])]:
                if item:
                    locations.extend(filter(None, [item.get("pdf_url"), item.get("landing_page_url")]))
        except (requests.RequestException, ValueError, TypeError):
            pass
        return list(dict.fromkeys(item for item in locations if item and item != url))


class HostAdapterRegistry:
    """Discover public document targets exposed by known landing-page patterns."""

    _DOCUMENT_HINT = re.compile(
        r"(?:\.pdf(?:$|\?)|download|full[-_ ]?text|document|report|publication)", re.I
    )
    _SUPPORTED_HOST = re.compile(
        r"(?:^|\.)(?:un\.org|undocs\.org|docs\.un\.org|gov|gov\.uk|europa\.eu)$",
        re.I,
    )

    def candidates(self, url: str, html: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        host = urlsplit(url).hostname or ""
        supported = bool(self._SUPPORTED_HOST.search(host)) or "doi.org" in host
        values: list[str] = []
        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "")
            label = anchor.get_text(" ", strip=True)
            candidate = urljoin(url, href)
            if candidate.startswith(("http://", "https://")) and (
                self._DOCUMENT_HINT.search(f"{href} {label}") or supported and ".pdf" in href.casefold()
            ):
                values.append(candidate)
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                payloads = json.loads(script.string or "")
            except (TypeError, ValueError):
                continue
            queue = payloads if isinstance(payloads, list) else [payloads]
            for payload in queue:
                if not isinstance(payload, dict):
                    continue
                for key in ("contentUrl", "encoding", "url"):
                    value = payload.get(key)
                    if isinstance(value, dict):
                        value = value.get("contentUrl") or value.get("url")
                    if isinstance(value, str) and self._DOCUMENT_HINT.search(value):
                        values.append(urljoin(url, value))
        return list(dict.fromkeys(values))[:8]


class PlaywrightInteractiveRetriever:
    enabled = True
    _SAFE_ACTIONS = (
        ("expand", re.compile(r"\b(show|read|view|load)\s+(more|full|all)\b", re.I)),
        ("next_page", re.compile(r"^(next|older|more results)$", re.I)),
        ("content_tab", re.compile(r"^(text|transcript|full text|document|report)$", re.I)),
        ("reject_cookies", re.compile(r"\b(reject|decline|dismiss|close)\b.*\b(cookie|cookies|all)\b", re.I)),
        ("download", re.compile(r"\b(download|view)\b.*\b(pdf|document|report)\b", re.I)),
    )
    _FORBIDDEN = re.compile(r"login|log in|sign in|subscribe|purchase|checkout|accept|agree|register", re.I)
    _ACCESS_CONTROL = re.compile(
        r"captcha|verify you are human|access denied|subscription required|purchase access|sign in to continue|log in to continue",
        re.I,
    )

    def __init__(self, timeout: int = 30, max_actions: int = 5, max_pages: int = 3, max_download_mb: int = 25):
        self.timeout = timeout
        self.max_actions = max_actions
        self.max_pages = max_pages
        self.max_download_bytes = max_download_mb * 1024 * 1024

    def render(self, url: str) -> InteractiveResult:
        validate_public_url(url)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("Install the browser extra and run `playwright install chromium`") from exc
        actions: list[dict] = []
        downloads = []
        started = time.monotonic()
        with sync_playwright() as driver:
            browser = driver.chromium.launch(headless=True)
            context = browser.new_context(accept_downloads=True)
            context.set_default_timeout(self.timeout * 1000)
            context.on("download", lambda download: downloads.append(download))

            def guard_request(route):
                try:
                    validate_public_url(route.request.url)
                    route.continue_()
                except RetrievalFailure:
                    route.abort("blockedbyclient")

            context.route("**/*", guard_request)
            page = context.new_page()
            response = page.goto(
                url, wait_until="domcontentloaded", timeout=self.timeout * 1000
            )
            validate_public_url(page.url)
            if response and response.status in {401, 402, 403}:
                raise RestrictedSourceError(
                    f"Browser received HTTP {response.status}",
                    outcome_code=f"http_{response.status}",
                )
            if page.locator(
                'input[type="password"], form[action*="login" i], form[action*="signin" i], form[action*="auth" i]'
            ).count():
                raise RestrictedSourceError(
                    "Browser detected an authentication form",
                    outcome_code="access_control_page",
                )
            if self._ACCESS_CONTROL.search(page.locator("body").inner_text(timeout=1000)):
                raise RestrictedSourceError(
                    "Browser detected an access-control page",
                    outcome_code="access_control_page",
                )
            origin = (urlsplit(page.url).scheme, urlsplit(page.url).netloc.casefold())
            page_count = 1
            candidates = page.locator("button, a[href], [role=tab]")
            for index in range(min(candidates.count(), 250)):
                remaining_ms = int((self.timeout - (time.monotonic() - started)) * 1000)
                if len(actions) >= self.max_actions or remaining_ms <= 0:
                    break
                element = candidates.nth(index)
                try:
                    label = " ".join(
                        (element.inner_text(timeout=min(500, remaining_ms)) or "").split()
                    )
                    if not label or self._FORBIDDEN.search(label):
                        continue
                    action_kind = next(
                        (kind for kind, pattern in self._SAFE_ACTIONS if pattern.search(label)), None
                    )
                    if not action_kind:
                        continue
                    href = element.get_attribute("href")
                    if href:
                        target = urljoin(page.url, href)
                        target_parts = urlsplit(target)
                        if (target_parts.scheme, target_parts.netloc.casefold()) != origin:
                            continue
                        validate_public_url(target)
                    if action_kind == "next_page" and page_count >= self.max_pages:
                        continue
                    before = page.url
                    element.click(timeout=min(2000, remaining_ms))
                    page.wait_for_timeout(250)
                    if page.url != before:
                        current = urlsplit(page.url)
                        if (current.scheme, current.netloc.casefold()) != origin:
                            raise RestrictedSourceError(
                                "Browser action navigated across origins", outcome_code="unsafe_redirect"
                            )
                        validate_public_url(page.url)
                        page_count += 1
                    actions.append({"kind": action_kind, "label": label[:160], "url": page.url})
                except RestrictedSourceError:
                    raise
                except Exception:
                    continue
            html = page.content()
            final_url = page.url
            download_bytes = None
            if downloads:
                download_url = downloads[-1].url
                validate_public_url(download_url)
                download_parts = urlsplit(download_url)
                if (download_parts.scheme, download_parts.netloc.casefold()) != origin:
                    raise RestrictedSourceError(
                        "Browser download crossed origins",
                        outcome_code="unsafe_redirect",
                    )
                path = downloads[-1].path()
                if path:
                    with open(path, "rb") as handle:
                        download_bytes = handle.read(self.max_download_bytes + 1)
                    if len(download_bytes) > self.max_download_bytes:
                        raise RetrievalFailure(
                            "Browser download exceeds configured limit",
                            outcome_code="download_too_large",
                        )
            context.close()
            browser.close()
        return InteractiveResult(
            html,
            final_url,
            actions,
            download_bytes,
            "application/pdf" if download_bytes and download_url.casefold().endswith(".pdf") else None,
        )


class SourceRetriever:
    def __init__(
        self,
        timeout: int = 30,
        chunker: TokenChunker | None = None,
        *,
        interactive: InteractiveRetriever | None = None,
        resolver: AlternateLocationResolver | None = None,
        adapters: HostAdapterRegistry | None = None,
        unpaywall_email: str | None = None,
        max_download_mb: int = 25,
        session=None,
    ):
        self.timeout = timeout
        self.headers = {"User-Agent": "PoliticalResearch/0.1 (+personal research tool)"}
        self.chunker = chunker or TokenChunker()
        self.interactive = interactive or DisabledInteractiveRetriever()
        self.session = session or requests.Session()
        self.resolver = resolver or AlternateLocationResolver(unpaywall_email, session=self.session)
        self.adapters = adapters or HostAdapterRegistry()
        self.max_download_bytes = max_download_mb * 1024 * 1024

    def retrieve(self, url: str) -> RetrievedDocument:
        alternates = self.resolver.resolve(url)
        attempts: list[dict] = [{
            "method": "identifier_resolution",
            "url": url,
            "outcome": "alternates_found" if alternates else "not_applicable",
            "alternate_count": len(alternates),
        }]
        candidates = list(dict.fromkeys([*alternates, url]))
        browser_candidates: list[tuple[str, str]] = []
        restricted = False
        last_error = f"No usable text was retrieved from {url}"
        for candidate in candidates:
            started = time.monotonic()
            try:
                validate_public_url(candidate)
                robots_status = self._robots_status(candidate)
                attempts.append({
                    "method": "preflight",
                    "url": candidate,
                    "outcome": robots_status,
                })
                if robots_status == "disallowed":
                    restricted = True
                    raise RestrictedSourceError(
                        f"robots.txt disallows retrieval: {candidate}",
                        outcome_code="robots_disallowed",
                    )
                response = self._get(candidate)
                content_type = response.headers.get("content-type", "").lower()
                if response.status_code in {401, 402, 403}:
                    restricted = True
                    raise RestrictedSourceError(
                        f"Restricted source returned HTTP {response.status_code}: {response.url}",
                        outcome_code=f"http_{response.status_code}",
                    )
                if response.status_code == 404:
                    raise RetrievalFailure(
                        f"Source returned HTTP 404: {response.url}", outcome_code="http_404"
                    )
                response.raise_for_status()
                self._read_bounded(response)
                if len(response.content) > self.max_download_bytes:
                    raise RetrievalFailure("Source exceeds configured size limit", outcome_code="download_too_large")
                is_pdf = "pdf" in content_type or urlsplit(response.url).path.lower().endswith(".pdf")
                if is_pdf:
                    document = self._pdf(response.content)
                else:
                    if self._looks_restricted_page(response.text):
                        restricted = True
                        raise RestrictedSourceError(
                            f"Access-control page detected at {response.url}",
                            outcome_code="access_control_page",
                        )
                    document = self._html(response.text, response.url)
                    if not document.chunks:
                        new_alternates = [
                            item for item in self.adapters.candidates(response.url, response.text)
                            if item not in candidates
                        ]
                        for alternate in new_alternates:
                            candidates.append(alternate)
                            attempts.append({
                                "method": "host_adapter",
                                "url": response.url,
                                "outcome": "alternate_discovered",
                                "resulting_url": alternate,
                            })
                        if self.interactive.enabled:
                            browser_candidates.append((response.url, robots_status))
                if document.needs_ocr:
                    raise RetrievalFailure(
                        f"Image-only PDF requires OCR: {response.url}",
                        outcome_code="needs_ocr", needs_ocr=True,
                    )
                if not document.chunks:
                    raise RetrievalFailure(
                        f"No usable text was retrieved from {response.url}",
                        outcome_code="no_usable_text",
                    )
                attempts.append({
                    "method": "http", "url": candidate, "resolved_url": response.url,
                    "outcome": "success", "http_status": response.status_code,
                    "content_type": content_type, "elapsed_seconds": round(time.monotonic() - started, 3),
                })
                document.robots_status = robots_status
                document.resolved_url = response.url
                document.retrieval_attempts = attempts
                document.alternate_urls = [
                    item for item in dict.fromkeys(candidates) if item != url
                ]
                return document
            except RetrievalFailure as exc:
                last_error = str(exc)
                attempts.extend(item for item in exc.attempts if item not in attempts)
                attempts.append({
                    "method": "http", "url": candidate, "outcome": exc.outcome_code,
                    "http_status": (
                        int(exc.outcome_code.removeprefix("http_"))
                        if exc.outcome_code.removeprefix("http_").isdigit() else None
                    ),
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                })
                if exc.needs_ocr:
                    raise RetrievalFailure(last_error, outcome_code="needs_ocr", attempts=attempts, needs_ocr=True)
            except requests.RequestException as exc:
                last_error = str(exc)
                attempts.append({
                    "method": "http", "url": candidate, "outcome": "http_error",
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                })
        for candidate, robots_status in dict.fromkeys(browser_candidates):
            started = time.monotonic()
            try:
                rendered = self.interactive.render(candidate)
                validate_public_url(rendered.url)
                if rendered.download:
                    if len(rendered.download) > self.max_download_bytes:
                        raise RetrievalFailure(
                            "Browser download exceeds configured limit",
                            outcome_code="download_too_large",
                        )
                    document = self._pdf(rendered.download)
                else:
                    if self._looks_restricted_page(rendered.html):
                        raise RestrictedSourceError(
                            f"Access-control page detected at {rendered.url}",
                            outcome_code="access_control_page",
                        )
                    document = self._html(rendered.html, rendered.url)
                outcome = "success" if document.chunks else (
                    "needs_ocr" if document.needs_ocr else "no_usable_text"
                )
                attempts.append({
                    "method": "browser",
                    "url": candidate,
                    "resolved_url": rendered.url,
                    "outcome": outcome,
                    "actions": rendered.actions,
                    "content_type": rendered.download_content_type,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                })
                if not document.chunks:
                    continue
                document.robots_status = robots_status
                document.resolved_url = rendered.url
                document.retrieval_attempts = attempts
                document.alternate_urls = list(dict.fromkeys(candidates[1:]))
                return document
            except RetrievalFailure as exc:
                last_error = str(exc)
                attempts.append({
                    "method": "browser", "url": candidate,
                    "outcome": exc.outcome_code,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                })
            except Exception as exc:
                last_error = str(exc)
                attempts.append({
                    "method": "browser", "url": candidate,
                    "outcome": "browser_error",
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                })
        terminal_attempts = [
            item for item in attempts if item.get("method") in {"http", "browser"}
        ]
        restricted_outcomes = {
            "robots_disallowed", "http_401", "http_402", "http_403",
            "access_control_page", "blocklisted",
        }
        error_class = RestrictedSourceError if restricted and terminal_attempts and all(
            item.get("outcome") in restricted_outcomes for item in terminal_attempts
        ) else RetrievalFailure
        raise error_class(last_error, outcome_code="restricted" if error_class is RestrictedSourceError else "retrieval_failed", attempts=attempts)

    def _get(self, url: str):
        current = url
        for _ in range(6):
            validate_public_url(current)
            response = self.session.get(
                current,
                headers=self.headers,
                timeout=self.timeout,
                allow_redirects=False,
                stream=True,
            )
            if response.status_code not in {301, 302, 303, 307, 308}:
                response.url = response.url or current
                return response
            location = response.headers.get("location")
            if not location:
                return response
            current = urljoin(current, location)
        raise RetrievalFailure("Too many source redirects", outcome_code="redirect_loop")

    def _read_bounded(self, response) -> None:
        length = response.headers.get("content-length")
        if length and length.isdigit() and int(length) > self.max_download_bytes:
            if getattr(response, "raw", None) is not None:
                response.close()
            raise RetrievalFailure(
                "Source exceeds configured size limit",
                outcome_code="download_too_large",
            )
        if getattr(response, "raw", None) is None or getattr(
            response, "_content_consumed", False
        ):
            return
        body = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            body.extend(chunk)
            if len(body) > self.max_download_bytes:
                if getattr(response, "raw", None) is not None:
                    response.close()
                raise RetrievalFailure(
                    "Source exceeds configured size limit",
                    outcome_code="download_too_large",
                )
        response._content = bytes(body)
        response._content_consumed = True

    def _robots_status(self, url: str) -> str:
        parts = urlsplit(url)
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        try:
            response = self.session.get(
                robots_url,
                headers=self.headers,
                timeout=min(self.timeout, 10),
            )
            if response.status_code == 404:
                return "not_present"
            if response.status_code >= 400:
                return f"unavailable_http_{response.status_code}"
            parser = RobotFileParser()
            parser.set_url(robots_url)
            parser.parse(response.text.splitlines())
            return "allowed" if parser.can_fetch("PoliticalResearch", url) else "disallowed"
        except requests.RequestException:
            return "unavailable"

    def _pdf(self, content: bytes) -> RetrievedDocument:
        chunks = []
        title = None
        try:
            reader = PdfReader(io.BytesIO(content), strict=False)
            title = reader.metadata.title if reader.metadata else None
            for page_number, page in enumerate(reader.pages, start=1):
                text = " ".join((page.extract_text() or "").split())
                if text:
                    chunks.extend(self.chunker.split(text, f"page {page_number}"))
        except Exception:
            chunks = []
        if not chunks:
            try:
                import fitz
                document = fitz.open(stream=content, filetype="pdf")
                for page_number, page in enumerate(document, start=1):
                    text = " ".join(page.get_text("text").split())
                    if text:
                        chunks.extend(self.chunker.split(text, f"page {page_number}"))
            except Exception:
                pass
        return RetrievedDocument(
            content="\n\n".join(text for _, text in chunks),
            chunks=chunks,
            title=title,
            outbound_links=[],
            needs_ocr=not chunks,
        )

    def _html(self, content: str, base_url: str) -> RetrievedDocument:
        soup = BeautifulSoup(content, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else None
        extracted = None
        try:
            import trafilatura
            extracted = trafilatura.extract(
                content, include_tables=True, include_comments=False,
                favor_recall=True, output_format="txt",
            )
        except (ImportError, ValueError, TypeError):
            extracted = None
        for element in soup(["script", "style", "nav", "footer", "form"]):
            element.decompose()
        if extracted:
            paragraphs = [" ".join(item.split()) for item in re.split(r"\n\s*\n|\n", extracted)]
        else:
            paragraphs = [
                " ".join(element.get_text(" ", strip=True).split())
                for element in soup.find_all(["p", "li", "blockquote", "h1", "h2", "h3", "noscript", "tr"])
            ]
        paragraphs = [text for text in paragraphs if len(text) >= 40]
        expanded: list[tuple[int, str, str]] = []
        for number, paragraph in enumerate(paragraphs, start=1):
            for locator, text in self.chunker.split(paragraph, f"paragraph {number}"):
                expanded.append((number, locator, text))
        chunks: list[tuple[str, str]] = []
        buffer: list[str] = []
        start = 1
        for number, locator, paragraph in expanded:
            candidate = "\n".join([*buffer, paragraph])
            if buffer and self.chunker.counter.count(candidate) > self.chunker.config.target_tokens:
                chunks.extend(self.chunker.split("\n".join(buffer), f"paragraphs {start}-{number - 1}"))
                buffer, start = [], number
            if self.chunker.counter.count(paragraph) > self.chunker.config.target_tokens:
                if buffer:
                    chunks.extend(self.chunker.split("\n".join(buffer), f"paragraphs {start}-{number - 1}"))
                    buffer = []
                chunks.append((locator, paragraph))
                start = number + 1
                continue
            buffer.append(paragraph)
        if buffer:
            chunks.extend(self.chunker.split("\n".join(buffer), f"paragraphs {start}-{len(paragraphs)}"))
        links = []
        for anchor in soup.find_all("a", href=True):
            url = urljoin(base_url, anchor["href"])
            if url.startswith(("http://", "https://")):
                links.append(url)
        license_link = next(
            (
                anchor.get("href")
                for anchor in soup.find_all("a", href=True)
                if "creativecommons.org/licenses/" in anchor.get("href", "").casefold()
            ),
            None,
        )
        terms_status = (
            "terms_link_present"
            if any(
                "terms" in (anchor.get_text(" ", strip=True) + " " + anchor.get("href", "")).casefold()
                for anchor in soup.find_all("a", href=True)
            )
            else "not_detected"
        )
        return RetrievedDocument(
            content="\n\n".join(text for _, text in chunks),
            chunks=chunks,
            title=title,
            outbound_links=list(dict.fromkeys(links)),
            detected_license=license_link,
            terms_status=terms_status,
        )

    @staticmethod
    def _looks_restricted_page(content: str) -> bool:
        soup = BeautifulSoup(content[:200000], "html.parser")
        if soup.select_one(
            'input[type="password"], form[action*="login" i], form[action*="signin" i], form[action*="auth" i]'
        ):
            return True
        sample = " ".join(soup.get_text(" ", strip=True).split()).casefold()
        indicators = (
            "verify you are human", "captcha", "access denied", "subscription required",
            "purchase access", "sign in to continue", "log in to continue",
        )
        return any(item in sample for item in indicators)

    @staticmethod
    def _split_text(text: str, locator: str, limit: int = 4000) -> list[tuple[str, str]]:
        # Compatibility shim for callers/tests; the active path is token-aware.
        return TokenChunker().split(text, locator)
