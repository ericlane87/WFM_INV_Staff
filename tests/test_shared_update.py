import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
OUTPUTS = ("source-records.json", "dashboard-data.js")


class SharedUpdateTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.app = Path(temporary.name) / "Automation"
        self.share = self.app.parent / "Shared WFM"
        (self.app / "input").mkdir(parents=True)
        (self.share / "Inputfile").mkdir(parents=True)
        for name in ("update_dashboard.py", "dashboard.html"):
            shutil.copyfile(PROJECT / name, self.app / name)
        # Reproduce the prior release: a full local store and its copy on the share.
        (self.app / "Sample Report.txt").write_text("Starting Inventory\t\tDec-30\nSample\tClaims\t888\n")
        (self.app / "input" / "local.csv").write_text("Starting Inventory,,Jan-26,Jan-30\nLocal,Claims,111,999\n")
        subprocess.run([sys.executable, str(self.app / "update_dashboard.py"), "--local-only"],
                       capture_output=True, check=True)
        shutil.copytree(self.app / "data", self.share / "data")

    def update(self, *args, check=True):
        return subprocess.run(
            [sys.executable, str(self.app / "update_dashboard.py"), "--share-root", str(self.share), *args],
            cwd=self.app, capture_output=True, text=True, check=check,
        )

    def check_snapshot(self, counts):
        for name in OUTPUTS:
            self.assertEqual((self.app / "data" / name).read_bytes(), (self.share / "data" / name).read_bytes())
        records = json.loads((self.share / "data/source-records.json").read_text(encoding="utf-8"))["records"]
        js = (self.share / "data/dashboard-data.js").read_text(encoding="utf-8")
        payload = json.loads(js.split("window.DASHBOARD_DATA = ", 1)[1].rstrip(";\n"))
        self.assertEqual(payload["records"], records)
        self.assertEqual([(row["period"], row["value"]) for row in records], counts)

    def test_empty_shared_input_replaces_legacy_data_on_both_sides(self):
        self.update()
        self.check_snapshot([])
        viewer = self.share / "Dashboard/dashboard.html"
        self.assertIn('src="../data/dashboard-data.js"', viewer.read_text(encoding="utf-8"))
        self.assertEqual(list(viewer.parent.iterdir()), [viewer])

    def test_shared_report_wins_over_legacy_history_then_survives_archiving(self):
        report = self.share / "Inputfile" / "current.csv"
        report.write_text("Starting Inventory,,Jan-26\nShared,Claims,42\n")
        self.update()
        self.check_snapshot([("2026-01", 42)])
        report.unlink()
        (self.app / "data/source-records.json").write_text("invalid local JSON")
        self.update()
        self.check_snapshot([("2026-01", 42)])

    def test_failed_shared_read_never_refreshes_the_local_copy(self):
        before = {name: (self.app / "data" / name).read_bytes() for name in OUTPUTS}
        result = self.update(str(self.app / "input/local.csv"), check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("inside", result.stderr)
        (self.share / "Inputfile").rmdir()
        (self.share / "Inputfile").touch()
        self.assertNotEqual(self.update(check=False).returncode, 0)
        for name in OUTPUTS:
            self.assertEqual(before[name], (self.app / "data" / name).read_bytes())
            self.assertEqual(before[name], (self.share / "data" / name).read_bytes())

    def test_local_copy_failure_leaves_shared_result_available_for_retry(self):
        report = self.share / "Inputfile" / "current.csv"
        report.write_text("Starting Inventory,,Feb-26\nShared,Claims,63\n")
        store = self.app / "data/source-records.json"
        store.unlink()
        store.mkdir()
        result = self.update(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Could not update the local copy", result.stderr)
        self.assertTrue((self.share / "Dashboard/dashboard.html").is_file())
        self.assertEqual(json.loads((self.share / "data/source-records.json").read_text())["records"][0]["value"], 63)
        store.rmdir()
        self.update()
        self.check_snapshot([("2026-02", 63)])


if __name__ == "__main__":
    unittest.main()
