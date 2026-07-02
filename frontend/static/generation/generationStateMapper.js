export function buildFrontendStateReference(state = {}) {
    return {
        current_stage: state.activeTab || state.currentPipelineStage || null,
        selected_volume: state.activeVolumeIndex ?? null,
        selected_chapter: state.activeChapterIndex ?? null,
        active_drawer_action: state.activeDrawerAction || null,
        pipeline_running: Boolean(state.isPipelineRunning),
        auto_execute: Boolean(state.isAutoExecuteMode),
        currently_writing_chapter: state.currentlyWritingChapterIndex ?? null
    };
}

