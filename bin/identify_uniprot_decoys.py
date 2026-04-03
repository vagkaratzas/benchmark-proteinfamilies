#!/usr/bin/env python3

import argparse
import pyfastx
import random


def parse_args():
    parser = argparse.ArgumentParser(
        description="Sample non-hit decoy sequences from a FASTA file."
    )
    parser.add_argument(
        "--hits_file",
        required=True,
        help="Path to diamond/blastp hits file (first column will be used)",
    )
    parser.add_argument(
        "--fasta_file", required=True, help="Path to full UniProt SwissProt FASTA file"
    )
    parser.add_argument(
        "--output_file", required=True, help="Path to output sampled decoy FASTA file"
    )
    parser.add_argument(
        "--num_decoys",
        type=int,
        default=10000,
        help="Number of decoys to sample (default: 10000)",
    )
    return parser.parse_args()


def get_non_hit_sequences(hits_file, fasta_file):
    # Read first column (hit IDs)
    hit_ids = set()
    with open(hits_file) as f:
        for line in f:
            if line.strip():
                cols = line.strip().split()
                if len(cols) >= 2:
                    hit_ids.add(cols[0])  # first column

    # Collect non-hit sequences from FASTA, ensuring no duplicates by name or sequence
    seen_names = set()
    seen_sequences = set()
    decoys = []

    for seq in pyfastx.Fasta(fasta_file, build_index=True):
        # Skip if the sequence name is a hit or if the sequence is already seen
        if (
            seq.name not in hit_ids
            and seq.name not in seen_names
            and seq.seq not in seen_sequences
        ):
            decoys.append((seq.name, seq.seq))
            seen_names.add(seq.name)
            seen_sequences.add(seq.seq)

    return decoys


def sample_decoys(decoy_pool, sample_size, output_file):
    sampled = random.sample(decoy_pool, min(sample_size, len(decoy_pool)))
    with open(output_file, "w") as out_f:
        for name, seq in sampled:
            out_f.write(f">{name}\n{seq}\n")


def main():
    args = parse_args()

    decoys = get_non_hit_sequences(args.hits_file, args.fasta_file)
    print(f"[INFO] Found {len(decoys)} non-hit sequences.")

    sample_decoys(decoys, args.num_decoys, args.output_file)
    print(
        f"[DONE] Wrote {min(args.num_decoys, len(decoys))} decoys to {args.output_file}"
    )


if __name__ == "__main__":
    main()
