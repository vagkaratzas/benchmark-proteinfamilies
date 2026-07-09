#!/usr/bin/env python3

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def run_command(args):
    result = subprocess.run(args, cwd=REPO, text=True, capture_output=True)
    if result.returncode != 0:
        raise AssertionError(result.stderr + result.stdout)


class DeterminismTest(unittest.TestCase):
    def write_interpro_pool(self, tmp):
        tmp.mkdir(parents=True, exist_ok=True)
        metadata = tmp / "interpro.tsv"
        tree = tmp / "tree.txt"
        rows = ["interpro_id\tdb\tdbkey\tprotein_count"]
        tree_rows = []
        for idx in range(5000):
            ipr = f"IPR{idx:06d}"
            rows.append(f"{ipr}\tPFAM\tPF{idx:05d}\t10")
            tree_rows.append(f"{ipr}::Family {idx}")
        metadata.write_text("\n".join(rows) + "\n")
        tree.write_text("\n".join(tree_rows) + "\n")
        return metadata, tree

    def sample_interpro(self, tmp, seed=None):
        output = tmp / f"sampled_{seed if seed is not None else 'none'}.csv"
        logfile = tmp / f"sampled_{seed if seed is not None else 'none'}.log"
        metadata, tree = self.write_interpro_pool(tmp)
        args = [
            sys.executable,
            str(REPO / "bin" / "sample_interpro.py"),
            "--interpro_file",
            str(metadata),
            "--tree_file",
            str(tree),
            "--min_membership",
            "1",
            "--num_per_db",
            "20",
            "--logfile",
            str(logfile),
            "--output",
            str(output),
        ]
        if seed is not None:
            args.extend(["--seed", str(seed)])
        run_command(args)
        return output.read_bytes()

    def write_decoy_pool(self, tmp):
        tmp.mkdir(parents=True, exist_ok=True)
        fasta = tmp / "swissprot.fasta"
        hits = tmp / "hits.tsv"
        fasta.write_text(
            "".join(
                f">sp_{idx:05d}\nM{'A' * (idx % 17)}G{idx:05d}\n" for idx in range(5000)
            )
        )
        hits.write_text("sp_00000\tfamily_hit\nsp_00001\tfamily_hit\n")
        return fasta, hits

    def identify_decoys(self, tmp, seed=None):
        fasta, hits = self.write_decoy_pool(tmp)
        output = tmp / f"decoys_{seed if seed is not None else 'none'}.fasta"
        args = [
            sys.executable,
            str(REPO / "bin" / "identify_uniprot_decoys.py"),
            "--hits_file",
            str(hits),
            "--fasta_file",
            str(fasta),
            "--output_file",
            str(output),
            "--num_decoys",
            "200",
        ]
        if seed is not None:
            args.extend(["--seed", str(seed)])
        run_command(args)
        return output.read_bytes()

    def test_sample_interpro_seed_produces_byte_identical_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            self.assertEqual(
                self.sample_interpro(tmp / "seeded_a", seed=123),
                self.sample_interpro(tmp / "seeded_b", seed=123),
            )

    def test_sample_interpro_unseeded_runs_differ(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            # The pool is large enough that two independent 20-family samples colliding
            # exactly would be vanishingly unlikely; a collision would indicate the
            # unseeded path is effectively deterministic in practice.
            self.assertNotEqual(
                self.sample_interpro(tmp / "unseeded_a"),
                self.sample_interpro(tmp / "unseeded_b"),
            )

    def test_identify_uniprot_decoys_seed_produces_byte_identical_fasta(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            self.assertEqual(
                self.identify_decoys(tmp / "seeded_a", seed=123),
                self.identify_decoys(tmp / "seeded_b", seed=123),
            )

    def test_identify_uniprot_decoys_unseeded_runs_differ(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            # Exact equality would require the same ordered 200-record draw from 4998
            # candidates, so this asserts that the seed changes observable behavior.
            self.assertNotEqual(
                self.identify_decoys(tmp / "unseeded_a"),
                self.identify_decoys(tmp / "unseeded_b"),
            )


if __name__ == "__main__":
    unittest.main()
