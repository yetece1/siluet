from siluet.project import Project, ROLE_COUNTER, ROLE_MAIN
from siluet.ui.workers import ClassifyWorker, ProcessWorker, start_worker

from conftest import TEST_PASSWORD


def test_classify_worker_emits_finished(qtbot, sample_pair):
    worker = ClassifyWorker(list(sample_pair))
    with qtbot.waitSignal(worker.finished, timeout=20000) as blocker:
        start_worker(worker, None)
    groups, ambiguous, failures = blocker.args[0]
    assert sum(len(g.profiles) for g in groups) + len(ambiguous) == 2 and not failures


def test_process_worker_runs(qtbot, sample_pair, tmp_path):
    project = Project.create(tmp_path / "p", TEST_PASSWORD)
    group = project.add_group("G")
    project.add_file(group.group_id, sample_pair[0], ROLE_MAIN)
    project.add_file(group.group_id, sample_pair[1], ROLE_COUNTER)
    worker = ProcessWorker(project, tmp_path / "out")
    with qtbot.waitSignal(worker.finished, timeout=30000) as blocker:
        start_worker(worker, None)
    results = blocker.args[0]
    assert all(r.successful for r in results)
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["ana.xlsx", "karsi.xlsx"]


def test_process_worker_cancel_removes_partial(qtbot, sample_pair, tmp_path):
    project = Project.create(tmp_path / "p", TEST_PASSWORD)
    group = project.add_group("G")
    project.add_file(group.group_id, sample_pair[0], ROLE_MAIN)
    project.add_file(group.group_id, sample_pair[1], ROLE_COUNTER)
    worker = ProcessWorker(project, tmp_path / "out")
    worker.cancel()
    with qtbot.waitSignal(worker.cancelled, timeout=30000):
        start_worker(worker, None)
    out = tmp_path / "out"
    assert not out.exists() or not [p for p in out.iterdir() if p.suffix == ".xlsx"]



def test_app_exit_right_after_worker_finishes_does_not_abort(tmp_path):
    """İşçi 'finished' yaydıktan hemen sonra uygulama kapanırsa QThread hâlâ çalışıyor olmamalı."""
    import subprocess, sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    script = tmp_path / "exit_after_finish.py"
    script.write_text(
        "import os, sys\n"
        "os.environ['QT_QPA_PLATFORM'] = 'offscreen'\n"
        "from pathlib import Path\n"
        "from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer\n"
        "from PySide6.QtWidgets import QApplication\n"
        "from siluet.ui.app import install_shutdown_hook\n"
        "from siluet.ui.workers import ClassifyWorker, start_worker\n"
        "app = QApplication([])\n"
        "install_shutdown_hook(app)\n"
        "paths = [Path(p) for p in sys.argv[1:]]\n"
        "for _ in range(5):\n"
        "    done = []\n"
        "    worker = ClassifyWorker(paths)\n"
        "    worker.finished.connect(lambda r: done.append(1))\n"
        "    start_worker(worker, None)\n"
        "    loop = QEventLoop()\n"
        "    while not done:\n"
        "        QTimer.singleShot(1, loop.quit); loop.exec()\n"
        "QTimer.singleShot(0, app.quit)\n"
        "app.exec()\n"
        "print('temiz-cikis')\n", encoding="utf-8")
    result = subprocess.run([sys.executable, str(script), str(root / "examples/sahte_ana_baz.xlsx"),
                             str(root / "examples/sahte_karsi_baz.xlsx")], cwd=root, capture_output=True,
                            text=True, timeout=120, env={**__import__("os").environ, "PYTHONPATH": str(root)})
    assert result.returncode == 0, result.stderr[-500:]
    assert "Destroyed while thread" not in result.stderr


def test_main_thread_gc_disables_automatic_collection(qapp):
    import gc
    from siluet.ui.app import _MainThreadGarbageCollector, install_main_thread_gc
    collector = install_main_thread_gc(qapp)
    assert isinstance(collector, _MainThreadGarbageCollector)
    assert install_main_thread_gc(qapp) is collector
    assert not gc.isenabled()
    class Cycle:
        pass
    a = Cycle(); a.self = a
    import weakref
    ref = weakref.ref(a)
    del a
    for _ in range(collector.threshold[0] + 10):
        [[]]  # sayaçları ilerletir
    junk = [[i] for i in range(collector.threshold[0] * 2)]
    collector.check()
    assert ref() is None
    del junk


def test_cancel_after_work_completed_reports_finished(qtbot, sample_pair, tmp_path, monkeypatch):
    from siluet import group_processor
    project = Project.create(tmp_path / "p", TEST_PASSWORD)
    worker = ProcessWorker(project, tmp_path / "out")
    def finish_then_cancel(self, group_ids=None):
        worker.cancel()  # kullanıcı tam iş bittiği anda İptal'e bastı
        return []
    monkeypatch.setattr(group_processor.GroupProcessor, "process", finish_then_cancel)
    with qtbot.waitSignal(worker.finished, timeout=10000):
        start_worker(worker, None)
