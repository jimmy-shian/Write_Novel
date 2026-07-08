// ==========================================
// API WRAPPERS & STREAMING CORE
// ==========================================

const GENERATION_TASK_LEGACY_KEYS = [
    'taskType',
    'userPrompt',
    'contextMode',
    'frontendState',
    'extraContext',
    'summaryContext',
    'conversationContext'
];

const GENERATION_TASK_REQUIRED_KEYS = [
    'novel_id',
    'task_type',
    'stage',
    'scope',
    'target',
    'context_mode',
    'options',
    'frontend_state',
    'instruction',
    'user_prompt'
];

export function assertCanonicalGenerationPayload(endpoint, body) {
    if (!endpoint || !String(endpoint).includes('/api/generation-task') || !body || typeof body !== 'object') {
        return;
    }
    const legacyKeys = GENERATION_TASK_LEGACY_KEYS.filter((key) => Object.prototype.hasOwnProperty.call(body, key));
    if (legacyKeys.length) {
        throw new Error(`generation-task payload contains obsolete keys: ${legacyKeys.join(', ')}`);
    }
    const missingKeys = GENERATION_TASK_REQUIRED_KEYS.filter((key) => !Object.prototype.hasOwnProperty.call(body, key));
    if (missingKeys.length) {
        throw new Error(`generation-task payload missing canonical keys: ${missingKeys.join(', ')}`);
    }
}

/**
 * 發送一般 API 請求（非串流）
 * @param {string} url - API 端點
 * @param {string} method - HTTP 方法（預設 GET）
 * @param {object|null} body - 請求 body（預設 null）
 * @returns {Promise<object>} 解析後的 JSON 回應
 */
export async function requestAPI(url, method = 'GET', body = null) {
    try {
        assertCanonicalGenerationPayload(url, body);
        const options = {
            method,
            headers: { 'Content-Type': 'application/json' }
        };
        if (body) {
            options.body = JSON.stringify(body);
        }
        const response = await fetch(url, options);
        
        if (!response.ok) {
            const errText = await response.text();
            let errData = null;
            try { errData = JSON.parse(errText); } catch (_) {}
            const detail = errData?.detail || errData?.message || errData?.error || errText || response.statusText;
            throw new Error(`${method} ${url} failed (${response.status}): ${detail}`);
        }
        return await response.json();
    } catch (e) {
        console.error(`API Error [${method} ${url}]: ${e.message}`);
        throw e;
    }
}

/**
 * 發送串流 API 請求（Server-Sent Events）
 * @param {string} endpoint - API 端點
 * @param {object} body - 請求 body
 * @param {function|null} onThinking - AI 思考中回呼（可選）
 * @param {function} onContent - 內容片段回呼
 * @param {function|null} onError - 錯誤回呼（可選）
 * @param {function|null} onDone - 完成回呼（可選），會收到一個布林參數 success
 * @param {function|null} onRetrying - 重試中回呼（可選）
 */
export async function streamAPI(endpoint, body, onThinking, onContent, onError, onDone, onRetrying, onEvent) {
    let attempt = 0;
    let streamHadFinalError = false;

    // Auto-inject stream and force_json settings
    if (body && typeof body === 'object') {
        body.options = {
            ...(body.options || {}),
            stream: true
        };
    }
    assertCanonicalGenerationPayload(endpoint, body);

    // Trigger start callback
    if (typeof window.onStreamAPIStart === 'function') {
        try {
            window.onStreamAPIStart(endpoint, body);
        } catch (e) {
            console.error("Error in onStreamAPIStart callback:", e);
        }
    }

    async function makeAttempt() {
        attempt++;
        const controller = new AbortController();
        const signal = controller.signal;

        let activityTimer = null;
        const STALL_TIMEOUT = 300000; // 300 seconds (5 minutes) - Director timeout set to 5 mins
        const CONNECT_TIMEOUT = 300000; // 300 seconds (5 minutes) - Director connect timeout set to 5 mins
        let connectTimer = null;

        function resetActivityTimer() {
            if (activityTimer) clearTimeout(activityTimer);
            activityTimer = setTimeout(() => {
                console.warn(`[streamAPI] Stalled! No stream activity for ${STALL_TIMEOUT / 1000}s on ${endpoint}. Aborting attempt ${attempt}...`);
                controller.abort();
            }, STALL_TIMEOUT);
        }

        connectTimer = setTimeout(() => {
            console.warn(`[streamAPI] Connect timeout! No response headers after ${CONNECT_TIMEOUT / 1000}s on ${endpoint}. Aborting attempt ${attempt}...`);
            controller.abort();
        }, CONNECT_TIMEOUT);

        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
                signal: signal
            });
            
            if (connectTimer) { clearTimeout(connectTimer); connectTimer = null; }
            resetActivityTimer();

            if (!response.ok) {
                if (response.status === 429) {
                    const errData429 = await response.json().catch(() => ({ detail: '此小說的流水線正在執行中，請等待完成。' }));
                    const msg429 = errData429.detail || '此小說的流水線正在執行中，請等待完成。';
                    if (typeof onError === 'function') onError(msg429, false);
                    if (typeof onDone === 'function') await onDone(false);
                    return;
                }
                const errText = await response.text();
                throw new Error(`HTTP 錯誤 ${response.status}: ${errText}`);
            }
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';
            let localHadError = false;
            let sawTerminalEnvelope = false;
            
            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                
                resetActivityTimer(); // Got a stream chunk, reset timer

                buffer += decoder.decode(value, { stream: true });
                
                // Split buffer by newlines to get complete lines
                const parts = buffer.split('\n');
                // The last element is kept in the buffer since it might be incomplete
                buffer = parts.pop();
                const lines = parts;
                
                // Accumulate deltas for this read chunk to avoid layout trashing
                let accumulatedThinking = '';
                let accumulatedContent = '';
                let hasReset = false;
                
                for (const line of lines) {
                    const trimmed = line.trim();
                    if (!trimmed || !trimmed.startsWith('data:')) continue;
                    
                    try {
                        const dataStr = trimmed.slice(5).trim();
                        if (dataStr === '[DONE]') continue;
                        const parsed = JSON.parse(dataStr);
                        
                        if (typeof onEvent === 'function') {
                            try { onEvent(parsed); } catch(err) { console.error(err); }
                        }

                        if (parsed.type === 'done' || parsed.status === 'completed' || parsed.status === 'failed') {
                            sawTerminalEnvelope = true;
                        }

                        if (parsed.type === 'reset') {
                            hasReset = true;
                        } else if (parsed.type === 'thinking') {
                            accumulatedThinking += parsed.delta;
                        } else if (parsed.type === 'content') {
                            accumulatedContent += parsed.delta;
                        } else if (parsed.type === 'error') {
                            localHadError = true;
                            streamHadFinalError = true;
                            const msg = parsed.message
                                || parsed.error
                                || parsed.detail
                                || parsed.result?.error
                                || parsed.result?.message
                                || '生成失敗';
                            if (typeof onError === 'function') onError(msg, false);
                        } else if (parsed.type === 'retrying') {
                            if (typeof onRetrying === 'function') onRetrying(parsed.message);
                        } else if (parsed.type === 'partial_state' || parsed.type === 'status' || parsed.type === 'need_characters') {
                            // 總監分段調度：即時回填與進度事件走全域 hook
                            // need_characters 也需走同一管線以觸發角色補充提醒
                            try {
                                if (typeof window.handleGenerationEvent === 'function') {
                                    window.handleGenerationEvent(parsed, endpoint);
                                }
                            } catch (evErr) { console.error('handleGenerationEvent error:', evErr); }
                        }
                    } catch (e) {
                        // 忽略 JSON 解析錯誤
                    }
                }
                
                // Flush accumulated deltas
                if (hasReset) {
                    // Signal reset with null to tell downstream handlers to clear their content
                    if (typeof onThinking === 'function') onThinking(null);
                    if (typeof onContent === 'function') onContent(null);
                    // Discard any accumulated content from before the reset
                    accumulatedThinking = '';
                    accumulatedContent = '';
                }
                if (accumulatedThinking) {
                    if (typeof onThinking === 'function') onThinking(accumulatedThinking);
                }
                if (accumulatedContent) {
                    if (typeof onContent === 'function') onContent(accumulatedContent);
                }
            }

            if (!sawTerminalEnvelope) {
                throw new Error('串流未收到後端完成封包即中斷');
            }
            
            if (activityTimer) clearTimeout(activityTimer);

            // Trigger end callback
            if (typeof window.onStreamAPIEnd === 'function') {
                try {
                    window.onStreamAPIEnd(endpoint, body);
                } catch (e) {}
            }

            // 傳遞 success 狀態給 onDone（讓前端可以區分成功/失敗）
            if (typeof onDone === 'function') await onDone(!localHadError);
        } catch (err) {
            if (connectTimer) { clearTimeout(connectTimer); connectTimer = null; }
            if (activityTimer) clearTimeout(activityTimer);

            const isAborted = err.name === 'AbortError';
            const isServerError = err.message.includes('HTTP 錯誤 5');
            const isInterruptedStream = err.message.includes('串流未收到後端完成封包');
            const isConnectionError = isAborted || isInterruptedStream || err.message.includes('FetchError') || err.message.includes('網路連接') || isServerError;
            if (isConnectionError) {
                const delayMs = Math.min(30000, 2000 + Math.min(attempt, 14) * 2000);
                console.warn(`[streamAPI] Stream interrupted at attempt ${attempt} (${err.message}). Retrying in ${delayMs / 1000}s...`);
                if (typeof onRetrying === 'function') {
                    onRetrying(`串流中斷，正在自動重送第 ${attempt + 1} 次`);
                }
                await new Promise(r => setTimeout(r, delayMs));
                return makeAttempt();
            }

            // Trigger end callback on error
            if (typeof window.onStreamAPIEnd === 'function') {
                try {
                    window.onStreamAPIEnd(endpoint, body);
                } catch (e) {}
            }

            streamHadFinalError = true;
            if (typeof onError === 'function') {
                onError(
                    isAborted ? `生成超時卡死，已中斷。` : `網路連接錯誤: ${err.message}`,
                    isConnectionError
                );
            }
            // 錯誤時也以 success=false 調用 onDone，確保 Promise 能結束
            if (typeof onDone === 'function') await onDone(false);
        }
    }

    return makeAttempt();
}

// Expose globally for modules/scripts that rely on window.streamAPI
window.streamAPI = streamAPI;
window.requestAPI = requestAPI;

