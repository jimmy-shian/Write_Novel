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
    const MAX_RETRIES = 1;
    let attempt = 0;
    let streamHadFinalError = false;

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
        const isHeavyEndpoint = /foreshadowing|worldview|volumes|architect/i.test(endpoint);
        const STALL_TIMEOUT = isHeavyEndpoint ? 120000 : 60000;
        const CONNECT_TIMEOUT = 30000;
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
                
                // 改進：更智能地處理 SSE 行分割
                // 確保完整的 "data:" 行被正確識別
                const lines = [];
                let searchFrom = 0;
                let dataIndex;
                
                while ((dataIndex = buffer.indexOf('data:', searchFrom)) !== -1) {
                    // 找到 "data:" 的位置
                    // 從這個位置開始查找行結束（\n，但雙換行 \n\n 是事件分隔符）
                    let lineEnd = buffer.indexOf('\n', dataIndex);
                    
                    if (lineEnd === -1) {
                        // 沒有換行，整個剩餘 buffer 構成不完整行
                        break;
                    }
                    
                    // 檢查這是否是一個完整的事件（可能包含 \n\n 作為結束標記）
                    // SSE 事件之間用雙換行分隔
                    let nextDataIndex = buffer.indexOf('data:', dataIndex + 5);
                    
                    // 如果下一個 "data:" 在當前行的換行之前，說明這是一個完整事件
                    if (nextDataIndex !== -1 && nextDataIndex < lineEnd) {
                        // 多個 data: 在同一行（不尋常但可能）
                        lineEnd = nextDataIndex - 1;
                    }
                    
                    const line = buffer.substring(dataIndex, lineEnd);
                    lines.push(line);
                    
                    // 如果下一個 "data:" 在當前換行之後，需要找到實際的事件結束
                    // 實際上，我們只需要確保我們取到了一個完整的 data: 行
                    // 更新 searchFrom
                    searchFrom = lineEnd + 1;
                }
                
                // 剩餘的 buffer（不包含完整 data: 行的部分）
                buffer = searchFrom > 0 ? buffer.substring(searchFrom) : buffer;
                
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
                    if (typeof onThinking === 'function') onThinking("[RESET]");
                    if (typeof onContent === 'function') onContent("[RESET]");
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

