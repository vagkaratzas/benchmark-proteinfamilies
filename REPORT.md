# Benchmark-proteinfamilies — overhaul report

What changed, why it mattered, and exactly how to run the three stages on this machine.

Status: **all 12 planned phases landed.** `nextflow run . -profile test` → 43 processes, 0 failed.
`nf-test` → 6/6. 10 Python tests. `nextflow lint` → 0 errors across 41 files.

---

## 1. Top findings

### 1.1 The pipeline was silently scoring zero on real data

Every POST metric was a set intersection on raw ID strings, and protein-family tools do not
round-trip sequence IDs:

| source                                | example header             |
| ------------------------------------- | -------------------------- |
| mgnifams `full_msa/1.fas.gz`          | `1814953751/178-297`       |
| mgnifams clustering TSV               | `711279214_315_691`        |
| proteinfamilies `*.aln` / `*.clipkit` | `1446399400_1_131`         |
| proteinfamilies `family_reps/*.faa`   | `2632373804_177_299/1-122` |
| curated originals                     | `Q9X1J3/1-250`             |

The old code did `record.id.split("/")[0]`. Measured against **real mgnifams output**:

```
raw observed IDs           : 486
resolve to a real input ID : 95
unmapped                   : 391   (80.45%)
example: '1814953751/178-297' -> '1814953751'   in universe? False
```

Four out of five sequences vanished. Membership sets came out empty, Jaccard came out `0.0` against
every curated family, and that was reported as a **legitimate score, not an error**.

After the fix, on the same real data:

| tool                    | raw IDs | resolved | unmapped   | ambiguous | fragments/seq |
| ----------------------- | ------- | -------- | ---------- | --------- | ------------- |
| nf-core/proteinfamilies | 115     | 115      | **0.0000** | 0.0000    | 1.00          |
| mgnifams                | 486     | 486      | **0.0000** | 0.0000    | **1.40**      |

mgnifams' 1.40 fragments per input sequence is real signal — it splits proteins into domains — and it
is now _recorded_ rather than mangled.

### 1.2 Identity is now recorded, not guessed

PRE emits `id_registry.tsv` (`universe_id, parent_id, source_type, db_layer, family, coords,
ungapped_len, seq_sha1`) plus `universe.sha256`. POST resolves observed IDs against that registry via
a forward alias index and an unordered coordinate lattice, disambiguating on the observed sequence
when several candidates survive.

The first design — regex canonicalisation against the input universe — was refuted during adversarial
review (false attribution, strip-order sensitivity, legitimate IDs ending `_12_34`). Following the
correction through revealed that the **comparison key is `universe_id`, not `parent_id`**: collapsing
to the protein merges two unrelated curated domains of the same protein across families and inflates
scores. `parent_id` survives as a reporting dimension only.

Because the failure mode is silence, POST now fails loudly: `unmapped_fraction` /
`ambiguous_fraction` gates, full `unmapped.tsv` / `ambiguous.tsv`, and a `universe.sha256` check
stamped into every result table so a samplesheet cannot be scored against a universe it was not built
from.

### 1.3 Metrics that can actually rank parameter combinations

Jaccard is symmetric and one-to-one, so it cannot tell a tool that splits one curated family into
five from one that merges five into one — exactly what a parameter sweep produces. Added:

- **P/R/F1** per matched (generated, original) pair, on `universe_id` sets, denominators named in the
  output header.
- **Split / merge topology**, directional and **union-based** so the counts do not depend on file
  iteration order, computed **within a `db_layer`** (curated families overlap across databases, so a
  Pfam/PANTHER pair is redundancy, not a merge), with an original-overlap baseline separating
  tool-caused merges from curation-caused ones.
- **Ranked cross-run scorecard** + **MultiQC**. The composite ships labelled `EXPLORATORY` — its
  weights and `association_threshold = 0.1` are heuristics, not yet validated on real runs.

An earlier justification of mine was simply wrong and was withdrawn: I claimed a family "cannot have
two matches at Jaccard ≥ 0.5 by definition". Counterexample: `O={1,2}`, `G1={1}`, `G2={2}` gives two
edges at exactly 0.5.

### 1.4 Samplesheet reduced to what tools actually produce

`sample,tool,msa_dir,clustering_tsv`. `hmm_dir` was never consumed. `generated_fasta_dir` carried no
unique information _and_ was silently broken — its only reader filtered on `.fasta.gz` while both
reference tools emit `.faa`/`.fas.gz`, so it loaded zero files and tagged **every** original family
`vanished`.

### 1.5 Bugs found by running things, not reading them

Several defects were invisible to `-stub` runs and unit tests, and only surfaced by executing the
real pipeline:

- `export PYTHONPATH="$PWD:$PYTHONPATH"` aborts every POST module: `.command.sh` runs under
  `bash -ue`, so an unset `PYTHONPATH` is fatal. Now `${PYTHONPATH:-}`.
- Seven rewritten `bin/*.py` lost their executable bit (exit 126); one lost its shebang and was run by
  `sh` (`import: command not found`).
- **MultiQC had never once run.** Every sample emitted identically-named `*_mqc.csv`, so collecting
  them across samples was an input filename collision; and `--skip_multiqc false` _skipped_ MultiQC,
  because on the CLI that value arrives as the String `"false"` and every non-empty String is truthy
  in Groovy.
- `nf-schema` rejected **every** valid CLI numeric (`--num_per_db 10` → _"Value is [string] but should
  be [integer]"_), because Nextflow 26 passes CLI params as `String` while config defaults stay
  `Integer`.
- `combine_decoy_fasta` deleted legitimate curated family members that share a sequence across
  databases — routine, per the overlap analysis — dropping them from the universe _and_ the registry
  while `sampled_fasta/` still listed them.

### 1.6 Other substantive changes

- **Performance**: Jaccard went from O(U×O) with a re-parse in the inner loop to an inverted index +
  multiprocessing. Pinned by two orthogonal tests — one asserts the pruning (fails at 2500 scored
  pairs on the old full scan), one asserts the _results_ are byte-identical (still passes with the
  index disabled).
- **PRE cleanup**: the four `EXTRACT_*_METADATA` modules merged into one `EXTRACT_DB_METADATA`,
  preserving NCBIFAM's dual `.SEED` formats and its `split(".")[0]` id rule (`NF000001.1.SEED` →
  `NF000001`).
- **nf-core conformance**: `nextflow_schema.json` + `nf-schema`, `tag`/`stub:` on every local module,
  `pipeline_initialisation` / `pipeline_completion`, aggregated `software_versions.yml`, SHA-pinned
  containers, DIAMOND aligned to 2.1.11 (`makedb` was on 2.1.8).
- **On-demand reference databases**: any of the seven DB path params left `null` is fetched by a
  `DOWNLOAD_*` module into `--db_cache_dir` via `storeDir`.
- **`seed` defaults to `null` on purpose.** A fresh random family pool per PRE run is the sampling
  design; comparability across tool runs is enforced by `universe.sha256`, not by seeding.

### 1.7 Open risks

1. The six download URLs have **never been fetched** — every Phase 10 proof is `-stub`. In particular
   `ftp.expasy.org/databases/hamap/old/hamap_alignments.tar.gz` looks wrong.
2. Those modules ship with conda environments but **no SHA-pinned container**; no digest could be
   resolved offline, and an invented one fails at runtime rather than at review. Use `-profile conda`,
   or supply the paths directly.
3. The **end-to-end benchmark against curated InterPro families has not been run** — it needs the real
   reference databases, which are not on this machine.
4. The scorecard composite and its ranking are `EXPLORATORY` until weights and `association_threshold`
   are tuned on real data.

Full detail: `PLAN.md` (frozen spec + risks) and `PLAN-REVIEW-LOG.md` (the whole grill → adversarial
review → build → verify argument).

---

## 2. Commands to run on this machine

Requires Nextflow ≥ 24.04.2 (developed against 26.04.4). Run everything from the repo root:

```bash
cd /home/vangelis/Desktop/Projects/benchmark-proteinfamilies/benchmark-proteinfamilies
```

### 2.0 Offline smoke test (no databases, no network, ~10 s)

Proves the whole POST graph over the committed synthetic fixtures, and the whole PRE graph as a stub:

```bash
nextflow run . -profile test     --outdir /tmp/post_test  -work-dir /tmp/post_test_work
nextflow run . -stub -profile test_pre --outdir /tmp/pre_stub -work-dir /tmp/pre_stub_work

python3 bin/benchmark_ids.py
python3 -m unittest discover -s tests -p 'test_*.py'
nf-test test
nextflow lint .
```

### 2.i PRE — build the benchmark dataset

PRE needs the seven reference inputs. **Leave any of them unset and it will be downloaded** into
`--db_cache_dir` (a persistent `storeDir` — keep it out of `work/` and out of `--outdir`).

> The download URLs have not been exercised (risk 1 above), and the download modules have no
> container (risk 2), so add `-profile conda` unless you supply every path yourself.

```bash
# (a) fully automatic: fetch whatever is missing into the cache
nextflow run . \
  -profile conda,local \
  --workflow_mode pre \
  --db_cache_dir /home/vangelis/Desktop/Projects/benchmark-proteinfamilies/data/reference \
  --outdir /home/vangelis/Desktop/Projects/benchmark-proteinfamilies/output/pre \
  -work-dir /home/vangelis/Desktop/Projects/benchmark-proteinfamilies/work \
  -resume

# (b) databases already on disk: nothing is downloaded
nextflow run . \
  -profile singularity,local \
  --workflow_mode pre \
  --interpro_hierarchy_file /path/to/interpro/ParentChildTreeFile.txt \
  --id_mapping_file         /path/to/interpro/interpro.xml.gz \
  --path_to_hamap           /path/to/hamap/hamap_alignments \
  --path_to_ncbifam         /path/to/ncbifam/hmm_PGAP \
  --path_to_panther         /path/to/panther/PANTHER19.0_fasta \
  --path_to_pfam            /path/to/pfam/37.2/seed/alignments \
  --path_to_swissprot       /path/to/uniprot/uniprot_sprot.fasta \
  --outdir /home/vangelis/Desktop/Projects/benchmark-proteinfamilies/output/pre \
  -resume
```

Useful knobs: `--min_membership 25 --num_per_db 50 --num_decoys 10000`. Add `--seed 42` only if you
want to reproduce a _specific_ PRE run; by default the family pool is intentionally random.

**PRE produces the four artefacts POST needs:**

```
output/pre/.../combined_decoy.faa      <- feed this to the family-generation tools
output/pre/.../id_registry.tsv
output/pre/.../universe.sha256
output/pre/.../sampled_fasta/          <- the curated originals
output/pre/.../updated_sampled_metadata.csv
```

### 2.ii The protein-family pipelines (run outside this repo)

They consume `combined_decoy.faa`. To exercise them with their own bundled test data:

```bash
# nf-core/proteinfamilies
cd /home/vangelis/Desktop/Projects/proteinfamilies/proteinfamilies && \
  nextflow run main.nf -c ../conf/local.config -profile test,local,singularity --outdir output -resume

# mgnifams
cd /home/vangelis/Desktop/Projects/mgnifams/mgnifams && \
  nextflow run main.nf -c ../conf/local.config -profile test,local,singularity --outdir output -resume
```

For a real benchmark, point them at PRE's `combined_decoy.faa` instead of their test data — for
proteinfamilies that means putting its path in the `fasta` column of `assets/samplesheet.csv`.

### 2.iii POST — score the tool runs

Write a samplesheet. `msa_dir` is required and must be the **full-family** MSA directory (not a seed
MSA); `clustering_tsv` is optional.

```bash
cat > /tmp/post_samplesheet.csv <<'CSV'
sample,tool,msa_dir,clustering_tsv
proteinfamilies_default,proteinfamilies,/home/vangelis/Desktop/Projects/proteinfamilies/proteinfamilies/output/full_msa/filtered/famsa_align/mgnifams_test,/home/vangelis/Desktop/Projects/proteinfamilies/proteinfamilies/output/mmseqs/initial_clustering/mmseqs_createtsv/mgnifams_test.tsv
mgnifams_default,mgnifams,/home/vangelis/Desktop/Projects/mgnifams/mgnifams/output/generate_families/families/full_msa,/home/vangelis/Desktop/Projects/mgnifams/mgnifams/output/setup_clusters/mmseqs/mgnifams_v2.tsv
CSV

PRE=/home/vangelis/Desktop/Projects/benchmark-proteinfamilies/output/pre

nextflow run . \
  -profile singularity,local \
  --workflow_mode post \
  --post_samplesheet      /tmp/post_samplesheet.csv \
  --pre_id_registry       $PRE/id_registry.tsv \
  --pre_universe_fasta    $PRE/combined_decoy.faa \
  --pre_universe_sha256   $PRE/universe.sha256 \
  --pre_sampled_metadata  $PRE/updated_sampled_metadata.csv \
  --pre_sampled_fasta_dir $PRE/sampled_fasta \
  --outdir /home/vangelis/Desktop/Projects/benchmark-proteinfamilies/output/post \
  -resume
```

> **The tool runs and the PRE artefacts must come from the same experiment.** POST verifies
> `universe.sha256` and refuses to score a samplesheet against a universe it was not built from. If
> you point POST at tool outputs produced from _different_ input (e.g. the bundled test data above),
> it will correctly fail with a high `unmapped_fraction` rather than silently report zeros.

Add `--skip_multiqc false` for the MultiQC report (needs a container). Other knobs:
`--match_threshold 0.5 --association_threshold 0.1 --min_intersection_size 3`.

**POST output:**

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

`post/comparison/benchmark_comparison.csv` is the deliverable: one row per tool run, ranked by the
`EXPLORATORY` composite, with every raw component published beside it so the ranking is auditable.

**Always check `jaccard_qc.tsv` first.** If `unmapped_fraction` is not ≈ 0, the IDs did not resolve
and no downstream number means anything — that is precisely the failure this overhaul made loud.
