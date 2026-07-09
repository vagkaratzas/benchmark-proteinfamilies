process PRODUCE_DB_STACKED_BARPLOT {
    tag "$meta.id"
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/3a/3af05bd5854cf509731bce100d59783262ba89546a2d980ff74e2b85ef23e965/data' :
        'community.wave.seqera.io/library/matplotlib_pandas_python:894947e54c3969d1' }"

    input:
    tuple val(meta), path(jaccard_edgelist)

    output:
    tuple val(meta), path("stacked_barplot.png"), emit: barplot
    tuple val(meta), path("versions.yml")       , emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    produce_db_stacked_barplot.py \\
        --input_file ${jaccard_edgelist} \\
        --output_file stacked_barplot.png

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: \$(python --version 2>&1 | sed 's/Python //g')
        matplotlib: \$(python -c "import importlib.metadata; print(importlib.metadata.version('matplotlib'))")
        pandas: \$(python -c "import importlib.metadata; print(importlib.metadata.version('pandas'))")
    END_VERSIONS
    """

    stub:
    """
    touch stacked_barplot.png
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: stub
        matplotlib: stub
        pandas: stub
    END_VERSIONS
    """
}
