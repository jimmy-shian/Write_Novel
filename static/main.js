// main.js - Premium Interactive Novel Factory Pipeline Controller

let activeNovelId = null;
let currentStage = "init";
let isOneClick = true;
let currentVolIndex = 0;
let currentChIndex = 1;
let directorLoopCount = 0;

document.addEventListener("DOMContentLoaded", () => {
    initEventListeners();
});

function initEventListeners() {
    // 1. Creation Action
    document.getElementById("btnCreate").addEventListener("click", handleCreateNovel);
    
    // 2. Next Step Action
    document.getElementById("btnRunStep").addEventListener("click", runActiveStageStep);
    
    // 3. Mode Toggle Action
    const toggle = document.getElementById("oneClickToggle");
    toggle.addEventListener("change", (e) => {
        isOneClick = e.target.checked;
        const chatArea = document.getElementById("chatInputArea");
        if (isOneClick) {
            chatArea.classList.add("hidden");
        } else {
            chatArea.classList.remove("hidden");
        }
        logTerminal(`[系統] 切換為: ${isOneClick ? '一鍵自動執行模式 (自動推進設定與寫作)' : '協同對話模式 (創意總監引導打磨)'}`);
    });
    
    // 4. Collapsible Drawer Controls
    const btnToggle = document.getElementById("btnToggleTerminal");
    const terminalPanel = document.getElementById("terminalPanel");
    const floatingBtn = document.getElementById("floatingTerminalBtn");
    
    btnToggle.addEventListener("click", () => {
        terminalPanel.classList.add("hidden");
        floatingBtn.classList.remove("hidden");
        // Re-adjust grid layout when right panel is hidden
        document.querySelector(".workspace-grid").style.gridTemplateColumns = "320px 1fr";
    });
    
    floatingBtn.addEventListener("click", () => {
        terminalPanel.classList.remove("hidden");
        floatingBtn.classList.add("hidden");
        document.querySelector(".workspace-grid").style.gridTemplateColumns = "320px 1fr 380px";
    });
    
    // Chat Send message (Interactive Mode)
    document.getElementById("btnSendChat").addEventListener("click", handleSendChat);
    document.getElementById("chatInput").addEventListener("keypress", (e) => {
        if (e.key === "Enter") handleSendChat();
    });

    // 5. Settings Modal Controls
    document.getElementById("btnSettings").addEventListener("click", openSettingsModal);
    document.getElementById("btnCloseSettings").addEventListener("click", closeSettingsModal);
    document.getElementById("btnCancelSettings").addEventListener("click", closeSettingsModal);
    
    const tabGlobal = document.getElementById("btnTabGlobal");
    const tabAgents = document.getElementById("btnTabAgents");
    const globalContent = document.getElementById("globalTab");
    const agentsContent = document.getElementById("agentsTab");
    
    tabGlobal.addEventListener("click", () => {
        tabGlobal.classList.add("active");
        tabAgents.classList.remove("active");
        globalContent.classList.remove("hidden");
        agentsContent.classList.add("hidden");
    });
    
    tabAgents.addEventListener("click", () => {
        tabAgents.classList.add("active");
        tabGlobal.classList.remove("active");
        agentsContent.classList.remove("hidden");
        globalContent.classList.add("hidden");
    });
    
    document.getElementById("agentSelector").addEventListener("change", (e) => {
        loadAgentOverrideInputs(e.target.value);
    });
    
    const agentInputs = ["cfg_agent_api_key", "cfg_agent_base_url", "cfg_agent_model", "cfg_agent_temp", "cfg_agent_thinking"];
    agentInputs.forEach(id => {
        document.getElementById(id).addEventListener("input", saveActiveAgentOverrideToCache);
    });
    
    document.getElementById("btnSaveSettings").addEventListener("click", handleSaveSettings);
}

// Create and initialize novel factory
async function handleCreateNovel() {
    const title = document.getElementById("novelTitle").value.trim();
    const background = document.getElementById("novelBg").value.trim();
    
    if (!title || !background) {
        alert("請填寫書名與背景設定！");
        return;
    }
    
    logTerminal(`[系統] 正在啟動小說創作工廠 - 《${title}》...`);
    
    try {
        const res = await fetch("/api/novels", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title, background, target_word_count: 300000 })
        });
        const data = await res.json();
        
        if (data.status === "success") {
            activeNovelId = data.novel_id;
            currentStage = "worldview";
            
            // UI transitions
            document.getElementById("novelSetupForm").classList.add("hidden");
            document.getElementById("factoryStatusArea").classList.remove("hidden");
            document.getElementById("lblActiveTitle").textContent = title;
            
            logTerminal(`[系統] 小說工廠初始化完畢！ID: ${activeNovelId}`);
            updateStageStepper();
            refreshNovelInfo();
        }
    } catch (e) {
        logTerminal(`[錯誤] 初始化失敗: ${e.message}`);
    }
}

// Fetch up-to-date novel data and refresh visual timeline map
async function refreshNovelInfo() {
    if (!activeNovelId) return;
    
    try {
        const res = await fetch(`/api/novels/${activeNovelId}`);
        const data = await res.json();
        
        currentStage = data.stage;
        document.getElementById("lblActiveStage").textContent = translateStage(currentStage);
        
        updateStageStepper();
        renderTimeline(data.volumes, data.chapters);
    } catch (e) {
        console.error("Error refreshing novel data", e);
    }
}

// Translate stages to Chinese
function translateStage(stage) {
    const maps = {
        "worldview": "世界觀設定中",
        "characters": "人物誌打磨中",
        "volumes": "分卷規劃中",
        "skeleton": "章節骨架規劃中",
        "plot": "微觀情節編織中",
        "writer": "正文撰寫中",
        "completed": "全卷創作完成"
    };
    return maps[stage] || stage;
}

// Update left panel stage checklist highlights
function updateStageStepper() {
    const stages = ["worldview", "skeleton", "plot", "writer"];
    const activeIndex = stages.indexOf(currentStage === "characters" || currentStage === "volumes" ? "worldview" : currentStage);
    
    document.querySelectorAll(".step-item").forEach((item, idx) => {
        item.classList.remove("active", "completed");
        const dot = item.querySelector(".step-icon");
        
        if (idx < activeIndex || currentStage === "completed") {
            item.classList.add("completed");
            dot.textContent = "🟢";
        } else if (idx === activeIndex) {
            item.classList.add("active");
            dot.textContent = "⚡";
        } else {
            dot.textContent = "⚪";
        }
    });
}

// Stream and execute the current active stage step using SSE
function runActiveStageStep() {
    if (!activeNovelId) return;
    directorLoopCount = 0;
    
    logTerminal(`\n> [執行] 開始進行階段：${translateStage(currentStage)}...`);
    
    // Clear display area and prepare for stream
    const proseArea = document.getElementById("proseDisplayArea");
    proseArea.innerHTML = `<div class="prose-text" id="activeStreamingText"></div>`;
    const streamingTextDiv = document.getElementById("activeStreamingText");
    
    // Initialize right terminal output for thinking stream
    const consoleDiv = document.getElementById("terminalConsole");
    let currentThinkBlock = null;
    
    // Connect to SSE Stream Endpoint
    const eventSource = new EventSource(`/api/novels/${activeNovelId}/stream-step?is_one_click=${isOneClick}`);
    
    eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            
            if (data.type === "thinking") {
                // Render in Collateral neon terminal drawer
                if (!currentThinkBlock) {
                    currentThinkBlock = document.createElement("div");
                    currentThinkBlock.className = "terminal-line think-block";
                    currentThinkBlock.innerHTML = "<strong>🧠 總監思考過程：</strong><br>";
                    consoleDiv.appendChild(currentThinkBlock);
                }
                currentThinkBlock.innerHTML += escapeHtml(data.delta);
                consoleDiv.scrollTop = consoleDiv.scrollHeight;
            } 
            else if (data.type === "content") {
                // Reset think block for next step
                currentThinkBlock = null;
                // Render prose content into book view
                streamingTextDiv.innerHTML += data.delta.replace(/\n/g, "<br>");
                proseArea.scrollTop = proseArea.scrollHeight;
            } 
            else if (data.type === "error") {
                logTerminal(`[錯誤] ${data.message}`);
                eventSource.close();
            } 
            else if (data.type === "stage_done") {
                logTerminal(`[系統] ${translateStage(data.stage)} 階段串流寫入完成，資料庫已自動存檔！`);
                eventSource.close();
                
                if (isOneClick) {
                    if (directorLoopCount >= 5) {
                        const toastMsg = "自動流程已安全停駐，請手動決定下一步。";
                        logTerminal(`\n⏸️ [系統] ${toastMsg}`);
                        const toastEl = document.getElementById("toastContainer");
                        if (toastEl) {
                            toastEl.textContent = toastMsg;
                            toastEl.classList.add("show");
                            setTimeout(() => { toastEl.classList.remove("show"); }, 4000);
                        }
                        refreshNovelInfo();
                    } else {
                        runDirectorDecision();
                    }
                } else {
                    refreshNovelInfo();
                }
            }
            else if (data.type === "done") {
                eventSource.close();
                refreshNovelInfo();
            }
        } catch (e) {
            console.error("SSE parse error", e);
        }
    };
    
    eventSource.onerror = (e) => {
        console.error("SSE error", e);
        eventSource.close();
    };
}

// Trigger Creative Director Decision SSE Stream
function runDirectorDecision() {
    if (isOneClick) {
        directorLoopCount++;
        if (directorLoopCount >= 5) {
            const toastMsg = "自動流程已安全停駐，請手動決定下一步。";
            logTerminal(`\n⏸️ [系統] ${toastMsg}`);
            const toastEl = document.getElementById("toastContainer");
            if (toastEl) {
                toastEl.textContent = toastMsg;
                toastEl.classList.add("show");
                setTimeout(() => { toastEl.classList.remove("show"); }, 4000);
            }
            return;
        }
    }
    logTerminal(`\n> [總監審查] 正在調度創意總監進行本輪產出品質評估...`);
    
    const consoleDiv = document.getElementById("terminalConsole");
    let currentThinkBlock = null;
    
    // Extract last generated prose snippet as context
    const lastProse = document.getElementById("activeStreamingText")?.textContent || "";
    
    // Connect to Director Decision Stream
    const eventSource = new EventSource(`/api/novels/${activeNovelId}/director-decision?is_one_click=${isOneClick}&last_output=${encodeURIComponent(lastProse)}&loop_count=${directorLoopCount}`);
    
    eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            
            if (data.type === "thinking") {
                if (!currentThinkBlock) {
                    currentThinkBlock = document.createElement("div");
                    currentThinkBlock.className = "terminal-line think-block";
                    currentThinkBlock.innerHTML = "<strong>🧠 總監審查思維：</strong><br>";
                    consoleDiv.appendChild(currentThinkBlock);
                }
                currentThinkBlock.innerHTML += escapeHtml(data.delta);
                consoleDiv.scrollTop = consoleDiv.scrollHeight;
            }
            else if (data.type === "content") {
                currentThinkBlock = null;
                // Output director dialogue to console log
                logTerminal(`🗣️ [創意總監] ${data.delta}`);
            }
            else if (data.type === "decision_resolved") {
                const dec = data.decision;
                logTerminal(`\n[決策] 總監批示結果：決策 - "${dec.decision}", 下一階段 - "${dec.next_stage}"`);
                logTerminal(`[反饋] ${dec.feedback_to_agent}`);
                
                eventSource.close();
                refreshNovelInfo();
                
                // If One-Click is active and decision was 'approve', automatically run next step!
                if (isOneClick && dec.decision === "approve" && dec.next_stage !== "completed") {
                    setTimeout(() => {
                        runActiveStageStep();
                    }, 2000);
                }
            }
            else if (data.type === "done") {
                if (isOneClick) {
                    directorLoopCount++;
                }
                eventSource.close();
                refreshNovelInfo();
            }
        } catch (e) {
            console.error("Director SSE error", e);
        }
    };
    
    eventSource.onerror = (e) => {
        console.error("Director SSE connection error", e);
        eventSource.close();
    };
}

// Send interactive message to director
async function handleSendChat() {
    const input = document.getElementById("chatInput");
    const text = input.value.trim();
    if (!text || !activeNovelId) return;
    
    directorLoopCount = 0;
    logTerminal(`👤 [作者] ${text}`);
    input.value = "";
    
    // We run Director Decision using interactive mode, sending author's guidance as last_output
    logTerminal(`\n> [總監審議] 正在根據作者回饋重新評估策略...`);
    runDirectorDecision();
}

// Render dynamic map footer
function renderTimeline(volumes, chapters) {
    const track = document.getElementById("timelineTrack");
    track.innerHTML = "";
    
    if (!volumes || volumes.length === 0) {
        track.innerHTML = `<div class="empty-timeline-state">尚未規劃分卷骨架。</div>`;
        return;
    }
    
    volumes.forEach(vol => {
        // Create Volume Card Node
        const volNode = document.createElement("div");
        volNode.className = "timeline-node active";
        volNode.innerHTML = `🎬 ${vol.title}`;
        volNode.title = vol.summary;
        track.appendChild(volNode);
        
        // Find matching chapters
        const volChaps = chapters.filter(c => c.vol_index === vol.vol_index);
        volChaps.forEach(ch => {
            const chNode = document.createElement("div");
            chNode.className = "timeline-node";
            if (ch.status === "completed") {
                chNode.classList.add("active");
                chNode.innerHTML = `🟢 ${ch.title}`;
            } else if (ch.status === "plot_generated") {
                chNode.innerHTML = `🟡 ${ch.title}`;
            } else {
                chNode.innerHTML = `⚪ ${ch.title}`;
            }
            
            // Extract chapter plot info
            let plotSummary = ch.summary;
            try {
                const parsed = JSON.parse(ch.summary);
                plotSummary = parsed.chapter_summary;
            } catch {}
            
            chNode.title = plotSummary || "章節骨架待生成";
            
            chNode.addEventListener("click", () => {
                // Load clicked chapter prose to center page
                document.getElementById("lblBookVolCh").textContent = `第 ${vol.vol_index + 1} 卷 - 第 ${ch.ch_index} 章`;
                document.getElementById("lblBookTitle").textContent = ch.title;
                const proseArea = document.getElementById("proseDisplayArea");
                
                if (ch.content) {
                    proseArea.innerHTML = `<div class="prose-text">${ch.content.replace(/\n/g, "<br>")}</div>`;
                } else {
                    proseArea.innerHTML = `
                        <div class="empty-book-state">
                            <div class="icon">📝</div>
                            <p><strong>章節大綱概要：</strong></p>
                            <p style="padding: 0 2rem; color: var(--text-muted); font-size: 0.9rem;">${plotSummary || '大綱生成中...'}</p>
                        </div>`;
                }
            });
            track.appendChild(chNode);
        });
    });
}

// Log directly into thought terminal console
function logTerminal(message) {
    const consoleDiv = document.getElementById("terminalConsole");
    const line = document.createElement("div");
    line.className = "terminal-line";
    line.innerHTML = message.replace(/\n/g, "<br>");
    consoleDiv.appendChild(line);
    consoleDiv.scrollTop = consoleDiv.scrollHeight;
}

function escapeHtml(text) {
    if (!text) return "";
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

let loadedConfigs = {};

async function openSettingsModal() {
    logTerminal("[系統] 正在載入系統設定檔...");
    try {
        const res = await fetch("/api/settings");
        const data = await res.json();
        
        if (data.status === "success") {
            loadedConfigs = data.configs || {};
            
            // 1. Populate global config inputs
            const g = loadedConfigs["global"] || {};
            document.getElementById("cfg_global_api_key").value = g.api_key || "";
            document.getElementById("cfg_global_base_url").value = g.base_url || "https://integrate.api.nvidia.com/v1";
            document.getElementById("cfg_global_model").value = g.model || "google/gemma-3n-e4b-it";
            document.getElementById("cfg_global_temp").value = g.temperature !== undefined ? g.temperature : 0.7;
            document.getElementById("cfg_global_tokens").value = g.max_tokens !== undefined ? g.max_tokens : 16384;
            
            // 2. Load architect as default override tab selection
            document.getElementById("agentSelector").value = "architect";
            loadAgentOverrideInputs("architect");
            
            // Show modal
            document.getElementById("settingsModal").classList.remove("hidden");
            logTerminal("[系統] 設定檔載入成功！");
        }
    } catch (e) {
        logTerminal(`[錯誤] 載入設定失敗: ${e.message}`);
    }
}

function closeSettingsModal() {
    document.getElementById("settingsModal").classList.add("hidden");
}

function loadAgentOverrideInputs(agentName) {
    const titleMap = {
        "architect": "故事架構師 (Architect)",
        "character": "分卷角色設計師 (Character)",
        "plot": "劇情情節大綱師 (Plot)",
        "writer": "文學正文撰寫師 (Writer)",
        "editor": "編輯潤色姬 (Editor)",
        "copilot": "創意總監評估器 (Copilot/Director)"
    };
    
    document.getElementById("overrideAgentTitle").textContent = `${titleMap[agentName] || agentName} 設定`;
    
    const cfg = loadedConfigs[agentName] || {};
    document.getElementById("cfg_agent_api_key").value = cfg.api_key || "";
    document.getElementById("cfg_agent_base_url").value = cfg.base_url || "";
    document.getElementById("cfg_agent_model").value = cfg.model || "";
    document.getElementById("cfg_agent_temp").value = cfg.temperature !== undefined ? cfg.temperature : "";
    document.getElementById("cfg_agent_thinking").value = cfg.enable_thinking !== undefined ? cfg.enable_thinking : "1";
}

function saveActiveAgentOverrideToCache() {
    const agentName = document.getElementById("agentSelector").value;
    if (!loadedConfigs[agentName]) {
        loadedConfigs[agentName] = {};
    }
    
    const cfg = loadedConfigs[agentName];
    cfg.api_key = document.getElementById("cfg_agent_api_key").value.trim();
    cfg.base_url = document.getElementById("cfg_agent_base_url").value.trim();
    cfg.model = document.getElementById("cfg_agent_model").value.trim();
    
    const tempVal = document.getElementById("cfg_agent_temp").value.trim();
    cfg.temperature = tempVal !== "" ? parseFloat(tempVal) : undefined;
    cfg.enable_thinking = parseInt(document.getElementById("cfg_agent_thinking").value);
}

async function handleSaveSettings() {
    logTerminal("[系統] 正在儲存設定...");
    
    // Save current active override values back to cache
    saveActiveAgentOverrideToCache();
    
    // Package global config back to cache
    if (!loadedConfigs["global"]) {
        loadedConfigs["global"] = {};
    }
    const g = loadedConfigs["global"];
    g.api_key = document.getElementById("cfg_global_api_key").value.trim();
    g.base_url = document.getElementById("cfg_global_base_url").value.trim();
    g.model = document.getElementById("cfg_global_model").value.trim();
    g.temperature = parseFloat(document.getElementById("cfg_global_temp").value);
    g.max_tokens = parseInt(document.getElementById("cfg_global_tokens").value);
    g.enable_thinking = 1; // Global thinking enabled by default
    
    try {
        const res = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ configs: loadedConfigs })
        });
        const data = await res.json();
        
        if (data.status === "success") {
            logTerminal("[系統] 設定已成功儲存並套用！所有 Agents 連接已重啟生效。");
            closeSettingsModal();
        }
    } catch (e) {
        logTerminal(`[錯誤] 儲存設定失敗: ${e.message}`);
    }
}
