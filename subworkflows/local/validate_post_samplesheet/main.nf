workflow VALIDATE_POST_SAMPLESHEET {
    take:
    samplesheet

    main:
    ch_samplesheet = channel.fromPath(samplesheet, checkIfExists: true)

    ch_samples = ch_samplesheet
        .splitCsv(header: true)
        .collect()
        .flatMap { rows ->
            def seen = [] as Set
            rows.collect { row ->
                def sample = row.sample?.toString()?.trim()
                def tool = row.tool?.toString()?.trim()
                def msa_dir = row.msa_dir?.toString()?.trim()
                def clustering_tsv = row.clustering_tsv?.toString()?.trim()

                if (!sample) {
                    error "POST samplesheet row is missing required sample"
                }
                if (!seen.add(sample)) {
                    error "POST samplesheet sample must be unique; duplicate: ${sample}"
                }
                if (!tool) {
                    error "POST samplesheet row ${sample} is missing required tool"
                }
                if (!msa_dir) {
                    error "POST samplesheet row ${sample} is missing required msa_dir"
                }

                tuple(
                    [id: sample, tool: tool, has_clustering: clustering_tsv ? true : false],
                    file(msa_dir, checkIfExists: true),
                    clustering_tsv ? file(clustering_tsv, checkIfExists: true) : []
                )
            }
        }

    emit:
    samples = ch_samples
}
