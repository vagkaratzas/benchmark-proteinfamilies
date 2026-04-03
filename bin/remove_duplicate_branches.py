#!/usr/bin/env python3

import argparse
import re


def count_leading_dashes(line):
    """Count the number of '--' groups at the beginning of the line."""
    match = re.match(r"^(--)+", line)
    return match.group().count("--") if match else 0


def extract_iprs(clade_lines):
    """Extract all IPR codes (like IPRxxxxxx) from a clade."""
    ipr_pattern = re.compile(r"IPR\d{6}")
    iprs = set()
    for line in clade_lines:
        matches = ipr_pattern.findall(line)
        iprs.update(matches)
    return iprs


def main():
    parser = argparse.ArgumentParser(
        description="Remove duplicate branches based on depth and IPR code uniqueness"
    )
    parser.add_argument("--infile", required=True, help="Input hierarchy file")
    parser.add_argument(
        "--max_depth", type=int, required=True, help="Max depth of the hierarchy"
    )
    parser.add_argument("--outfile", required=True, help="Filtered output file")
    args = parser.parse_args()

    # Read all non-empty lines from the input
    with open(args.infile) as f:
        lines = [line.rstrip("\n") for line in f if line.strip()]

    # Split into clades (block starts with a non-dashed line)
    clades = []
    current = []
    for line in lines:
        if not line.startswith("--"):
            if current:
                clades.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        clades.append(current)

    seen_iprs = set()
    written_clades = []

    for depth in range(args.max_depth, 0, -1):
        for clade in clades:
            clade_iprs = extract_iprs(clade)

            # Skip if any IPR has already been written
            if clade_iprs & seen_iprs:
                continue

            # Write clade if it has at least one line with the current depth
            if any(count_leading_dashes(line) >= depth for line in clade):
                written_clades.append(clade)
                seen_iprs.update(clade_iprs)

    # Write result to file
    with open(args.outfile, "w") as out:
        for clade in written_clades:
            out.write("\n".join(clade) + "\n")


if __name__ == "__main__":
    main()
