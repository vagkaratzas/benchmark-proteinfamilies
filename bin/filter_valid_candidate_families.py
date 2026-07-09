#!/usr/bin/env python3

import argparse
from pathlib import Path
import pandas as pd


KNOWN_DBS = ("HAMAP", "NCBIFAM", "PANTHER", "PFAM")


def load_metadata(path):
    df = pd.read_csv(path, sep="\t", dtype=str)
    df.set_index("id", inplace=True)
    return df["num_proteins"].to_dict()


def infer_db_from_path(path):
    name = Path(path).name.lower()
    for db in KNOWN_DBS:
        if name.startswith(db.lower()):
            return db
    raise ValueError(
        f"Cannot infer database type from metadata filename {path!r}; "
        "use DB=path syntax"
    )


def load_metadata_files(paths):
    metadata = {}
    for item in paths:
        if "=" in item:
            db, path = item.split("=", 1)
            db = db.upper()
        else:
            path = item
            db = infer_db_from_path(path)
        metadata[db] = load_metadata(path)
    return metadata


def main(interpro_path, metadata_paths, output_path):
    metadata = load_metadata_files(metadata_paths)

    # Load InterPro TSV
    interpro = pd.read_csv(interpro_path, sep="\t", dtype=str)

    # Filter and update
    valid_rows = []
    for _, row in interpro.iterrows():
        db = row["db"]
        dbkey = row["dbkey"]
        if db in metadata and dbkey in metadata[db]:
            row["protein_count"] = metadata[db][dbkey]
            valid_rows.append(row)

    # Create and write filtered dataframe
    filtered_df = pd.DataFrame(valid_rows)
    filtered_df.to_csv(output_path, sep="\t", index=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Filter InterPro entries based on metadata and update protein_count"
    )
    parser.add_argument("interpro", help="Path to InterPro TSV file")
    parser.add_argument("output", help="Output filtered InterPro TSV")
    parser.add_argument(
        "--metadata",
        nargs="+",
        required=True,
        help="Metadata TSVs, either named like hamap_metadata.tsv or passed as DB=path.",
    )
    args = parser.parse_args()

    main(args.interpro, args.metadata, args.output)
