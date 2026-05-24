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
 * @param {function|null} onDone - 完成回呼（可選）
 */
export async function streamAPI(endpoint, body, onThinking, onContent, onError, onDone) {
    const MAX_RETRIES = 2;
    let attempt = 0;

    async function makeAttempt() {
        attempt++;
        const controller = new AbortController();
        const signal = controller.signal;

        let activityTimer = null;
        const STALL_TIMEOUT = 60000; // 60 seconds stall timeout

        function resetActivityTimer() {
            if (activityTimer) clearTimeout(activityTimer);
            activityTimer = setTimeout(() => {
                console.warn(`[streamAPI] Stalled! No stream activity for ${STALL_TIMEOUT / 1000}s on ${endpoint}. Aborting attempt ${attempt}...`);
                controller.abort();
            }, STALL_TIMEOUT);
        }

        // Start initial timer
        resetActivityTimer();

        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
                signal: signal
            });
            
            resetActivityTimer(); // Got response headers, reset timer

            if (!response.ok) {
                const errText = await response.text();
                throw new Error(`HTTP 錯誤 ${response.status}: ${errText}`);
            }
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';
            
            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                
                resetActivityTimer(); // Got a stream chunk, reset timer

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop(); 
                
                for (const line of lines) {
                    const trimmed = line.trim();
                    if (!trimmed || !trimmed.startsWith('data:')) continue;
                    
                    try {
                        const dataStr = trimmed.slice(5).trim();
                        if (dataStr === '[DONE]') continue;
                        const parsed = JSON.parse(dataStr);
                        
                        if (parsed.type === 'thinking') {
                            if (typeof onThinking === 'function') onThinking(parsed.delta);
                        } else if (parsed.type === 'content') {
                            if (typeof onContent === 'function') onContent(parsed.delta);
                        } else if (parsed.type === 'error') {
                            if (typeof onError === 'function') onError(parsed.message);
                        }
                    } catch (e) {
                        // Ignore JSON parsing errors for partial chunks
                    }
                }
            }
            
            if (activityTimer) clearTimeout(activityTimer);

            if (typeof onDone === 'function') onDone();
        } catch (err) {
            if (activityTimer) clearTimeout(activityTimer);

            const isAborted = err.name === 'AbortError';
            if ((isAborted || err.message.includes('FetchError') || err.message.includes('網路連接') || err.message.includes('HTTP 錯誤 5')) && attempt <= MAX_RETRIES) {
                console.warn(`[streamAPI] Attempt ${attempt} failed or aborted (${err.message}). Retrying in 3 seconds...`);
                // Wait 3 seconds before retrying
                await new Promise(r => setTimeout(r, 3000));
                return makeAttempt();
            }

            if (typeof onError === 'function') {
                onError(isAborted ? `生成超時卡死，已嘗試 ${attempt} 次重新請求失敗。` : `網路連接錯誤: ${err.message}`);
            }
            if (typeof onDone === 'function') onDone();
        }
    }

    return makeAttempt();
}

// Expose globally for modules/scripts that rely on window.streamAPI
window.streamAPI = streamAPI;
window.requestAPI = requestAPI;