# Plan Review Log: benchmark-proteinfamilies overhaul

Act 1 (grill) complete — plan locked with the user. MAX_ROUNDS=5.

## Act 1 — decisions settled

| #   | Decision                     | Resolution                                                                                                                            |
| --- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| D1  | Protein-ID canonicalisation  | Two-level, universe-anchored. Jaccard on `parent_id`; fragmentation + `unmapped_fraction` recorded. **User-confirmed.**               |
| D2  | `hmm_dir` samplesheet column | Dropped. **User-confirmed.**                                                                                                          |
| D3  | `generated_fasta_dir` column | Dropped — redundant with `msa_dir`, and already silently broken (`.fasta.gz` filter vs `.faa`/`.fas.gz` reality). **User-confirmed.** |
| D4  | Samplesheet schema           | `sample,tool,msa_dir,clustering_tsv`. `msa_dir` required, `clustering_tsv` optional.                                                  |
| D5  | Metrics to add               | P/R/F1 per matched family, split/merge analysis, headline scorecard + ranking, MultiQC. **User-confirmed (all four).**                |
| D6  | Alignment format detection   | Sniff first non-blank line; cover `.clipkit/.aln/.fas.gz/.sto/.sto.gz/.faa/.fasta/.afa`.                                              |

Facts established by inspecting real outputs (not assumed):

- mgnifams **does** emit a clustering TSV — the old plan's Phase 3 premise was wrong.
- mgnifams emits no per-family FASTA dir; proteinfamilies does.
- Headers nest two coordinate systems: `2632373804_177_299/1-122`.
- `investigate_matched_originals.py` currently loads zero generated FASTAs (extension mismatch),
  so every original family is tagged `vanished`.

## Round 1 — Codex (gpt-5.5, xhigh→high, read-only)

````
- D1 false attribution: first-hit stripping can resolve `X_1_2/3-4` to universe `X_1_2` even if the true input was `X`; fix: generate all candidate stripped IDs and fail on multiple universe hits unless a PRE registry disambiguates.
- D1 prefix collision: a tool-added coordinate suffix can equal another legitimate universe ID, so “universe anchored” is not enough; fix: store `universe_id -> parent_id/source_type/coords/sequence_hash` during PRE and resolve against that registry.
- D1 order sensitivity: stripping `/\d+-\d+$` before `_\d+_\d+$` changes outcomes for mixed suffixes; fix: canonicalise via an unordered candidate lattice, not one linear strip order.
- D1 exact-hit ambiguity: raw `1446399400_1_131` being a universe hit does not prove it is the true source if tools also append `_1_131`; fix: treat exact coordinate-looking hits as ambiguous when their stripped parent also exists.
- D1 parent collapse: stripping all coordinate suffixes merges distinct domains from the same protein across unrelated curated families; fix: compute family similarity on `universe_id`/domain IDs and publish protein-level `parent_id` metrics separately.
- D1 legitimate IDs: any real input ID ending in `_number_number` or `/number-number` is silently reinterpreted as a coordinate-bearing ID; fix: only strip suffixes known from the PRE ID registry or from observed tool-added forms.
- D1 UniProt rule mismatch: PRE `clean_id()` replaces `|` with `_`, so `sp|ACC|NAME -> ACC` may not match actual universe headers; fix: support both raw and cleaned UniProt encodings with regression tests.
- D1 observability gap: `unmapped_fraction` catches missing IDs but not wrong or ambiguous mappings; fix: add `ambiguous_fraction`, per-family unmapped/ambiguous counts, and example raw IDs in QC output.
- D1 checksum gap: POST does not prove the samplesheet outputs came from the same `combined_decoy.faa` used as the universe; fix: require and report the universe FASTA checksum for each POST run.
- `bin/` import fix: staging `benchmark_ids.py` into each task workdir is the robust option; `env.PYTHONPATH="${projectDir}/bin"` may pass into Docker/Singularity but the host path is not reliably mounted/portable; fix: pass the helper as a staged `path` input or package it.
- `path('benchmark_ids.py')` is underspecified Nextflow syntax/design; fix: create a channel/value from `file("${projectDir}/bin/benchmark_ids.py")` and stage it with `name: 'benchmark_ids.py'`.
- Phase 6 split/merge claim is false: at threshold `>=0.5`, `O={1,2}`, `G1={1}`, `G2={2}` gives two split edges, and overlapping generated families can both exceed 0.5; fix: justify `0.1` empirically or define splits/merges from best-hit coverage rules.
- Phase 6 terminology conflict: using `0.1` for split/merge and `0.5` for reported matches means “match” has two meanings in one report; fix: name them separately, e.g. `association_threshold` vs `match_threshold`.
- Dropping `generated_fasta_dir` loses information when MSAs are seed-only rather than full-family alignments; fix: separate `membership_dir` from `alignment_dir`, allowing the same path only when valid.
- Dropping `generated_fasta_dir` loses sequences filtered out before alignment; fix: benchmark membership from the earliest generated family membership artifact, with MSA-only as an explicit degraded mode.
- Ungapped length recovery from MSA is not equivalent to full sequence length after trimming/clipping; fix: recover sequence lengths from the universe FASTA by canonical ID.
- MSA membership can contain duplicate domain fragments that collapse to one parent; fix: keep raw/universe/domain counts alongside parent counts.
- Phase ordering is wrong: Phase 1 canonicalisation consumers depend on a universe/registry whose production is only made reproducible after PRE/download cleanup; fix: define the PRE registry and synthetic universe fixture before wiring POST consumers.
- Phase 11 is not CI-reproducible because it depends on running external reference pipelines; fix: add small committed/stub proteinfamilies and mgnifams fixtures before full external verification.
- Optional `clustering_tsv` as a plain value may not be staged into containers; fix: model optional files explicitly and stage them when present.
- `parent_id` breaks decoy recruitment semantics: decoys are full proteins while originals may be domains, so an original domain and a decoy full protein can share a parent; fix: classify decoys using PRE source labels/universe IDs and validate original/decoy parent sets are disjoint.
- `parent_id` inflates sequence coverage: recovering one domain/protein can mark multiple domain family members as covered; fix: report both domain-level coverage on `universe_id` and protein-level coverage on `parent_id`.
- Coverage path matching by family prefix risks collisions like `PF1` vs `PF10`; fix: build exact metadata-to-file mappings.
- Scorecard denominator is underspecified after parent/domain collapse, especially for decoy rate and sequence coverage; fix: define denominators explicitly for each granularity and publish both raw components.
- Simpler alternative ignored: regex canonicalisation is trying to reverse-engineer identity after the fact; fix: make PRE emit an ID registry and require all POST canonicalisation to go through it.

VERDICT: REVISE```

### Claude's response

**Accepted (plan rewritten):**
- **PRE ID registry** replaces regex canonicalisation. Codex is right that reverse-engineering
  identity after the fact is unsound; PRE knows the truth at construction time. This single change
  dissolves false attribution, prefix collision, order sensitivity, legitimate `_n_n` IDs, and the
  `clean_id` UniProt encoding mismatch.
- Candidate **lattice** (unordered) instead of a linear strip order; `ambiguous` is a first-class
  status, never resolved arbitrarily.
- `ambiguous_fraction` + per-family counts + example raw IDs; `max_ambiguous_fraction` param.
- `universe.sha256` provenance — POST verifies the samplesheet was scored against the universe it
  was built from.
- Decoys classified by registry `source_type`, never by ID shape/parent. PRE asserts
  family-parent ∩ decoy-parent = ∅ (DIAMOND caps hits at 25/query, so leakage is real).
- Dual-granularity coverage (`universe_id` and `parent_id`); no coverage inflation.
- `association_threshold` vs `match_threshold` renaming — one word no longer means two things.
- Exact metadata→file mapping, no prefix matching (`PF1` vs `PF10`).
- `clustering_tsv` as a staged optional *file*, not a bare `val`.
- Lengths recovered from the universe FASTA via `seq_sha1`, not by ungapping a trimmed alignment.
- Phase reorder: identity core + synthetic fixtures first; PRE registry before POST consumers.
- CI tier decoupled from external pipeline runs.
- `path(benchmark_ids)` staged input + `export PYTHONPATH="$PWD"`; `env.PYTHONPATH="${projectDir}/bin"`
  is a host path not reliably mounted in containers.

**Codex refuted my own claim — accepted.** Round-0 asserted a family "cannot have two matches at
J≥0.5 by definition". False: `O={1,2}`, `G1={1}`, `G2={2}` → J=0.5 each. Justification withdrawn.
Replaced with **directional** split/merge definitions (precision/recall based), computed
**within a `db_layer`** — because curated families overlap across databases, so a generated family
matching one Pfam and one PANTHER original is DB redundancy, not a merge. Codex did not catch that
second point.

**Improved on Codex's proposal.** Codex said: compute similarity on `universe_id`/domain IDs and
publish `parent_id` metrics separately. Going further — the comparison key is `universe_id`
*throughout*, and `parent_id` is only a reporting dimension. Reason: the tools are fed
`combined_decoy.faa`, whose headers *are* the `universe_id`s, and original membership is expressed
in the same IDs. So no collapse is needed at all, and Codex's own "parent collapse merges unrelated
domains across families" objection disappears rather than being mitigated. This still honours the
user's instruction, because the thing to resolve *to* is the input sequence = the `universe_id`.

**Rejected:**
- *Reinstate a separate `membership_dir`/`alignment_dir` column.* The user explicitly dropped
  `generated_fasta_dir`. The failure Codex guards against (seed-only MSA) is caught by the
  `universe_coverage` warning + schema docs. Rejecting keeps the samplesheet at 4 columns.
- *"Treat exact coordinate-looking hits as ambiguous when their stripped parent also exists."*
  Over-triggers: with the registry, an exact hit **is** authoritative by construction — that is the
  entire point of recording identity at build time. Flagging it would make legitimate inputs
  ambiguous.

**Added — Codex missed it (D7):** `bin/identify_uniprot_decoys.py` calls `random.sample()` with no
seed. Two PRE runs yield different decoy sets, so benchmark numbers are not comparable across runs.
Added `params.seed` (default 42), threaded into all stochastic scripts, recorded in the registry.

## Round 2 — Codex

````

- Prior parent-collapse objection: mostly addressed for Jaccard/P/R/F1 because scoring on `universe_id` preserves domain-level identity; fix: keep `parent_id` out of every composite score unless explicitly labelled protein-level.
- New contradiction: user says `parent_id` removed from scoring, but Phase 7 scorecard includes sequence coverage at both `universe_id` and `parent_id`; fix: publish parent coverage as auxiliary QC, not as a scorecard component.
- Decoy granularity: fixed in principle by registry `source_type` and family-parent/decoy-parent disjoint assertion; fix: ensure decoy recruitment uses `source_type` on resolved `universe_id`, never parent IDs.
- Coverage inflation: fixed for `universe_id` coverage, but reintroduced if parent-level coverage affects ranking; fix: rank on `universe_id` coverage only.
- Exact-hit rejection is still unsafe: a raw tool output can equal another valid universe ID while actually being a transformed form of a different input ID; registry proves the string exists, not provenance; fix: if exact hit is coordinate-looking and stripped candidates also hit distinct registry rows, mark ambiguous.
- Candidate alias bug: registry decoy `universe_id` is `sp|P12345|NAME`, but the `sp|ACC|NAME -> ACC` candidate will not hit a universe-id registry keyed by full SwissProt headers; fix: build an alias index mapping ACC and cleaned forms back to the single registry `universe_id`.
- Decoy cleaning asymmetry: PRE originals are cleaned but decoys keep pipes, so tools that sanitize `sp|P12345|NAME` to `sp_P12345_NAME` may become unmapped; fix: either clean decoy headers consistently in PRE or register cleaned aliases.
- `clean_id` variant direction is incomplete: applying `clean_id` to already-sanitized raw IDs cannot recover pipe-containing registry IDs; fix: aliases must be generated from registry rows, not only from observed raw IDs.
- `seq_sha1` alone cannot recover length; fix: add `ungapped_len` to `id_registry.tsv` or explicitly read `pre_universe_fasta` for lengths.
- `seq_sha1` is not sufficient to distinguish duplicate biological sequences with different universe IDs; fix: keep `universe_id` as the primary identity and use SHA only for length/dedupe diagnostics.
- `msa_dir`-only deviation remains a correctness risk: a warning detects suspicious low universe coverage but cannot prove MSAs are full-family membership; fix: label the benchmark as MSA-membership-based and make `universe_coverage` a hard QC gate configurable per run.
- Seed-MSA warning can false-pass when seed MSAs cover enough of the universe or false-warn for legitimately conservative tools; fix: report “membership source = MSA” prominently and require users to select full-family MSA paths in schema examples/tests.
- If `clustering_tsv` exists, the plan should use it to sanity-check MSA completeness; fix: compare resolved MSA members against resolved cluster members and warn/fail on large missing fractions.
- Directional split/merge is much sounder than the withdrawn Jaccard claim, but current split definition counts duplicate generated families covering the same slice of `O` as a split; fix: require each additional `G` to contribute unique `O` members or report union recall.
- Directional merge definition can count trivial 10% overlaps as merges at default `0.1`; fix: add minimum intersection size and threshold sensitivity reporting.
- `precision(G,O) >= association_threshold` for splits and `recall(G,O) >= association_threshold` for merges is conceptually defensible; fix: document the denominator choice directly in output headers.
- Within-`db_layer` restriction is sound for avoiding Pfam/PANTHER redundancy being called a merge; fix: also report cross-db overlaps separately, as planned.
- Within-db split/merge can still be distorted by overlapping curated families inside the same DB; fix: compute an original-family overlap baseline and flag/exclude highly overlapping original pairs.
- Phase ordering is now materially better: fixtures first, registry before POST consumers, external runs manual; fix: keep CI fixtures independent of PRE downloads.
- PYTHONPATH/container issue is addressed correctly by staging `benchmark_ids.py` and exporting `$PWD`; fix: apply it uniformly to every Python process that imports the helper.
- Optional `clustering_tsv` is improved by staging it as an optional file; fix: test both absent and present cases under Docker/Singularity.
- Checksum guard is addressed; fix: store checksum in every per-run result table, not only the report.
- Remaining observability gap: ambiguity examples are capped, but no mention of full rejected-ID artifact; fix: emit full `unmapped.tsv` and `ambiguous.tsv` per run for debugging.
- Scorecard remains scientifically fragile despite published components; fix: default ranking should be clearly marked exploratory until weights/thresholds are validated on real runs.

VERDICT: REVISE```

### Claude's response

Findings narrowed from structural to refinement — this is convergence, not deadlock.

**Accepted (two were sharp catches):**

- **Alias-index direction bug.** The registry is keyed on `universe_id` = `sp|P12345|NAME`; my
  backward candidate `sp|ACC|NAME → ACC` yields `P12345`, which is not a registry key. Every decoy
  would have resolved to _unmapped_ and tripped `max_unmapped_fraction`. Fixed: aliases are now
  generated **forward from registry rows** (`alias -> universe_id`).
- **Self-contradiction on the scoring key.** I declared `universe_id` the key "throughout" and then
  listed `parent_id` coverage as a scorecard component. `parent_id` coverage is now auxiliary QC
  only; ranking is `universe_id`-only.
- Decoy header cleaning asymmetry (originals cleaned, decoys keep pipes) → apply `clean_id` to decoys.
- `ungapped_len` column added; `seq_sha1` demoted to disambiguation/diagnostics, not an identity key.
- Split definition requires each additional `G` to contribute a **unique** member of `O`, else two
  near-duplicate generated families are miscounted as a split.
- `min_intersection_size=3` floor so a trivial 10% two-sequence overlap is not a merge.
- Original-family overlap baseline **within** a db_layer; `n_merges_excl_overlapping_originals`.
- Full `unmapped.tsv` / `ambiguous.tsv` artifacts, not capped examples.
- Universe checksum recorded in every per-run result table.
- `clustering_tsv`, when present, cross-checks MSA completeness — a better seed-MSA detector than
  an absolute coverage cutoff.
- Denominators named in output headers; scorecard labelled EXPLORATORY.
- nf-test covers `clustering_tsv` absent **and** present under a container profile.

**Contested → resolved with better evidence (exact-hit provenance, raised twice).** Codex is right
that a registry proves a string _exists_, not that the tool derived it from _that row_: a universe
containing both `X` and `X_1_2` lets a tool fed `X` emit `X_1_2`, which exact-hits the wrong row.
But its fix — flag any coordinate-looking exact hit whose stripped parent also exists as ambiguous
— over-triggers on legitimate inputs and would inflate `ambiguous_fraction` toward the fail gate.
Adopted instead: **sequence disambiguation**. The MSA carries the sequence; hash the observed
ungapped sequence against candidate `seq_sha1`, fall back to substring containment (aligners trim),
and declare `ambiguous` only when sequence evidence cannot settle it. Uses data already in hand and
resolves the case exactly rather than by over-flagging.

**Rejected:**

- _Hard `universe_coverage` gate._ A conservative tool legitimately recruits few sequences; a hard
  gate false-fails good runs. Kept as a warning, with `params.min_universe_coverage` (default
  `null`) for opt-in gating, and the clustering cross-check as the real detector.
- _Reinstating `membership_dir`_ (raised again). User dropped it; `membership_source = MSA` is now
  stated prominently in every report, which addresses the honesty concern without a schema change.

**Superseded by user input (D7).** Round-1 added `params.seed=42` to force reproducibility. The
user clarified that a fresh random family pool per PRE run **is the sampling design**. Comparability
across tool runs is guaranteed by all runs scoring against the same `combined_decoy.faa` — which
`universe.sha256` already enforces mechanically. `seed` is now optional, default `null`.
Note both stochastic sites: `random.sample()` at `identify_uniprot_decoys.py:62` **and** pandas
`.sample(n=1)` at `sample_interpro.py:101`.

## Round 3 — Codex

````
- Round-2 parent-collapse/coverage issue: addressed; scorecard is now explicitly `universe_id`-only and `parent_id` coverage is auxiliary QC.
- Round-2 decoy alias issue: addressed; decoy headers are cleaned consistently and aliases are built forward from registry rows.
- Round-2 exact-hit provenance: mostly addressed; sequence-based disambiguation is the right escape hatch and avoids over-triggering exact coordinate-looking IDs.
- Implementation guardrail: substring disambiguation requires access to actual universe sequences, not just `seq_sha1`/`ungapped_len`; fix: make `Registry` load `pre_universe_fasta` or pass a sequence index into `resolve()`.
- Sequence disambiguation limitation: it only works for MSA-derived IDs where observed sequence is available; cluster TSV IDs without sequences may remain ambiguous; acceptable if those ambiguities affect cluster QC only and are reported.
- `msa_dir`-only deviation: acceptable now because the report explicitly states `membership_source = MSA`, examples point to full MSAs, `min_universe_coverage` is optional, and `clustering_tsv` cross-check catches the best-detectable seed/full mismatch.
- Seed default `null`: sound for the stated design; comparability is between POST runs sharing one PRE universe, and `universe.sha256` enforces that. Fixed seeds remain available for reproducible PRE regeneration.
- Forward alias index: sound; it fixes the prior backward-candidate decoy failure and correctly treats alias collisions as ambiguous.
- Unique-contribution split rule: conceptually sound; implementation should define it order-independently, e.g. a family contributes only if it adds members beyond the union of the other associated families.
- `min_intersection_size`: sound as a guard against tiny accidental overlaps, especially with sampled families above the minimum membership threshold.
- Within-`db_layer` restriction: sound; cross-DB matches are reported separately, avoiding false merge calls from database redundancy.
- Within-db original-overlap baseline: sound; reporting raw merges plus `n_merges_excl_overlapping_originals` handles curation redundancy without hiding it.
- Remaining heuristic risks are documented under Risks and no longer look like silent wrong-result failures.

VERDICT: APPROVED```

### Claude's response

**VERDICT: APPROVED** after 3 rounds. Two implementation guardrails folded in before freezing:

1. **Substring disambiguation needs residues, not hashes.** `seq_sha1`/`ungapped_len` cannot support
   step 2 of sequence disambiguation. `load_registry()` now also takes `pre_universe_fasta` and
   builds a `universe_id -> sequence` index; `resolve()` accepts an optional `seq`. Documented that
   `clustering_tsv` IDs carry no sequence, so >1-candidate cases there remain `ambiguous` — which
   affects `cluster_count` QC only and is reported in `ambiguous.tsv`.
2. **Unique-contribution rule must be order-independent.** Restated against the **union** of the
   other associated families rather than pairwise or greedy-left-to-right, so split/merge counts do
   not depend on file iteration order.

## Act 2 outcome

Converged in 3 rounds. What the two acts changed, in order of impact:

1. **Identity is recorded, not inferred.** The plan entered Act 2 proposing regex canonicalisation
   against the input universe. Codex refuted it (false attribution, order sensitivity, legitimate
   `_n_n` IDs). PRE now emits an authoritative `id_registry.tsv` + `universe.sha256`. Following that
   through revealed that the correct scoring key is `universe_id`, not `parent_id` — which dissolves
   the score-inflation objection entirely rather than mitigating it.
2. **Two wrong claims were killed** — one mine, one a latent bug. Mine: "a family cannot have two
   matches at J≥0.5 by definition" (counterexample `O={1,2}, G1={1}, G2={2}`), which invalidated the
   split/merge design; replaced with directional, union-based, within-db_layer definitions. The bug:
   the backward alias direction would have marked **every decoy unmapped** and failed every run.
3. **The failure mode throughout is silence, so the plan now fails loudly.** `unmapped_fraction` /
   `ambiguous_fraction` gates, full `unmapped.tsv` / `ambiguous.tsv`, universe checksum in every
   per-run table, decoy/family parent-disjointness assertion in PRE, and a regression test that must
   fail against today's `split("/")[0]` code.

Codex was rejected on 4 points (membership_dir ×2, hard coverage gate, over-triggering exact-hit
ambiguity), each with a logged reason. Round 1's `params.seed=42` was later superseded by user input.
````
