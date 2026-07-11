process CALCULATE_JACCARD_SIMILARITY {
    tag "$meta.id"
    label 'process_medium'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/eb/eb3700531c7ec639f59f084ab64c05e881d654dcf829db163539f2f0b095e09d/data' :
        'community.wave.seqera.io/library/biopython:1.84--3318633dad0031e7' }"

    input:
    tuple val(meta), path(aln_folder), path(clustering_tsv)
    path original_folder
    path metadata
    path id_registry
    path pre_universe_fasta
    path pre_universe_sha256
    path benchmark_ids
    path post_common
    val similarity_threshold
    val max_unmapped_fraction
    val max_ambiguous_fraction
    val min_universe_coverage

    output:
    tuple val(meta), path("jaccard_similarities.csv"), emit: edgelist
    tuple val(meta), path("unmapped.tsv")            , emit: unmapped
    tuple val(meta), path("ambiguous.tsv")           , emit: ambiguous
    tuple val(meta), path("jaccard_qc.tsv")          , emit: qc

    tuple val("${task.process}"), val('python'), eval("python --version 2>&1 | sed 's/Python //g'"), emit: versions_python, topic: versions
    tuple val("${task.process}"), val('biopython'), eval("python -c \"import importlib.metadata; print(importlib.metadata.version('biopython'))\""), emit: versions_biopython, topic: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def minCoverageArg = min_universe_coverage ? "--min_universe_coverage ${min_universe_coverage}" : ''
    def clusterArg = clustering_tsv ? "--cluster_file ${clustering_tsv}" : ''
    """
    export PYTHONPATH="\$PWD:\${PYTHONPATH:-}"
    calculate_jaccard_similarity.py \\
        --use_case_dir ${aln_folder} \\
        --original_base_dir ${original_folder} \\
        --metadata ${metadata} \\
        --id_registry ${id_registry} \\
        --pre_universe_fasta ${pre_universe_fasta} \\
        --pre_universe_sha256 ${pre_universe_sha256} \\
        --output_file jaccard_similarities.csv \\
        --unmapped_file unmapped.tsv \\
        --ambiguous_file ambiguous.tsv \\
        --qc_file jaccard_qc.tsv \\
        ${clusterArg} \\
        --similarity_threshold ${similarity_threshold} \\
        --max_unmapped_fraction ${max_unmapped_fraction} \\
        --max_ambiguous_fraction ${max_ambiguous_fraction} \\
        --num_workers ${task.cpus} \\
        --sample '${meta.id}' \\
        --tool '${meta.tool}' \\
        ${minCoverageArg}
    """

    stub:
    """
    touch jaccard_similarities.csv unmapped.tsv ambiguous.tsv jaccard_qc.tsv
    """
}
