process ANALYZE_SPLITS_MERGES {
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
    val association_threshold
    val min_intersection_size

    output:
    tuple val(meta), path("split_merge_summary.tsv")    , emit: summary
    tuple val(meta), path("original_overlap_baseline.tsv"), emit: overlap
    tuple val(meta), path("split_merge_summary_mqc.csv") , emit: mqc
    tuple val(meta), path("versions.yml")               , emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    export PYTHONPATH="\$PWD:\${PYTHONPATH:-}"
    analyze_splits_merges.py \\
        --use_case_dir ${msa_dir} \\
        --original_base_dir ${sampled_fasta} \\
        --metadata ${metadata} \\
        --id_registry ${id_registry} \\
        --pre_universe_fasta ${pre_universe_fasta} \\
        --pre_universe_sha256 ${pre_universe_sha256} \\
        --output_file split_merge_summary.tsv \\
        --original_overlap_file original_overlap_baseline.tsv \\
        --mqc_csv split_merge_summary_mqc.csv \\
        --association_threshold ${association_threshold} \\
        --min_intersection_size ${min_intersection_size} \\
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
    touch split_merge_summary.tsv original_overlap_baseline.tsv split_merge_summary_mqc.csv
    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: stub
        biopython: stub
    END_VERSIONS
    """
}
