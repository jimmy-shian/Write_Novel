// ==========================================
// SYSTEM SETTINGS CONTROLS - 系統設定管理
// ==========================================

import { state } from './state.js';
import { el } from './dom.js';
import { showToast } from './toast.js';
import { requestAPI } from './api.js';

/**
 * 載入系統設定
 */
export async function loadSettings() {
    try {
        state.settingsData = await requestAPI('/api/settings');
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
        const presetModels = ["nvidia/nemotron-3-super-120b-a12b", "openai/gpt-oss-120b", "minimaxai/minimax-m2.7", "mistralai/mistral-small-4-119b-2603", "stepfun-ai/step-3.5-flash", "google/gemma-3n-e4b-it", "qwen/qwen3.5-122b-a10b"];
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
    
    const tempRaw = el.settingTemperature.value.trim();
    const temperature = tempRaw === '' ? 0.7 : (isNaN(parseFloat(tempRaw)) ? 0.7 : parseFloat(tempRaw));
    
    const topPRaw = el.settingTopP.value.trim();
    const top_p = topPRaw === '' ? 0.95 : (isNaN(parseFloat(topPRaw)) ? 0.95 : parseFloat(topPRaw));
    
    const payload = {
        agent_name: agentName,
        api_key: el.settingApiKey.value,
        base_url: el.settingBaseUrl.value,
        model: el.settingModel.value,
        temperature: temperature,
        top_p: top_p,
        max_tokens: parseInt(el.settingMaxTokens.value) || 4096,
        enable_thinking: el.settingEnableThinking.checked ? 1 : 0
    };
    
    try {
        await requestAPI('/api/settings', 'POST', payload);
        showToast(`${agentName} 設定保存成功`);
        loadSettings(); // refresh state
    } catch (e) {
        showToast("設定保存失敗");
    }
}