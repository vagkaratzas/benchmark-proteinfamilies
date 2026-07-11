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

    tuple val("${task.process}"), val('python'), eval("python --version 2>&1 | sed 's/Python //g'"), emit: versions_python, topic: versions
    tuple val("${task.process}"), val('matplotlib'), eval("python -c \"import importlib.metadata; print(importlib.metadata.version('matplotlib'))\""), emit: versions_matplotlib, topic: versions
    tuple val("${task.process}"), val('pandas'), eval("python -c \"import importlib.metadata; print(importlib.metadata.version('pandas'))\""), emit: versions_pandas, topic: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    produce_db_stacked_barplot.py \\
        --input_file ${jaccard_edgelist} \\
        --output_file stacked_barplot.png
    """

    stub:
    """
    touch stacked_barplot.png
    """
}
