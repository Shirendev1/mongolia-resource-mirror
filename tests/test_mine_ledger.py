import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import mine_ledger as ml  # noqa: E402

SRC = ROOT / "data" / "mine"


class MineLedgerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for name in ("mines.csv", "measurements.csv", "declarations.csv"):
            shutil.copy(SRC / name, self.tmp / name)
        self.out = self.tmp / "mine.json"
        ml.ingest(self.tmp, now="2026-11-01T00:00:00Z")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def batches(self):
        return {b["batch_id"]: b for b in ml.analyze(self.tmp, self.out)["batches"]}

    def test_chain_verifies(self):
        ok, bad = ml.verify(ml.read_ledger(self.tmp / "ledger.jsonl"))
        self.assertTrue(ok)
        self.assertIsNone(bad)

    def test_ingest_is_idempotent(self):
        added, edited = ml.ingest(self.tmp)
        self.assertEqual(added, [])
        self.assertEqual(edited, [])

    def test_tampering_breaks_chain(self):
        path = self.tmp / "ledger.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        e = json.loads(lines[2])
        e["record"]["Au_gpt"] = "0"
        lines[2] = json.dumps(e, ensure_ascii=False)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        ok, bad = ml.verify(ml.read_ledger(path))
        self.assertFalse(ok)
        self.assertEqual(bad, 2)
        with self.assertRaises(SystemExit):
            ml.ingest(self.tmp)

    def test_edited_csv_row_is_flagged_and_ledger_keeps_original(self):
        p = self.tmp / "declarations.csv"
        p.write_text(p.read_text(encoding="utf-8").replace(
            "B002,DEMO-A,2026-10-04,Зэсийн баяжмал,3000,24.8,,,",
            "B002,DEMO-A,2026-10-04,Зэсийн баяжмал,3000,24.8,0.2,6.0,"), encoding="utf-8")
        b = self.batches()["B002"]
        self.assertIn("EDITED_AFTER_LEDGER", b["flags"])
        self.assertIn("UNDECLARED_ELEMENT", b["flags"])  # judged on the locked original

    def test_clean_batch_has_no_flags(self):
        self.assertEqual(self.batches()["B001"]["flags"], [])

    def test_undeclared_gold(self):
        gaps = {g["element"]: g for g in self.batches()["B002"]["gaps"]}
        self.assertEqual(gaps["Au_gpt"]["contained_gap"], 18.0)  # 6 g/t x 3000 t = 18 kg

    def test_company_vs_independent(self):
        b = self.batches()["B003"]
        self.assertIn("SOURCE_GAP", b["flags"])
        self.assertIn("DECLARED_BELOW", b["flags"])

    def test_no_independent_sample(self):
        self.assertEqual(self.batches()["B004"]["flags"], ["NO_INDEPENDENT_SAMPLE"])

    def test_tonnage_and_by_products(self):
        b = self.batches()["B005"]
        self.assertIn("TONNAGE_GAP", b["flags"])
        self.assertEqual({g["element"] for g in b["gaps"]}, {"Zn_pct", "REE_ppm"})

    def test_trace_amounts_are_ignored(self):
        p = self.tmp / "measurements.csv"
        with p.open("a", encoding="utf-8") as f:
            f.write("M099,B001,DEMO-A,2026-10-01T12:00,LAB,independent,Lab,3000,25.0,0.3,5.2,47,,0.1,\n")
        ml.ingest(self.tmp)
        self.assertEqual(self.batches()["B001"]["flags"], [])


if __name__ == "__main__":
    unittest.main()
