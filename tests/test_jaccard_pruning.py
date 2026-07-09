#!/usr/bin/env python3

import csv
import hashlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "bin"))

import calculate_jaccard_similarity as cjs  # noqa: E402  (must follow sys.path.insert above)
from benchmark_ids import sha1_of  # noqa: E402


def write_fasta(path, records):
    with Path(path).open("w") as handle:
        for record_id, sequence in records:
            handle.write(f">{record_id}\n{sequence}\n")


def build_synthetic_registry(root, n_families=50):
    original_dir = root / "originals" / "pfam"
    use_case_dir = root / "use_cases"
    original_dir.mkdir(parents=True)
    use_case_dir.mkdir()

    metadata = root / "sampled_metadata.csv"
    registry = root / "id_registry.tsv"
    universe = root / "combined_decoy.faa"
    checksum = root / "universe.sha256"

    rows = []
    for i in range(n_families):
        universe_id = f"SEQ{i:05d}"
        family = f"PF{i:05d}"
        sequence = f"M{i:05d}AAA"
        rows.append((universe_id, family, sequence))
        write_fasta(original_dir / f"{family}.faa", [(universe_id, sequence)])
        write_fasta(use_case_dir / f"UC{i:05d}.faa", [(universe_id, sequence)])

    with metadata.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["interpro_id", "db", "dbkey", "num_members"])
        for i, (_universe_id, family, _sequence) in enumerate(rows):
            writer.writerow([f"IPR{i:05d}", "pfam", family, "1"])

    with registry.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "universe_id",
                "parent_id",
                "source_type",
                "db_layer",
                "family",
                "coords",
                "ungapped_len",
                "seq_sha1",
            ],
            delimiter="\t",
        )
        writer.writeheader()
        for universe_id, family, sequence in rows:
            writer.writerow(
                {
                    "universe_id": universe_id,
                    "parent_id": universe_id,
                    "source_type": "family",
                    "db_layer": "pfam",
                    "family": family,
                    "coords": "-",
                    "ungapped_len": str(len(sequence)),
                    "seq_sha1": sha1_of(sequence),
                }
            )

    write_fasta(
        universe, [(universe_id, sequence) for universe_id, _family, sequence in rows]
    )
    checksum.write_text(
        f"{hashlib.sha256(universe.read_bytes()).hexdigest()}  combined_decoy.faa\n"
    )
    return original_dir.parent, use_case_dir, metadata, registry, universe, checksum


class JaccardPruningTest(unittest.TestCase):
    def test_only_candidate_originals_are_scored(self):
        n_families = 50
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            original_base, use_case_dir, metadata, registry, universe, checksum = (
                build_synthetic_registry(tmp, n_families)
            )
            scored_pairs = 0
            original_similarity = cjs.jaccard_similarity
            original_argv = sys.argv
            original_cpu_count = getattr(getattr(cjs, "os", None), "cpu_count", None)

            def counting_similarity(set1, set2):
                nonlocal scored_pairs
                scored_pairs += 1
                return original_similarity(set1, set2)

            cjs.jaccard_similarity = counting_similarity
            sys.argv = [
                "calculate_jaccard_similarity.py",
                "--use_case_dir",
                str(use_case_dir),
                "--original_base_dir",
                str(original_base),
                "--metadata",
                str(metadata),
                "--id_registry",
                str(registry),
                "--pre_universe_fasta",
                str(universe),
                "--pre_universe_sha256",
                str(checksum),
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
            ]

            if hasattr(cjs, "os"):
                cjs.os.cpu_count = lambda: 1

            try:
                with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                    cjs.main()
            finally:
                cjs.jaccard_similarity = original_similarity
                sys.argv = original_argv
                if hasattr(cjs, "os") and original_cpu_count is not None:
                    cjs.os.cpu_count = original_cpu_count

        self.assertLessEqual(scored_pairs, 2 * n_families)


if __name__ == "__main__":
    unittest.main()
