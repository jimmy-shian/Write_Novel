import { state } from './state.js';
import { el } from './dom.js';

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
        
        let terminal = indicator.querySelector('.agent-stream-output');
        if (!terminal) {
            terminal = document.createElement('div');
            terminal.id = `stream-output-${tabName}`;
            indicator.appendChild(terminal);
        }
        terminal.className = `agent-stream-output active${state.showStreamLog ? '' : ' hidden'}`;
        terminal.textContent = ''; 
    }
    
    if (navTab) {
        navTab.classList.add('processing');
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
        const terminal = indicator.querySelector('.agent-stream-output');
        if (terminal) {
            terminal.remove();
        }
        indicator.classList.remove('has-terminal');
    }
    
    if (navTab) {
        navTab.classList.remove('processing');
    }
}

export function hideAllAgentProcessingIndicators() {
    document.querySelectorAll('.agent-processing-indicator').forEach(ind => {
        ind.classList.add('hidden');
    });
    document.querySelectorAll('.nav-tab.processing').forEach(tab => {
        tab.classList.remove('processing');
    });
}