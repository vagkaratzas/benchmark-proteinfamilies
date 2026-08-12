# AGENTS.md

Guidance for coding agents (Claude Code, Codex, etc.) working in this repository.

## Working rules

- **Never push to remote.** Commit only when explicitly asked, one commit per feature.
- **Before a commit, run the build, lint, typecheck, and the relevant test suite** (see _Testing_).
- **Always use the `token-saviour` skill.**
- **Keep responses concise** — summarise rather than dumping full files, to stay inside output token
  limits.
- **`README.md` is for users of the pipeline; `AGENTS.md` is for developers.** Design rationale,
  measurements, conventions and risks belong here, not there.
- **These four files are the whole documentation set** (`README.md`, `AGENTS.md`, `CHANGELOG.md`,
  and `CLAUDE.md`, which only points here).
- **A user-visible change means a `CHANGELOG.md` entry** under the unreleased heading, in the same
  commit. User-visible means a parameter, an output, a default, or a behaviour someone running the
  pipeline would notice — not a refactor, a test, or a doc edit. Renaming or removing a parameter
  also needs a row in that release's _Breaking changes_ table.

## Project Overview

Nextflow DSL2 framework that benchmarks **any** protein-family generation tool against manually
curated InterPro families (HAMAP, NCBIFAM, PANTHER, PFAM). It answers: _which tool / parameter
combinations reconstruct curated families as well as human curators?_

Three steps:

1. **PRE** (runs once) — samples curated InterPro families, adds SwissProt decoys, emits
   `combined_decoy.faa` **plus `id_registry.tsv` and `universe.sha256`**.
2. **External tools** — run by the user, outside this pipeline, on `combined_decoy.faa`.
   Reference implementations: `nf-core/proteinfamilies` and `mgnifams`.
3. **POST** — ingests a samplesheet of tool runs, scores each against the curated originals, and
   emits a ranked cross-run report.

POST is tool-agnostic: no hardcoded database layers, file extensions, or protein-ID formats, and no
assumption that a tool emits anything beyond per-family MSAs.

## The single most important invariant

**Identity is recorded by PRE, never inferred by POST.**

Tools do not round-trip sequence IDs. mgnifams emits `1814953751/178-297`; proteinfamilies emits
`2632373804_177_299/1-122`; curated originals are keyed `Q9X1J3/1-250`. Every metric is a set
intersection on ID strings, so the old `record.id.split("/")[0]` silently dropped **80.45%** of real
mgnifams sequences, leaving Jaccard at 0.0 against every family — reported as a legitimate score.

PRE therefore writes `id_registry.tsv`:

```
universe_id  parent_id  source_type  db_layer  family  coords  ungapped_len  seq_sha1
```

- `universe_id` — the exact header in `combined_decoy.faa` (what tools were fed). **This is the
  comparison key for every metric.**
- `parent_id` — protein accession. **Reporting only. Never a scoring key** — collapsing to the
  protein merges two unrelated curated domains of the same protein across families and inflates
  scores.
- `source_type ∈ {family, decoy}` — authoritative. Decoys are never inferred from ID shape.

`bin/benchmark_ids.py` resolves an observed ID via a **forward alias index** built from registry
rows, plus an unordered coordinate lattice; when several candidates survive it disambiguates on the
observed **sequence** (`seq_sha1`, then substring containment). Ambiguity is a first-class status,
never resolved arbitrarily.

Note the deliberate asymmetry: PRE strips only a trailing `/start-end` (curated alignments use no
other form), while `benchmark_ids.py` keeps both `/start-end` and `_start_end` when resolving tool
output. **PRE records truth; POST resolves drift.** Do not "unify" them.

The failure mode is silence, so POST fails loudly: `unmapped_fraction` / `ambiguous_fraction` gates,
full `unmapped.tsv` / `ambiguous.tsv` per run, and a `universe.sha256` check recorded in every result
table so a samplesheet cannot be scored against a different universe than it was built from.

**Measured, on real tool output** (registries built from the exact FASTA each pipeline consumed —
this needs no curated databases and is reproducible today):

| tool                    | universe                            | raw IDs | resolved | unmapped   | ambiguous | fragments/seq |
| ----------------------- | ----------------------------------- | ------- | -------- | ---------- | --------- | ------------- |
| nf-core/proteinfamilies | `mgnifams_input_small.faa` (50,000) | 115     | 115      | **0.0000** | 0.0000    | 1.00          |
| mgnifams                | `mgnifams_v2.fa` (26,949)           | 486     | 486      | **0.0000** | 0.0000    | **1.40**      |

mgnifams' 1.40 fragments per input sequence is the domain-shredding signal the design preserves
rather than discards. Against the same output the old `record.id.split("/")[0]` resolved 95/486 —
`'1814953751/178-297' -> '1814953751'`, not in the universe. That is the bug this design exists to
kill, and it is why every change here is checked against real output, not only fixtures.

### Rejected designs — do not re-litigate

Each of these was proposed, argued and rejected on evidence. Re-proposing one needs new evidence.

- **Regex canonicalisation of observed IDs against the universe** (the original design). Unsound:
  false attribution (`X_1_2/3-4` strips to a universe hit `X_1_2` when the true source was `X`),
  strip-order sensitivity on mixed suffixes, and legitimate input IDs ending `_12_34` silently
  reinterpreted as coordinates. Replaced by the registry — PRE knows the truth at construction time.
- **Collapsing to `parent_id` for scoring.** Merges two unrelated curated domains of the same protein
  across families and inflates scores. `universe_id` needs no collapsing: the tools are fed
  `combined_decoy.faa`, whose headers _are_ the `universe_id`s.
- **Flagging every coordinate-looking exact registry hit as ambiguous.** Over-triggers on legitimate
  inputs and pushes `ambiguous_fraction` toward the fail gate. Sequence disambiguation settles the
  real case (`X` vs `X_1_2` both present) using evidence already in hand.
- **Generating aliases backward from the observed ID.** `sp|P12345|NAME -> P12345` is not a registry
  key, so every decoy resolved to unmapped. Aliases are built **forward from registry rows**.
- **A separate `membership_dir` / `generated_fasta_dir` samplesheet column.** Dropped by the user;
  `membership_source = MSA` stated prominently in every report addresses the honesty concern without
  a schema change.
- **A hard `universe_coverage` gate.** A conservative tool legitimately recruits few sequences, so a
  hard gate false-fails good runs. It warns; `min_universe_coverage` (default `null`) opts in, and
  the `clustering_tsv` cross-check is the real seed-MSA detector.
- **Seeding PRE by default.** A fresh random family pool per run _is_ the sampling design;
  comparability comes from `universe.sha256`. `seed` stays `null`.

A withdrawn claim worth remembering: "a family cannot have two matches at Jaccard >= 0.5 by
definition" is **false** — `O={1,2}`, `G1={1}`, `G2={2}` gives two edges at exactly 0.5. That error
is why split/merge is defined directionally rather than off Jaccard.

## Running the Pipeline

Requires Nextflow >= 24.04.2 (developed against 26.04.4). A container/conda profile is required
alongside any executor profile. Production invocations are in `README.md`; these are the offline
developer smoke tests.

```bash
# offline smoke tests over the committed synthetic fixtures
nextflow run . -profile test,conda --outdir /tmp/post_test              # POST
nextflow run . -profile test_pre,conda --outdir /tmp/pre_test           # PRE, every *_db supplied
nextflow run . -profile test_pre_download,conda --outdir /tmp/pre_dl    # PRE via the DOWNLOAD_* path
```

`test_pre` and `test_pre_download` produce a byte-identical universe; they differ only in whether the
databases arrive from `conf/test_pre.config`'s fixture paths or are fetched by the `DOWNLOAD_*`
modules from `file://` fixture archives in `assets/fixtures/downloads/`. Both need `-profile conda`
(the `DOWNLOAD_*` modules ship no container — see the TODO in each).

### Reference databases

Every database follows the same three-param shape:

| Param           | Meaning                                                          |
| --------------- | ---------------------------------------------------------------- |
| `*_db`          | path to a copy you already have; when set, nothing is downloaded |
| `*_latest_link` | URL fetched when `*_db` is null                                  |
| `*_version`     | **provenance only** — process `tag`, trace, execution report     |

`*_version` does not build the URL and does not select a release; the link does. Bump both together.

Downloaded databases are **published under `<outdir>/pre/databases`**, like any other output. That
is the whole reuse mechanism: point the matching `--*_db` at the published directory on the next run
instead of refetching tens of GB. There is no `storeDir` and no `--db_cache_dir` any more, so publish
somewhere with room, and remember `publish_dir_mode = 'copy'` duplicates rather than moves.

The four member databases (`hamap`, `ncbifam`, `panther`, `pfam`) are individually skippable via
`--skip_<db>`; InterPro and SwissProt are not, since one drives the sampling design and the other is
the decoy source. **At least one member database must survive** — `pipeline_initialisation` rejects
an all-skipped run rather than letting it deadlock on an empty channel downstream.

## Architecture

Routed in `main.nf` by `--workflow_mode` (`pre` | `post`), wrapped by
`subworkflows/local/pipeline_initialisation` (nf-schema `validateParameters()` + explicit assertions)
and `pipeline_completion`.

- **`workflows/pre.nf`** — parses the InterPro hierarchy, extracts metadata from however many
  member databases survived `--skip_*` (one keyed `DOWNLOAD_DBS.out.member_dbs` channel fanned out
  through one parameterised `EXTRACT_DB_METADATA`), samples families respecting tree structure,
  emits `sampled_fasta/`, `combined_db.faa`, `id_registry.tsv`, then generates decoys via DIAMOND
  BLASTP against SwissProt and emits `combined_decoy.faa` + `universe.sha256`.
- **`workflows/post.nf`** — samplesheet-driven, one `meta` map per row, per-`${meta.id}` publishDir.
  Jaccard, per-family P/R/F1, split/merge topology, decoy recruitment, coverage, scorecard,
  cross-run comparison, MultiQC.

### Layout

- `modules/local/` — 27 modules, each with `main.nf` + `environment.yml` + `meta.yml` + `tests/`, a
  `tag`, a `label` and a `stub:` block. `modules/nf-core/` — DIAMOND (`makedb`, `blastp`), MultiQC.
- `subworkflows/local/` — 7: `pipeline_initialisation`, `pipeline_completion`,
  `validate_post_samplesheet`, `download_dbs`, `generate_decoys` (PRE), `score_samples`,
  `report_benchmark` (POST).
- `bin/` — 23 Python scripts. `benchmark_ids.py` and `post_common.py` are **libraries**, not CLIs.
- `assets/fixtures/` — committed fixtures (universe, PRE, POST, db_metadata, expected goldens). The
  module tests reuse these; no module ships its own copy of test data.
- `tests/` — 6 Python test files (10 tests) + the 2 workflow nf-tests. Module nf-tests live beside
  their module, not here. `conf/` — `base.config` (resource labels), `modules.config` (publishing,
  `ext.when`).

**Versions** are collected on the global `versions` topic: every module emits
`tuple val("${task.process}"), val('<tool>'), eval("<cmd>"), topic: versions`, and
`PIPELINE_COMPLETION` drains the topic into `pipeline_info/software_versions.yml` for both modes.
There is no `versions.yml` and no collector process.

### Conventions that will bite you

- **`bin/` helper import.** Nextflow puts `bin/` on `PATH`, not `PYTHONPATH`. Modules that import
  `benchmark_ids` / `post_common` stage them as `path` inputs and start the script block with
  `export PYTHONPATH="\$PWD:\${PYTHONPATH:-}"`. The `:-` matters: `.command.sh` runs under
  `bash -ue`, so a bare `$PYTHONPATH` aborts the task when it is unset.
- **Every `bin/*.py` needs `#!/usr/bin/env python3` and the executable bit.** Losing either fails at
  runtime (exit 126, or `sh` trying to run `import`), and no `-stub` run will catch it.
- **`-stub` never executes the script block.** A green stub run proves the DAG, nothing more.
- **CLI numerics arrive as `String`** on Nextflow 26, while config defaults stay `Integer`. Numeric
  params in `nextflow_schema.json` therefore accept `["integer","string"]` with a numeric `pattern`;
  `pipeline_initialisation` coerces and enforces `> 0`. Do not "tighten" the schema back.
- **Groovy string truthiness.** `--skip_multiqc false` arrives as the String `"false"`, which is
  truthy. Coerce before testing.
- **`conf/base.config` holds production resource tiers.** Never lower a tier to make a test schedule;
  cap the test with `resourceLimits` in the profile.
- Never pass an empty `--outdir`: Nextflow publishes into a directory literally named `true`.
- **Never run `nextflow lint -format`.** The formatter deletes comments that sit inside a process
  `input:` / `output:` block — measured: 187 comment lines in, 163 out, `-harshil-alignment` or not.
  That is precisely where the modules explain their non-obvious emits (e.g. why the `DOWNLOAD_*`
  processes emit no versions at all). `nextflow lint .` (check only) is what runs in pre-commit and
  is what must stay clean.
- **A `storeDir` process cannot emit `topic: versions`.** A topic emit is a `tuple` output and
  Nextflow permits only `val`/`path` outputs alongside `storeDir`. This is why the `DOWNLOAD_*`
  modules emitted no versions while they used `storeDir`; they now publish normally and do emit.
  Reintroducing `storeDir` anywhere means giving up that module's version emit.
- **Boolean params need `["boolean","string"]` in the schema too**, for exactly the reason the
  numerics do: `--skip_pfam true` arrives as the String `"true"` and `validateParameters()` rejects
  it against a bare `boolean` before the workflow's own coercion ever runs. Only the bare-flag form
  `--skip_pfam` survives a boolean-only schema.
- **Alignment format is sniffed, never inferred from the extension.** Observed in the wild:
  `.clipkit` (FASTA-formatted), `.aln`, `.fas.gz`, `.sto`, `.sto.gz`, `.faa`, `.fasta`, `.afa`.
  Detect Stockholm vs FASTA from the first non-blank line (`# STOCKHOLM` vs `>`); fall back to the
  extension only when sniffing is inconclusive. `.clipkit` says nothing about format.
- **Match families to files by exact mapping from the metadata CSV, never by prefix** — `PF1`
  prefix-matches `PF10`.

## Key Parameters

| Param                    | Default | Meaning                                                                                                                                                                                                               |
| ------------------------ | ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `min_membership`         | 25      | minimum proteins per family to be sampled                                                                                                                                                                             |
| `num_per_db`             | 50      | families sampled per database                                                                                                                                                                                         |
| `num_decoys`             | 10000   | SwissProt decoys                                                                                                                                                                                                      |
| `seed`                   | `null`  | **nondeterministic by design.** A fresh random family pool per PRE run is the sampling design; cross-run comparability is enforced by `universe.sha256`, not by seeding. Set it only to reproduce a specific PRE run. |
| `match_threshold`        | 0.5     | a reported family match (was `jaccard_similarity_threshold`)                                                                                                                                                          |
| `association_threshold`  | 0.1     | an edge considered for split/merge topology                                                                                                                                                                           |
| `min_intersection_size`  | 3       | floor on \|G ∩ O\| for an association                                                                                                                                                                                 |
| `max_unmapped_fraction`  | 0.05    | hard fail above this                                                                                                                                                                                                  |
| `max_ambiguous_fraction` | 0.01    | hard fail above this                                                                                                                                                                                                  |
| `min_universe_coverage`  | `null`  | opt-in hard gate; low coverage otherwise only warns                                                                                                                                                                   |
| `scorecard_weights`      | `null`  | equal weights                                                                                                                                                                                                         |
| `skip_<db>`              | `false` | skip one of the four member databases (`hamap`, `ncbifam`, `panther`, `pfam`). At least one must stay enabled.                                                                                                        |

`match_threshold` and `association_threshold` are two different notions of "match" in one report —
never conflate them.

## POST samplesheet

```
sample,tool,msa_dir,clustering_tsv
```

`msa_dir` is **required** and is the sole membership source; it must point at the **full-family** MSA
directory, not a seed MSA. `clustering_tsv` is optional; when present it drives `cluster_count` and
cross-checks MSA completeness, and `INVESTIGATE_MATCHED_ORIGINALS` is gated on it declaratively via
`ext.when = { meta.has_clustering }` in `conf/modules.config` — not by an `if` in the workflow.

`hmm_dir` and `generated_fasta_dir` were deliberately removed: nothing consumed the former, and the
latter was redundant with `msa_dir` and silently broken (it filtered on `.fasta.gz` while both
reference tools emit `.faa`/`.fas.gz`, tagging every original family `vanished`).

## Metrics

Jaccard is symmetric and one-to-one, so it cannot distinguish a tool that splits one curated family
into five from one that merges five into one. Therefore:

- **P/R/F1 per matched (generated, original) pair**, on `universe_id` sets, denominators named in the
  output header.
- **Split / merge**, defined _directionally_ and **union-based** so counts are independent of file
  iteration order (a greedy left-to-right rule is order-dependent and wrong). Computed **within a
  `db_layer`**, because curated families overlap across databases — a Pfam/PANTHER pair is database
  redundancy, not a merge. An original-overlap baseline separates tool-caused merges from
  curation-caused ones.
- **Scorecard**, composed only of `universe_id`-keyed components. Ships labelled **EXPLORATORY**: the
  weights and `association_threshold` are heuristics, not validated on real runs.

## NCBIFAM Note

NCBIFAM has two family ID formats (`TIGRxxxxx`, `NFxxxxxx`) **and** two alignment formats. Its `.SEED`
files are Stockholm _or_ FASTA, and its family id is derived with `fname.split(".")[0]`, **not**
`splitext` — so `NF000001.1.SEED` must yield `NF000001`. The other three databases use `splitext`.
`bin/extract_db_metadata.py` preserves this; `tests/test_extract_db_metadata.py` pins it.

## Testing

```bash
python3 bin/benchmark_ids.py                        # identity-core self-check
python3 -m unittest discover -s tests -p 'test_*.py'

# 51 nf-tests: 2 per local module (real + stub) plus the 3 workflow stubs.
# The `+` APPENDS the container profile to the base `test` profile from nf-test.config, which
# supplies resourceLimits. Without the `+` it REPLACES it, and process_medium then asks for 36.GB
# and never schedules.
export NXF_SINGULARITY_CACHEDIR=<your path>
nf-test test --profile +singularity

nextflow lint .                                     # check only -- never -format, see above
```

**Snapshots pin tool versions, so they are environment-sensitive.** Many module snapshots currently
fail on a drifted conda environment with `python`/`biopython` version mismatches while every file
md5 matches. Before blaming your change, get a baseline: `git worktree add --detach /tmp/base HEAD`
and run the suite there. Regenerate a snapshot only when its _content_ changed, and regenerate on
the reference environment rather than baking a local toolchain version into the repo.

Testing the modules against a container profile rather than host Python matters: two container
bugs (a pandas image pinned with both a tag and a digest, which Singularity refuses; and a
biopython import forced onto two modules whose images do not ship it) were invisible for as long
as the tests ran on the host interpreter.

Tests are expected to be **load-bearing**: each regression test here fails when its bug is
reintroduced (verified by mutation). If you add one, check it can fail.

## Linting

`pre-commit` enforces formatting; install once with `pip install pre-commit && pre-commit install`.
Hooks: prettier (Nextflow, YAML, Markdown), trailing-whitespace / end-of-file-fixer, ruff (`bin/`),
and `nextflow lint` in check-only mode. Run them all with `pre-commit run --all-files`.

## Open risks

1. **The six `DOWNLOAD_*` remote URLs have never been fetched.** `-profile test_pre_download`
   exercises the modules end to end — curl, tar, gunzip, `split_pfam_seed.py`, the non-empty
   assertions — but only against local `file://` fixture archives, so the real endpoints remain
   unproven. HAMAP's `.../hamap/old/hamap_alignments.tar.gz` looks wrong and should be confirmed
   against the provider before release.
2. **The download modules ship without a SHA-pinned container.** They declare conda +
   `environment.yml` (curl, plus python for Pfam), but no digest could be resolved or verified
   offline, and an invented one fails at runtime rather than at review. Under `-profile
docker/singularity` they run on the host. Use `-profile conda`, or supply the paths directly.
3. **The end-to-end benchmark against curated InterPro families has not been run** — it needs the
   real reference databases, which are not on this machine.
4. **The scorecard composite and `association_threshold = 0.1` are heuristics**, labelled
   EXPLORATORY until tuned on real runs with a threshold-sensitivity sweep. `min_intersection_size`
   blunts the worst of it but does not remove the arbitrariness.
5. **A tool that fully renames sequences** (hash IDs, integer reindexing) cannot be resolved against
   the registry; the run fails loudly on `unmapped_fraction`. Accepted limitation — such tools need a
   per-tool mapping file.
6. **Seed-vs-full MSA** is a user-configuration hazard mitigated by the `clustering_tsv` cross-check
   and warnings, not prevented.
7. PANTHER is tens of GB, so the download path is not fully testable on a laptop.

## Out of scope

Deliberately excluded; do not add without asking:

- Running the external family-generation pipelines from inside this pipeline. The benchmark is
  tool-agnostic precisely because it does not own the tool invocation.
- HMM retrieval benchmarking (`hmmsearch` vs `combined_decoy.faa`) — deferred by the user, which is
  why the samplesheet schema is kept additive so it can return without a breaking change.
- Domain-level re-projection of InterPro originals.
- Structural / functional-annotation metrics.
