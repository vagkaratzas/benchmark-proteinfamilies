# Plan: benchmark-proteinfamilies — generic protein-family benchmarking framework

_Locked via grill — by Claude + vagkaratzas (2026-07-09). Revised after Codex adversarial review round 1._

## Goal

Turn this two-mode Nextflow pipeline into a standardised, nf-core-conformant benchmarking
framework that answers: **"which computational tool / parameter combinations can match the
quality of manual curation in generating protein families?"**

Three-step framework:

1. **PRE** (runs once) — sample manually curated InterPro families (HAMAP, NCBIFAM, PANTHER,
   PFAM), add SwissProt-derived decoys, emit `combined_decoy.faa` **plus an ID registry**.
2. **External tools** (run by the user, outside this pipeline) — any family-generation pipeline
   consumes `combined_decoy.faa`. Reference implementations: `nf-core/proteinfamilies`, `mgnifams`.
3. **POST** — ingest a samplesheet of one-or-more tool runs, score each against the curated
   originals, emit a **ranked cross-run benchmark report**.

POST must be tool-agnostic: no hardcoded DB layers, file extensions, or protein-ID formats, and
no assumption that a tool emits anything beyond per-family MSAs.

---

## Key decisions & tradeoffs

### D1 — Identity is _recorded_ by PRE, not reverse-engineered by POST

**Problem.** Tools do not round-trip sequence IDs. Observed in real outputs:

| Source                                           | Example header             |
| ------------------------------------------------ | -------------------------- |
| mgnifams `full_msa/1.fas.gz`                     | `1814953751/178-297`       |
| mgnifams `setup_clusters/mmseqs/*.tsv`           | `711279214_315_691`        |
| proteinfamilies `*.clipkit` / `*.aln`            | `1446399400_1_131`         |
| proteinfamilies `family_reps/*.faa`              | `2632373804_177_299/1-122` |
| PRE originals (`clean_id`: `.\|=`→`_`, `/` kept) | `Q9X1J3/1-250`             |
| PRE decoys (raw SwissProt, **pipes kept**)       | `sp\|P12345\|NAME`         |

Every POST metric is a set-intersection on ID strings. Uncorrected, a tool that appends domain
coordinates scores **Jaccard 0.0 against every original family**, reported as a legitimate score
rather than an error. `calculate_jaccard_similarity.py` does `record.id.split("/")[0]`, which
handles `/s-e` but not `_s_e`, and mangles `2632373804_177_299/1-122` → `2632373804_177_299`.

**Rejected approach (was D1 in round 0): regex canonicalisation against the universe set.**
Codex refuted it and it is genuinely unsound:

- _False attribution_ — `X_1_2/3-4` can strip to a universe hit `X_1_2` when the true source was `X`.
- _Order sensitivity_ — stripping `/\d+-\d+$` before `_\d+_\d+$` changes the outcome on mixed suffixes.
- _Legitimate IDs_ — a real input ID ending in `_12_34` is silently reinterpreted as coordinates.
- _Encoding mismatch_ — `clean_id` already rewrote `|`→`_`, so a `sp|ACC|NAME` rule may never fire.

**Decision.** PRE _knows_ the truth at construction time. Record it; never guess it later.

**`PREPARE_BENCHMARK_FASTA` additionally emits `id_registry.tsv`:**

```
universe_id      parent_id   source_type   db_layer   family   coords   ungapped_len   seq_sha1
Q9X1J3/1-250     Q9X1J3      family        pfam       PF00069  1-250    250            <sha1>
sp_P12345_NAME   P12345      decoy         -         -        -        413            <sha1>
```

- `universe_id` — the **exact** header written into `combined_decoy.faa` (what tools are fed).
- `parent_id` — protein accession, computed by PRE from the source alignment, not by regex guessing.
- `source_type ∈ {family, decoy}` — authoritative; decoys are **never** inferred from ID shape.
- `ungapped_len` — true sequence length. `seq_sha1` alone cannot recover length, and ungapping a
  **trimmed** alignment (`.clipkit`) yields the wrong number.
- `seq_sha1` — sequence identity, used only for disambiguation and dedupe diagnostics. It is
  **not** an identity key: two distinct `universe_id`s may share a sequence.
- PRE also writes `universe.sha256` (checksum of `combined_decoy.faa`). Every POST run records it
  **in every per-run result table**, not just the report, so a samplesheet can never be silently
  scored against a different universe than it was built from.
- PRE **asserts** `{parent_id : family} ∩ {parent_id : decoy} = ∅` and fails loudly otherwise
  (DIAMOND caps hits at 25/query, so decoy leakage is possible and must not pass silently).

**Decoy headers are cleaned in PRE.** Today originals pass through `clean_id` (`.|=`→`_`) while
decoys keep raw SwissProt pipes — an asymmetry that breaks any tool sanitising `|`. Apply
`clean_id` to decoys too, so the universe is uniformly pipe-free (`sp_P12345_NAME`).

**The alias index is built forward, from registry rows.** For each registry row, PRE/POST generate
its alias set — the `clean_id` form, the bare accession from `sp|ACC|NAME`/`tr|ACC|NAME`, the
coordinate-stripped forms — and index `alias -> universe_id`. Resolution then looks the raw
observed ID up in that index. (Generating candidates _backward_ from the observed ID, as in the
previous revision, silently fails: `sp|P12345|NAME → P12345` is not a registry key, so **every
decoy would resolve to unmapped** and trip `max_unmapped_fraction`.) An alias colliding onto two
distinct `universe_id`s is recorded as ambiguous, never resolved arbitrarily.

**The comparison key is `universe_id`, not `parent_id`.**

This is the key correction. The tools are fed `combined_decoy.faa`; its headers _are_ the
`universe_id`s; original family membership is expressed in those same IDs. So set comparison at
`universe_id` level is exact and requires no collapsing. Collapsing to `parent_id` would merge
two _unrelated_ curated domains of the same protein — e.g. `Q9X1J3/1-250` in family F1 and
`Q9X1J3/300-400` in F2 both become `Q9X1J3`, so a generated family holding only the first gets
credit against F2. That is score inflation, and it is avoided entirely by keying on `universe_id`.

This satisfies the user's instruction ("Jaccard looks into the parent id, not the domain"): the
thing to resolve _to_ is the input sequence, and the input sequence is the `universe_id`. A tool's
own added sub-coordinates (`.../10-100`) collapse into it.

**Resolution of a raw observed ID → `universe_id`:**

1. Look the raw ID up in the alias index (which contains every `universe_id` as its own alias).
2. Also generate the coordinate-stripped candidate **lattice** (any combination of trailing
   `/\d+-\d+` and `_\d+_\d+`, unordered — not one linear strip order) and look each up.
3. Collect the set of distinct `universe_id`s hit:
   - exactly 1 → **resolved**.
   - 0 → **unmapped**.
   - > 1 → go to sequence disambiguation.

**Sequence disambiguation (settles Codex's exact-hit provenance objection).** A registry hit proves
a string _exists_; it does not prove the tool derived it from _that_ row. The pathological case is a
universe containing both `X` and `X_1_2`, where a tool fed `X` emits `X_1_2`. Flagging every
coordinate-looking exact hit as ambiguous (Codex's proposed fix) would over-trigger on legitimate
inputs. Instead use evidence we already hold — the MSA carries the **sequence**:

1. Hash the observed ungapped sequence; if it equals exactly one candidate's `seq_sha1` → resolved.
2. Else if it is a substring of exactly one candidate's sequence (aligners trim/clip) → resolved.
3. Else → **ambiguous**.

Step 2 needs the actual residues, which `seq_sha1`/`ungapped_len` cannot supply. `load_registry()`
therefore also takes `pre_universe_fasta` and builds a `universe_id -> sequence` index; `resolve()`
accepts an optional `seq` argument. **Sequence disambiguation is only available where the observed
sequence exists** — i.e. MSA-derived IDs. IDs read from `clustering_tsv` carry no sequence, so a

> 1-candidate case there stays `ambiguous`; that is acceptable because it affects `cluster_count` QC
> only, and it is reported in `ambiguous.tsv` like any other.

**Observability (this is the whole point — the failure mode is silence):**

- `unmapped_fraction`, `ambiguous_fraction`, per-family counts.
- Emit **full `unmapped.tsv` and `ambiguous.tsv` per run** (raw ID, candidates, reason) — not just
  capped examples. Debugging an ID-drift failure needs every offending ID.
- **Fail the run** above `params.max_unmapped_fraction` (default `0.05`) or
  `params.max_ambiguous_fraction` (default `0.01`); warn below.
- Report `n_fragments` per `universe_id` (distinct raw IDs collapsing into it),
  `mean_fragments`, `median_fragments` — the domain-shredding signal, preserved not discarded.
- Coverage is reported at both `universe_id` (domain) and `parent_id` (protein) granularity.
  **`parent_id` coverage is auxiliary QC only — it never enters the scorecard or the ranking.**
  Recovering one domain must not mark a protein's other domains as covered.

### D2 — `hmm_dir` column is dropped

Nothing consumed it. An `hmmsearch`-vs-`combined_decoy.faa` retrieval benchmark
(precision/recall/F1/decoy-FPR per model) was proposed and **rejected by the user** as scope.
Keep the samplesheet schema additive so it can return without a breaking change.

### D3 — `generated_fasta_dir` column is dropped; `msa_dir` is the membership source

Its only consumer, `investigate_matched_originals.py`, used it for a set of sequence IDs
(`load_use_case_data`, line 69) and an `avg_len` that only ever reaches a log line (line 143),
never the output CSV. It is **also already broken**: line 72 hard-filters on `.fasta.gz` while
proteinfamilies emits `.faa` and mgnifams `.fas.gz` — today it loads zero files, so every original
family is tagged `vanished`.

**Known limitation, must be documented prominently.** A _seed_ MSA is not full family membership.
Pointing `msa_dir` at `seed_msa/` measures something different from `full_msa/`. Mitigations:

- Every report states **`membership_source = MSA`** prominently. This benchmark measures
  MSA-based membership; that is a property of the method, not a hidden assumption.
- README + schema description + all example samplesheets and test fixtures point at the
  **full-family** MSA directory (`full_msa/`, not `seed_msa/`).
- POST emits `n_members_total` and `universe_coverage` per run. Low coverage is **warned**, not
  failed — a conservative tool legitimately recruits little, and a hard gate would fail good runs.
  `params.min_universe_coverage` (default `null` = off) lets a user opt into a hard gate.
- **When `clustering_tsv` is present, cross-check it:** compare resolved MSA members against
  resolved cluster members and warn on a large missing fraction. This is a far better signal for
  "you pointed at a seed MSA" than a coverage threshold, because it is relative to the tool's own
  clustering rather than to an absolute cutoff.
- Sequence **lengths** are recovered from the registry's `ungapped_len`, _not_ by ungapping the
  alignment — trimming/clipping (e.g. `.clipkit`) makes ungapped MSA length a wrong proxy.

_(Codex proposed reinstating a separate `membership_dir`, and later a hard `universe_coverage`
gate. Both rejected: the user explicitly dropped this column, a hard gate false-fails conservative
tools, and the clustering cross-check above catches the real misconfiguration.)_

### D4 — Samplesheet is `sample,tool,msa_dir,clustering_tsv`

- `sample` — unique run id, primary key. `tool` — label for grouping in plots.
- `msa_dir` — **required**, sole membership source; both reference tools always emit it.
- `clustering_tsv` — **optional**, 2-column rep→member TSV; drives `cluster_count` only.
  Modelled as an optional _file_ input (staged, `[]` sentinel when absent) — **not** a bare `val`,
  which would not be staged into a container.

Correcting the round-0 premise: **both** reference tools emit a clustering TSV
(`mgnifams` → `setup_clusters/mmseqs/mgnifams_v2.tsv`;
`proteinfamilies` → `mmseqs/initial_clustering/mmseqs_createtsv/*.tsv`).
mgnifams emits **no** per-family FASTA dir, which is why `msa_dir` is the required column.

### D5 — Jaccard alone cannot separate splitting from merging

Jaccard is symmetric and one-to-one; it cannot distinguish a tool that splits one true family
into five from one that merges five into one — exactly what a parameter sweep produces. User
selected all four additions: per-family P/R/F1, split/merge analysis, headline scorecard with
cross-run ranking, MultiQC.

**Two distinct thresholds, named to prevent one word meaning two things:**

- `match_threshold` (default `0.5`) — a reported family match. Was `jaccard_similarity_threshold`.
- `association_threshold` (default `0.1`) — an edge considered for split/merge topology.

**The round-0 justification for this was wrong and is withdrawn.** It claimed a family "cannot
have two matches at ≥0.5 by definition". Counterexample (Codex's): `O={1,2}`, `G1={1}`, `G2={2}`
→ `J = 0.5` each: two split edges at the threshold. Generated families also need not be disjoint.

**Replacement definition — directional, not symmetric.** Splits/merges are derived from
directional coverage, which is what the concepts actually mean:

- `recall(G,O) = |G∩O| / |O|`, `precision(G,O) = |G∩O| / |G|`
- an edge `(G,O)` is an **association** iff it clears `association_threshold` **and**
  `|G∩O| ≥ params.min_intersection_size` (default `3`). Without the size floor, a 10% overlap of
  two sequences registers as a merge.
- **split**: one `O` associated with ≥2 generated `G` via `precision(G,O)`, **and each counted `G`
  must add ≥1 member of `O` beyond the union of all the other associated `G`s**. Stating it against
  the union — not pairwise, and not "the ones before it" — makes the rule **order-independent**;
  a greedy left-to-right test would give different counts for different file orderings. Otherwise
  two near-duplicate generated families covering the same slice of `O` are miscounted as a split.
- **merge**: one `G` associated with ≥2 originals `O` via `recall(G,O)`, with the same
  union-based, order-independent unique-contribution requirement.
- `n_one_to_one`, `n_vanished` (no edge), `n_spurious` (G matching no O)
- Each output table names its denominator explicitly in the column header
  (`precision_denom=|G|`, `recall_denom=|O|`).

**Split/merge is computed within a `db_layer`.** Curated families overlap _across_ databases (the
same protein region appears in a Pfam and a PANTHER family), so a generated family matching one
Pfam and one PANTHER original is database redundancy, **not** a merge. Cross-layer edges are
reported separately as `n_cross_db_matches`.

**Curated families also overlap _within_ a database.** Compute an original-family overlap baseline
(pairwise Jaccard among originals in the same `db_layer`) and flag highly-overlapping original
pairs, so a merge attributable to curation redundancy is distinguishable from one caused by the
tool. Report `n_merges_excl_overlapping_originals` alongside the raw count.

### D6 — Alignment format auto-detection

Observed, not guessed: `.clipkit` (FASTA-formatted), `.aln`, `.fas.gz`, `.sto`, `.sto.gz`, `.faa`,
`.fasta`, `.afa`. Detect Stockholm vs FASTA by **sniffing the first non-blank line**
(`# STOCKHOLM` vs `>`), never by extension — `.clipkit` says nothing about format. Fall back to
extension only when sniffing is inconclusive.

### D7 — Comparability comes from the shared universe, not from seeding

Two stochastic sites exist, neither seeded: `random.sample()` in `identify_uniprot_decoys.py:62`
and pandas `available.sample(n=1)` in `sample_interpro.py:101` (so the _sampled families_ differ
between PRE runs, not just the decoys).

**This is by design, per the user: PRE runs once, and a fresh random family pool is the point of
the sampling design.** Cross-run comparability is therefore _not_ achieved by seeding — it is
achieved by every benchmarked tool run scoring against the **same** `combined_decoy.faa`, which
`universe.sha256` (D1) already enforces mechanically. Two POST rows built from different PRE
universes will fail the checksum check rather than be silently compared.

Add `params.seed` (default **`null`** = nondeterministic). When set, thread it into both sites
(`random.seed(seed)`, `.sample(random_state=seed)`) and record it in the registry header, so a
specific PRE run can be reproduced on demand. Do **not** default it to a fixed value.

---

## Approach

### Phase 1 — Identity core + fixtures (everything depends on this)

- [ ] `bin/benchmark_ids.py` — importable helper (not a CLI):
  - `load_registry(tsv) -> Registry` — `universe_id -> row`, plus the **forward alias index**
    (`alias -> universe_id`, built from registry rows) and a `parent_id` index.
  - `resolve(raw_id, registry, seq=None) -> Resolution(universe_id | None, status ∈ {resolved,unmapped,ambiguous})`
    — alias lookup + candidate **lattice** (no linear strip order); on >1 candidate, sequence
    disambiguation via `seq_sha1` then substring containment, per D1.
  - `canonicalise(raw_ids, registry) -> (members: set[universe_id], frags: dict, unmapped: list, ambiguous: list)`
  - `demo()`/`__main__` self-check asserting every worked example in D1 **and** each pathological
    case the review surfaced: false attribution (`X` vs `X_1_2` both in universe, settled by
    sequence), order sensitivity on mixed suffixes, a legitimate ID ending in `_n_n`, an
    alias collision onto two `universe_id`s, and **a decoy resolving via the forward alias index**
    (the bug that would otherwise mark every decoy unmapped).
- [ ] **Import mechanism (container-safe, deterministic).** Nextflow puts `bin/` on `PATH`, not on
      `PYTHONPATH`, and `env.PYTHONPATH="${projectDir}/bin"` is a _host_ path that is not reliably
      mounted under Docker/Singularity. Therefore: each consuming module declares a staged input
      `path(benchmark_ids)` fed from `file("${projectDir}/bin/benchmark_ids.py")`, and its script block
      prefixes `export PYTHONPATH="$PWD:$PYTHONPATH"`. Apply uniformly; do not rely on `sys.path[0]`.
- [ ] `tests/fixtures/universe/` — a tiny **synthetic** universe + registry + two fake tool output
      dirs (one clean, one with mangled/ambiguous IDs). Built by hand, committed. This unblocks all
      downstream work without running PRE or any external pipeline.
- [ ] Params: `max_unmapped_fraction=0.05`, `max_ambiguous_fraction=0.01`,
      `min_intersection_size=3`, `min_universe_coverage=null`, `seed=null`.

### Phase 2 — PRE emits the registry (must precede POST consumers)

- [ ] `PREPARE_BENCHMARK_FASTA` (merges `CONVERT_SAMPLED_TO_FASTA` + `COMBINE_DB_FASTA`) emits
      `sampled_fasta/`, `combined_db.faa`, `updated_sampled_metadata.csv`, **`id_registry.tsv`**,
      **`universe.sha256`**.
- [ ] `COMBINE_DECOY_FASTA` appends decoy rows to the registry with `source_type=decoy`, then
      recomputes `universe.sha256` over the final `combined_decoy.faa`.
- [ ] Assert family-parent ∩ decoy-parent = ∅; fail loudly.
- [ ] Fix the latent dedupe bug in `convert_sampled_to_fasta.py`: `seen_ids` keys on the **raw**
      `record.id` while the **cleaned** id is written, so `A.B` and `A|B` both emit `A_B` →
      duplicate universe IDs. Key the dedupe on `cleaned_id`.
- [ ] Seed all stochastic sampling (D7).
- [ ] `.faa` extension for PRE amino-acid outputs.

### Phase 3 — POST samplesheet infrastructure

- [ ] `assets/schema_post_samplesheet.json` (nf-schema), columns per D4.
- [ ] `subworkflows/local/validate_post_samplesheet/main.nf` → `tuple(val(meta), path(msa_dir), path(clustering_tsv))`,
      `meta = [id:, tool:]`; optional file → `[]`.
- [ ] `nextflow.config`: drop `path_to_alignments`, `path_to_mmseqs_tsv`, `path_to_generated_fasta`;
      add `post_samplesheet`, `pre_id_registry`, `pre_universe_fasta`; rename to `pre_db_fasta`,
      `pre_decoy_fasta`, `pre_sampled_metadata`, `pre_sampled_fasta_dir`; replace `'null'`
      **string** defaults with real `null`; rename `jaccard_similarity_threshold` → `match_threshold`.
- [ ] `main.nf` / `workflows/post.nf`: samplesheet-driven, `meta` threaded through every module so
      `publishDir` keys on `${meta.id}`. Every POST module takes the registry as a staged input.
- [ ] POST verifies `pre_universe_fasta`'s sha256 against `universe.sha256` and records it in the report.

### Phase 4 — Dynamic DB-layer detection

Replace hardcoded `db_layers = ["pfam","panther","ncbifam","hamap"]` in
`calculate_jaccard_similarity.py` (line 74), `calculate_db_family_coverage.py`,
`calculate_db_sequence_coverage.py`, `produce_db_stacked_barplot.py` (colours via `matplotlib.cm.tab10`).
Derive layers from `sampled_fasta_dir` subdirs / the metadata `db` column.
**Build exact family→file mappings from the metadata CSV — never prefix matching** (`PF1` would
match `PF10`).

### Phase 5 — Alignment format auto-detection (D6)

- [ ] `calculate_sequence_stats.py`: `--alignment_type auto`, per-file sniffing, mixed formats,
      generic `alignment_` output prefix.
- [ ] One shared extension/basename helper used by `calculate_jaccard_similarity.py`,
      `analyze_recruited_decoys.py`, `investigate_matched_originals.py`.

### Phase 6 — Optional `clustering_tsv`

- [ ] `investigate_matched_originals.py`: drop `--generated_fasta` (D3); `--cluster_file` optional
      (`cluster_count=0` when absent); membership + lengths from `msa_dir` + registry.
      Canonicalise **both** sides of the cluster lookup — the TSV carries the tool's ID format.
- [ ] When present, cross-check resolved MSA members against resolved cluster members; warn on a
      large missing fraction (the seed-MSA detector from D3).
- [ ] Gate via `ext.when` in `conf/modules.config`, not an `if` in the workflow.
- [ ] nf-test must cover **both** the absent and present `clustering_tsv` cases under a container
      profile — optional-file staging is exactly where `val`-vs-`path` bugs hide.

### Phase 7 — New metrics (D5)

- [ ] `bin/calculate_family_metrics.py` — per matched (G,O) pair: `tp, fp, fn, precision, recall,
f1, jaccard` on `universe_id` sets.
- [ ] `bin/analyze_splits_merges.py` — directional definitions, within-`db_layer`,
      `association_threshold`; emits `n_splits, n_merges, n_one_to_one, n_vanished, n_spurious,
n_cross_db_matches`.
- [ ] `bin/compute_scorecard.py` — one normalised composite per run + ranked cross-run table.
      Components, **all keyed on `universe_id`**: mean F1 over matched originals; family coverage;
      sequence coverage; `1 − decoy_recruitment_rate`; `1 − split_merge_rate`.
      **`parent_id` coverage is published as auxiliary QC and is NOT a scorecard component** —
      including it would reintroduce the coverage inflation that keying on `universe_id` removes.
      Every denominator defined explicitly in the docstring and the output header. Weights via
      `params.scorecard_weights` (default equal); all raw components published beside the composite.
      The composite and its ranking are labelled **EXPLORATORY** in the output header and README
      until the weights and `association_threshold` are validated against real runs (see Risks).
- [ ] `modules/local/compare_benchmark_runs/` + `bin/compare_benchmark_runs.py` — cross-tool CSV,
      per-tool Jaccard/F1 violin plots, tool-grouped stacked barplot. Runs for `n >= 1` rows.
- [ ] MultiQC (`modules/nf-core/multiqc`, `assets/multiqc_config.yml`); emit `*_mqc.csv` / `*_mqc.png`.
- [ ] Decoys classified via registry `source_type`, **never** by ID shape or parent identity.

### Phase 8 — Performance

- [ ] `calculate_jaccard_similarity.py` — **critical**: currently O(U × O), re-parsing every
      original FASTA inside the inner loop (line 109). Pre-parse originals once; build an inverted
      index `universe_id -> {(db_layer, family)}`; score only candidates. `multiprocessing.Pool`,
      `--num_workers` (default `os.cpu_count()`). Label → `process_medium`.
- [ ] `investigate_matched_originals.py` — same inverted-index treatment for the triple-nested loop.
- [ ] `calculate_sequence_stats.py` — `ProcessPoolExecutor`. Label → `process_low`.
- [ ] `combine_decoy_fasta.py` — `seq in unique_sequences.values()` is a linear scan inside a
      per-record loop → **O(n²)** over ~10⁵ sequences. Invert to a `seq -> name` dict.
- [ ] `sample_interpro.py` — pre-compute ancestry/descendant/sibling caches at tree build.
- [ ] `conf/base.config` — update labels.

### Phase 9 — PRE cleanup

- [ ] Merge the 4 `EXTRACT_*_METADATA` modules into `EXTRACT_DB_METADATA` (`--db_type`).
      **Preserve NCBIFAM's dual `TIGRxxxxx`/`NFxxxxxx` formats and differing alignment layouts —
      the one place a naive merge regresses.**
- [ ] `filter_valid_candidate_families.py` accepts a collected, variable-length metadata list.
- [ ] Delete superseded modules and scripts.

### Phase 10 — Reference database acquisition

- [ ] All 7 DB path params default `null`; if `null`, a download module supplies the path.
- [ ] `modules/local/download_{interpro,hamap,ncbifam,panther,pfam,swissprot}/`.
- [ ] **`storeDir "${params.db_cache_dir}/<db>/<version>"`** (not `publishDir`) so Nextflow owns the
      cache-hit check — no manual `file.exists()` logic. `db_cache_dir` must not live inside
      `work/` or `outdir/`; document that.
- [ ] New `process_download` label (1 cpu, 1 GB, 12 h, `errorStrategy 'retry'`, `maxRetries 3`).
- [ ] Version params `interpro_release`, `pfam_version`, `panther_version`. PANTHER is tens of GB —
      log a size warning.

### Phase 11 — nf-core conformance

- [ ] `nextflow_schema.json` + `nf-schema`; `validateParameters()` in `main.nf`.
- [ ] `stub:` block in every local module (none today). `tag` on every local process (none today).
- [ ] `subworkflows/local/{pipeline_initialisation,pipeline_completion}`.
- [ ] Aggregate `versions.yml` → `pipeline_info/software_versions.yml`.
- [ ] Pin containers; replace bare `biocontainers/pandas:1.4.3` in `SAMPLE_INTERPRO`.
      **Align DIAMOND: `makedb` is 2.1.8, `blastp` is 2.1.11.**
- [ ] `manifest` description; `tower.yml`; `seqera` profile.

### Phase 12 — Verification

**CI-reproducible tier (no external pipelines, no network):**

- [ ] `benchmark_ids.py` self-check: the D1 worked examples + false attribution + order sensitivity + legitimate `_n_n` + ambiguous-hit cases.
- [ ] nf-test module tests: `sample_interpro`, `calculate_jaccard_similarity`, `extract_db_metadata`,
      `prepare_benchmark_fasta` (registry shape + checksum).
- [ ] `-stub` workflow tests for PRE and POST using `tests/fixtures/`.
- [ ] **Canonicalisation regression:** the mangled-ID fixture must yield non-zero Jaccard and
      `unmapped_fraction ≈ 0`. This test must _fail_ against the current `split("/")[0]` code —
      it is the specific bug D1 exists to prevent.
- [ ] Determinism: two PRE runs at the same `seed` produce byte-identical `combined_decoy.faa`.

**Manual tier (documented, not CI):**

- [ ] PRE end-to-end; run both reference pipelines per `CLAUDE.md`; 1-row POST (proteinfamilies);
      1-row POST (mgnifams, empty `clustering_tsv`); 2-row POST → ranked scorecard.
- [ ] Benchmark `calculate_jaccard_similarity.py` before/after on real data.

---

## Risks / open questions

1. **A tool that fully renames sequences** (hash IDs, integer reindexing) cannot be resolved
   against the registry; `unmapped_fraction` → 1.0 and the run **fails loudly**. That is the
   intent, but such tools need a per-tool mapping file. Accepted limitation.
2. **The composite score and its ranking ship as EXPLORATORY.** Equal weights are
   arbitrary-but-defensible; all components are published so users can re-weight. The headline
   ranking must not be presented as settled until weights are validated on real runs. Needs user
   sign-off before publication.
3. **`association_threshold` (0.1) vs `match_threshold` (0.5)** — two thresholds in one report.
   The default 0.1 is a _heuristic_, not derived; it must be tuned once on real data and a
   threshold-sensitivity sweep reported, otherwise split/merge counts are arbitrary. The
   `min_intersection_size=3` floor blunts the worst of it but does not remove the arbitrariness.
4. **Seed vs full MSA** (D3) is a user-configuration hazard mitigated by warnings, not prevented.
5. PANTHER download is tens of GB; Phase 10 is untestable end-to-end on a laptop.

## Out of scope

- Running the external family-generation pipelines from inside this pipeline.
- HMM retrieval benchmarking (`hmmsearch` vs `combined_decoy.faa`) — deferred by user (D2).
- Domain-level re-projection of InterPro originals.
- Structural / functional-annotation metrics.
