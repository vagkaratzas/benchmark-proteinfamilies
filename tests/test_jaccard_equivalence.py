#!/usr/bin/env python3

import csv
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "assets" / "fixtures" / "universe"
EXPECTED = REPO / "assets" / "fixtures" / "expected" / "jaccard_edges.sorted.tsv"
SCRIPT = REPO / "bin" / "calculate_jaccard_similarity.py"


def canonical_rows(path):
    with Path(path).open(newline="") as handle:
        return sorted(
            csv.DictReader(handle, delimiter="\t"), key=lambda row: tuple(row.values())
        )


def canonical_tsv(rows):
    fieldnames = [
        "sample",
        "tool",
        "universe_sha256",
        "use_case_basename",
        "original_basename",
        "similarity_score",
        "use_case_layer",
        "db_layer",
    ]
    lines = ["\t".join(fieldnames)]
    for row in sorted(rows, key=lambda row: tuple(row[name] for name in fieldnames)):
        lines.append("\t".join(row[name] for name in fieldnames))
    return ("\n".join(lines) + "\n").encode()


class JaccardEquivalenceTest(unittest.TestCase):
    def test_fixture_edge_tables_match_pre_optimisation_golden_after_sorting(self):
        rows = []
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            env = os.environ.copy()
            env["PYTHONPATH"] = f"{REPO / 'bin'}:{env.get('PYTHONPATH', '')}"

            for tool_dir in sorted(FIXTURE.glob("tool_*")):
                output = tmp / f"{tool_dir.name}.tsv"
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--use_case_dir",
                        str(tool_dir),
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
                        str(output),
                        "--unmapped_file",
                        str(tmp / f"{tool_dir.name}.unmapped.tsv"),
                        "--ambiguous_file",
                        str(tmp / f"{tool_dir.name}.ambiguous.tsv"),
                        "--qc_file",
                        str(tmp / f"{tool_dir.name}.qc.tsv"),
                        "--similarity_threshold",
                        "0.1",
                        "--num_workers",
                        "2",
                        "--sample",
                        "fixture",
                        "--tool",
                        tool_dir.name,
                    ],
                    cwd=REPO,
                    env=env,
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                rows.extend(canonical_rows(output))

        self.assertEqual(canonical_tsv(rows), EXPECTED.read_bytes())


if __name__ == "__main__":
    unittest.main()
