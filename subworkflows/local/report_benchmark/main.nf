include { PRODUCE_DB_STACKED_BARPLOT   } from '../../../modules/local/produce_db_stacked_barplot/main'
include { CALCULATE_DB_FAMILY_COVERAGE } from '../../../modules/local/calculate_db_family_coverage/main'
include { GET_SIZE_DISTRIBUTIONS       } from '../../../modules/local/get_size_distributions/main'
include { COMPARE_BENCHMARK_RUNS       } from '../../../modules/local/compare_benchmark_runs/main'
include { MULTIQC                      } from '../../../modules/nf-core/multiqc/main'

//
// Turn per-sample scores into the report: what each run covered, then how the runs rank against
// one another. The barplot / coverage / size-distribution modules are still per-sample (they all
// read the Jaccard edgelist); COMPARE_BENCHMARK_RUNS is the only step that sees every run at once.
//
workflow REPORT_BENCHMARK {

    take:
    edgelist         // per-sample Jaccard edgelist
    scorecard        // per-sample scorecard
    metrics          // per-sample family metrics
    summary          // per-sample split/merge summary
    coverage         // per-sample db-layer sequence coverage
    score_mqc        // MultiQC files produced during scoring
    metadata         // PRE sampled_metadata.csv
    sampled_fasta    // PRE sampled_fasta/
    universe         // PRE combined_decoy.faa
    universe_sha256  // PRE universe.sha256
    benchmark_ids    // bin/benchmark_ids.py, staged as a library
    post_common      // bin/post_common.py, staged as a library
    multiqc_config
    comparison_meta
    skip_multiqc

    main:
    PRODUCE_DB_STACKED_BARPLOT( edgelist )

    CALCULATE_DB_FAMILY_COVERAGE(
        edgelist,
        sampled_fasta,
        metadata,
        universe,
        universe_sha256,
        benchmark_ids,
        post_common
    )

    GET_SIZE_DISTRIBUTIONS(
        edgelist,
        metadata,
        universe,
        universe_sha256,
        benchmark_ids,
        post_common
    )

    // `.collect()` is what makes this cross-run: every sample's table arrives as one input, so
    // the ranking sees all runs together.
    COMPARE_BENCHMARK_RUNS(
        comparison_meta,
        scorecard.map { _meta, file -> file }.collect(),
        metrics.map   { _meta, file -> file }.collect(),
        summary.map   { _meta, file -> file }.collect(),
        coverage.map  { _meta, file -> file }.collect(),
        benchmark_ids,
        post_common
    )

    if (!skip_multiqc) {
        ch_mqc_files = score_mqc
            .mix(
                COMPARE_BENCHMARK_RUNS.out.mqc_csv,
                COMPARE_BENCHMARK_RUNS.out.mqc_f1_plot,
                COMPARE_BENCHMARK_RUNS.out.mqc_db_plot
            )
            .map { _meta, mqc_file -> mqc_file }
            .collect()

        MULTIQC(
            comparison_meta,
            ch_mqc_files,
            multiqc_config
        )
    }

    emit:
    comparison     = COMPARE_BENCHMARK_RUNS.out.comparison
    family_coverage = CALCULATE_DB_FAMILY_COVERAGE.out.coverage
    barplot        = PRODUCE_DB_STACKED_BARPLOT.out.barplot
}
