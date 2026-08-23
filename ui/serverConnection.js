import { getAPIBase, setAPIBase, getHFToken, setHFToken } from '../api/api.js';
import { showToast } from '../core/toast.js';
import { loadNovels } from './novelLifecycle.js';
import { injectCloudButtonIfWebOrConfigured } from './autonomousDashboard.js';

/**
 * 自動將任何形式的 Space 網址或本機網址正規化為正確的 API 端點
 */
export function normalizeBackendUrl(url) {
    if (!url) return '';
    let clean = url.trim().replace(/\/+$/, '');
    
    // 解析 Hugging Face Space 頁面網址: https://huggingface.co/spaces/{owner}/{name}
    const hfPageMatch = clean.match(/huggingface\.co\/spaces\/([^/]+)\/([^/]+)/i);
    if (hfPageMatch) {
        const owner = hfPageMatch[1].toLowerCase().replace(/_/g, '-');
        const name = hfPageMatch[2].toLowerCase().replace(/_/g, '-');
        return `https://${owner}-${name}.hf.space`;
    }
    
    // 解析簡寫格式: owner/repo (如 xxx/xxx)
    const shortMatch = clean.match(/^([a-zA-Z0-9_-]+)\/([a-zA-Z0-9_-]+)$/);
    if (shortMatch && !clean.startsWith('http')) {
        const owner = shortMatch[1].toLowerCase().replace(/_/g, '-');
        const name = shortMatch[2].toLowerCase().replace(/_/g, '-');
        return `https://${owner}-${name}.hf.space`;
    }
    
    // 若未輸入協定前綴，預設加上 https://
    if (!clean.startsWith('http://') && !clean.startsWith('https://')) {
        clean = 'https://' + clean;
    }
    return clean;
}

export function initServerConnection() {
    createBackendModalDOM();
    setupConnectionDOM();
    updateConnectionStatusUI();
    
    // 若在 GitHub Pages 且尚未設定後端網址，自動彈出設定引導視窗
    if (typeof window !== 'undefined' && window.location.hostname.includes('github.io') && !getAPIBase()) {
        setTimeout(() => {
            openBackendModal(true);
        }, 600);
    }
}

function createBackendModalDOM() {
    if (document.getElementById('modal-backend-server')) return;

    const modal = document.createElement('div');
    modal.id = 'modal-backend-server';
    modal.className = 'modal-overlay';
    modal.innerHTML = `
        <div class="modal-card" style="max-width: 560px; padding: 24px; border-radius: 16px;">
            <div class="modal-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; border-bottom: 1px solid var(--border-color); padding-bottom: 12px;">
                <h2 style="font-size: 1.35rem; font-weight: 700; display: flex; align-items: center; gap: 10px; color: var(--text-primary);">
                    <span>🌐</span> 自訂後端伺服器連線
                </h2>
                <button class="btn-close-modal" id="btn-close-backend-modal" style="background: none; border: none; font-size: 1.5rem; cursor: pointer; color: var(--text-muted);">✕</button>
            </div>
            <div class="modal-body">
                <p style="font-size: 1.05rem; color: var(--text-secondary); margin-bottom: 18px; line-height: 1.6;">
                    請輸入您的個人後端服務網址。本系統前端完全不寫死任何後端位址，一切由您自主掌控。
                </p>
                
                <div class="form-group" style="margin-bottom: 16px;">
                    <label style="display: block; font-weight: 600; margin-bottom: 8px; font-size: 1.05rem;">
                        1️⃣ 後端伺服器網址 (Backend Base URL)
                    </label>
                    <input type="text" id="input-backend-url" class="form-control" placeholder="例如：https://xxx-xxx.hf.space 或 https://huggingface.co/spaces/xxx/xxx" style="width: 100%; font-family: monospace; font-size: 1.05rem; padding: 12px; border-radius: 8px; border: 1px solid var(--border-color); background: var(--bg-primary); color: var(--text-primary);">
                </div>

                <div class="form-group" style="margin-bottom: 18px;">
                    <label style="display: block; font-weight: 600; margin-bottom: 8px; font-size: 1.05rem;">
                        2️⃣ Hugging Face Access Token <span style="font-weight: normal; color: var(--text-muted); font-size: 0.9rem;">(若 Space 設為 Private 則必填)</span>
                    </label>
                    <input type="password" id="input-backend-token" class="form-control" placeholder="貼上您的 HF Token (如 hf_...)" style="width: 100%; font-family: monospace; font-size: 1.05rem; padding: 12px; border-radius: 8px; border: 1px solid var(--border-color); background: var(--bg-primary); color: var(--text-primary);">
                    <p style="font-size: 0.9rem; color: var(--text-muted); margin-top: 6px;">
                        💡 此 Token 僅加密保存在您個人瀏覽器中，用於通過 Private Space 的身份驗證，不會公開外洩。
                    </p>
                </div>

                <div id="backend-test-result" style="font-size: 1.05rem; margin-bottom: 18px; padding: 12px 16px; border-radius: 8px; display: none; line-height: 1.5;"></div>
                
                <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 20px; gap: 12px; flex-wrap: wrap;">
                    <button id="btn-test-backend" class="btn btn-secondary" style="font-size: 1.05rem; padding: 10px 18px; font-weight: 600;">🔍 測試連線</button>
                    <div style="display: flex; gap: 10px;">
                        <button id="btn-clear-backend" class="btn btn-ghost" style="font-size: 1.05rem; padding: 10px 14px;">重設</button>
                        <button id="btn-save-backend" class="btn btn-primary" style="font-size: 1.05rem; padding: 10px 22px; font-weight: 700;">💾 儲存並連線</button>
                    </div>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
}

export function openBackendModal(isFirstTime = false) {
    createBackendModalDOM();
    const modal = document.getElementById('modal-backend-server');
    const inputUrl = document.getElementById('input-backend-url');
    const inputToken = document.getElementById('input-backend-token');
    const resultDiv = document.getElementById('backend-test-result');
    if (!modal) return;

    if (inputUrl) inputUrl.value = getAPIBase() || '';
    if (inputToken) inputToken.value = getHFToken() || '';
    if (resultDiv) {
        resultDiv.style.display = 'none';
        resultDiv.textContent = '';
    }
    modal.classList.add('active');
}

export function closeBackendModal() {
    const modal = document.getElementById('modal-backend-server');
    if (modal) modal.classList.remove('active');
}

export async function testBackendConnection(targetUrl, targetToken) {
    const cleanUrl = normalizeBackendUrl(targetUrl);
    if (!cleanUrl) {
        return { success: false, message: '請輸入後端網址！' };
    }

    try {
        let testEndpoint = `${cleanUrl}/api/pipeline/auto-status`;
        if (cleanUrl.includes('hf.space')) {
            testEndpoint = `${cleanUrl}/gradio_api/novel/pipeline/auto-status`;
        }

        const headers = { 'Accept': 'application/json' };
        const token = (targetToken !== undefined ? targetToken : getHFToken()) || '';
        if (token.trim()) {
            headers['Authorization'] = `Bearer ${token.trim()}`;
        }

        const res = await fetch(testEndpoint, { method: 'GET', headers });
        if (res.ok) {
            const data = await res.json().catch(() => ({}));
            return { 
                success: true, 
                normalizedUrl: cleanUrl,
                message: `✅ 連線成功！後端狀態: ${data.status_message || '運作中'}` 
            };
        } else if (res.status === 401 || res.status === 404) {
            return { 
                success: false, 
                normalizedUrl: cleanUrl,
                message: `⚠️ 連線驗證失敗 (HTTP ${res.status}): 若您的 Space 設為 Private，請填寫正確的 Hugging Face Access Token！` 
            };
        } else {
            return { 
                success: false, 
                normalizedUrl: cleanUrl,
                message: `⚠️ 連線失敗 (HTTP ${res.status}): 請確認 Space 是否已啟動。` 
            };
        }
    } catch (e) {
        return { 
            success: false, 
            normalizedUrl: cleanUrl,
            message: `❌ 無法連線 (${e.message})：請確認網址與網路連線。` 
        };
    }
}

export async function updateConnectionStatusUI() {
    const dot = document.getElementById('backend-status-dot');
    const label = document.getElementById('backend-status-label');
    const base = getAPIBase();

    if (!dot || !label) return;

    if (!base) {
        if (typeof window !== 'undefined' && window.location.hostname.includes('github.io')) {
            dot.style.background = '#f59e0b'; // 黃色
            label.textContent = '⚠️ 請設定後端網址';
        } else {
            dot.style.background = '#10b981'; // 綠色
            label.textContent = '🟢 本機伺服器連線中';
        }
        return;
    }

    dot.style.background = '#3b82f6'; // 藍色檢測中
    label.textContent = '🔄 檢測連線中...';

    const testRes = await testBackendConnection(base);
    if (testRes.success) {
        dot.style.background = '#10b981'; // 綠色
        label.textContent = '🟢 雲端後端已連線';
    } else {
        dot.style.background = '#ef4444'; // 紅色
        label.textContent = '🔴 連線異常 (點擊修改)';
    }
    
    injectCloudButtonIfWebOrConfigured();
}

function setupConnectionDOM() {
    createBackendModalDOM();
    const btnOpen = document.getElementById('btn-backend-server');
    const btnClose = document.getElementById('btn-close-backend-modal');
    const btnSave = document.getElementById('btn-save-backend');
    const btnTest = document.getElementById('btn-test-backend');
    const btnClear = document.getElementById('btn-clear-backend');
    const inputUrl = document.getElementById('input-backend-url');
    const inputToken = document.getElementById('input-backend-token');
    const resultDiv = document.getElementById('backend-test-result');

    if (btnOpen) {
        btnOpen.addEventListener('click', () => openBackendModal(false));
    }

    if (btnClose) {
        btnClose.addEventListener('click', closeBackendModal);
    }

    if (btnTest && inputUrl && resultDiv) {
        btnTest.addEventListener('click', async () => {
            resultDiv.style.display = 'block';
            resultDiv.style.background = 'rgba(59, 130, 246, 0.1)';
            resultDiv.style.color = '#3b82f6';
            resultDiv.textContent = '🔍 正在測試連線...';

            const tokenVal = inputToken ? inputToken.value.trim() : '';
            const res = await testBackendConnection(inputUrl.value, tokenVal);
            if (res.normalizedUrl && res.normalizedUrl !== inputUrl.value.trim()) {
                inputUrl.value = res.normalizedUrl;
            }
            resultDiv.style.background = res.success ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)';
            resultDiv.style.color = res.success ? '#10b981' : '#ef4444';
            resultDiv.textContent = res.message;
        });
    }

    if (btnSave && inputUrl) {
        btnSave.addEventListener('click', async () => {
            const rawVal = inputUrl.value.trim();
            const normalized = normalizeBackendUrl(rawVal);
            const tokenVal = inputToken ? inputToken.value.trim() : '';
            
            setAPIBase(normalized);
            setHFToken(tokenVal);
            
            if (normalized) inputUrl.value = normalized;
            closeBackendModal();
            showToast('已儲存後端伺服器與憑證設定！', 'success');
            await updateConnectionStatusUI();
            
            // 重新載入小說清單
            await loadNovels();
        });
    }

    if (btnClear && inputUrl) {
        btnClear.addEventListener('click', async () => {
            setAPIBase('');
            setHFToken('');
            inputUrl.value = '';
            if (inputToken) inputToken.value = '';
            closeBackendModal();
            showToast('已重設為預設伺服器設定', 'info');
            await updateConnectionStatusUI();
            await loadNovels();
        });
    }
}
