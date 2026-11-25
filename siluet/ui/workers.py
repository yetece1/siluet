"""Arka plan işleri: sınıflandırma ve anonimleştirme.

İş, sade bir Python iş parçacığında yürür; işçi QObject'i ana iş parçacığında yaşar ve
sinyalleri Qt tarafından ana iş parçacığına kuyruklanır. QThread kullanılmaz: Python'a ait
QThread/QObject'lerin çöp toplayıcı tarafından rastgele bir iş parçacığında yok edilmesi
ara sıra çökmeye yol açıyordu. İşçiye son referans her zaman ana iş parçacığında bırakılır.
"""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, Qt, Signal, Slot

from ..auto_classifier import classify_files
from ..group_processor import GroupProcessor, _safe_error_message

# Çalışan işçiler; yalnız ana iş parçacığında eklenir ve çıkarılır.
_ACTIVE: set["_CancellableWorker"] = set()


class _CancellableWorker(QObject):
    failed = Signal(str)
    cancelled = Signal()
    done = Signal(object)  # her durumda en son yayılır; işçinin kendisini taşır

    def __init__(self) -> None:
        super().__init__()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    def _execute(self) -> None:
        try:
            self.run()
        finally:
            self.done.emit(self)

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel.is_set()


class ClassifyWorker(_CancellableWorker):
    progress = Signal(int, int, str)
    finished = Signal(object)

    def __init__(self, paths: list[Path]) -> None:
        super().__init__()
        self.paths = list(paths)

    @Slot()
    def run(self) -> None:
        try:
            result = classify_files(self.paths, lambda done, total, name: self.progress.emit(done, total, name),
                                    self._cancel.is_set)
        except InterruptedError:
            self.cancelled.emit()
        except Exception as exc:  # noqa: BLE001 - kullanıcıya güvenli mesaj
            self.failed.emit(_safe_error_message(exc))
        else:
            self.finished.emit(result)


class ProcessWorker(_CancellableWorker):
    progress = Signal(int, int, str, str)
    finished = Signal(object)

    def __init__(self, project, output_dir: Path) -> None:
        super().__init__()
        self.project = project
        self.output_dir = Path(output_dir)

    @Slot()
    def run(self) -> None:
        try:
            if self._cancel.is_set():
                raise InterruptedError
            processor = GroupProcessor(self.project, self.output_dir, self._cancel,
                                       lambda done, total, group, name: self.progress.emit(done, total, group, name),
                                       continue_on_error=True)
            results = processor.process()
        except InterruptedError:
            self.cancelled.emit()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(_safe_error_message(exc))
        else:
            # process() normal döndüyse bütün çıktılar tamamdır; geç basılan İptal bunu değiştirmez.
            self.finished.emit(results)


class _Janitor(QObject):
    @Slot(object)
    def release(self, worker) -> None:
        if worker._thread is not None:
            worker._thread.join()
        _ACTIVE.discard(worker)


_JANITOR: _Janitor | None = None


def _janitor() -> _Janitor:
    global _JANITOR
    if _JANITOR is None:
        _JANITOR = _Janitor(QCoreApplication.instance())
    return _JANITOR


def start_worker(worker: _CancellableWorker, parent: QObject | None = None) -> threading.Thread:
    """İşçiyi arka plan iş parçacığında başlatır. Ana iş parçacığından çağrılmalıdır."""
    _ACTIVE.add(worker)
    worker.done.connect(_janitor().release, Qt.QueuedConnection)
    worker._thread = threading.Thread(target=worker._execute, name=type(worker).__name__, daemon=True)
    worker._thread.start()
    return worker._thread


def wait_all() -> None:
    """Uygulama kapanırken çalışan bütün işleri iptal edip bitmelerini bekler."""
    for worker in list(_ACTIVE):
        worker.cancel()
        if worker._thread is not None:
            worker._thread.join()
    _ACTIVE.clear()
