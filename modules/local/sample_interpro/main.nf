process SAMPLE_INTERPRO {
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'https://depot.galaxyproject.org/singularity/pandas:1.4.3' :
        'biocontainers/pandas:1.4.3' }"

    input:
    path metadata
    path hierarchy
    val min_membership
    val num_per_db

    output:
    path "log.txt"             , emit: log
    path "sampled_metadata.csv", emit: metadata
    path "versions.yml"        , emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    sample_interpro.py \\
        --interpro_file ${metadata} \\
        --tree_file ${hierarchy} \\
        --min_membership ${min_membership} \\
        --num_per_db ${num_per_db} \\
        --logfile log.txt \\
        --output sampled_metadata.csv

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: \$(python --version 2>&1 | sed 's/Python //g')
        pandas: \$(python -c "import importlib.metadata; print(importlib.metadata.version('pandas'))")
    END_VERSIONS
    """
}
