process EXTRACT_CANDIDATE_INTERPRO_FAMILIES {
    tag "interpro"
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/31/313e1c18a344323886cf97a151ab66d81c1a146fb129558cb9382b69a72d5532/data' :
        'community.wave.seqera.io/library/python:b1b4b1f458c605bb' }"

    input:
    path valid_ids
    path mapping

    output:
    path "intepro_families.tsv", emit: metadata

    tuple val("${task.process}"), val('python'), eval("python --version 2>&1 | sed 's/Python //g'"), emit: versions_python, topic: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    extract_candidate_interpro_families.py \\
        ${mapping} ${valid_ids} intepro_families.tsv
    """

    stub:
    """
    touch intepro_families.tsv
    """
}
