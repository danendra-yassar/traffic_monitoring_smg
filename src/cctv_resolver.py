
import json
import re

import requests

from urllib.parse import urljoin, urlsplit, urlunsplit

from config.settings import (
    CCTV_PAGE_URL,
    CCTV_REQUEST_TIMEOUT,
    CCTV_STREAM_PLAYLIST,
)


class CCTVResolverError(Exception):
    """Error ketika URL CCTV tidak berhasil ditemukan."""


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


def get_cctv_url(target_cctv_name):
    """
    Mengambil URL stream berdasarkan nama CCTV.

    Contoh:
        get_cctv_url("ARAH TUGU TUNAS")
    """

    if not target_cctv_name:
        raise CCTVResolverError(
            "Nama CCTV tidak boleh kosong."
        )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Cache-Control": "no-cache",
    }

    print("[CCTV] Mengambil halaman PANTAUSEMAR...")

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

    print("[CCTV] Mengekstrak data kamera...")

    cctvs_data = _extract_cctvs_data(response.text)

    if not isinstance(cctvs_data, list):
        raise CCTVResolverError(
            "Format data CCTV tidak sesuai."
        )

    target_name = target_cctv_name.strip().casefold()

    print(
        f"[CCTV] Mencari kamera: {target_cctv_name}"
    )

    for cctv in cctvs_data:
        if not isinstance(cctv, dict):
            continue

        owner_name = str(
            cctv.get("owner_name", "")
        ).strip().casefold()

        if owner_name != target_name:
            continue

        links = cctv.get("links", [])

        if not isinstance(links, list):
            raise CCTVResolverError(
                "Format links CCTV tidak sesuai."
            )

        # Gunakan link pertama yang memiliki URL valid.
        for link in links:
            if not isinstance(link, dict):
                continue

            raw_url = link.get("url")

            if not isinstance(raw_url, str) or not raw_url.strip():
                continue

            # Mendukung URL absolut, relatif, dan //host/path.
            stream_url = urljoin(
                CCTV_PAGE_URL,
                raw_url.strip(),
            )

            parsed_url = urlsplit(stream_url)

            current_playlist = parsed_url.path.rsplit("/", 1)[-1]

            if current_playlist == "index.m3u8":
                new_path = (
                    parsed_url.path.rsplit("/", 1)[0]
                    + "/"
                    + CCTV_STREAM_PLAYLIST
                )

                stream_url = urlunsplit(
                    parsed_url._replace(path=new_path)
                )

            print(f"[CCTV] Playlist terpilih: {CCTV_STREAM_PLAYLIST}")

            parsed_url = urlsplit(stream_url)

            if parsed_url.scheme not in ("http", "https"):
                continue

            print(
                f"[CCTV] Kamera ditemukan: {target_cctv_name}"
            )

            return stream_url

        raise CCTVResolverError(
            f"Kamera '{target_cctv_name}' ditemukan, "
            "tetapi tidak memiliki URL stream yang valid."
        )

    raise CCTVResolverError(
        f"Kamera '{target_cctv_name}' tidak ditemukan."
    )
