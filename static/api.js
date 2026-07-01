// ==========================================
// API WRAPPERS & STREAMING CORE
// ==========================================

/**
 * 發送一般 API 請求（非串流）
 * @param {string} url - API 端點
 * @param {string} method - HTTP 方法（預設 GET）
 * @param {object|null} body - 請求 body（預設 null）
 * @returns {Promise<object>} 解析後的 JSON 回應
 */
export async function requestAPI(url, method = 'GET', body = null) {
    try {
        const options = {
            method,
            headers: { 'Content-Type': 'application/json' }
        };
        if (body) {
            options.body = JSON.stringify(body);
        }
        const response = await fetch(url, options);
        
        if (!response.ok) {
            const errData = await response.json().catch(() => ({ detail: response.statusText }));
            throw new Error(errData.detail || response.statusText);
        }
        return await response.json();
    } catch (e) {
        console.error(`API Error: ${e.message}`);
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
export async function streamAPI(endpoint, body, onThinking, onContent, onError, onDone, onRetrying) {
    const MAX_RETRIES = 10;
    let attempt = 0;
    let streamHadFinalError = false;

    // Auto-inject stream and force_json settings
    if (body && typeof body === 'object') {
        body.stream = true;
        const structuredEndpoints = [
            'story-architect',
            'character-designer',
            'volumes-planner',
            'volume-skeleton'
        ];
        const isStructured = structuredEndpoints.some(ep => endpoint.includes(ep));
        body.force_json = isStructured;
    }

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
        const STALL_TIMEOUT = 300000; // 300 seconds
        const CONNECT_TIMEOUT = 300000; // 300 seconds
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
                    if (typeof onError === 'function') onError(msg429);
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
                        
                        if (parsed.type === 'reset') {
                            hasReset = true;
                        } else if (parsed.type === 'thinking') {
                            accumulatedThinking += parsed.delta;
                        } else if (parsed.type === 'content') {
                            accumulatedContent += parsed.delta;
                        } else if (parsed.type === 'error') {
                            localHadError = true;
                            streamHadFinalError = true;
                            if (typeof onError === 'function') onError(parsed.message);
                        } else if (parsed.type === 'retrying') {
                            if (typeof onRetrying === 'function') onRetrying(parsed.message);
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
            
            if (activityTimer) clearTimeout(activityTimer);

            // Trigger end callback
            if (typeof window.onStreamAPIEnd === 'function') {
                try {
                    window.onStreamAPIEnd(endpoint);
                } catch (e) {}
            }

            // 傳遞 success 狀態給 onDone（讓前端可以區分成功/失敗）
            if (typeof onDone === 'function') await onDone(!localHadError);
        } catch (err) {
            if (connectTimer) { clearTimeout(connectTimer); connectTimer = null; }
            if (activityTimer) clearTimeout(activityTimer);

            const isAborted = err.name === 'AbortError';
            const isServerError = err.message.includes('HTTP 錯誤 5');
            if ((isAborted || err.message.includes('FetchError') || err.message.includes('網路連接') || isServerError) && attempt <= MAX_RETRIES) {
                console.warn(`[streamAPI] Attempt ${attempt} failed or aborted (${err.message}). Retrying in 3 seconds...`);
                // Wait 3 seconds before retrying
                await new Promise(r => setTimeout(r, 3000));
                return makeAttempt();
            }

            // Trigger end callback on error
            if (typeof window.onStreamAPIEnd === 'function') {
                try {
                    window.onStreamAPIEnd(endpoint);
                } catch (e) {}
            }

            streamHadFinalError = true;
            if (typeof onError === 'function') {
                onError(isAborted ? `生成超時卡死，已嘗試 ${attempt} 次重新請求失敗。` : `網路連接錯誤: ${err.message}`);
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

