process SAMPLE_INTERPRO {
    tag "interpro"
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'docker://quay.io/biocontainers/pandas:1.4.3@sha256:3a2c607b31c9f34dcdefb7045dd23063091f55c78050530b79c4755335fb7ba7' :
        'quay.io/biocontainers/pandas:1.4.3@sha256:3a2c607b31c9f34dcdefb7045dd23063091f55c78050530b79c4755335fb7ba7' }"

    input:
    path metadata
    path hierarchy
    val min_membership
    val num_per_db
    val seed

    output:
    path "log.txt"             , emit: log
    path "sampled_metadata.csv", emit: metadata
    path "versions.yml"        , emit: versions

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

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: \$(python --version 2>&1 | sed 's/Python //g')
        pandas: \$(python -c "import importlib.metadata; print(importlib.metadata.version('pandas'))")
    END_VERSIONS
    """

    stub:
    """
    touch log.txt sampled_metadata.csv

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: stub
        pandas: stub
    END_VERSIONS
    """
}
