include { VALIDATE_POST_SAMPLESHEET } from '../subworkflows/local/validate_post_samplesheet/main'
include { SCORE_SAMPLES             } from '../subworkflows/local/score_samples/main'
include { REPORT_BENCHMARK          } from '../subworkflows/local/report_benchmark/main'

//
// POST scores tool runs against the universe PRE built, and ranks them.
//
// It is deliberately tool-agnostic: no hardcoded database layers, file extensions or protein-ID
// formats, and no assumption that a tool emits anything beyond one MSA per family. Identity comes
// from the PRE registry, never from the shape of the IDs a tool happened to write.
//
workflow POST {

    take:
    post_samplesheet
    pre_id_registry
    pre_universe_fasta
    pre_universe_sha256
    pre_sampled_metadata
    pre_sampled_fasta_dir
    match_threshold
    association_threshold
    max_unmapped_fraction
    max_ambiguous_fraction
    min_intersection_size
    min_universe_coverage
    scorecard_weights
    skip_multiqc

    main:
    VALIDATE_POST_SAMPLESHEET( post_samplesheet )

    // The PRE outputs are read once and shared by every downstream module. They are value
    // channels so each one is re-emitted for every sample instead of being consumed by the first.
    ch_registry      = channel.value(file(pre_id_registry, checkIfExists: true))
    ch_universe      = channel.value(file(pre_universe_fasta, checkIfExists: true))
    ch_universe_sha  = channel.value(file(pre_universe_sha256, checkIfExists: true))
    ch_metadata      = channel.value(file(pre_sampled_metadata, checkIfExists: true))
    ch_sampled_fasta = channel.value(file(pre_sampled_fasta_dir, checkIfExists: true))

    // Nextflow puts bin/ on PATH, not PYTHONPATH, so the two shared libraries are staged as
    // ordinary path inputs and re-exported onto PYTHONPATH inside each module's script block.
    ch_benchmark_ids = channel.value(file("${projectDir}/bin/benchmark_ids.py", checkIfExists: true))
    ch_post_common   = channel.value(file("${projectDir}/bin/post_common.py", checkIfExists: true))

    ch_multiqc_config  = channel.value(file("${projectDir}/assets/multiqc_config.yml", checkIfExists: true))
    ch_comparison_meta = channel.value([id: 'comparison', tool: 'comparison'])

    // These two are optional. An unset param must reach the script block as an empty string,
    // because the modules test it for truthiness to decide whether to pass the CLI flag at all.
    min_universe_coverage_cli = min_universe_coverage == null ? '' : min_universe_coverage
    scorecard_weights_cli     = scorecard_weights == null ? '' : scorecard_weights.toString()

    //
    // Score every run in the samplesheet against the curated originals.
    //
    SCORE_SAMPLES(
        VALIDATE_POST_SAMPLESHEET.out.samples,
        ch_registry,
        ch_universe,
        ch_universe_sha,
        ch_metadata,
        ch_sampled_fasta,
        ch_benchmark_ids,
        ch_post_common,
        match_threshold,
        association_threshold,
        max_unmapped_fraction,
        max_ambiguous_fraction,
        min_intersection_size,
        min_universe_coverage_cli,
        scorecard_weights_cli
    )

    //
    // Rank the runs against each other and render the report.
    //
    REPORT_BENCHMARK(
        SCORE_SAMPLES.out.edgelist,
        SCORE_SAMPLES.out.scorecard,
        SCORE_SAMPLES.out.metrics,
        SCORE_SAMPLES.out.summary,
        SCORE_SAMPLES.out.coverage,
        SCORE_SAMPLES.out.mqc,
        ch_metadata,
        ch_sampled_fasta,
        ch_universe,
        ch_universe_sha,
        ch_benchmark_ids,
        ch_post_common,
        ch_multiqc_config,
        ch_comparison_meta,
        skip_multiqc
    )

    emit:
    comparison = REPORT_BENCHMARK.out.comparison
    scorecard  = SCORE_SAMPLES.out.scorecard
}
