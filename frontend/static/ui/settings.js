// ==========================================
// SYSTEM SETTINGS CONTROLS - 系統設定管理
// ==========================================

import { state } from '../core/state.js';
import { el } from '../core/dom.js';
import { showToast } from '../core/toast.js';
import { requestAPI } from '../api/api.js';

// Cache fetched models per base URL to prevent redundant network calls
const modelsCache = new Map();

/**
 * 載入系統設定
 */
export async function loadSettings() {
    try {
        state.settingsData = await requestAPI('/api/settings');
        loadAgentConfigFields(state.activeSettingAgent || 'global');
    } catch (e) {
        console.error("Failed to load settings", e);
        showToast("載入設定失敗");
    }
}

/**
 * 填充模型下拉選單與 datalist
 * @param {string[]} models - 模型 ID 陣列
 * @param {string} currentModel - 當前選定的模型
 */
export function populateModelOptions(models, currentModel = '') {
    if (!el.settingModelSelect || !el.modelsDatalist) return;

    const selectEl = el.settingModelSelect;
    const datalistEl = el.modelsDatalist;

    selectEl.innerHTML = '';
    datalistEl.innerHTML = '';

    const defaultOpt = document.createElement('option');
    defaultOpt.value = '';
    defaultOpt.textContent = models.length > 0
        ? `-- 從模型清單快速選取 (共 ${models.length} 個可用模型) --`
        : '-- 尚未獲取模型清單 (請輸入 Base URL 並點擊「獲取模型清單」) --';
    selectEl.appendChild(defaultOpt);

    let matchFound = false;
    models.forEach(modelId => {
        // Dropdown option
        const opt = document.createElement('option');
        opt.value = modelId;
        opt.textContent = modelId;
        if (modelId === currentModel) {
            opt.selected = true;
            matchFound = true;
        }
        selectEl.appendChild(opt);

        // Datalist option for free typing autocomplete
        const dlOpt = document.createElement('option');
        dlOpt.value = modelId;
        datalistEl.appendChild(dlOpt);
    });

    if (!matchFound && currentModel) {
        selectEl.value = '';
    }
}

/**
 * 向端點發送請求獲取可用模型清單
 * @param {boolean} isManual - 是否由使用者手動點擊觸發
 */
export async function fetchModelsForCurrentUrl(isManual = true) {
    const baseUrl = (el.settingBaseUrl.value || '').trim();
    const apiKey = (el.settingApiKey.value || '').trim();

    if (!baseUrl) {
        if (isManual) {
            showToast("請先輸入 API Base URL");
            if (el.modelsFetchStatus) {
                el.modelsFetchStatus.textContent = "⚠️ 請先輸入 API Base URL";
                el.modelsFetchStatus.className = "settings-status-hint error";
            }
        }
        return;
    }

    // Check cache
    const cacheKey = `${baseUrl}::${apiKey}`;
    if (!isManual && modelsCache.has(cacheKey)) {
        const cached = modelsCache.get(cacheKey);
        populateModelOptions(cached, el.settingModel.value.trim());
        if (el.modelsFetchStatus) {
            el.modelsFetchStatus.textContent = `✅ 已載入 ${cached.length} 個模型 (快取)`;
            el.modelsFetchStatus.className = "settings-status-hint success";
        }
        return;
    }

    if (el.btnFetchModels) {
        el.btnFetchModels.disabled = true;
        el.btnFetchModels.textContent = "⏳ 查詢中...";
    }
    if (el.modelsFetchStatus) {
        el.modelsFetchStatus.textContent = "⏳ 正在向端點查詢模型清單...";
        el.modelsFetchStatus.className = "settings-status-hint loading";
    }

    try {
        const res = await requestAPI('/api/settings/fetch-models', 'POST', {
            base_url: baseUrl,
            api_key: apiKey
        });

        const models = res.models || [];
        modelsCache.set(cacheKey, models);

        populateModelOptions(models, el.settingModel.value.trim());

        if (el.modelsFetchStatus) {
            el.modelsFetchStatus.textContent = `✅ 成功獲取 ${models.length} 個可用模型`;
            el.modelsFetchStatus.className = "settings-status-hint success";
        }
        if (isManual) {
            showToast(`成功獲取 ${models.length} 個可用模型`);
        }
    } catch (e) {
        const errMsg = e.detail || e.message || String(e);
        console.error("Failed to fetch models:", e);
        if (el.modelsFetchStatus) {
            el.modelsFetchStatus.textContent = `❌ 獲取失敗: ${errMsg}`;
            el.modelsFetchStatus.className = "settings-status-hint error";
        }
        if (isManual) {
            showToast(`獲取模型失敗: ${errMsg}`);
        }
    } finally {
        if (el.btnFetchModels) {
            el.btnFetchModels.disabled = false;
            el.btnFetchModels.textContent = "🔍 獲取模型清單";
        }
    }
}

/**
 * 根據代理名稱載入設定欄位
 * @param {string} agentName - 代理名稱（如 'global', 'architect', 'character' 等）
 */
export function loadAgentConfigFields(agentName) {
    const config = state.settingsData[agentName] || {};
    
    el.settingAgentName.value = agentName;
    el.settingApiKey.value = config.api_key || '';
    el.settingBaseUrl.value = config.base_url || 'https://integrate.api.nvidia.com/v1';
    el.settingModel.value = config.model || '';
    el.settingMaxTokens.value = config.max_tokens ?? 16384;
    el.settingTemperature.value = config.temperature ?? 1.0;
    el.settingTopP.value = config.top_p ?? 0.95;
    el.settingEnableThinking.checked = config.enable_thinking === 1;
    
    // Update headers and badges
    el.settingsAgentTitle.textContent = config.display_name || agentName;
    if (el.settingsAgentBadge) {
        el.settingsAgentBadge.textContent = agentName === 'global'
            ? '🌐 全域預設基礎設置'
            : '💡 若留空將自動繼承 Global 設置';
    }

    // Populate model options from cache or reset status
    const baseUrl = el.settingBaseUrl.value.trim();
    const apiKey = el.settingApiKey.value.trim();
    const cacheKey = `${baseUrl}::${apiKey}`;

    if (modelsCache.has(cacheKey)) {
        const cached = modelsCache.get(cacheKey);
        populateModelOptions(cached, el.settingModel.value.trim());
        if (el.modelsFetchStatus) {
            el.modelsFetchStatus.textContent = `✅ 已載入 ${cached.length} 個可用模型`;
            el.modelsFetchStatus.className = "settings-status-hint success";
        }
    } else {
        populateModelOptions([], el.settingModel.value.trim());
        if (el.modelsFetchStatus) {
            el.modelsFetchStatus.textContent = "";
            el.modelsFetchStatus.className = "settings-status-hint";
        }
    }
}

/**
 * 儲存當前代理設定並同步寫入 .env 檔案
 */
export async function saveCurrentAgentSettings() {
    const agentName = el.settingAgentName.value;

    const payload = {
        agent_name: agentName
    };

    const apiKey = el.settingApiKey.value.trim();
    payload.api_key = apiKey;

    const baseUrl = el.settingBaseUrl.value.trim();
    payload.base_url = baseUrl;

    const model = el.settingModel.value.trim();
    payload.model = model;

    const tempRaw = el.settingTemperature.value.trim();
    if (tempRaw !== '' && !Number.isNaN(Number.parseFloat(tempRaw))) {
        payload.temperature = Number.parseFloat(tempRaw);
    }

    const topPRaw = el.settingTopP.value.trim();
    if (topPRaw !== '' && !Number.isNaN(Number.parseFloat(topPRaw))) {
        payload.top_p = Number.parseFloat(topPRaw);
    }

    const maxTokensRaw = el.settingMaxTokens.value.trim();
    if (maxTokensRaw !== '' && !Number.isNaN(Number.parseInt(maxTokensRaw, 10))) {
        payload.max_tokens = Number.parseInt(maxTokensRaw, 10);
    }

    payload.enable_thinking = el.settingEnableThinking.checked ? 1 : 0;
    
    try {
        const res = await requestAPI('/api/settings', 'POST', payload);
        showToast(`✅ ${configDisplayName(agentName)} 設定已成功儲存並同步寫入 .env！`);
        await loadSettings(); // refresh state
    } catch (e) {
        const errMsg = e.detail || e.message || String(e);
        console.error("Save settings failed:", e);
        showToast(`❌ 設定保存失敗: ${errMsg}`);
    }
}

function configDisplayName(agentName) {
    const map = {
        'global': 'Global 全域',
        'architect': 'Story Architect',
        'character': 'Character Designer',
        'volumes': 'Volumes Planner',
        'volume_skeleton': 'Skeleton Planner',
        'plot': 'Plot Planner',
        'writer': 'Chapter Writer',
        'editor': 'Editor Agent',
        'copilot': 'AI 總監 Copilot',
    };
    return map[agentName] || agentName;
}
