import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "universe"
SCRIPT = ROOT / "bin" / "analyze_splits_merges.py"


def write_fasta(path, records):
    with path.open("w") as handle:
        for record_id, sequence in records:
            handle.write(f">{record_id}\n{sequence}\n")


def read_summary(path):
    with path.open(newline="") as handle:
        rows = [
            row
            for row in csv.DictReader(
                (line for line in handle if not line.startswith("#")),
                delimiter="\t",
            )
        ]
    return rows[0]


class SplitMergeOrderIndependenceTest(unittest.TestCase):
    def test_nested_generated_family_order_does_not_create_split(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            originals = tmp / "originals" / "pfam"
            originals.mkdir(parents=True)
            write_fasta(
                originals / "PFORDER.faa",
                [("1814953751", "MAAA"), ("711279214", "MBBB")],
            )
            metadata = tmp / "metadata.csv"
            metadata.write_text(
                "interpro_id,db,dbkey,num_members\nIPRORDER,pfam,PFORDER,2\n"
            )

            generated = tmp / "generated"
            generated.mkdir()
            small = generated / "small.faa"
            large = generated / "large.faa"
            write_fasta(small, [("1814953751", "MAAA")])
            write_fasta(
                large,
                [("1814953751", "MAAA"), ("711279214", "MBBB")],
            )

            summaries = []
            for order in ([small, large], [large, small]):
                out = tmp / f"summary_{len(summaries)}.tsv"
                overlap = tmp / f"overlap_{len(summaries)}.tsv"
                subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--use_case_files",
                        *map(str, order),
                        "--original_base_dir",
                        str(tmp / "originals"),
                        "--metadata",
                        str(metadata),
                        "--id_registry",
                        str(FIXTURES / "id_registry.tsv"),
                        "--pre_universe_fasta",
                        str(FIXTURES / "combined_decoy.faa"),
                        "--pre_universe_sha256",
                        str(FIXTURES / "universe.sha256"),
                        "--output_file",
                        str(out),
                        "--original_overlap_file",
                        str(overlap),
                        "--association_threshold",
                        "0.1",
                        "--min_intersection_size",
                        "1",
                        "--sample",
                        "order",
                        "--tool",
                        "unit",
                    ],
                    check=True,
                )
                summaries.append(read_summary(out))

            self.assertEqual(summaries[0]["n_splits"], "0")
            self.assertEqual(summaries[0]["n_merges"], "0")
            self.assertEqual(
                (summaries[0]["n_splits"], summaries[0]["n_merges"]),
                (summaries[1]["n_splits"], summaries[1]["n_merges"]),
            )


if __name__ == "__main__":
    unittest.main()
