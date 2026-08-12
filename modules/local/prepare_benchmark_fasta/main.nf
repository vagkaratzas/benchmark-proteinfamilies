process PREPARE_BENCHMARK_FASTA {
    tag "prepare_benchmark_fasta"
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/eb/eb3700531c7ec639f59f084ab64c05e881d654dcf829db163539f2f0b095e09d/data' :
        'community.wave.seqera.io/library/biopython:1.84--3318633dad0031e7' }"

    input:
    path sampled_metadata
    // db_names is aligned with db_dirs by position. The directories are restaged under generated
    // names so that two databases supplied from paths with the same basename cannot collide, which
    // is exactly why the names have to travel alongside them rather than be read off the path.
    tuple val(db_names), path(db_dirs, stageAs: 'member_db_*')
    val seed

    output:
    path "sampled_fasta"               , emit: fasta_folder
    path "updated_sampled_metadata.csv", emit: metadata
    path "combined_db.faa"             , emit: fasta
    path "id_registry.tsv"             , emit: registry
    path "combined_db.sha256"          , emit: combined_db_sha256
    path "log.txt"                     , emit: log

    tuple val("${task.process}"), val('python'), eval("python --version 2>&1 | sed 's/Python //g'"), emit: versions_python, topic: versions
    tuple val("${task.process}"), val('biopython'), eval("python -c \"import importlib.metadata; print(importlib.metadata.version('biopython'))\""), emit: versions_biopython, topic: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def seed_arg = seed == null ? '' : "--seed ${seed}"
    // A single-element input arrives as a bare value rather than a list, so both are normalised
    // before being zipped -- otherwise a one-database run would iterate over characters.
    def names = db_names instanceof List ? db_names : [db_names]
    def dirs = db_dirs instanceof List ? db_dirs : [db_dirs]
    def db_args = [names, dirs].transpose().collect { name, dir -> "--db ${name}=${dir}" }.join(' \\\n        ')
    """
    prepare_benchmark_fasta.py \\
        --metadata_file ${sampled_metadata} \\
        ${db_args} \\
        --output_folder sampled_fasta \\
        --updated_metadata_file updated_sampled_metadata.csv \\
        --combined_fasta combined_db.faa \\
        --id_registry id_registry.tsv \\
        --combined_db_sha256 combined_db.sha256 \\
        --log_file log.txt \\
        ${seed_arg}
    """

    stub:
    """
    mkdir -p sampled_fasta
    touch sampled_fasta/.stub
    touch updated_sampled_metadata.csv combined_db.faa id_registry.tsv combined_db.sha256 log.txt
    """
}
