from __future__ import annotations

import hashlib
import json
from pathlib import Path

from openpyxl import load_workbook

from .detector import detect_sections


def inspect_workbook(path: Path) -> dict:
    wb = load_workbook(path, read_only=False, data_only=False)
    result = {"file_id": hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:12], "sheets": []}
    for sheet_index, ws in enumerate(wb.worksheets, 1):
        sections = detect_sections(ws)
        result["sheets"].append({
            "sheet_index": sheet_index,
            "name_hash": hashlib.sha256(ws.title.encode("utf-8")).hexdigest()[:12],
            "rows": ws.max_row,
            "columns": ws.max_column,
            "merged_ranges": len(ws.merged_cells.ranges),
            "sections": [{
                "title_hash": hashlib.sha256(s.title.encode("utf-8")).hexdigest()[:12],
                "title_row": s.title_row,
                "header_row": s.header_row,
                "end_row": s.end_row,
                "columns": [{"column": col, "header_hash": hashlib.sha256(s.raw_headers.get(col, "").encode("utf-8")).hexdigest()[:12], "category": cat} for col, cat in sorted(s.columns.items())],
            } for s in sections],
        })
    wb.close()
    return result


def write_inspection(path: Path, output: Path) -> None:
    output.write_text(json.dumps(inspect_workbook(path), ensure_ascii=False, indent=2), encoding="utf-8")
