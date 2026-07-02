function deepClone(value) {
    if (typeof structuredClone === 'function') {
        return structuredClone(value);
    }
    return JSON.parse(JSON.stringify(value));
}

function unescapePointerSegment(segment) {
    return segment.replace(/~1/g, '/').replace(/~0/g, '~');
}

function parsePointer(path) {
    if (!path || path === '/') return [];
    return String(path)
        .replace(/^\//, '')
        .split('/')
        .filter(Boolean)
        .map(unescapePointerSegment);
}

function ensureContainer(parent, key, nextKey) {
    if (parent[key] === undefined || parent[key] === null) {
        parent[key] = Number.isInteger(Number(nextKey)) ? [] : {};
    }
    return parent[key];
}

function applySinglePatch(root, patch) {
    if (!patch || !patch.path) return root;
    const op = patch.op || 'replace';
    const segments = parsePointer(patch.path);
    if (!segments.length) {
        if (op === 'remove') {
            return undefined;
        }
        return patch.value;
    }

    const next = Array.isArray(root) ? root : (root && typeof root === 'object' ? root : {});
    let cursor = next;
    for (let i = 0; i < segments.length - 1; i += 1) {
        const key = segments[i];
        const nextKey = segments[i + 1];
        cursor = ensureContainer(cursor, key, nextKey);
    }

    const leafKey = segments[segments.length - 1];
    if (op === 'remove') {
        if (Array.isArray(cursor)) {
            cursor.splice(Number(leafKey), 1);
        } else {
            delete cursor[leafKey];
        }
        return next;
    }

    if (Array.isArray(cursor)) {
        const index = Number(leafKey);
        if (Number.isFinite(index)) {
            cursor[index] = patch.value;
        } else {
            cursor[leafKey] = patch.value;
        }
    } else {
        cursor[leafKey] = patch.value;
    }
    return next;
}

export function applyIncrementalPatches(root, patches = []) {
    let next = deepClone(root ?? {});
    for (const patch of patches || []) {
        const updated = applySinglePatch(next, patch);
        if (updated === undefined) {
            next = undefined;
            break;
        }
        next = updated;
    }
    return next;
}

function upsertChapter(novelData, chapter) {
    if (!chapter || typeof chapter !== 'object') return;
    const chapterIndex = Number(chapter.chapter_index ?? chapter.index ?? chapter.id);
    if (!Number.isFinite(chapterIndex)) return;
    const next = novelData;
    if (!Array.isArray(next.chapters)) {
        next.chapters = [];
    }
    const existingIndex = next.chapters.findIndex(item => Number(item?.chapter_index) === chapterIndex);
    if (existingIndex >= 0) {
        next.chapters[existingIndex] = { ...next.chapters[existingIndex], ...chapter };
    } else {
        next.chapters.push(chapter);
        next.chapters.sort((a, b) => Number(a?.chapter_index || 0) - Number(b?.chapter_index || 0));
    }
}

export function applyGenerationTaskResult(state, envelope = {}) {
    if (!state) return null;
    if (!state.currentNovelData) {
        state.currentNovelData = {};
    }

    const nextNovelData = deepClone(state.currentNovelData);
    const stateUpdates = envelope.state_updates || {};

    for (const [key, value] of Object.entries(stateUpdates)) {
        if (key === 'chapter') {
            upsertChapter(nextNovelData, value);
        } else {
            nextNovelData[key] = value;
        }
    }

    if (Array.isArray(envelope.patches) && envelope.patches.length > 0) {
        const patched = applyIncrementalPatches(nextNovelData, envelope.patches);
        state.currentNovelData = patched ?? nextNovelData;
    } else {
        state.currentNovelData = nextNovelData;
    }

    return state.currentNovelData;
}

