from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass

from .mapping_store import MappingStore


@dataclass(frozen=True)
class Match:
    start: int
    end: int
    kind: str
    value: str


EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
URL_RE = re.compile(r"(?i)\bhttps?://[^\s<>]+")
IPV4_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?90[\s().-]*)?0?\d{3}[\s().-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}(?!\d)")
IBAN_RE = re.compile(r"(?i)\bTR\d{2}(?:[\s-]?\d){22}\b")
LONG_NUMBER_RE = re.compile(r"(?<!\d)\d{11,20}(?!\d)")


def _valid_ipv4(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).version == 4
    except ValueError:
        return False


class TextAnonymizer:
    """Eşleşmeleri orijinal metinden toplar ve sağdan sola tek kez uygular."""

    def __init__(self, store: MappingStore):
        self.store = store

    def _matches(self, text: str) -> list[Match]:
        candidates: list[Match] = []
        for kind, regex in (("url", URL_RE), ("email", EMAIL_RE), ("iban", IBAN_RE), ("ipv4", IPV4_RE), ("phone", PHONE_RE), ("number", LONG_NUMBER_RE)):
            for found in regex.finditer(text):
                if kind == "ipv4" and not _valid_ipv4(found.group(0)):
                    continue
                candidates.append(Match(found.start(), found.end(), kind, found.group(0)))
        # Öncelik sırasına göre çakışan alt eşleşmeleri çıkar.
        priority = {"url": 0, "email": 1, "iban": 2, "ipv4": 3, "phone": 4, "number": 5}
        selected: list[Match] = []
        for candidate in sorted(candidates, key=lambda m: (priority[m.kind], m.start, -(m.end - m.start))):
            if not any(candidate.start < x.end and x.start < candidate.end for x in selected):
                selected.append(candidate)
        return sorted(selected, key=lambda m: m.start)

    def _replacement(self, match: Match) -> str:
        if match.kind == "phone": return self.store.phone(match.value)
        if match.kind == "ipv4": return self.store.ip(match.value)
        if match.kind == "email":
            local, _domain = match.value.rsplit("@", 1)
            domain = self.store.token(match.value, "email-domain").lower()
            return f"{self.store.token(local, 'email-local').lower()}@{domain}.test"
        if match.kind == "url": return self.store.url(match.value, mode="domain")
        if match.kind == "iban": return self.store.formatted_identifier(match.value, "iban")
        digits = re.sub(r"\D", "", match.value)
        if len(digits) == 11: return self.store.tc(match.value)
        if len(digits) in (14, 15): return self.store.imei(match.value)
        return self.store.numeric_identifier(match.value, "embedded-identifier")

    def transform(self, text: str) -> tuple[str, dict[str, int]]:
        matches = self._matches(text)
        result = text
        counts: dict[str, int] = {}
        for match in reversed(matches):
            replacement = self._replacement(match)
            result = result[:match.start] + replacement + result[match.end:]
            counts[match.kind] = counts.get(match.kind, 0) + 1
        return result, counts

    def counts(self, text: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for match in self._matches(text):
            counts[match.kind] = counts.get(match.kind, 0) + 1
        return counts

    def fingerprints(self, text: str) -> set[str]:
        return {self.store.source_hash("residual", f"{m.kind}\0{m.value}") for m in self._matches(text)}
