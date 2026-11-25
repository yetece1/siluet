from __future__ import annotations

import hashlib
from dataclasses import dataclass

from openpyxl import load_workbook


def _style_fingerprint(cell) -> tuple:
    # openpyxl boş hücrelerde varsayılan StyleArray ile None arasında geçiş
    # yapabilir; iki durum Excel açısından aynı görünür biçimdir.
    style = tuple(cell._style) if cell._style is not None else (0,) * 9
    return (style, cell.number_format, cell.alignment.horizontal, cell.alignment.vertical)


def workbook_structure(path) -> dict:
    wb = load_workbook(path, data_only=False)
    result = {
        "sheetnames": wb.sheetnames,
        "sheets": [{
            "title": ws.title,
            "max_row": ws.max_row,
            "max_column": ws.max_column,
            "merged": tuple(sorted(str(x) for x in ws.merged_cells.ranges)),
            "row_dims": tuple(sorted((k, v.height, v.hidden) for k, v in ws.row_dimensions.items())),
            "col_dims": tuple(sorted((k, v.width, v.hidden) for k, v in ws.column_dimensions.items())),
            "styles": tuple(_style_fingerprint(c) for row in ws.iter_rows() for c in row),
        } for ws in wb.worksheets],
    }
    wb.close()
    return result


def value_hashes(path) -> list[str]:
    wb = load_workbook(path, data_only=False)
    result = [hashlib.sha256(str(c.value).encode("utf-8")).hexdigest() for ws in wb for row in ws.iter_rows() for c in row if c.value is not None]
    wb.close()
    return result


@dataclass
class ValidationResult:
    structure_preserved: bool
    row_order_preserved: bool
    no_formula_loss: bool

    @property
    def ok(self) -> bool:
        return all((self.structure_preserved, self.row_order_preserved, self.no_formula_loss))


def validate_structure(before, after) -> ValidationResult:
    a, b = workbook_structure(before), workbook_structure(after)
    structure = a == b
    # Değer değişikliği beklenir; satır/sütun ve sayfa sırası yapısal parmak izindedir.
    row_order = all(x["max_row"] == y["max_row"] and x["max_column"] == y["max_column"] for x, y in zip(a["sheets"], b["sheets"]))
    wa, wb = load_workbook(before, data_only=False), load_workbook(after, data_only=False)
    formulas_a = [(ws.title, c.coordinate, c.value) for ws in wa for row in ws.iter_rows() for c in row if c.data_type == "f"]
    formulas_b = [(ws.title, c.coordinate, c.value) for ws in wb for row in ws.iter_rows() for c in row if c.data_type == "f"]
    wa.close(); wb.close()
    return ValidationResult(structure, row_order, formulas_a == formulas_b)
