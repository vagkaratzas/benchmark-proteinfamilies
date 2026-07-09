process EXTRACT_VALID_INTERPRO_IDS {
    tag "interpro"
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/31/313e1c18a344323886cf97a151ab66d81c1a146fb129558cb9382b69a72d5532/data' :
        'community.wave.seqera.io/library/python:b1b4b1f458c605bb' }"

    input:
    path hierarchy

    output:
    path "intepro_valid_ids.txt", emit: output
    path "versions.yml"         , emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    grep -o 'IPR[0-9]\\{6\\}' ${hierarchy} > intepro_valid_ids.txt

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        sed: \$(sed --version 2>&1 | sed -n 1p | sed 's/sed (GNU sed) //')
    END_VERSIONS
    """

    stub:
    """
    touch intepro_valid_ids.txt

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        sed: stub
    END_VERSIONS
    """
}
