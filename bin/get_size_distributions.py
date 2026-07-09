#!/usr/bin/env python3

import argparse

import pandas as pd

from post_common import verify_universe_checksum


def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyze matched and unmatched family size distributions based on similarity results."
    )
    parser.add_argument(
        "--metadata_file",
        required=True,
        help="Path to metadata TSV file (with protein_count, dbkey, etc.).",
    )
    parser.add_argument(
        "--similarity_file", required=True, help="Path to similarity results TSV file."
    )
    parser.add_argument(
        "--output_file", required=True, help="Path to output report file (text format)."
    )
    parser.add_argument("--pre_universe_fasta", required=True)
    parser.add_argument("--pre_universe_sha256", required=True)
    parser.add_argument("--sample", default="")
    parser.add_argument("--tool", default="")
    return parser.parse_args()


def main():
    args = parse_args()
    universe_sha256 = verify_universe_checksum(
        args.pre_universe_fasta, args.pre_universe_sha256
    )

    # Load input files
    metadata_df = pd.read_csv(args.metadata_file)
    similarity_df = pd.read_csv(args.similarity_file, sep="\t")
    size_col = (
        "protein_count" if "protein_count" in metadata_df.columns else "num_members"
    )

    # Get unique matched IDs
    matched_ids = set(similarity_df["original_basename"].unique())

    # Split metadata into matched and unmatched
    matched_df = metadata_df[metadata_df["dbkey"].isin(matched_ids)].copy()
    unmatched_df = metadata_df[~metadata_df["dbkey"].isin(matched_ids)].copy()

    # Open output file
    with open(args.output_file, "w") as out_f:
        out_f.write(f"sample\t{args.sample}\n")
        out_f.write(f"tool\t{args.tool}\n")
        out_f.write(f"universe_sha256\t{universe_sha256}\n\n")
        # Original distribution
        out_f.write(f"Original size distribution ({size_col} column):\n")
        out_f.write(str(metadata_df[size_col].describe()) + "\n\n")

        # Matched distribution
        out_f.write(f"Matched size distribution ({size_col} column):\n")
        out_f.write(str(matched_df[size_col].describe()) + "\n\n")

        # Unmatched distribution
        out_f.write(f"Unmatched size distribution ({size_col} column):\n")
        out_f.write(str(unmatched_df[size_col].describe()) + "\n\n")

    # Optionally save splits too if you want
    for frame in (matched_df, unmatched_df):
        frame.insert(0, "universe_sha256", universe_sha256)
        frame.insert(0, "tool", args.tool)
        frame.insert(0, "sample", args.sample)
    matched_df.to_csv("matched_metadata.tsv", sep="\t", index=False)
    unmatched_df.to_csv("unmatched_metadata.tsv", sep="\t", index=False)


if __name__ == "__main__":
    main()
