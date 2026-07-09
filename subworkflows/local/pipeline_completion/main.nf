workflow PIPELINE_COMPLETION {

    main:
    def run_workflow = workflow
    def run_params = params
    def pipeline_name = run_workflow.manifest.name
    workflow.onComplete {
        log.info """
        ------------------------------------------------------
        Completed : ${pipeline_name}
        Duration  : ${run_workflow.duration}
        Outdir    : ${run_params.outdir}
        Status    : ${run_workflow.success ? 'SUCCESS' : 'FAILED'}
        ------------------------------------------------------
        """.stripIndent()
    }
}
