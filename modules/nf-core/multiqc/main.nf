process MULTIQC {
    tag "$meta.id"
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'https://depot.galaxyproject.org/singularity/multiqc:1.25.1--pyhdfd78af_0' :
        'biocontainers/multiqc:1.25.1--pyhdfd78af_0' }"

    input:
    val meta
    // Every sample emits identically-named *_mqc.csv files; stage each in its own
    // numbered subdirectory so collecting them across samples is not a name collision.
    path multiqc_files, stageAs: "?/*"
    path multiqc_config

    output:
    tuple val(meta), path("multiqc_report.html"), emit: report
    tuple val(meta), path("multiqc_data")       , emit: data
    tuple val(meta), path("versions.yml")       , emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def args = task.ext.args ?: ''
    """
    multiqc \\
        --config ${multiqc_config} \\
        --filename multiqc_report.html \\
        --outdir . \\
        ${args} \\
        .

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        multiqc: \$(multiqc --version | sed 's/multiqc, version //')
    END_VERSIONS
    """

    stub:
    """
    mkdir -p multiqc_data
    touch multiqc_report.html
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        multiqc: stub
    END_VERSIONS
    """
}
