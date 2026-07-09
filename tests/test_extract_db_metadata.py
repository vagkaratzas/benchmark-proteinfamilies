#!/usr/bin/env python3

import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "assets" / "fixtures" / "db_metadata"
EXPECTED = REPO / "assets" / "fixtures" / "expected"
SCRIPT = REPO / "bin" / "extract_db_metadata.py"


class ExtractDbMetadataTest(unittest.TestCase):
    def test_new_extractor_matches_old_per_database_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            for db_type in ("hamap", "ncbifam", "panther", "pfam"):
                observed = tmp / f"{db_type}_metadata.tsv"
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--db_type",
                        db_type,
                        str(FIXTURE / db_type),
                        str(observed),
                    ],
                    cwd=REPO,
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                self.assertEqual(
                    observed.read_bytes(),
                    (EXPECTED / f"{db_type}_metadata.tsv").read_bytes(),
                )

    def test_ncbifam_nf_seed_id_drops_version_suffix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            observed = Path(tmpdir) / "ncbifam_metadata.tsv"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--db_type",
                    "ncbifam",
                    str(FIXTURE / "ncbifam"),
                    str(observed),
                ],
                check=True,
                cwd=REPO,
            )
            with observed.open(newline="") as handle:
                rows = {
                    row["id"]: row for row in csv.DictReader(handle, delimiter="\t")
                }
            self.assertIn("NF000001", rows)
            self.assertNotIn("NF000001.1", rows)


if __name__ == "__main__":
    unittest.main()
