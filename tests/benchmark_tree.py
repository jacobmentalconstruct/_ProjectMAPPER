"""Explicit benchmark: python -m pytest -q -s tests/benchmark_tree.py."""
import json
import platform
import statistics
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.support import temporary_directory, tk_root
from src.app import ProjectMapperApp
from src.core.exclusions import ExclusionPolicy
from src.core.tree import scan_project_tree


class TreeBenchmark(unittest.TestCase):
    def test_wide_render(self):
        root = tk_root(self)
        root.withdraw()
        app = ProjectMapperApp(root)
        for timer in root.tk.call("after", "info"):
            root.after_cancel(timer)
        base = Path("wide-benchmark").resolve()
        rows = [dict(path=base, parent=None, name="wide", entry_type="dir", size_bytes=10000)]
        rows.extend(dict(path=base / str(index), parent=base, name=str(index),
                         entry_type="file", size_bytes=1) for index in range(10000))
        timings, delays = [], []
        for _ in range(3):
            previous = time.perf_counter()
            def heartbeat():
                nonlocal previous
                now = time.perf_counter()
                delays.append(now - previous)
                previous = now
                if app.tree_projection.timer is not None:
                    root.after(1, heartbeat)
            start = time.perf_counter()
            app.populate_tree(rows)
            self.assertLess(len(app.widgets["folder_tree"].get_children(str(base))), 10000)
            root.after(0, heartbeat)
            while app.tree_projection.timer is not None:
                root.update()
            root.update()
            timings.append(time.perf_counter() - start)
        self.assertEqual(len(app.widgets["folder_tree"].get_children(str(base))), 10000)
        print(json.dumps(dict(shape="10000 direct children", render_median_s=statistics.median(timings),
                              max_heartbeat_gap_s=max(delays), widgets=10001)))

    def test_measure(self):
        fixture = temporary_directory(self)
        root = tk_root(self)
        root.withdraw()
        app = ProjectMapperApp(root)
        for timer in root.tk.call("after", "info"):
            root.after_cancel(timer)
        for count in (200, 10000):
            folder = Path(fixture.name) / str(count)
            folder.mkdir()
            for index in range(count):
                parent = folder / f"group{index // 100:03}" / "nested"
                parent.mkdir(parents=True, exist_ok=True)
                (parent / f"file{index:05}.txt").write_bytes(b"example\n")
            ignored = folder / "node_modules"
            ignored.mkdir()
            (ignored / "ignore.txt").write_bytes(b"ignored")
            policy = ExclusionPolicy()
            scans, renders = [], []
            for _ in range(3):
                start = time.perf_counter()
                rows, skipped = scan_project_tree(folder, policy)
                scans.append(time.perf_counter() - start)
                app.folder_item_states = {str(r["path"]): "checked" for r in rows}
                start = time.perf_counter()
                app.populate_tree(rows)
                while app.tree_projection.timer is not None:
                    root.update()
                root.update_idletasks()
                renders.append(time.perf_counter() - start)
            tree = app.widgets["folder_tree"]
            def widgets(iid=""):
                children = tree.get_children(iid)
                return len(children) + sum(widgets(c) for c in children)
            stat_count = 0
            original = Path.stat
            def counted(path, *args, **kwargs):
                nonlocal stat_count
                stat_count += 1
                return original(path, *args, **kwargs)
            with patch.object(Path, "stat", counted), patch.object(Path, "open", side_effect=AssertionError("metadata scan read content")):
                verified, _ = scan_project_tree(folder, policy)
            self.assertEqual(len(verified), len(rows))
            print(json.dumps({"files": count, "rows": len(rows), "skipped": len(skipped),
                "scan_median_s": statistics.median(scans), "render_median_s": statistics.median(renders),
                "widgets": widgets(), "path_stat_calls": stat_count,
                "python": platform.python_version(), "platform": platform.platform()}))
