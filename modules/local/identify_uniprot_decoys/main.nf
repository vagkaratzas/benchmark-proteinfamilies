process IDENTIFY_UNIPROT_DECOYS {
    tag "$meta.id"
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/43/438649357e4dcaab676b1bff95e3aace1decb36a658d6257869a641155867e0c/data' :
        'community.wave.seqera.io/library/pip_pyfastx:c1d255a74c4291f8' }"

    input:
    tuple val(meta) , path(hits)
    tuple val(meta2), path(sp_fasta)
    val num_decoys
    val seed

    output:
    path "decoys.fasta", emit: decoys
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def seed_arg = seed == null ? '' : "--seed ${seed}"
    """
    identify_uniprot_decoys.py \\
        --hits_file ${hits} \\
        --fasta_file ${sp_fasta} \\
        --output_file decoys.fasta \\
        --num_decoys ${num_decoys} \\
        ${seed_arg}

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: \$(python --version 2>&1 | sed 's/Python //g')
        pyfastx: \$(python -c "import importlib.metadata; print(importlib.metadata.version('pyfastx'))")
    END_VERSIONS
    """

    stub:
    """
    touch decoys.fasta

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: stub
        pyfastx: stub
    END_VERSIONS
    """
}
