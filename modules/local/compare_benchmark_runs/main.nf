process COMPARE_BENCHMARK_RUNS {
    tag "$meta.id"
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/3a/3af05bd5854cf509731bce100d59783262ba89546a2d980ff74e2b85ef23e965/data' :
        'community.wave.seqera.io/library/matplotlib_pandas_python:894947e54c3969d1' }"

    input:
    val meta
    path scorecards            , stageAs: 'scorecards/scorecard_??.tsv'
    path family_metrics        , stageAs: 'family_metrics/family_metrics_??.tsv'
    path split_merge_summaries , stageAs: 'split_merge/split_merge_summary_??.tsv'
    path db_coverage_files     , stageAs: 'db_coverage/sequence_coverage_??.txt'
    path benchmark_ids
    path post_common

    output:
    tuple val(meta), path("benchmark_comparison.csv")        , emit: comparison
    tuple val(meta), path("benchmark_comparison_mqc.csv")    , emit: mqc_csv
    tuple val(meta), path("f1_jaccard_distribution_mqc.png") , emit: mqc_f1_plot
    tuple val(meta), path("db_layer_coverage_mqc.png")       , emit: mqc_db_plot
    tuple val(meta), path("versions.yml")                    , emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    export PYTHONPATH="\$PWD:\${PYTHONPATH:-}"
    compare_benchmark_runs.py \\
        --scorecards scorecards/*.tsv \\
        --family_metrics family_metrics/*.tsv \\
        --split_merge_summaries split_merge/*.tsv \\
        --db_coverage_files db_coverage/*.txt \\
        --output_csv benchmark_comparison.csv \\
        --mqc_csv benchmark_comparison_mqc.csv \\
        --f1_jaccard_plot f1_jaccard_distribution_mqc.png \\
        --db_coverage_plot db_layer_coverage_mqc.png

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: \$(python --version 2>&1 | sed 's/Python //g')
        matplotlib: \$(python -c "import importlib.metadata; print(importlib.metadata.version('matplotlib'))")
        pandas: \$(python -c "import importlib.metadata; print(importlib.metadata.version('pandas'))")
    END_VERSIONS
    """

    stub:
    """
    touch benchmark_comparison.csv benchmark_comparison_mqc.csv f1_jaccard_distribution_mqc.png db_layer_coverage_mqc.png
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: stub
        matplotlib: stub
        pandas: stub
    END_VERSIONS
    """
}
