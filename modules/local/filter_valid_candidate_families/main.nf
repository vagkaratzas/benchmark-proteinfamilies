process FILTER_VALID_CANDIDATE_FAMILIES {
    tag "interpro"
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'docker://quay.io/biocontainers/pandas@sha256:3a2c607b31c9f34dcdefb7045dd23063091f55c78050530b79c4755335fb7ba7' :
        'quay.io/biocontainers/pandas@sha256:3a2c607b31c9f34dcdefb7045dd23063091f55c78050530b79c4755335fb7ba7' }"

    input:
    path interpro
    path metadata

    output:
    path "filtered_metadata.tsv", emit: metadata

    tuple val("${task.process}"), val('python'), eval("python --version 2>&1 | sed 's/Python //g'"), emit: versions_python, topic: versions
    tuple val("${task.process}"), val('pandas'), eval("python -c \"import importlib.metadata; print(importlib.metadata.version('pandas'))\""), emit: versions_pandas, topic: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    filter_valid_candidate_families.py \\
        ${interpro} filtered_metadata.tsv \\
        --metadata ${metadata}
    """

    stub:
    """
    touch filtered_metadata.tsv
    """
}
