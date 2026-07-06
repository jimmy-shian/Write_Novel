const GENERATION_STAGES = [
    'worldview',
    'characters',
    'foreshadowing',
    'volumes',
    'volume_skeleton',
    'writer',
    'editor',
    'evaluate'
];

const GENERATION_TASK_TYPES = [
    'generate',
    'regenerate',
    'patch',
    'batch_generate',
    'refine',
    'evaluate'
];

const GENERATION_CONTEXT_MODES = ['full', 'compact', 'minimal'];

const DEFAULT_STAGE_BY_TASK_TYPE = {
    generate: 'worldview',
    regenerate: 'worldview',
    patch: 'worldview',
    batch_generate: 'volume_skeleton',
    refine: 'editor',
    evaluate: 'evaluate'
};

const DEFAULT_SCOPE_BY_STAGE = {
    worldview: 'global',
    characters: 'global',
    foreshadowing: 'global',
    volumes: 'global',
    volume_skeleton: 'volume',
    writer: 'chapter',
    editor: 'chapter',
    evaluate: 'global'
};

function makeTaskId() {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
        return crypto.randomUUID();
    }
    return `task_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

export function inferStageForTaskType(taskType) {
    return DEFAULT_STAGE_BY_TASK_TYPE[taskType] || 'worldview';
}

export function inferScopeForStage(stage) {
    return DEFAULT_SCOPE_BY_STAGE[stage] || 'global';
}

export function normalizeTarget(target = {}) {
    const safeTarget = target && typeof target === 'object' ? target : {};
    return {
        volume_id: safeTarget.volume_id ?? null,
        chapter_id: safeTarget.chapter_id ?? null,
        section_id: safeTarget.section_id ?? null,
        volume_index: safeTarget.volume_index ?? null,
        chapter_index: safeTarget.chapter_index ?? null,
        section_index: safeTarget.section_index ?? null,
        selection: Array.isArray(safeTarget.selection) ? safeTarget.selection : null
    };
}

export function validateGenerationTaskPayload(payload) {
    const errors = [];
    const warnings = [];
    if (!payload || typeof payload !== 'object') {
        return { ok: false, errors: ['payload must be an object'], warnings };
    }
    if (!payload.novel_id) errors.push('novel_id is required');
    if (!GENERATION_TASK_TYPES.includes(payload.task_type)) errors.push(`invalid task_type: ${payload.task_type}`);
    if (!GENERATION_STAGES.includes(payload.stage)) errors.push(`invalid stage: ${payload.stage}`);
    if (!GENERATION_CONTEXT_MODES.includes(payload.context_mode)) errors.push(`invalid context_mode: ${payload.context_mode}`);
    if (!payload.scope) warnings.push('scope missing, backend will infer a default');
    return { ok: errors.length === 0, errors, warnings };
}

export function buildGenerationTaskPayload({
    novelId,
    taskType = 'generate',
    stage = null,
    scope = null,
    target = null,
    contextMode = 'compact',
    options = {},
    frontendState = {},
    instruction = '',
    userPrompt = '',
    hint = '',
    taskId = null,
    conversationContext = null,
    summaryContext = null,
    extraContext = null
} = {}) {
    const normalizedTaskType = GENERATION_TASK_TYPES.includes(taskType) ? taskType : 'generate';
    const normalizedStage = GENERATION_STAGES.includes(stage) ? stage : inferStageForTaskType(normalizedTaskType);
    const normalizedContextMode = GENERATION_CONTEXT_MODES.includes(contextMode) ? contextMode : 'compact';
    const normalizedScope = scope || inferScopeForStage(normalizedStage);
    const safeOptions = {
        batch: false,
        overwrite: false,
        stream: true,
        ...options
    };
    const prompt = (instruction || userPrompt || hint || '').trim();

    return {
        novel_id: novelId,
        task_type: normalizedTaskType,
        stage: normalizedStage,
        scope: normalizedScope,
        target: normalizeTarget(target),
        context_mode: normalizedContextMode,
        options: safeOptions,
        frontend_state: frontendState && typeof frontendState === 'object' ? frontendState : {},
        instruction: prompt,
        user_prompt: prompt,
        hint: hint || '',
        task_id: taskId || makeTaskId(),
        conversation_context: conversationContext,
        summary_context: summaryContext,
        extra_context: extraContext
    };
}

export {
    GENERATION_STAGES,
    GENERATION_TASK_TYPES,
    GENERATION_CONTEXT_MODES
};
