process GET_SIZE_DISTRIBUTIONS {
    tag "$meta.id"
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'docker://quay.io/biocontainers/pandas:1.4.3@sha256:3a2c607b31c9f34dcdefb7045dd23063091f55c78050530b79c4755335fb7ba7' :
        'quay.io/biocontainers/pandas:1.4.3@sha256:3a2c607b31c9f34dcdefb7045dd23063091f55c78050530b79c4755335fb7ba7' }"

    input:
    tuple val(meta), path(similarity_file)
    path metadata_file
    path pre_universe_fasta
    path pre_universe_sha256
    path benchmark_ids
    path post_common

    output:
    tuple val(meta), path("size_distributions.txt"), emit: log
    tuple val(meta), path("matched_metadata.tsv")  , emit: matched
    tuple val(meta), path("unmatched_metadata.tsv"), emit: unmatched
    tuple val(meta), path("versions.yml")          , emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    export PYTHONPATH="\$PWD:\${PYTHONPATH:-}"
    get_size_distributions.py \\
        --metadata_file ${metadata_file} \\
        --similarity_file ${similarity_file} \\
        --pre_universe_fasta ${pre_universe_fasta} \\
        --pre_universe_sha256 ${pre_universe_sha256} \\
        --output_file size_distributions.txt \\
        --sample '${meta.id}' \\
        --tool '${meta.tool}'

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: \$(python --version 2>&1 | sed 's/Python //g')
        pandas: \$(python -c "import importlib.metadata; print(importlib.metadata.version('pandas'))")
    END_VERSIONS
    """

    stub:
    """
    touch size_distributions.txt matched_metadata.tsv unmatched_metadata.tsv
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: stub
        pandas: stub
    END_VERSIONS
    """
}
