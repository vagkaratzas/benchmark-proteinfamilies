process CALCULATE_SEQUENCE_STATS {
    tag "$meta.id"
    label 'process_low'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/eb/eb3700531c7ec639f59f084ab64c05e881d654dcf829db163539f2f0b095e09d/data' :
        'community.wave.seqera.io/library/biopython:1.84--3318633dad0031e7' }"

    input:
    tuple val(meta), path(alignments), path(clustering_tsv)
    path id_registry
    path pre_universe_fasta
    path pre_universe_sha256
    path benchmark_ids
    path post_common

    output:
    tuple val(meta), path("sequence_decoy_counts.txt")     , emit: decoy_count
    tuple val(meta), path("sequence_original_counts.txt")  , emit: original_count
    tuple val(meta), path("sequence_summary.txt")          , emit: summary
    tuple val(meta), path("sequence_unknown_sequences.txt"), emit: unknown

    tuple val("${task.process}"), val('python'), eval("python --version 2>&1 | sed 's/Python //g'"), emit: versions_python, topic: versions
    tuple val("${task.process}"), val('biopython'), eval("python -c \"import importlib.metadata; print(importlib.metadata.version('biopython'))\""), emit: versions_biopython, topic: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    export PYTHONPATH="\$PWD:\${PYTHONPATH:-}"
    calculate_sequence_stats.py \\
        --alignment_folder ${alignments} \\
        --id_registry ${id_registry} \\
        --pre_universe_fasta ${pre_universe_fasta} \\
        --pre_universe_sha256 ${pre_universe_sha256} \\
        --output_prefix sequence \\
        --num_workers ${task.cpus} \\
        --sample '${meta.id}' \\
        --tool '${meta.tool}'
    """

    stub:
    """
    touch sequence_decoy_counts.txt sequence_original_counts.txt sequence_summary.txt sequence_unknown_sequences.txt
    """
}
