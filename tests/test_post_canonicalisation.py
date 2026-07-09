#!/usr/bin/env python3

import csv
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "universe"


class PostCanonicalisationTest(unittest.TestCase):
    def test_mangled_ids_produce_nonzero_jaccard_and_no_unmapped_ids(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            env = os.environ.copy()
            env["PYTHONPATH"] = f"{REPO / 'bin'}:{env.get('PYTHONPATH', '')}"
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO / "bin" / "calculate_jaccard_similarity.py"),
                    "--use_case_dir",
                    str(FIXTURE / "tool_mangled_ambiguous"),
                    "--original_base_dir",
                    str(FIXTURE / "sampled_fasta"),
                    "--metadata",
                    str(FIXTURE / "sampled_metadata.csv"),
                    "--id_registry",
                    str(FIXTURE / "id_registry.tsv"),
                    "--pre_universe_fasta",
                    str(FIXTURE / "combined_decoy.faa"),
                    "--pre_universe_sha256",
                    str(FIXTURE / "universe.sha256"),
                    "--output_file",
                    str(tmp / "jaccard.tsv"),
                    "--unmapped_file",
                    str(tmp / "unmapped.tsv"),
                    "--ambiguous_file",
                    str(tmp / "ambiguous.tsv"),
                    "--qc_file",
                    str(tmp / "qc.tsv"),
                    "--similarity_threshold",
                    "0.1",
                ],
                cwd=REPO,
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

            with (tmp / "jaccard.tsv").open() as handle:
                edges = list(csv.DictReader(handle, delimiter="\t"))
            self.assertTrue(edges, "expected at least one matched original family")
            self.assertGreater(
                max(float(row["similarity_score"]) for row in edges), 0.0
            )
            matched_families = {row["original_basename"] for row in edges}
            self.assertTrue(
                {"PF00004", "PF00005"}.issubset(matched_families),
                "coordinate-suffixed IDs must resolve to their universe IDs",
            )

            with (tmp / "qc.tsv").open() as handle:
                qc = next(csv.DictReader(handle, delimiter="\t"))
            self.assertAlmostEqual(float(qc["unmapped_fraction"]), 0.0, places=6)


if __name__ == "__main__":
    unittest.main()
