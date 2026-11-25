from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook

from .detector import detect_sections
from .normalization import digits, fold
from .project import ROLE_COUNTER, ROLE_MAIN


FILE_LABELS = ("dosya no", "esas no", "sorusturma no", "karar no", "evrak no", "yazi no")
QUERY_DATE_LABELS = ("sorgu baslangic", "sorgu bitis", "sorgu araligi", "tarih araligi")
PRIMARY_HEADERS = {"numara", "telefon", "telefon no", "gsm", "sorgulanan no"}
OTHER_NUMBER_TOKENS = ("diger", "arayan", "aranan", "a numara", "b numara")


@dataclass
class WorkbookProfile:
    path: Path
    sheets: list[str] = field(default_factory=list)
    primary_key: str = ""
    case_key: str = ""
    date_key: str = ""
    family_key: str = ""
    richness: int = 0
    base_sections: int = 0
    internet_sections: int = 0
    role: str | None = None
    confidence: str = "belirsiz"
    reasons: list[str] = field(default_factory=list)

    @property
    def relation_key(self) -> str:
        if self.primary_key and self.case_key:
            return f"case-phone:{self.case_key}:{self.primary_key}"
        if self.primary_key and self.date_key:
            return f"date-phone:{self.date_key}:{self.primary_key}"
        if self.primary_key:
            return f"phone:{self.primary_key}"
        if self.case_key:
            return f"case:{self.case_key}"
        return f"family:{self.family_key}"


@dataclass
class AutoGroup:
    group_key: str
    profiles: list[WorkbookProfile]
    confident: bool


@dataclass
class InspectionFailure:
    path: Path
    error_type: str


def _assign_role(profile: WorkbookProfile) -> None:
    if profile.internet_sections > 0 or profile.base_sections > 1:
        profile.role, profile.confidence = ROLE_MAIN, "yüksek"
        profile.reasons.append("zengin ana-baz bölüm yapısı")
    elif profile.base_sections == 1:
        profile.role, profile.confidence = ROLE_COUNTER, "yüksek"
        profile.reasons.append("tek karşı-baz bölüm yapısı")


def _match_score(main: WorkbookProfile, counter: WorkbookProfile) -> int:
    score = 0
    has_relation_evidence = False
    if main.primary_key and counter.primary_key:
        # Matching queried numbers are strong evidence. A mismatch is not a
        # rejection: counter-baz exports may put the related number in another
        # semantic column, so structural/family evidence must remain usable.
        if main.primary_key == counter.primary_key:
            score += 100
            has_relation_evidence = True
    if main.case_key and counter.case_key:
        if main.case_key == counter.case_key:
            score += 60
            has_relation_evidence = True
        else:
            score -= 80
    if main.date_key and counter.date_key:
        if main.date_key == counter.date_key:
            score += 30
            has_relation_evidence = True
        else:
            score -= 20
    if main.family_key == counter.family_key:
        score += 80
        has_relation_evidence = True
    if main.path.parent == counter.path.parent:
        score += 40
    # Sharing a directory is only a tie-breaker; it can never create a pair.
    return score if has_relation_evidence else -10_000


def _private_key(namespace: str, value: str) -> str:
    return hashlib.sha256(f"{namespace}\0{fold(value)}".encode("utf-8")).hexdigest()


def _family_key(path: Path) -> str:
    stem = fold(path.stem)
    stem = re.sub(r"\b(?:ana|karsi|karşı|main|counter|normal|baz)\b", " ", stem)
    # Some operator exports use 2/4 and 6/8 as pair identifiers. This is only
    # a relation fallback; role detection above never depends on a filename.
    pair_suffix = ""
    match = re.search(r"(?:^|[_ .-])(2|4|6|8)$", stem)
    if match:
        pair_suffix = "-a" if match.group(1) in {"2", "4"} else "-b"
        stem = stem[:match.start()].strip(" _.-")
    return _private_key("family", (stem or path.parent.name) + pair_suffix)


def _metadata_values(ws, labels: tuple[str, ...]) -> list[str]:
    values: list[str] = []
    for row in ws.iter_rows():
        for cell in row:
            if not isinstance(cell.value, str):
                continue
            normalized = fold(cell.value)
            if not any(label in normalized for label in labels):
                continue
            if ":" in cell.value:
                right = cell.value.split(":", 1)[1].strip()
                if right:
                    values.append(right)
            neighbor = ws.cell(cell.row, cell.column + 1).value
            if neighbor not in (None, ""):
                values.append(str(neighbor))
    return values


def inspect_profile(path: Path, cancelled=None) -> WorkbookProfile:
    profile = WorkbookProfile(path=path.resolve(), family_key=_family_key(path))
    wb = load_workbook(path, data_only=False, read_only=False)
    profile.sheets = list(wb.sheetnames)
    phone_counts: Counter[str] = Counter()
    case_values: list[str] = []
    date_values: list[str] = []
    category_counts: Counter[str] = Counter()
    try:
        for ws in wb.worksheets:
            if cancelled and cancelled():
                raise InterruptedError("Dosya analizi iptal edildi")
            case_values.extend(_metadata_values(ws, FILE_LABELS))
            date_values.extend(_metadata_values(ws, QUERY_DATE_LABELS))
            for section in detect_sections(ws):
                title = fold(section.title)
                if any(token in title for token in ("gprs", "wap", "internet baglanti", "cgnat", "ipdr")):
                    profile.internet_sections += 1
                if not section.header_row:
                    continue
                category_counts.update(section.columns.values())
                if any(category == "base" for category in section.columns.values()):
                    profile.base_sections += 1
                for col, category in section.columns.items():
                    if category != "phone":
                        continue
                    raw_header = fold(section.raw_headers.get(col, ""))
                    is_primary = raw_header in PRIMARY_HEADERS or (
                        "numara" in raw_header and not any(token in raw_header for token in OTHER_NUMBER_TOKENS)
                    )
                    if not is_primary:
                        continue
                    for row in range(section.header_row + 1, section.end_row + 1):
                        if row % 500 == 0 and cancelled and cancelled():
                            raise InterruptedError("Dosya analizi iptal edildi")
                        value = digits(ws.cell(row, col).value)
                        if 10 <= len(value) <= 13:
                            phone_counts[value] += 1
    finally:
        wb.close()

    if phone_counts:
        primary = max(phone_counts, key=lambda value: (phone_counts[value], value))
        profile.primary_key = _private_key("primary", primary)
    if case_values:
        profile.case_key = _private_key("case", "|".join(sorted(fold(x) for x in case_values if fold(x))))
    if date_values:
        profile.date_key = _private_key("dates", "|".join(sorted(fold(x) for x in date_values if fold(x))))

    profile.richness = (
        profile.internet_sections * 10
        + profile.base_sections * 4
        + category_counts["ip"] * 2
        + category_counts["url"] * 2
        + category_counts["byte_size"]
    )
    if profile.internet_sections:
        profile.reasons.append("internet/GPRS/WAP bölümü")
    if profile.base_sections > 1:
        profile.reasons.append("birden çok bölümde BAZ sütunu")
    return profile


def classify_files(
    paths: list[Path], progress=None, cancelled=None
) -> tuple[list[AutoGroup], list[WorkbookProfile], list[InspectionFailure]]:
    """Classify any number of workbooks without retaining them in memory.

    Roles come from workbook content.  Filenames are used only as a low-weight
    relationship hint and never decide whether a workbook is main or counter.
    """
    profiles: list[WorkbookProfile] = []
    failures: list[InspectionFailure] = []
    unique = list(dict.fromkeys(Path(p).resolve() for p in paths))
    for index, path in enumerate(unique, 1):
        if cancelled and cancelled():
            raise InterruptedError("Dosya analizi iptal edildi")
        try:
            profile = inspect_profile(path, cancelled)
            _assign_role(profile)
            profiles.append(profile)
        except InterruptedError:
            raise
        except Exception as exc:
            failures.append(InspectionFailure(path, type(exc).__name__))
        if progress:
            progress(index, len(unique), path.name)

    mains = [p for p in profiles if p.role == ROLE_MAIN]
    counters = [p for p in profiles if p.role == ROLE_COUNTER]
    ambiguous = [p for p in profiles if p.role is None]
    candidates = sorted(
        ((_match_score(m, c), m, c) for m in mains for c in counters),
        key=lambda item: (-item[0], str(item[1].path), str(item[2].path)),
    )
    used_main: set[Path] = set()
    used_counter: set[Path] = set()
    groups: list[AutoGroup] = []
    for score, main, counter in candidates:
        # 25 means at least a matching filename family; 100 means a matching
        # primary number. Lower scores are unsafe and remain isolated.
        if score < 25 or main.path in used_main or counter.path in used_counter:
            continue
        key = _private_key("pair", f"{main.path}\0{counter.path}")
        groups.append(AutoGroup(key, [main, counter], score >= 60))
        used_main.add(main.path)
        used_counter.add(counter.path)

    # A confident role is still processable without a mate. Keeping it in its
    # own group prevents mappings from leaking into any unrelated workbook.
    remaining = [p for p in mains if p.path not in used_main] + [p for p in counters if p.path not in used_counter]
    for profile in sorted(remaining, key=lambda p: str(p.path)):
        groups.append(AutoGroup(_private_key("single", str(profile.path)), [profile], False))
    return groups, ambiguous, failures
