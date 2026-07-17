from app.interfaces.telegram.job_models import JobState


PIPELINE_STAGE_STATES = {
    "extract_pages": JobState.extracting,
    "build_document": JobState.processing,
    "build_outline": JobState.processing,
    "export": JobState.exporting,
    "export_outline": JobState.exporting,
    "extract_concepts": JobState.processing,
    "export_knowledge_graph": JobState.exporting,
}
