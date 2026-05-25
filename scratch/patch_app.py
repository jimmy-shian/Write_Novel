import os

app_js_path = r"c:\Users\user\Desktop\test_html\新增資料夾\Write_Novel\static\app.js"
app_js_tmp = app_js_path + ".tmp"

with open(app_js_path, "r", encoding="utf-8") as f:
    content = f.read()

# Replacement 1: smartScrollToBottom & updateAgentStreamOutput
old_update_output = """window.updateAgentStreamOutput = function(tabName, delta) {
    const terminal = document.getElementById(`stream-output-${tabName}`);
    if (!terminal) return;
    
    // 智能捲動：記錄是否已經綁定捲動事件監聽器
    if (!terminal._smartScrollInitialized) {
        terminal._smartScrollInitialized = true;
        terminal._userScrolled = false;
        
        // 監聽使用者手動捲動事件
        terminal.addEventListener('scroll', function() {
            // 檢查是否接近底部（容差 50px）
            const isNearBottom = terminal.scrollTop + terminal.clientHeight >= terminal.scrollHeight - 50;
            terminal._userScrolled = !isNearBottom;
        });
    }
    
    // 追加內容
    terminal.textContent += delta;
    
    // 只有在未手動捲動（已在底部）或首次更新時才自動捲動到底部
    if (!terminal._userScrolled || terminal.scrollTop + terminal.clientHeight >= terminal.scrollHeight - 50) {
        terminal.scrollTop = terminal.scrollHeight;
        terminal._userScrolled = false; // 重置狀態
    }
};"""

new_update_output = """// smart scroll helper to support scroll-back
window.smartScrollToBottom = function(container, force = false) {
    if (!container) return;
    if (force) {
        container.scrollTop = container.scrollHeight;
        return;
    }
    const isNearBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 120;
    if (isNearBottom) {
        container.scrollTop = container.scrollHeight;
    }
};

function getAgentDetails(endpoint) {
    if (endpoint.includes('story-architect') || endpoint.includes('incremental-architect')) {
        return { name: '故事結構架構師 (Story Architect)', icon: '🌍' };
    } else if (endpoint.includes('character-designer')) {
        return { name: '角色設計大師 (Character Designer)', icon: '👥' };
    } else if (endpoint.includes('plot-planner')) {
        return { name: '章節劇情規劃師 (Plot Planner)', icon: '📋' };
    } else if (endpoint.includes('write-chapter')) {
        return { name: '章節寫作作家 (Chapter Writer)', icon: '✍️' };
    } else if (endpoint.includes('edit-chapter')) {
        return { name: '正文編輯編審 (Editor Agent)', icon: '✏️' };
    } else if (endpoint.includes('copilot-chat')) {
        return { name: '協同總監 (Co-pilot Novel Director)', icon: '🧠' };
    }
    return { name: 'AI Agent', icon: '🤖' };
}

window.currentActiveStreamCardId = null;

window.onStreamAPIStart = function(endpoint, body) {
    const container = document.getElementById('stream-content-area');
    if (!container) return;
    
    // Hide empty placeholder
    const emptyState = container.querySelector('.stream-empty-state');
    if (emptyState) {
        emptyState.style.display = 'none';
    }
    
    const uniqueId = 'stream-card-' + Date.now();
    window.currentActiveStreamCardId = uniqueId;
    
    const details = getAgentDetails(endpoint);
    
    const card = document.createElement('div');
    card.className = 'stream-step-card';
    card.id = uniqueId;
    card.innerHTML = `
        <div class="stream-step-header">
            <div class="step-agent-info">
                <span class="step-agent-icon">${details.icon}</span>
                <span class="step-agent-name">${details.name}</span>
            </div>
            <div class="step-status-badge">🔄 執行中...</div>
        </div>
        <div class="step-body-container">
            <div class="step-thinking-box hidden">
                <div class="step-thinking-title">🧠 思考過程 (enable_thinking)</div>
                <pre class="step-thinking-body"></pre>
            </div>
            <div class="step-content-box hidden">
                <div class="step-content-title">📝 生成內容</div>
                <pre class="step-content-body"></pre>
            </div>
        </div>
    `;
    
    container.appendChild(card);
    
    // Keep only last 5 cards
    const cards = container.querySelectorAll('.stream-step-card');
    if (cards.length > 5) {
        cards[0].remove();
    }
    
    // Scroll container to bottom
    window.smartScrollToBottom(container, true);
};

window.onStreamAPIEnd = function(endpoint) {
    if (window.currentActiveStreamCardId) {
        const card = document.getElementById(window.currentActiveStreamCardId);
        if (card) {
            const badge = card.querySelector('.step-status-badge');
            if (badge) {
                badge.textContent = '✓ 已完成';
                badge.classList.add('completed');
            }
        }
    }
    window.currentActiveStreamCardId = null;
};

window.updateAgentStreamOutput = function(tabName, delta, type = 'content') {
    // Append to the active dynamic card
    if (window.currentActiveStreamCardId) {
        const activeCard = document.getElementById(window.currentActiveStreamCardId);
        if (activeCard) {
            if (type === 'thinking') {
                const thinkingBox = activeCard.querySelector('.step-thinking-box');
                const thinkingBody = activeCard.querySelector('.step-thinking-body');
                if (thinkingBox && thinkingBody) {
                    thinkingBox.classList.remove('hidden');
                    thinkingBody.textContent += delta;
                    window.smartScrollToBottom(thinkingBody, false);
                }
            } else {
                const contentBox = activeCard.querySelector('.step-content-box');
                const contentBody = activeCard.querySelector('.step-content-body');
                if (contentBox && contentBody) {
                    contentBox.classList.remove('hidden');
                    contentBody.textContent += delta;
                    window.smartScrollToBottom(contentBody, false);
                }
            }
            
            const container = document.getElementById('stream-content-area');
            if (container) {
                window.smartScrollToBottom(container, false);
            }
        }
    }
    
    // Legacy fallback terminal support
    const terminal = document.getElementById(`stream-output-${tabName}`);
    if (terminal) {
        terminal.textContent += delta;
        window.smartScrollToBottom(terminal, false);
    }
};"""

# Replacement 2: startAgentStream stream handling
old_start_agent_stream = """function startAgentStream(endpoint, body, onContentTarget, onDoneCallback, options = {}) {
    const tabName = options.tabName || 'worldview';
    const agentName = options.agentName || 'AI Agent';
    
    // Reset thinking text, show streaming box
    el.aiThinkingStream.classList.remove('hidden');
    el.aiThinkingText.textContent = '';
    
    // Clear and focus target
    onContentTarget.value = '';
    
    // Show Agent processing indicator
    showAgentProcessingIndicator(tabName, agentName);
    
    let hasError = false; // Track error to prevent done callback
    
    streamAPI(
        endpoint,
        body,
        // onThinking
        (delta) => {
            el.aiThinkingText.textContent += delta;
            window.updateAgentStreamOutput(tabName, delta);
        },
        // onContent
        (delta) => {
            onContentTarget.value += delta;
            // auto scroll textarea to bottom while streaming
            onContentTarget.scrollTop = onContentTarget.scrollHeight;
            window.updateAgentStreamOutput(tabName, delta);
        },
        // onError
        (msg) => {
            showToast(msg);
            el.aiThinkingText.textContent += `\\n[Error: ${msg}]`;
            window.updateAgentStreamOutput(tabName, `\\n[Error: ${msg}]`);
            hasError = true;
        },"""

new_start_agent_stream = """function startAgentStream(endpoint, body, onContentTarget, onDoneCallback, options = {}) {
    const tabName = options.tabName || 'worldview';
    const agentName = options.agentName || 'AI Agent';
    
    // Reset thinking text, show streaming box
    el.aiThinkingStream.classList.remove('hidden');
    el.aiThinkingText.textContent = '';
    
    // Clear and focus target
    onContentTarget.value = '';
    
    // Show Agent processing indicator
    showAgentProcessingIndicator(tabName, agentName);
    
    let hasError = false; // Track error to prevent done callback
    
    streamAPI(
        endpoint,
        body,
        // onThinking
        (delta) => {
            el.aiThinkingText.textContent += delta;
            window.updateAgentStreamOutput(tabName, delta, 'thinking');
        },
        // onContent
        (delta) => {
            onContentTarget.value += delta;
            if (typeof window.smartScrollToBottom === 'function') {
                window.smartScrollToBottom(onContentTarget, false);
            } else {
                onContentTarget.scrollTop = onContentTarget.scrollHeight;
            }
            window.updateAgentStreamOutput(tabName, delta, 'content');
        },
        // onError
        (msg) => {
            showToast(msg);
            el.aiThinkingText.textContent += `\\n[Error: ${msg}]`;
            window.updateAgentStreamOutput(tabName, `\\n[Error: ${msg}]`, 'content');
            hasError = true;
        },"""

# Replacement 3: virtualTarget 1 (indentation 16 spaces)
old_vt1 = """                const virtualTarget = {
                    get value() { return state.writingBuffer; },
                    set value(val) {
                        state.writingBuffer = val;
                        if (state.activeChapterIndex === state.currentlyWritingChapterIndex) {
                            el.editorProse.value = val;
                            el.editorProse.scrollTop = el.editorProse.scrollHeight;
                        }
                    },
                    get scrollTop() { return el.editorProse ? el.editorProse.scrollTop : 0; },
                    set scrollTop(val) {
                        if (state.activeChapterIndex === state.currentlyWritingChapterIndex) {
                            if (el.editorProse) {
                                el.editorProse.scrollTop = val;
                            }
                        }
                    },
                    get scrollHeight() { return el.editorProse ? el.editorProse.scrollHeight : 0; }
                };"""

new_vt1 = """                const virtualTarget = {
                    get value() { return state.writingBuffer; },
                    set value(val) {
                        state.writingBuffer = val;
                        if (state.activeChapterIndex === state.currentlyWritingChapterIndex) {
                            let proseVal = val;
                            let thinkingVal = "";
                            const specialWords = ["[START_OF_PROSE]", "[正文開始]"];
                            let splitIndex = -1;
                            for (const sw of specialWords) {
                                const idx = val.indexOf(sw);
                                if (idx !== -1) {
                                    splitIndex = idx;
                                    thinkingVal = val.substring(0, idx).trim();
                                    proseVal = val.substring(idx + sw.length).trim();
                                    break;
                                }
                            }
                            if (splitIndex === -1) {
                                thinkingVal = val;
                                proseVal = "";
                            }
                            
                            if (el.editorProse) {
                                el.editorProse.value = proseVal;
                                window.smartScrollToBottom(el.editorProse, false);
                            }
                            
                            // Update thinking preview real-time
                            const thinkingPreviewText = document.getElementById('chapter-thinking-preview-text');
                            const thinkingPreview = document.getElementById('chapter-thinking-preview');
                            if (thinkingPreview && thinkingPreviewText && thinkingVal.trim()) {
                                thinkingPreview.classList.remove('hidden');
                                thinkingPreviewText.textContent = thinkingVal;
                            }
                        }
                    },
                    get scrollTop() { return el.editorProse ? el.editorProse.scrollTop : 0; },
                    set scrollTop(val) {
                        if (state.activeChapterIndex === state.currentlyWritingChapterIndex) {
                            if (el.editorProse) {
                                el.editorProse.scrollTop = val;
                            }
                        }
                    },
                    get scrollHeight() { return el.editorProse ? el.editorProse.scrollHeight : 0; }
                };"""

# Replacement 4: virtualTarget 2, 3, 4 (indentation 8 spaces)
old_vt_8 = """        const virtualTarget = {
            get value() { return state.writingBuffer; },
            set value(val) {
                state.writingBuffer = val;
                if (state.activeChapterIndex === state.currentlyWritingChapterIndex) {
                    if (el.editorProse) {
                        el.editorProse.value = val;
                        el.editorProse.scrollTop = el.editorProse.scrollHeight;
                    }
                }
            },
            get scrollTop() { return el.editorProse ? el.editorProse.scrollTop : 0; },
            set scrollTop(val) {
                if (state.activeChapterIndex === state.currentlyWritingChapterIndex) {
                    if (el.editorProse) {
                        el.editorProse.scrollTop = val;
                    }
                }
            },
            get scrollHeight() { return el.editorProse ? el.editorProse.scrollHeight : 0; }
        };"""

old_vt_8_variant = """        const virtualTarget = {
            get value() { return state.writingBuffer; },
            set value(val) {
                state.writingBuffer = val;
                if (state.activeChapterIndex === state.currentlyWritingChapterIndex) {
                    el.editorProse.value = val;
                    el.editorProse.scrollTop = el.editorProse.scrollHeight;
                }
            },
            get scrollTop() { return el.editorProse ? el.editorProse.scrollTop : 0; },
            set scrollTop(val) {
                if (state.activeChapterIndex === state.currentlyWritingChapterIndex) {
                    if (el.editorProse) {
                        el.editorProse.scrollTop = val;
                    }
                }
            },
            get scrollHeight() { return el.editorProse ? el.editorProse.scrollHeight : 0; }
        };"""

new_vt_8 = """        const virtualTarget = {
            get value() { return state.writingBuffer; },
            set value(val) {
                state.writingBuffer = val;
                if (state.activeChapterIndex === state.currentlyWritingChapterIndex) {
                    let proseVal = val;
                    let thinkingVal = "";
                    const specialWords = ["[START_OF_PROSE]", "[正文開始]"];
                    let splitIndex = -1;
                    for (const sw of specialWords) {
                        const idx = val.indexOf(sw);
                        if (idx !== -1) {
                            splitIndex = idx;
                            thinkingVal = val.substring(0, idx).trim();
                            proseVal = val.substring(idx + sw.length).trim();
                            break;
                        }
                    }
                    if (splitIndex === -1) {
                        thinkingVal = val;
                        proseVal = "";
                    }
                    
                    if (el.editorProse) {
                        el.editorProse.value = proseVal;
                        window.smartScrollToBottom(el.editorProse, false);
                    }
                    
                    // Update thinking preview real-time
                    const thinkingPreviewText = document.getElementById('chapter-thinking-preview-text');
                    const thinkingPreview = document.getElementById('chapter-thinking-preview');
                    if (thinkingPreview && thinkingPreviewText && thinkingVal.trim()) {
                        thinkingPreview.classList.remove('hidden');
                        thinkingPreviewText.textContent = thinkingVal;
                    }
                }
            },
            get scrollTop() { return el.editorProse ? el.editorProse.scrollTop : 0; },
            set scrollTop(val) {
                if (state.activeChapterIndex === state.currentlyWritingChapterIndex) {
                    if (el.editorProse) {
                        el.editorProse.scrollTop = val;
                    }
                }
            },
            get scrollHeight() { return el.editorProse ? el.editorProse.scrollHeight : 0; }
        };"""

# Replacement 5: virtualTarget 5 (indentation 4 spaces)
old_vt5 = """    const virtualTarget = {
        get value() { return state.writingBuffer; },
        set value(val) {
            state.writingBuffer = val;
            if (state.activeChapterIndex === state.currentlyWritingChapterIndex) {
                if (el.editorProse) {
                    el.editorProse.value = val;
                    el.editorProse.scrollTop = el.editorProse.scrollHeight;
                }
            }
        },
        get scrollTop() { return el.editorProse ? el.editorProse.scrollTop : 0; },
        set scrollTop(val) {
            if (state.activeChapterIndex === state.currentlyWritingChapterIndex) {
                if (el.editorProse) {
                    el.editorProse.scrollTop = val;
                }
            }
        },
        get scrollHeight() { return el.editorProse ? el.editorProse.scrollHeight : 0; }
    };"""

new_vt5 = """    const virtualTarget = {
        get value() { return state.writingBuffer; },
        set value(val) {
            state.writingBuffer = val;
            if (state.activeChapterIndex === state.currentlyWritingChapterIndex) {
                let proseVal = val;
                let thinkingVal = "";
                const specialWords = ["[START_OF_PROSE]", "[正文開始]"];
                let splitIndex = -1;
                for (const sw of specialWords) {
                    const idx = val.indexOf(sw);
                    if (idx !== -1) {
                        splitIndex = idx;
                        thinkingVal = val.substring(0, idx).trim();
                        proseVal = val.substring(idx + sw.length).trim();
                        break;
                    }
                }
                if (splitIndex === -1) {
                    thinkingVal = val;
                    proseVal = "";
                }
                
                if (el.editorProse) {
                    el.editorProse.value = proseVal;
                    window.smartScrollToBottom(el.editorProse, false);
                }
                
                // Update thinking preview real-time
                const thinkingPreviewText = document.getElementById('chapter-thinking-preview-text');
                const thinkingPreview = document.getElementById('chapter-thinking-preview');
                if (thinkingPreview && thinkingPreviewText && thinkingVal.trim()) {
                    thinkingPreview.classList.remove('hidden');
                    thinkingPreviewText.textContent = thinkingVal;
                }
            }
        },
        get scrollTop() { return el.editorProse ? el.editorProse.scrollTop : 0; },
        set scrollTop(val) {
            if (state.activeChapterIndex === state.currentlyWritingChapterIndex) {
                if (el.editorProse) {
                    el.editorProse.scrollTop = val;
                }
            }
        },
        get scrollHeight() { return el.editorProse ? el.editorProse.scrollHeight : 0; }
    };"""

# Replacement 6: director chat scroll to bottom adjustments
old_copilot_chat = """        el.chatMessagesContainer.appendChild(userMsg);
        el.chatMessagesContainer.scrollTop = el.chatMessagesContainer.scrollHeight;
        
        // Create assistant message stream bubble placeholder
        const assistantMsg = document.createElement('div');
        assistantMsg.className = 'message assistant-msg';
        const assistantTimestamp = formatTimestamp();
        assistantMsg.innerHTML = `<div class="msg-sender-row"><div class="msg-sender">Novel Director</div><div class="msg-timestamp">${assistantTimestamp}</div></div><div class="msg-content stream-typing"></div>`;
        el.chatMessagesContainer.appendChild(assistantMsg);
        el.chatMessagesContainer.scrollTop = el.chatMessagesContainer.scrollHeight;
        
        const streamTarget = assistantMsg.querySelector('.stream-typing');
        
        // Start streaming copilot response
        streamAPI(
            '/api/agent/copilot-chat',
            { novel_id: state.currentNovelId, user_message: text },
            // onThinking
            () => {}, // don't show reasoning details in chat bubble to keep it clean
            // onContent
            (delta) => {
                streamTarget.textContent += delta;
                el.chatMessagesContainer.scrollTop = el.chatMessagesContainer.scrollHeight;
            },"""

new_copilot_chat = """        el.chatMessagesContainer.appendChild(userMsg);
        window.smartScrollToBottom(el.chatMessagesContainer, true);
        
        // Create assistant message stream bubble placeholder
        const assistantMsg = document.createElement('div');
        assistantMsg.className = 'message assistant-msg';
        const assistantTimestamp = formatTimestamp();
        assistantMsg.innerHTML = `<div class="msg-sender-row"><div class="msg-sender">Novel Director</div><div class="msg-timestamp">${assistantTimestamp}</div></div><div class="msg-content stream-typing"></div>`;
        el.chatMessagesContainer.appendChild(assistantMsg);
        window.smartScrollToBottom(el.chatMessagesContainer, true);
        
        const streamTarget = assistantMsg.querySelector('.stream-typing');
        
        // Start streaming copilot response
        streamAPI(
            '/api/agent/copilot-chat',
            { novel_id: state.currentNovelId, user_message: text },
            // onThinking
            () => {}, // don't show reasoning details in chat bubble to keep it clean
            // onContent
            (delta) => {
                streamTarget.textContent += delta;
                window.smartScrollToBottom(el.chatMessagesContainer, false);
            },"""

old_run_decision_scroll = """        directorResponseContainer.innerHTML = `<div class="msg-sender-row"><div class="msg-sender">🎬 AI 總監決策中...</div><div class="msg-timestamp">${directorTimestamp}</div></div><div class="msg-content stream-typing"></div>`;
        el.chatMessagesContainer.appendChild(directorResponseContainer);
        el.chatMessagesContainer.scrollTop = el.chatMessagesContainer.scrollHeight;
        
        const streamTarget = directorResponseContainer.querySelector('.stream-typing');
        
        const userPrompt = (providedUserPrompt || '').trim()
            || (state.pipelinePrompt || '').trim()
            || (state.currentNovelData?.novel?.pipeline_prompt || '').trim()
            || '';
        
        streamAPI(
            '/api/novels/' + state.currentNovelId + '/director-decision',
            { current_stage: currentStage, user_prompt: userPrompt },
            () => {},
            (delta) => {
                streamTarget.textContent += delta;
                el.chatMessagesContainer.scrollTop = el.chatMessagesContainer.scrollHeight;
            },"""

new_run_decision_scroll = """        directorResponseContainer.innerHTML = `<div class="msg-sender-row"><div class="msg-sender">🎬 AI 總監決策中...</div><div class="msg-timestamp">${directorTimestamp}</div></div><div class="msg-content stream-typing"></div>`;
        el.chatMessagesContainer.appendChild(directorResponseContainer);
        window.smartScrollToBottom(el.chatMessagesContainer, true);
        
        const streamTarget = directorResponseContainer.querySelector('.stream-typing');
        
        const userPrompt = (providedUserPrompt || '').trim()
            || (state.pipelinePrompt || '').trim()
            || (state.currentNovelData?.novel?.pipeline_prompt || '').trim()
            || '';
        
        streamAPI(
            '/api/novels/' + state.currentNovelId + '/director-decision',
            { current_stage: currentStage, user_prompt: userPrompt },
            () => {},
            (delta) => {
                streamTarget.textContent += delta;
                window.smartScrollToBottom(el.chatMessagesContainer, false);
            },"""

old_decision_help_scroll = """        directorResponseContainer.innerHTML = `<div class="msg-sender-row"><div class="msg-sender">🎬 AI 總監二次審查中...</div><div class="msg-timestamp">${directorTimestamp}</div></div><div class="msg-content stream-typing"></div>`;
        el.chatMessagesContainer.appendChild(directorResponseContainer);
        el.chatMessagesContainer.scrollTop = el.chatMessagesContainer.scrollHeight;
        
        const streamTarget = directorResponseContainer.querySelector('.stream-typing');
        
        streamAPI(
            '/api/novels/' + state.currentNovelId + '/director-decision/help',
            { current_stage: currentStage, help_action: helpAction, help_reason: helpReason },
            () => {},
            (delta) => {
                streamTarget.textContent += delta;
                el.chatMessagesContainer.scrollTop = el.chatMessagesContainer.scrollHeight;
            },"""

new_decision_help_scroll = """        directorResponseContainer.innerHTML = `<div class="msg-sender-row"><div class="msg-sender">🎬 AI 總監二次審查中...</div><div class="msg-timestamp">${directorTimestamp}</div></div><div class="msg-content stream-typing"></div>`;
        el.chatMessagesContainer.appendChild(directorResponseContainer);
        window.smartScrollToBottom(el.chatMessagesContainer, true);
        
        const streamTarget = directorResponseContainer.querySelector('.stream-typing');
        
        streamAPI(
            '/api/novels/' + state.currentNovelId + '/director-decision/help',
            { current_stage: currentStage, help_action: helpAction, help_reason: helpReason },
            () => {},
            (delta) => {
                streamTarget.textContent += delta;
                window.smartScrollToBottom(el.chatMessagesContainer, false);
            },"""

# Replacement 7: custom inline streams scroll to bottom
old_inline_worldview = """                        if (el.editorWorldview) {
                            el.editorWorldview.value += delta;
                            el.editorWorldview.scrollTop = el.editorWorldview.scrollHeight;
                        }"""
new_inline_worldview = """                        if (el.editorWorldview) {
                            el.editorWorldview.value += delta;
                            window.smartScrollToBottom(el.editorWorldview, false);
                        }"""

old_inline_characters = """                        if (el.editorCharactersJson) {
                            el.editorCharactersJson.value += delta;
                            el.editorCharactersJson.scrollTop = el.editorCharactersJson.scrollHeight;
                        }"""
new_inline_characters = """                        if (el.editorCharactersJson) {
                            el.editorCharactersJson.value += delta;
                            window.smartScrollToBottom(el.editorCharactersJson, false);
                        }"""

old_inline_plot = """                        if (el.editorPlotJson) {
                            el.editorPlotJson.value += delta;
                            el.editorPlotJson.scrollTop = el.editorPlotJson.scrollHeight;
                        }"""
new_inline_plot = """                        if (el.editorPlotJson) {
                            el.editorPlotJson.value += delta;
                            window.smartScrollToBottom(el.editorPlotJson, false);
                        }"""

# Replacement 8: DOMContentLoaded initialization of resizer
old_init = """// ==========================================
// INITIALIZATION
// ==========================================
window.addEventListener('DOMContentLoaded', async () => {
    // 0. 初始化聊天歷史顯示
    initializeChatHistory();"""

new_init = """// ==========================================
// INITIALIZATION
// ==========================================
window.addEventListener('DOMContentLoaded', async () => {
    // Initialize Sidebar Resizer Dragging
    const resizer = document.getElementById('sidebar-right-resizer');
    const appContainer = document.getElementById('app-container');

    if (resizer && appContainer) {
        let isDragging = false;
        
        resizer.addEventListener('mousedown', function(e) {
            isDragging = true;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            e.preventDefault();
        });
        
        document.addEventListener('mousemove', function(e) {
            if (!isDragging) return;
            const newWidth = window.innerWidth - e.clientX;
            const minWidth = 300;
            const maxWidth = window.innerWidth * 0.8;
            
            if (newWidth >= minWidth && newWidth <= maxWidth) {
                appContainer.style.setProperty('--sidebar-right-width', `${newWidth}px`);
            }
        });
        
        document.addEventListener('mouseup', function() {
            if (isDragging) {
                isDragging = false;
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
            }
        });
    }

    // 0. 初始化聊天歷史顯示
    initializeChatHistory();"""

replacements = [
    (old_update_output, new_update_output, "updateAgentStreamOutput"),
    (old_start_agent_stream, new_start_agent_stream, "startAgentStream"),
    (old_vt1, new_vt1, "virtualTarget 1"),
    (old_vt_8, new_vt_8, "virtualTarget 2, 3, 4 (Standard)"),
    (old_vt_8_variant, new_vt_8, "virtualTarget 2, 3, 4 (Variant)"),
    (old_vt5, new_vt5, "virtualTarget 5"),
    (old_copilot_chat, new_copilot_chat, "copilotChat"),
    (old_run_decision_scroll, new_run_decision_scroll, "runDecisionScroll"),
    (old_decision_help_scroll, new_decision_help_scroll, "decisionHelpScroll"),
    (old_inline_worldview, new_inline_worldview, "inlineWorldviewScroll"),
    (old_inline_characters, new_inline_characters, "inlineCharactersScroll"),
    (old_inline_plot, new_inline_plot, "inlinePlotScroll"),
    (old_init, new_init, "DOMContentLoadedInit")
]

modified = content
for old, new, name in replacements:
    count = modified.count(old)
    if count > 0:
        modified = modified.replace(old, new)
        print(f"Success: Replaced '{name}' ({count} occurrences)")
    else:
        # Check if already replaced
        if new in modified:
            print(f"Skipped: '{name}' already present")
        else:
            print(f"Warning: '{name}' not found for replacement!")

with open(app_js_tmp, "w", encoding="utf-8") as f:
    f.write(modified)

os.replace(app_js_tmp, app_js_path)
print("Atomically replaced app.js successfully!")
