"""Helpers for decoding XML files without depending on the process locale."""

from __future__ import annotations

import locale
import re

_XML_ENCODING_RE = re.compile(br"<\?xml[^>]*\bencoding=[\"']([^\"']+)[\"']", re.IGNORECASE)


def declared_xml_encoding(data: bytes) -> str | None:
    """Return the XML declaration encoding, if present in the first bytes."""
    match = _XML_ENCODING_RE.search(data[:512])
    if not match:
        return None
    try:
        return match.group(1).decode("ascii")
    except UnicodeDecodeError:
        return None


def decode_xml_bytes(data: bytes) -> str:
    """Decode XML bytes using declaration/UTF-8 before the OS ANSI code page."""
    encodings: list[str] = []
    declared = declared_xml_encoding(data)
    if declared:
        encodings.append(declared)
    encodings.extend(["utf-8-sig", "utf-8"])

    preferred = locale.getpreferredencoding(False)
    if preferred:
        encodings.append(preferred)

    tried: set[str] = set()
    last_error: UnicodeDecodeError | None = None
    for encoding in encodings:
        normalized = encoding.lower()
        if normalized in tried:
            continue
        tried.add(normalized)
        try:
            return data.decode(encoding)
        except UnicodeDecodeError as e:
            last_error = e

    if last_error is not None:
        raise last_error
    return data.decode("utf-8")
