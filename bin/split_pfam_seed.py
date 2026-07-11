#!/usr/bin/env python3
"""Split the single Pfam-A.seed Stockholm stream into one file per family.

Pfam ships every family concatenated in one (gzipped) file; the rest of the pipeline expects one
alignment file per family, like the other three databases. Streams rather than loading the file,
which is several GB uncompressed.
"""

import argparse
import gzip
import re
from pathlib import Path


ACCESSION_RE = re.compile(r"^#=GF\s+AC\s+(\S+)")


def open_text(path):
    if str(path).endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return Path(path).open(encoding="utf-8")


def flush_entry(lines, accession, output_dir):
    if not lines:
        return 0
    if not accession:
        raise ValueError("Pfam seed entry is missing a #=GF AC accession line")
    family = accession.split(".")[0]
    output_path = output_dir / f"{family}.sto"
    output_path.write_text("".join(lines), encoding="utf-8")
    return 1


def split_seed(input_path, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    accession = None
    count = 0

    with open_text(input_path) as handle:
        for line in handle:
            lines.append(line)
            match = ACCESSION_RE.match(line)
            if match:
                accession = match.group(1)
            if line.strip() == "//":
                count += flush_entry(lines, accession, output_dir)
                lines = []
                accession = None

    if lines:
        count += flush_entry(lines, accession, output_dir)
    return count


def parse_args():
    parser = argparse.ArgumentParser(
        description="Split Pfam-A.seed Stockholm entries into one .sto file per family."
    )
    parser.add_argument(
        "--input", required=True, help="Path to Pfam-A.seed or Pfam-A.seed.gz"
    )
    parser.add_argument(
        "--output-dir", required=True, help="Directory for PFxxxxx.sto files"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    count = split_seed(Path(args.input), Path(args.output_dir))
    print(f"Wrote {count} Pfam seed alignment files to {args.output_dir}")


if __name__ == "__main__":
    main()
