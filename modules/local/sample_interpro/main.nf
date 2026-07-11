process SAMPLE_INTERPRO {
    tag "interpro"
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'docker://quay.io/biocontainers/pandas@sha256:3a2c607b31c9f34dcdefb7045dd23063091f55c78050530b79c4755335fb7ba7' :
        'quay.io/biocontainers/pandas@sha256:3a2c607b31c9f34dcdefb7045dd23063091f55c78050530b79c4755335fb7ba7' }"

    input:
    path metadata
    path hierarchy
    val min_membership
    val num_per_db
    val seed

    output:
    path "log.txt"             , emit: log
    path "sampled_metadata.csv", emit: metadata

    tuple val("${task.process}"), val('python'), eval("python --version 2>&1 | sed 's/Python //g'"), emit: versions_python, topic: versions
    tuple val("${task.process}"), val('pandas'), eval("python -c \"import importlib.metadata; print(importlib.metadata.version('pandas'))\""), emit: versions_pandas, topic: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def seed_arg = seed == null ? '' : "--seed ${seed}"
    """
    sample_interpro.py \\
        --interpro_file ${metadata} \\
        --tree_file ${hierarchy} \\
        --min_membership ${min_membership} \\
        --num_per_db ${num_per_db} \\
        --logfile log.txt \\
        --output sampled_metadata.csv \\
        ${seed_arg}
    """

    stub:
    """
    touch log.txt sampled_metadata.csv
    """
}
