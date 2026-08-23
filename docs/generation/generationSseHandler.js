export function parseGenerationTaskEventLine(line) {
    if (!line) return null;
    const trimmed = line.trim();
    if (!trimmed.startsWith('data:')) return null;
    const payload = trimmed.slice(5).trim();
    if (!payload || payload === '[DONE]') {
        return { type: 'done' };
    }
    try {
        return JSON.parse(payload);
    } catch (error) {
        return {
            type: 'parse_error',
            message: error?.message || 'Failed to parse SSE payload',
            raw: payload
        };
    }
}

export function parseGenerationTaskEventChunk(chunk) {
    const events = [];
    if (!chunk || typeof chunk !== 'string') {
        return events;
    }
    for (const line of chunk.split('\n')) {
        const event = parseGenerationTaskEventLine(line);
        if (event) {
            events.push(event);
        }
    }
    return events;
}

export function isTerminalGenerationEvent(event) {
    if (!event || typeof event !== 'object') return false;
    if (event.type === 'done') return true;
    return ['completed', 'failed'].includes(event.status);
}

export function extractFinalGenerationEnvelope(events = []) {
    for (let i = events.length - 1; i >= 0; i -= 1) {
        const event = events[i];
        if (isTerminalGenerationEvent(event)) {
            return event;
        }
    }
    return null;
}

