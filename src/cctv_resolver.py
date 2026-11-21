# src/cctv_resolver.py

import json
import re
import threading
import time
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests

from config.settings import (
    CCTV_LIST_CACHE_TTL,
    CCTV_PAGE_URL,
    CCTV_REQUEST_TIMEOUT,
    CCTV_STREAM_PLAYLIST,
)


class CCTVResolverError(Exception):
    """Error ketika daftar atau URL CCTV tidak berhasil ditemukan."""


_CACHE_LOCK = threading.Lock()
_CACHED_CATALOG = {}  # key: owner_name.casefold() -> {"name": str, "url": str}
_CACHE_EXPIRES_AT = 0.0


def _extract_cctvs_data(html):
    """
    Mengambil array JSON dari deklarasi:
        var cctvs = [...];

    Parser memperhitungkan nested array dan tanda
    kurung siku yang mungkin berada di dalam string.
    """
    match = re.search(
        r"\b(?:var|let|const)\s+cctvs\s*=",
        html,
    )

    if not match:
        raise CCTVResolverError(
            "Variabel 'cctvs' tidak ditemukan pada halaman."
        )

    start = html.find("[", match.end())

    if start == -1:
        raise CCTVResolverError(
            "Array data CCTV tidak ditemukan."
        )

    depth = 0
    quote = None
    escaped = False
    end = None

    for index in range(start, len(html)):
        char = html[index]

        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue

        if char in ('"', "'", "`"):
            quote = char
            continue

        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                end = index + 1
                break

    if end is None:
        raise CCTVResolverError(
            "Array data CCTV tidak lengkap."
        )

    json_text = html[start:end]

    try:
        return json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise CCTVResolverError(
            "Data cctvs ditemukan, tetapi bukan JSON valid."
        ) from exc


def _resolve_valid_stream_url(links):
    """Memilih URL stream HTTP/HTTPS pertama yang valid dari daftar links."""
    if not isinstance(links, list):
        return None

    for link in links:
        if not isinstance(link, dict):
            continue

        raw_url = link.get("url")
        if not isinstance(raw_url, str) or not raw_url.strip():
            continue

        stream_url = urljoin(CCTV_PAGE_URL, raw_url.strip())
        parsed_url = urlsplit(stream_url)

        current_playlist = parsed_url.path.rsplit("/", 1)[-1]
        if current_playlist == "index.m3u8":
            new_path = (
                parsed_url.path.rsplit("/", 1)[0]
                + "/"
                + CCTV_STREAM_PLAYLIST
            )
            stream_url = urlunsplit(parsed_url._replace(path=new_path))
            parsed_url = urlsplit(stream_url)

        if parsed_url.scheme in ("http", "https") and parsed_url.netloc:
            return stream_url

    return None


def _get_cctv_catalog(force_refresh=False):
    """Mengambil dan meng-cache katalog kamera PANTAUSEMAR yang valid."""
    global _CACHED_CATALOG, _CACHE_EXPIRES_AT

    now = time.monotonic()

    with _CACHE_LOCK:
        if (
            not force_refresh
            and _CACHED_CATALOG
            and now < _CACHE_EXPIRES_AT
        ):
            return dict(_CACHED_CATALOG)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Cache-Control": "no-cache",
    }

    print("[CCTV] Mengambil daftar kamera dari PANTAUSEMAR...")

    try:
        response = requests.get(
            CCTV_PAGE_URL,
            headers=headers,
            timeout=CCTV_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise CCTVResolverError(
            f"Gagal mengakses halaman CCTV: {exc}"
        ) from exc

    cctvs_data = _extract_cctvs_data(response.text)

    if not isinstance(cctvs_data, list):
        raise CCTVResolverError("Format data CCTV tidak sesuai.")

    catalog = {}

    for cctv in cctvs_data:
        if not isinstance(cctv, dict):
            continue

        display_name = str(cctv.get("owner_name", "")).strip()
        if not display_name:
            continue

        stream_url = _resolve_valid_stream_url(cctv.get("links", []))
        if not stream_url:
            continue

        key = display_name.casefold()
        if key not in catalog:
            catalog[key] = {
                "name": display_name,
                "url": stream_url,
            }

    if not catalog:
        raise CCTVResolverError(
            "Tidak ada kamera dengan URL stream valid yang ditemukan."
        )

    with _CACHE_LOCK:
        _CACHED_CATALOG = catalog
        _CACHE_EXPIRES_AT = time.monotonic() + CCTV_LIST_CACHE_TTL
        return dict(_CACHED_CATALOG)


def list_available_cctvs(force_refresh=False):
    """
    Mengembalikan daftar nama kamera (owner_name) yang tersedia
    dan memiliki URL stream valid untuk dropdown antarmuka web.
    """
    catalog = _get_cctv_catalog(force_refresh=force_refresh)
    return sorted(
        (item["name"] for item in catalog.values()),
        key=str.casefold,
    )


def get_cctv_url(target_cctv_name, force_refresh=False):
    """
    Mengambil URL stream berdasarkan nama CCTV resmi dari PANTAUSEMAR.
    """
    if not isinstance(target_cctv_name, str) or not target_cctv_name.strip():
        raise CCTVResolverError("Nama CCTV tidak boleh kosong.")

    target_key = target_cctv_name.strip().casefold()
    catalog = _get_cctv_catalog(force_refresh=force_refresh)

    entry = catalog.get(target_key)

    # Jika tidak ditemukan di cache lama, coba refresh satu kali.
    if entry is None and not force_refresh:
        catalog = _get_cctv_catalog(force_refresh=True)
        entry = catalog.get(target_key)

    if entry is None:
        raise CCTVResolverError(
            f"Kamera '{target_cctv_name}' tidak ditemukan di daftar PANTAUSEMAR."
        )

    print(f"[CCTV] Kamera tervalidasi: {entry['name']}")
    return entry["url"]