import { requestAPI } from '../api/api.js';
import { parseGenerationTaskEventChunk, extractFinalGenerationEnvelope } from './generationSseHandler.js';

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function runStreamingAttempt(endpoint, body, {
    onThinking = null,
    onContent = null,
    onError = null,
    onDone = null,
    onRetrying = null,
    onEvent = null
} = {}) {
    const controller = new AbortController();
    const signal = controller.signal;
    const CONNECT_TIMEOUT = 600000;
    const STALL_TIMEOUT = 600000;

    let connectTimer = null;
    let activityTimer = null;
    let finalEnvelope = null;
    let localHadError = false;

    function resetActivityTimer() {
        if (activityTimer) clearTimeout(activityTimer);
        activityTimer = setTimeout(() => controller.abort(), STALL_TIMEOUT);
    }

    connectTimer = setTimeout(() => controller.abort(), CONNECT_TIMEOUT);

    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            signal
        });

        if (connectTimer) {
            clearTimeout(connectTimer);
            connectTimer = null;
        }

        if (!response.ok) {
            if (response.status === 429) {
                const errData = await response.json().catch(() => ({ detail: '此小說的流水線正在執行中，請等待完成。' }));
                const msg = errData.detail || '此小說的流水線正在執行中，請等待完成。';
                if (typeof onError === 'function') onError(msg);
                if (typeof onDone === 'function') await onDone(null, false);
                return { success: false, retryable: false, error: msg, notifiedError: true, notifiedDone: true };
            }
            const errText = await response.text();
            return { success: false, retryable: true, error: `HTTP ${response.status}: ${errText}`, notifiedError: false, notifiedDone: false };
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';
        resetActivityTimer();

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            resetActivityTimer();
            buffer += decoder.decode(value, { stream: true });

            const parts = buffer.split('\n');
            buffer = parts.pop() || '';

            for (const line of parts) {
                const events = parseGenerationTaskEventChunk(line);
                for (const event of events) {
                    if (!event || typeof event !== 'object') continue;
                    if (typeof onEvent === 'function') onEvent(event);

                    if (event.type === 'thinking') {
                        if (typeof onThinking === 'function') onThinking(event.delta ?? '');
                    } else if (event.type === 'content') {
                        if (typeof onContent === 'function') onContent(event.delta ?? '');
                    } else if (event.type === 'reset') {
                        if (typeof onThinking === 'function') onThinking(null);
                        if (typeof onContent === 'function') onContent(null);
                    } else if (event.type === 'status') {
                        if (typeof onEvent === 'function') onEvent(event);
                    } else if (event.type === 'retrying') {
                        if (typeof onRetrying === 'function') onRetrying(event.message || '');
                    } else if (event.type === 'error') {
                        localHadError = true;
                        if (typeof onError === 'function') onError(event.message || '生成失敗');
                    } else if (event.type === 'done') {
                        finalEnvelope = event;
                    }
                }
            }
        }

        if (connectTimer) {
            clearTimeout(connectTimer);
            connectTimer = null;
        }
        if (activityTimer) clearTimeout(activityTimer);

        if (!finalEnvelope) {
            finalEnvelope = extractFinalGenerationEnvelope([]);
        }

        if (typeof onDone === 'function') {
            await onDone(finalEnvelope, !localHadError && !(finalEnvelope && finalEnvelope.ok === false));
        }

        return {
            success: !localHadError && !(finalEnvelope && finalEnvelope.ok === false),
            retryable: false,
            finalEnvelope,
            notifiedError: localHadError,
            notifiedDone: true
        };
    } catch (error) {
        if (connectTimer) clearTimeout(connectTimer);
        if (activityTimer) clearTimeout(activityTimer);
        const isAbort = error?.name === 'AbortError';
        return {
            success: false,
            retryable: true,
            error: isAbort ? '生成逾時或中斷' : (error?.message || String(error)),
            notifiedError: false,
            notifiedDone: false
        };
    }
}

export async function submitGenerationTask(payload, callbacks = {}) {
    const endpoint = callbacks.endpoint || '/api/generation-task';
    const maxRetries = callbacks.maxRetries ?? 10;
    const requestBody = {
        ...payload,
        options: {
            batch: false,
            overwrite: false,
            stream: true,
            ...(payload?.options || {})
        }
    };

    if (!requestBody.options.stream) {
        return requestAPI(endpoint, 'POST', requestBody);
    }

    let lastError = null;
    let hadPreviousError = false;

    for (let attempt = 1; attempt <= maxRetries; attempt += 1) {
        const attemptResult = await runStreamingAttempt(endpoint, requestBody, callbacks);
        if (attemptResult.success) {
            if (hadPreviousError && typeof callbacks.onRetryRecovered === 'function') {
                await callbacks.onRetryRecovered(attemptResult.finalEnvelope || null);
            }
            return attemptResult.finalEnvelope;
        }

        lastError = attemptResult.error || (attemptResult.finalEnvelope && attemptResult.finalEnvelope.error) || lastError;
        if (!attemptResult.retryable || attempt === maxRetries) {
            if (!attemptResult.notifiedError && typeof callbacks.onError === 'function' && lastError) {
                callbacks.onError(lastError);
            }
            if (!attemptResult.notifiedDone && typeof callbacks.onDone === 'function') {
                await callbacks.onDone(null, false);
            }
            throw new Error(lastError || 'generation-task failed');
        }

        hadPreviousError = true;
        if (typeof callbacks.onRetrying === 'function') {
            callbacks.onRetrying(`重試第 ${attempt}/${maxRetries} 次`);
        }
        await sleep(Math.min(3000, attempt * 2000));
    }

    throw new Error(lastError || 'generation-task failed');
}
