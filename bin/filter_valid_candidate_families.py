#!/usr/bin/env python3

import argparse
import pandas as pd


def load_metadata(path):
    df = pd.read_csv(path, sep="\t", dtype=str)
    df.set_index("id", inplace=True)
    return df["num_proteins"].to_dict()


def main(interpro_path, hamap_path, ncbifam_path, panther_path, pfam_path, output_path):
    # Load metadata into lookup dicts
    metadata = {
        "HAMAP": load_metadata(hamap_path),
        "NCBIFAM": load_metadata(ncbifam_path),
        "PANTHER": load_metadata(panther_path),
        "PFAM": load_metadata(pfam_path),
    }

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
    parser.add_argument("hamap", help="HAMAP metadata TSV")
    parser.add_argument("ncbifam", help="NCBIFAM metadata TSV")
    parser.add_argument("panther", help="PANTHER metadata TSV")
    parser.add_argument("pfam", help="PFAM metadata TSV")
    parser.add_argument("output", help="Output filtered InterPro TSV")
    args = parser.parse_args()

    main(args.interpro, args.hamap, args.ncbifam, args.panther, args.pfam, args.output)
