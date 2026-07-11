process COMBINE_DECOY_FASTA {
    tag "pre"
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/eb/eb3700531c7ec639f59f084ab64c05e881d654dcf829db163539f2f0b095e09d/data' :
        'community.wave.seqera.io/library/biopython:1.84--3318633dad0031e7' }"

    input:
    path db_fasta
    path decoy
    path id_registry

    output:
    path "combined_decoy_log.txt", emit: log
    path "combined_decoy.faa"    , emit: fasta
    path "id_registry.tsv"       , emit: registry
    path "universe.sha256"       , emit: universe_sha256

    tuple val("${task.process}"), val('python'), eval("python --version 2>&1 | sed 's/Python //g'"), emit: versions_python, topic: versions
    tuple val("${task.process}"), val('biopython'), eval("python -c \"import importlib.metadata; print(importlib.metadata.version('biopython'))\""), emit: versions_biopython, topic: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    cp ${id_registry} family_id_registry.tsv

    combine_decoy_fasta.py \\
        --families_fasta ${db_fasta} \\
        --decoys_fasta ${decoy} \\
        --combined_fasta combined_decoy.faa \\
        --id_registry family_id_registry.tsv \\
        --output_registry id_registry.tsv \\
        --universe_sha256 universe.sha256 \\
        --log_file combined_decoy_log.txt
    """

    stub:
    """
    touch combined_decoy_log.txt combined_decoy.faa id_registry.tsv universe.sha256
    """
}
