// ==========================================
// SYSTEM SETTINGS CONTROLS - 系統設定管理
// ==========================================

import { state } from '../core/state.js';
import { el } from '../core/dom.js';
import { showToast } from '../core/toast.js';
import { requestAPI } from '../api/api.js';

/**
 * 載入系統設定
 */
export async function loadSettings() {
    try {
        state.settingsData = await requestAPI('/api/settings');
        
        // Dynamically populate model dropdown
        if (state.settingsData._modelsConfig && el.settingPresetModel) {
            const selectEl = el.settingPresetModel;
            selectEl.innerHTML = '<option value="">-- 手動輸入或選擇預設 --</option>';
            const configObj = state.settingsData._modelsConfig;
            for (const [id, data] of Object.entries(configObj)) {
                const opt = document.createElement('option');
                opt.value = id;
                opt.textContent = data.name || data.model;
                selectEl.appendChild(opt);
            }
        }
        
        loadAgentConfigFields(state.activeSettingAgent);
    } catch (e) {
        console.error("Failed to load settings");
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
    el.settingMaxTokens.value = config.max_tokens || '';
    el.settingTemperature.value = config.temperature ?? '';
    el.settingTopP.value = config.top_p ?? '';
    el.settingEnableThinking.checked = config.enable_thinking === 1;
    
    // Auto-select match preset if it exists
    if (el.settingPresetModel) {
        let presetModels = [];
        if (state.settingsData._modelsConfig) {
            presetModels = Object.keys(state.settingsData._modelsConfig);
        }
        if (config.model && presetModels.includes(config.model)) {
            el.settingPresetModel.value = config.model;
        } else {
            el.settingPresetModel.value = "";
        }
    }
    
    // Use display_name from backend if available
    el.settingsAgentTitle.textContent = config.display_name || agentName;
}

/**
 * 儲存當前代理設定
 */
export async function saveCurrentAgentSettings() {
    const agentName = el.settingAgentName.value;

    const payload = {
        agent_name: agentName
    };

    const apiKey = el.settingApiKey.value.trim();
    if (apiKey) payload.api_key = apiKey;

    const baseUrl = el.settingBaseUrl.value.trim();
    if (baseUrl) payload.base_url = baseUrl;

    const model = el.settingModel.value.trim();
    if (model) payload.model = model;

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
        await requestAPI('/api/settings', 'POST', payload);
        showToast(`${agentName} 設定保存成功`);
        loadSettings(); // refresh state
    } catch (e) {
        showToast("設定保存失敗");
    }
}

