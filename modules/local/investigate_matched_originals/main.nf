process INVESTIGATE_MATCHED_ORIGINALS {
    tag "$meta.id"
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/eb/eb3700531c7ec639f59f084ab64c05e881d654dcf829db163539f2f0b095e09d/data' :
        'community.wave.seqera.io/library/biopython:1.84--3318633dad0031e7' }"

    input:
    tuple val(meta), path(msa_dir), path(clustering_tsv)
    path sampled_fasta
    path metadata
    path id_registry
    path pre_universe_fasta
    path pre_universe_sha256
    path benchmark_ids
    path post_common

    output:
    tuple val(meta), path("metadata.tsv")    , emit: metadata
    tuple val(meta), path("all_clusters.txt"), emit: clusters
    tuple val(meta), path("all_matches.txt") , emit: matches
    tuple val(meta), path("versions.yml")    , emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def clusterArg = clustering_tsv ? "--cluster_file ${clustering_tsv}" : ''
    """
    export PYTHONPATH="\$PWD:\${PYTHONPATH:-}"
    investigate_matched_originals.py \\
        --db_folder ${sampled_fasta} \\
        --msa_dir ${msa_dir} \\
        ${clusterArg} \\
        --metadata ${metadata} \\
        --id_registry ${id_registry} \\
        --pre_universe_fasta ${pre_universe_fasta} \\
        --pre_universe_sha256 ${pre_universe_sha256} \\
        --output metadata.tsv \\
        --cluster_log all_clusters.txt \\
        --match_log all_matches.txt \\
        --sample '${meta.id}' \\
        --tool '${meta.tool}'

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: \$(python --version 2>&1 | sed 's/Python //g')
        biopython: \$(python -c "import importlib.metadata; print(importlib.metadata.version('biopython'))")
    END_VERSIONS
    """

    stub:
    """
    touch metadata.tsv all_clusters.txt all_matches.txt
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: stub
        biopython: stub
    END_VERSIONS
    """
}
