"""Son açılan proje klasörleri (yalnız klasör yolu saklanır)."""
from __future__ import annotations

import os
from pathlib import Path

KEY = "recent_projects"
LIMIT = 8


class RecentProjects:
    def __init__(self, settings) -> None:
        self.settings = settings

    def _raw(self) -> list[str]:
        value = self.settings.value(KEY, [])
        if isinstance(value, str):
            value = [value] if value else []
        return [str(x) for x in (value or [])]

    def list(self) -> list[Path]:
        return [Path(x) for x in self._raw() if Path(x).is_dir()]

    def add(self, path: Path) -> None:
        resolved = str(Path(path).resolve())
        items = [x for x in self._raw() if os.path.normcase(x) != os.path.normcase(resolved)]
        self.settings.setValue(KEY, [resolved, *items][:LIMIT])

    def remove(self, path: Path) -> None:
        resolved = os.path.normcase(str(Path(path).resolve()))
        self.settings.setValue(KEY, [x for x in self._raw() if os.path.normcase(x) != resolved])
