process FILTER_VALID_CANDIDATE_FAMILIES {
    tag "interpro"
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'docker://quay.io/biocontainers/pandas:1.4.3@sha256:3a2c607b31c9f34dcdefb7045dd23063091f55c78050530b79c4755335fb7ba7' :
        'quay.io/biocontainers/pandas:1.4.3@sha256:3a2c607b31c9f34dcdefb7045dd23063091f55c78050530b79c4755335fb7ba7' }"

    input:
    path interpro
    path metadata

    output:
    path "filtered_metadata.tsv", emit: metadata
    path "versions.yml"         , emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    filter_valid_candidate_families.py \\
        ${interpro} filtered_metadata.tsv \\
        --metadata ${metadata}

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: \$(python --version 2>&1 | sed 's/Python //g')
        pandas: \$(python -c "import importlib.metadata; print(importlib.metadata.version('pandas'))")
    END_VERSIONS
    """

    stub:
    """
    touch filtered_metadata.tsv

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: stub
        pandas: stub
    END_VERSIONS
    """
}
