process CALCULATE_FAMILY_METRICS {
    tag "$meta.id"
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/eb/eb3700531c7ec639f59f084ab64c05e881d654dcf829db163539f2f0b095e09d/data' :
        'community.wave.seqera.io/library/biopython:1.84--3318633dad0031e7' }"

    input:
    tuple val(meta), path(msa_dir), path(clustering_tsv)
    path sampled_fasta
    path metadata
    path id_registry
    path pre_universe_fasta
    path pre_universe_sha256
    path benchmark_ids
    path post_common

    output:
    tuple val(meta), path("family_metrics.tsv")    , emit: metrics
    tuple val(meta), path("family_metrics_mqc.csv"), emit: mqc

    tuple val("${task.process}"), val('python'), eval("python --version 2>&1 | sed 's/Python //g'"), emit: versions_python, topic: versions
    tuple val("${task.process}"), val('biopython'), eval("python -c \"import importlib.metadata; print(importlib.metadata.version('biopython'))\""), emit: versions_biopython, topic: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    export PYTHONPATH="\$PWD:\${PYTHONPATH:-}"
    calculate_family_metrics.py \\
        --use_case_dir ${msa_dir} \\
        --original_base_dir ${sampled_fasta} \\
        --metadata ${metadata} \\
        --id_registry ${id_registry} \\
        --pre_universe_fasta ${pre_universe_fasta} \\
        --pre_universe_sha256 ${pre_universe_sha256} \\
        --output_file family_metrics.tsv \\
        --mqc_csv family_metrics_mqc.csv \\
        --sample '${meta.id}' \\
        --tool '${meta.tool}'
    """

    stub:
    """
    touch family_metrics.tsv family_metrics_mqc.csv
    """
}
