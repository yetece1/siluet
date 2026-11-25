from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class AuditReport:
    files: int = 0
    sheets: int = 0
    rows: int = 0
    sections: list[dict] = field(default_factory=list)
    changed: Counter = field(default_factory=Counter)
    protected_base_cells: int = 0
    empty_cells: int = 0
    unknown_columns: list[dict] = field(default_factory=list)
    residual_findings: list[dict] = field(default_factory=list)
    sanitized_cells: int = 0
    identifier_count_errors: int = 0
    simplified_phone_cells: int = 0
    simplified_cells: Counter = field(default_factory=Counter)
    collisions: int = 0
    integrity: dict[str, bool] = field(default_factory=dict)

    def safe_dict(self) -> dict:
        data = asdict(self)
        data["changed"] = dict(self.changed)
        data["simplified_cells"] = dict(self.simplified_cells)
        return data

    def write(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        data = self.safe_dict()
        (output_dir / "rapor.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        lines = [
            "HTS ANONİMLEŞTİRME DENETİM RAPORU",
            f"İşlenen dosya: {self.files}", f"İşlenen sayfa: {self.sheets}", f"İşlenen satır: {self.rows}",
            f"Korunan BAZ hücresi: {self.protected_base_cells}", f"Boş hücre: {self.empty_cells}",
            f"Sadeleştirilen birleşik telefon hücresi: {self.simplified_phone_cells}",
            f"Tanımlayıcı sayım hatası: {self.identifier_count_errors}",
        ]
        lines.extend(f"Sadeleştirilen {key} hücresi: {count}" for key, count in sorted(self.simplified_cells.items()))
        lines.extend(f"Değiştirilen {key}: {count}" for key, count in sorted(self.changed.items()))
        lines.extend(f"Bütünlük {key}: {'GEÇTİ' if value else 'BAŞARISIZ'}" for key, value in sorted(self.integrity.items()))
        (output_dir / "rapor.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
