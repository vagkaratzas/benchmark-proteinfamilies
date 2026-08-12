# benchmark-proteinfamilies

Sample manually curated InterPro families (`pre` workflow) and measure how well **any** protein-family
generation tool reconstructs them (`post` workflow). It answers: _which tool / parameter combinations
match the quality of manual curation?_

Three steps:

1. **PRE** (runs once) — samples curated InterPro families from NCBIFAM, PANTHER, HAMAP and PFAM,
   adds SwissProt decoys, and emits `combined_decoy.faa` plus `id_registry.tsv` and `universe.sha256`.
2. **Your tool** — run outside this pipeline on `combined_decoy.faa`.
3. **POST** — ingests a samplesheet of one or more tool runs and emits a ranked cross-run report.

Protein-family tools do not round-trip sequence IDs: mgnifams emits `1814953751/178-297`,
proteinfamilies emits `2632373804_177_299/1-122`, curated originals are keyed `Q9X1J3/1-250`. PRE
therefore records identity at construction time in `id_registry.tsv`, and POST resolves every
observed ID through it instead of guessing. Keep those three PRE files together — POST needs all of
them, and it refuses to score a tool run against a universe it was not built from.

Requires Nextflow >= 24.04.2. A container or conda profile is required alongside any executor profile.

Contributing? See **[AGENTS.md](AGENTS.md)**.

## pre-proteinfamilies

During the `pre` `workflow_mode`, the InterPro hierarchy tree is parsed and sampled (different branches)
for NCBIFAM, PANTHER, HAMAP and PFAM protein families.
Their member amino acid sequences are compiled in a fasta file,
along with unrelated sequences from UniProt-SwissProt.

A configuration file can provide the following paths:

```
interpro_hierarchy_db = '/path/to/interpro/ParentChildTreeFile.txt'
interpro_mapping_db   = '/path/to/interpro/interpro.xml.gz'
hamap_db              = '/path/to/hamap/hamap_alignments'
ncbifam_db            = '/path/to/ncbifam/hmm_PGAP'
panther_db            = '/path/to/panther/msa/PANTHER19.0_fasta'
pfam_db               = '/path/to/pfam/37.2/seed/alignments'
swissprot_db          = '/path/to/uniprot/fasta/uniprot_sprot_parsed.fasta'
```

When any of these seven `*_db` parameters is `null`, the PRE workflow downloads that database from
the matching `*_latest_link` parameter. Each database also has a `*_version` parameter, which is
recorded for provenance only — the link, not the version, decides what gets fetched.

Downloaded databases are published under `<outdir>/pre/databases`. To avoid refetching tens of GB on
the next run, point the matching `*_db` parameter at the published directory:

```bash
# first run downloads everything
nextflow run benchmark-proteinfamilies --workflow_mode pre --outdir results -profile singularity

# later runs reuse it
nextflow run benchmark-proteinfamilies --workflow_mode pre --outdir results2 -profile singularity \
    --pfam_db results/pre/databases/pfam \
    --hamap_db results/pre/databases/hamap_alignments
```

The four member databases can be skipped individually with `--skip_hamap`, `--skip_ncbifam`,
`--skip_panther` and `--skip_pfam`; at least one must remain enabled. InterPro and SwissProt cannot
be skipped: InterPro defines the curated families being sampled, and SwissProt supplies the decoys.

Example versions and formats of the databases can be found [here](#protein-families-database-links-and-versions).

Useful knobs: `--min_membership 25 --num_per_db 50 --num_decoys 10000`. Add `--seed 42` only to
reproduce a _specific_ PRE run — by default the family pool is intentionally random, because a fresh
pool per PRE run is the sampling design. Comparability across tool runs comes from every run scoring
against the same universe, which `universe.sha256` enforces, not from seeding.

An example run command looks like this:
`nextflow run benchmark-proteinfamilies -c slurm_benchmark.config -profile singularity,slurm --workflow_mode pre -resume`

**PRE produces the artefacts POST needs:**

```
pre/combined_decoy.faa                             <- feed this to the family-generation tools
pre/families/sampled/id_registry.tsv
pre/universe.sha256
pre/families/sampled/sampled_fasta/                <- the curated originals
pre/families/sampled/updated_sampled_metadata.csv
pre/databases/                                     <- whatever was downloaded, for reuse
```

## nf-core/proteinfamilies

The generated output file named `combined_decoy.faa` must be given as input to `nf-core/proteinfamilies` by placing its path in the `samplesheet.csv` input file. PRE also emits `id_registry.tsv` and `universe.sha256` beside it; POST needs all three.

An example run command looks like this:
`nextflow run proteinfamilies -c slurm.config -profile singularity,slurm --input samplesheet.csv --outdir /path/to/proteinfamilies/use-case/output_1 --clustering_tool cluster --cluster_size_threshold 3 --cluster_seq_identity 0.5 --hmmsearch_family_length_threshold 1 --remove_sequence_redundancy false --save_non_redundant_fams_fasta true -with-tower -resume`

## post-proteinfamilies

During the `post` `workflow_mode`, generated full-family MSAs are compared with the sampled original families. POST metrics resolve tool IDs through the PRE `id_registry.tsv` and score set intersections on `universe_id`; `parent_id` coverage is reported only as auxiliary QC and is not part of the ranking.

POST is samplesheet-driven:

```
sample,tool,msa_dir,clustering_tsv
run_1,proteinfamilies,/path/to/full_msa/filtered/hhsuite_reformat/use_case,/path/to/mmseqs/use_case.tsv
run_2,mgnifams,/path/to/full_msa,
```

`msa_dir` is **required** and must be the **full-family** MSA directory, not a seed MSA — a seed MSA
is not full family membership, and pointing at one measures something different. `clustering_tsv` is
optional. When it is present, POST runs the clustering investigation, cross-checks cluster IDs, and
uses that cross-check to detect exactly this seed-MSA misconfiguration; when absent, that process is
skipped.

A configuration file must provide the PRE outputs used to build the tool input:

```
workflow_mode          = 'post'
post_samplesheet       = '/path/to/post_samplesheet.csv'
pre_id_registry        = '/path/to/pre/families/sampled/id_registry.tsv'
pre_universe_fasta     = '/path/to/pre/families/sampled/combined_decoy.faa'
pre_universe_sha256    = '/path/to/pre/families/sampled/universe.sha256'
pre_sampled_metadata   = '/path/to/pre/families/sampled/sampled_metadata.csv'
pre_sampled_fasta_dir  = '/path/to/pre/families/sampled/sampled_fasta'
association_threshold  = 0.1
min_intersection_size  = 3
scorecard_weights      = null
skip_multiqc           = false
```

> **The tool runs and the PRE artefacts must come from the same experiment.** POST verifies
> `universe.sha256` and refuses to score a samplesheet against a universe it was not built from. If
> you point POST at tool outputs produced from _different_ input, it fails with a high
> `unmapped_fraction` rather than silently reporting zeros.

An example run command looks like this:
`nextflow run benchmark-proteinfamilies -c slurm_benchmark.config -profile singularity,slurm --workflow_mode post -resume`

### POST output

```
post/<sample>/reproducibility_stats/   jaccard_similarities.csv, jaccard_qc.tsv,
                                       unmapped.tsv, ambiguous.tsv, decoy_stats.csv
post/<sample>/family_metrics/          family_metrics.tsv        (tp/fp/fn, P/R/F1, jaccard)
post/<sample>/split_merge/             split_merge_summary.tsv, original_overlap_baseline.tsv
post/<sample>/scorecard/               scorecard.tsv
post/<sample>/db_coverage/             family_coverage.csv, sequence_coverage.txt
post/comparison/                       benchmark_comparison.csv  <- the ranked answer
pipeline_info/                         software_versions.yml
```

- `family_metrics.tsv`: one row for every generated/original pair with a non-empty `universe_id` intersection. `precision_denom=|G|`, `recall_denom=|O|`, `f1` is their harmonic mean, and `jaccard_denom=|G union O|`.
- `split_merge_summary.tsv`: directional split/merge counts within each `db_layer`. Split associations use `precision(G,O)`; merge associations use `recall(G,O)`; both require `|G intersect O| >= min_intersection_size`.
- `scorecard.tsv`: an **EXPLORATORY** composite per run using `mean_f1`, `family_coverage`, `sequence_coverage`, `1 - decoy_recruitment_rate`, and `1 - split_merge_rate`, all keyed on `universe_id`.
- `post/comparison/benchmark_comparison.csv`: the deliverable — one row per tool run, ranked by the
  `EXPLORATORY` composite (rank 1 = highest, sorted descending), with every raw component published
  beside it so the ranking is auditable.

`match_threshold` (default 0.5, a reported family match) and `association_threshold` (default 0.1, an
edge considered for split/merge topology) are two different notions of "match" in one report — never
conflate them.

**Always check `jaccard_qc.tsv` first.** If `unmapped_fraction` is not ≈ 0, the IDs did not resolve
and no downstream number means anything.

### Known limits of the report

- The scorecard composite and its ranking ship labelled **EXPLORATORY**. Equal weights are
  arbitrary-but-defensible, and `association_threshold = 0.1` is a heuristic; every raw component is
  published so you can re-weight. Do not present the headline ranking as settled.
- A tool that fully renames sequences (hash IDs, integer reindexing) cannot be resolved against the
  registry. `unmapped_fraction` goes to 1.0 and the run fails loudly, by design; such a tool needs a
  per-tool mapping file.
- The end-to-end benchmark against real curated InterPro families has not been run yet.

### Protein families database links and versions

If internet access is unavailable on worker nodes, download and decompress the protein family SEED
alignments yourself and set the `*_db` parameters above. Otherwise leave them as `null` and let the
PRE workflow download each database from its `*_latest_link`.

```
DB  ver link    last_update size
NCBIFAM current https://ftp.ncbi.nlm.nih.gov/hmm/current/hmm_PGAP.SEED.tgz  2026-06-25 10:24    77M
PANTHER 19.0    https://data.pantherdb.org/ftp/panther_library/current_release/PANTHER19.0_fasta.tgz    2024    461M
HAMAP   -   https://ftp.expasy.org/databases/hamap/old/hamap_alignments.tar.gz  2025-10-07 01:41    2.2G
PFAM    37.2    https://ftp.ebi.ac.uk/pub/databases/Pfam/releases/Pfam37.2/Pfam-A.seed.gz   2024-12-05 07:31    159M
```

NCBIFAM has two types of families; TIGRxxxxx and NFxxxxxx. PANTHER is tens of GB — make sure
`--outdir` has room for it.

> **These remote URLs have never been fetched.** The download modules are exercised end to end
> against local fixture archives, so the download, extraction and splitting code is proven while the
> real endpoints are not. The HAMAP URL above in particular looks wrong. The download modules also
> ship without a SHA-pinned container: use `-profile conda`, or supply the database paths yourself.

## Example file formats

If you supply your own `*_db` paths, each directory should hold one alignment file per family, in
whichever of these layouts that database uses. Format is detected by sniffing the file, not by
extension.

**NCBIFAM** — `NF000005.4.SEED`, FASTA-formatted (its `TIGRxxxxx.SEED` files are Stockholm instead):

```
>AAG34545.1/3-119
DQATPNLPSRDFDSTAAFYERLGFGIVFRDAGWMILQRGDLKLEFFAHPGLDPLASWFSCCLRLDDLAEFYRQCKSVGIQ
ETSSGYPRIHAPELQEWGGTMAALVDPDGTLLRLIQN
>WP_021018480.1/3-119
DQATPNLPSRDFDSTAAFYEKLGFRSVFRDSGWMILQRGDLILEFFAHPELDPLASWFSCCLRLDDLAGFYERCKSVGIQ
ETSRGYPRIHAPELQEWGGTMAALVDSDGTLLRLIQN
```

**PANTHER** — `PTHR10059.fasta`, FASTA with pipe-delimited cross-references in the header:

```
>BOVIN|Ensembl=ENSBTAG00000001570|UniProtKB=P11052
MWLQNLLLLGTVVCSFSAPTRPPNTATRPWQHVDAIKEALSLLNHSSDTDAVMNDTEVVS
EKFDSQEPTCLQTRLKLYKNGLQGSLTSLMGSLTMMATHYEKHCPPTPETSCGTQFISFK
>HUMAN|HGNC=2434|UniProtKB=P04141
MWLQSLLLLGTVACSISAPARSPSPSTQPWEHVNAIQEARRLLNLSRDTAAEMNETVEVI
SEMFDLQEPTCLQTRLELYKQGLRGSLTKLKGPLTMMASHYKQHCPPTPETSCATQIITF
```

**HAMAP** — `MF_00264.msa`, FASTA-formatted with a metadata-laden description line:

```
>A0A0S3QRG7_THET7 L=1  103.017  11200 pos.        1 -     230 [   21,    -4] T|A0A0S3QRG7|A0A0S3QRG7_THET7
--------------------MSVVELREIQALNTLVFETLGQPEKEREFKFKTLKRWGLD
LILGKKNGSETYFVSEYGKRHKGDVYTEDGVEYEVSEILEELPSNKKLFAHIEMKDGRAY
>C5A445_THEGJ L=1  134.298  14670 pos.        1 -     222 [   30,    -4] T|C5A445|C5A445_THEGJ
-----------------------------MLEGYYIVENTGVVPAERRFKFKDLKAWGYD
LHLGTIDGKEAYFVSRTGTHEEGETYTQDGREYHITETQREIPKNARLLARIVIERGQPY
```

**PFAM** — Stockholm, and the one database needing preprocessing: Pfam ships every family
concatenated in a single `Pfam-A.seed`, which the pipeline splits into one `PFxxxxx.sto` per family,
keyed on the `#=GF AC` accession. Supply either the original `Pfam-A.seed` via `--pfam_latest_link`,
or an already-split directory via `--pfam_db`.

```
# STOCKHOLM 1.0
#=GF ID   VWC
#=GF AC   PF00093.24
#=GF DE   von Willebrand factor type C domain
#=GF SQ   19
CO5A2_HUMAN/41-96     CT.QNGQMYLNRDIWKPAP........CQ.ICVCDN........GAILCDKIE..CQD.....VLDCADP......VTPPGECCP..VC
CO3A1_MOUSE/33-89     CS.HLGQSYESRDVWKPEP........CQ.ICVCDS........GSVLCDDII..CDEE....PLDCPNP......EIPFGECCA..IC
#=GC seq_cons         Ch.psGphYpss-sWpss.........Cp.hCsCps........uplhCcpl...Cs.......hsCsss........s.GECCs..hC
//
```
