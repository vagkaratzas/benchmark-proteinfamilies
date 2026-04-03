#!/usr/bin/env python3

import argparse
import gzip
import xml.etree.ElementTree as ET


def parse_interpro(interpro_xml_gz, valid_ids_file, output_tsv):
    valid_ids = set()
    with open(valid_ids_file) as f:
        for line in f:
            line = line.strip()
            if line:
                valid_ids.add(line)

    allowed_dbs = {"PFAM", "PANTHER", "NCBIFAM", "HAMAP"}

    with gzip.open(interpro_xml_gz, "rt", encoding="utf-8") as f:
        context = ET.iterparse(f, events=("start", "end"))
        _, root = next(context)  # Get root element

        with open(output_tsv, "w") as out:
            out.write("interpro_id\tprotein_count\tshort_name\tdb\tdbkey\tname\n")

            for event, elem in context:
                if event == "end" and elem.tag == "interpro":
                    interpro_id = elem.attrib.get("id")
                    type_ = elem.attrib.get("type")
                    is_llm = elem.attrib.get("is-llm") == "true"
                    short_name = elem.attrib.get("short_name", "")
                    protein_count = elem.attrib.get("protein_count", "")

                    if interpro_id in valid_ids and type_ == "Family" and not is_llm:
                        member_list = elem.find("member_list")
                        if member_list is not None:
                            for member in member_list.findall("db_xref"):
                                db = member.attrib.get("db")
                                if db in allowed_dbs:
                                    dbkey = member.attrib.get("dbkey", "")
                                    name = member.attrib.get("name", "")
                                    out.write(
                                        f"{interpro_id}\t{protein_count}\t{short_name}\t{db}\t{dbkey}\t{name}\n"
                                    )
                    root.clear()  # Free memory


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Parse InterPro XML and extract metadata."
    )
    parser.add_argument("interpro_xml_gz", help="Path to interpro XML .gz file")
    parser.add_argument(
        "valid_ids_file", help="Text file with valid interpro IDs (one per line)"
    )
    parser.add_argument("output_tsv", help="Path to output TSV file")

    args = parser.parse_args()
    parse_interpro(args.interpro_xml_gz, args.valid_ids_file, args.output_tsv)
