process EXTRACT_DB_METADATA {
    tag "$meta.id"
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/eb/eb3700531c7ec639f59f084ab64c05e881d654dcf829db163539f2f0b095e09d/data' :
        'community.wave.seqera.io/library/biopython:1.84--3318633dad0031e7' }"

    input:
    tuple val(meta), path(alignments)

    output:
    tuple val(meta), path("*_metadata.tsv"), emit: metadata

    tuple val("${task.process}"), val('python'), eval("python --version 2>&1 | sed 's/Python //g'"), emit: versions_python, topic: versions
    tuple val("${task.process}"), val('biopython'), eval("python -c \"import importlib.metadata; print(importlib.metadata.version('biopython'))\""), emit: versions_biopython, topic: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def dbType = meta.db_type ?: meta.id
    """
    extract_db_metadata.py \\
        --db_type ${dbType} \\
        ${alignments} ${dbType}_metadata.tsv
    """

    stub:
    def dbType = meta.db_type ?: meta.id
    """
    touch ${dbType}_metadata.tsv
    """
}
