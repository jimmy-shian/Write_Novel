import { state } from '../core/state.js';
import { el } from '../core/dom.js';

// 全局：最後一個串流終端，用於保留最近的串流內容
let lastStreamTerminal = null;
let lastStreamContent = '';

/**
 * 切換到串流頁籤
 */
export function switchToStreamTab() {
    const streamBtn = document.getElementById('tab-stream');
    const directorBtn = document.getElementById('tab-director');
    const streamContent = document.getElementById('tab-content-stream');
    const directorContent = document.getElementById('tab-content-director');
    
    if (streamBtn && streamContent && directorContent) {
        streamBtn.classList.add('active');
        directorBtn.classList.remove('active');
        streamContent.classList.add('active');
        directorContent.classList.remove('active');
    }
}

/**
 * 取得串流內容區域
 */
function getStreamContentArea() {
    return document.getElementById('stream-content-area');
}

export function showAgentProcessingIndicator(tabName, agentName) {
    let indicator = null;
    let navTab = null;
    
    if (tabName === 'worldview') {
        indicator = el.agentProcessingWorldview;
        navTab = document.querySelector('[data-tab="worldview"]');
    } else if (tabName === 'characters') {
        indicator = document.getElementById('agent-processing-characters');
        navTab = document.querySelector('[data-tab="characters"]');
    } else if (tabName === 'plot') {
        indicator = document.getElementById('agent-processing-plot');
        navTab = document.querySelector('[data-tab="plot"]');
    } else if (tabName === 'writer') {
        indicator = document.getElementById('agent-processing-writer');
        navTab = document.querySelector('[data-tab="writer"]');
    }
    
    if (indicator) {
        indicator.classList.remove('hidden');
        indicator.classList.add('has-terminal');
        const textEl = indicator.querySelector('.processing-text');
        if (textEl && agentName) {
            textEl.innerHTML = `<strong>${agentName}</strong> 正在處理中，請稍候...`;
        }
    }
    
    if (navTab) {
        navTab.classList.add('processing');
    }
    
    // 在右側串流頁籤中進行顯示隱藏切換，保留最近一次內容
    const streamArea = getStreamContentArea();
    if (streamArea) {
        // 隱藏空狀態
        const emptyState = streamArea.querySelector('.stream-empty-state');
        if (emptyState) {
            emptyState.style.display = 'none';
        }
        
        // 隱藏所有的串流終端區塊
        const terminals = streamArea.querySelectorAll('.agent-stream-output');
        terminals.forEach(term => {
            term.classList.add('hidden');
            term.classList.remove('active');
        });
        
        // 【單一化終端重構】：不再動態創建 stream-output-${tabName} 盒子
        // 全面改用原生的 #stream-output-terminal 統一終端
        let terminal = document.getElementById('stream-output-terminal');
        if (terminal) {
            // 確保原生終端可見
            terminal.classList.remove('hidden');
            terminal.classList.add('active');
            // 保存引用
            lastStreamTerminal = terminal;
            lastStreamContent = '';
        }
        
        // 串流開始時切換到串流頁籤 (僅在初始化時觸發 1 次)
        switchToStreamTab();
    }
}

export function hideAgentProcessingIndicator(tabName) {
    let indicator = null;
    let navTab = null;
    
    if (tabName === 'worldview') {
        indicator = el.agentProcessingWorldview;
        navTab = document.querySelector('[data-tab="worldview"]');
    } else if (tabName === 'characters') {
        indicator = document.getElementById('agent-processing-characters');
        navTab = document.querySelector('[data-tab="characters"]');
    } else if (tabName === 'plot') {
        indicator = document.getElementById('agent-processing-plot');
        navTab = document.querySelector('[data-tab="plot"]');
    } else if (tabName === 'writer') {
        indicator = document.getElementById('agent-processing-writer');
        navTab = document.querySelector('[data-tab="writer"]');
    }
    
    if (indicator) {
        indicator.classList.add('hidden');
        indicator.classList.remove('has-terminal');
    }
    
    if (navTab) {
        navTab.classList.remove('processing');
    }
    
    // 不再移除串流終端，保留最後一次內容在右側串流頁籤中
}

export function hideAllAgentProcessingIndicators() {
    document.querySelectorAll('.agent-processing-indicator').forEach(ind => {
        ind.classList.add('hidden');
    });
    document.querySelectorAll('.nav-tab.processing').forEach(tab => {
        tab.classList.remove('processing');
    });
}

/**
 * 取得最後一個串流終端，用於寫入內容
 */
export function getLastStreamTerminal() {
    return lastStreamTerminal;
}

/**
 * 更新最後一個串流內容
 */
export function updateLastStreamContent(content) {
    lastStreamContent = content;
}

/**
 * 取得最後一個串流內容
 */
export function getLastStreamContent() {
    return lastStreamContent;
}

/**
 * 切換到總監頁籤
 */
export function switchToDirectorTab() {
    const streamBtn = document.getElementById('tab-stream');
    const directorBtn = document.getElementById('tab-director');
    const streamContent = document.getElementById('tab-content-stream');
    const directorContent = document.getElementById('tab-content-director');
    
    if (streamBtn && streamContent && directorContent) {
        streamBtn.classList.remove('active');
        directorBtn.classList.add('active');
        streamContent.classList.remove('active');
        directorContent.classList.add('active');
    }
}


