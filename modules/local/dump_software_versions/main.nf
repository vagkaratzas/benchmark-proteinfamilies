process DUMP_SOFTWARE_VERSIONS {
    tag "software_versions"
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'https://community-cr-prod.seqera.io/docker/registry/v2/blobs/sha256/31/313e1c18a344323886cf97a151ab66d81c1a146fb129558cb9382b69a72d5532/data' :
        'community.wave.seqera.io/library/python:b1b4b1f458c605bb' }"

    input:
    path versions, stageAs: "?/*"

    output:
    path "software_versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    """
    python - <<'PY'
    from pathlib import Path

    blocks = {}
    for path in sorted(Path(".").glob("*/versions.yml")):
        key = None
        block = []
        for line in path.read_text().splitlines():
            if line and not line[0].isspace() and line.rstrip().endswith(":"):
                if key is not None:
                    blocks.setdefault(key, block)
                key = line.rstrip()
                block = [line]
            elif key is not None:
                block.append(line)
        if key is not None:
            blocks.setdefault(key, block)

    with Path("software_versions.yml").open("w") as out:
        for key in sorted(blocks):
            out.write("\\n".join(blocks[key]).rstrip() + "\\n")
    PY
    """

    stub:
    """
    cat <<-END_VERSIONS > software_versions.yml
    "${task.process}":
        software_versions: stub
    END_VERSIONS
    """
}
