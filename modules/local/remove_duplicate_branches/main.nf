process REMOVE_DUPLICATE_BRANCHES {
    tag "interpro"
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/31/313e1c18a344323886cf97a151ab66d81c1a146fb129558cb9382b69a72d5532/data' :
        'community.wave.seqera.io/library/python:b1b4b1f458c605bb' }"

    input:
    path hierarchy

    output:
    path "parsed_hierarchy.txt", emit: hierarchy
    path "versions.yml"        , emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    max_depth=\$(grep -o '^--\\+' ${hierarchy} | awk '{ print length(\$0)/2 }' | sort -nr | head -1)
    remove_duplicate_branches.py \\
        --infile ${hierarchy} \\
        --max_depth \$max_depth \\
        --outfile parsed_hierarchy.txt

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: \$(python --version 2>&1 | sed 's/Python //g')
    END_VERSIONS
    """

    stub:
    """
    touch parsed_hierarchy.txt

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: stub
    END_VERSIONS
    """
}
