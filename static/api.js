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
    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        
        if (!response.ok) {
            const errText = await response.text();
            if (typeof onError === 'function') onError(`HTTP 錯誤 ${response.status}: ${errText}`);
            if (typeof onDone === 'function') onDone();
            return;
        }
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';
        
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            
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
        if (typeof onDone === 'function') onDone();
    } catch (err) {
        if (typeof onError === 'function') onError(`網路連接錯誤: ${err.message}`);
        if (typeof onDone === 'function') onDone();
    }
}