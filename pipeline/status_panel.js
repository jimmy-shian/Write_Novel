// -*- coding: utf-8 -*-
export function renderSubAgentStatus(statusData) {
    const container = document.getElementById('sub-agent-status-panel');
    if (!container) return;
    
    container.innerHTML = '';
    
    const agents = [
        { key: 'architect', label: '故事架構師' },
        { key: 'character', label: '角色設計師' },
        { key: 'foreshadowing', label: '伏筆編織師' },
        { key: 'volumes', label: '篇卷規劃師' },
        { key: 'volume_skeleton', label: '骨架規劃師' },
        { key: 'writer', label: '正文寫作' },
        { key: 'editor', label: '編輯潤色' },
    ];
    
    agents.forEach(({ key, label }) => {
        const status = statusData[key] || 'idle';
        const dot = { running: '🟡', done: '🟢', error: '🔴', idle: '⚪' }[status] || '⚪';
        const row = document.createElement('div');
        row.className = 'agent-status-row';
        row.style.margin = '4px 0';
        row.style.display = 'flex';
        row.style.alignItems = 'center';
        row.style.fontSize = '14px';
        row.innerHTML = `<span style="margin-right: 8px;">${dot}</span><span>${label} (${status})</span>`;
        container.appendChild(row);
    });
}
