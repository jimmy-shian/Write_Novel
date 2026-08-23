// ==========================================
// AUTONOMOUS CLOUD PIPELINE DASHBOARD
// ==========================================

import { startAutonomousPipeline, getAutonomousPipelineStatus, stopAutonomousPipeline, getAPIBase } from '../api/api.js';
import { state } from '../core/state.js';
import { showToast } from '../core/toast.js';

let pollTimer = null;
let lastKnownStage = '';
let lastKnownChapter = 0;
let isUserDismissed = false;
let lastSeenIsRunning = false;

/**
 * 動態判斷環境並注入「☁️ 雲端無人值守」按鈕（僅在發布至網頁/連線雲端時出現，本機單機版保持乾淨純淨）
 */
export function injectCloudButtonIfWebOrConfigured() {
    const isWeb = typeof window !== 'undefined' && (window.location.hostname.includes('github.io') || window.location.hostname.includes('hf.space'));
    const hasCustomBackend = !!getAPIBase();
    
    const existingBtn = document.getElementById('btn-autonomous-cloud');
    const headerActions = document.getElementById('novel-header-actions');
    const pipelineBtn = document.getElementById('btn-pipeline-execute');

    if (isWeb || hasCustomBackend) {
        if (!existingBtn && headerActions && pipelineBtn) {
            const btn = document.createElement('button');
            btn.id = 'btn-autonomous-cloud';
            btn.className = 'btn btn-primary btn-sm';
            btn.style.cssText = 'display: inline-flex; align-items: center; gap: 6px; background: linear-gradient(135deg, #6366f1, #a855f7); color: #fff; font-weight: 700;';
            btn.title = '指令送達後您可直接關閉電腦或網頁，雲端後端自動寫完並同步備份';
            btn.innerHTML = '<span>☁️</span><span>雲端無人值守</span>';
            
            btn.addEventListener('click', async () => {
                if (!state.currentNovelId) {
                    showToast('請先在左側選擇或建立一部小說！', 'warning');
                    return;
                }
                const targetNovel = state.novels?.find(n => String(n.id) === String(state.currentNovelId));
                const novelTitle = targetNovel?.title || '當前小說';

                try {
                    isUserDismissed = false; // 重新啟動時解開手動關閉
                    showToast(`🚀 已啟動《${novelTitle}》雲端全自動創作！後端 AI 總監正在自主規劃與接續撰寫...`, 'info');
                    const res = await startAutonomousPipeline(state.currentNovelId, '', 10);
                    showToast(res.message || '雲端無人值守生成已成功啟動！您可以隨時關閉瀏覽器。', 'success');
                    pollPipelineStatus();
                } catch (e) {
                    showToast('啟動失敗: ' + e.message, 'error');
                }
            });

            headerActions.insertBefore(btn, pipelineBtn);
        }
    } else {
        if (existingBtn) {
            existingBtn.remove();
        }
    }
}

/**
 * 初始化雲端無人值守生成儀表板與狀態輪詢
 */
export function initAutonomousDashboard() {
    createDashboardDOM();
    injectCloudButtonIfWebOrConfigured();
    startStatusPolling();
}

function createDashboardDOM() {
    if (document.getElementById('autonomous-dashboard-widget')) return;

    // 建立頂部無人值守浮動指示面板
    const container = document.createElement('div');
    container.id = 'autonomous-dashboard-widget';
    container.innerHTML = `
        <div class="auto-widget-card" id="auto-widget-card" style="display: none;">
            <div class="auto-widget-header">
                <div class="auto-widget-header-left">
                    <span class="auto-pulse-dot" id="auto-pulse-dot"></span>
                    <span class="auto-widget-title" id="auto-widget-title">🚀 雲端無人值守自主創作中...</span>
                </div>
                <div class="auto-widget-header-right">
                    <button class="auto-widget-stop-btn" id="auto-widget-stop-btn">🛑 中止</button>
                    <button class="auto-widget-close-btn" id="auto-widget-close-btn" title="關閉視窗">✕</button>
                </div>
            </div>
            <div class="auto-widget-progress-container">
                <div class="auto-widget-progress-bar" id="auto-widget-progress-bar" style="width: 0%;"></div>
            </div>
            <div class="auto-widget-info">
                <div class="auto-widget-status-text" id="auto-widget-stage">階段: 準備中</div>
                <div class="auto-widget-pct-badge" id="auto-widget-progress-text">0%</div>
            </div>
            <div class="auto-widget-logs" id="auto-widget-logs"></div>
        </div>
    `;
    document.body.appendChild(container);

    // 綁定中止按鈕事件
    const stopBtn = document.getElementById('auto-widget-stop-btn');
    if (stopBtn) {
        stopBtn.addEventListener('click', async () => {
            if (stopBtn.dataset.action === 'close') {
                isUserDismissed = true;
                const card = document.getElementById('auto-widget-card');
                if (card) card.style.display = 'none';
                return;
            }
            if (confirm('確定要中止雲端無人值守生成嗎？已完成的章節將被安全保留。')) {
                try {
                    const res = await stopAutonomousPipeline();
                    showToast(res.message || '已發送中止請求');
                    pollPipelineStatus();
                } catch (e) {
                    showToast('中止失敗: ' + e.message, 'error');
                }
            }
        });
    }

    // 綁定右上角關閉按鈕事件
    const closeBtn = document.getElementById('auto-widget-close-btn');
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            isUserDismissed = true;
            const card = document.getElementById('auto-widget-card');
            if (card) card.style.display = 'none';
        });
    }

    // 注入 CSS 樣式 (排版清晰、避免文字重疊、字體放大)
    const style = document.createElement('style');
    style.textContent = `
        #autonomous-dashboard-widget {
            position: fixed;
            bottom: 24px;
            right: 24px;
            z-index: 99999;
            font-family: inherit;
        }
        .auto-widget-card {
            background: rgba(18, 18, 28, 0.96);
            border: 1px solid rgba(99, 102, 241, 0.4);
            border-radius: 16px;
            padding: 18px 20px;
            box-shadow: 0 16px 48px rgba(0, 0, 0, 0.6);
            backdrop-filter: blur(20px);
            width: 440px;
            max-width: 90vw;
            color: #fff;
            animation: autoSlideUp 0.3s ease;
        }
        @keyframes autoSlideUp {
            from { transform: translateY(30px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }
        .auto-widget-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 12px;
            gap: 8px;
        }
        .auto-widget-header-left {
            display: flex;
            align-items: center;
            gap: 8px;
            flex: 1;
            min-width: 0;
        }
        .auto-widget-header-right {
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .auto-pulse-dot {
            width: 12px;
            height: 12px;
            background: #10b981;
            border-radius: 50%;
            display: inline-block;
            flex-shrink: 0;
            box-shadow: 0 0 10px #10b981;
            animation: autoPulse 1.5s infinite;
        }
        @keyframes autoPulse {
            0% { transform: scale(0.95); opacity: 0.8; }
            50% { transform: scale(1.25); opacity: 1; }
            100% { transform: scale(0.95); opacity: 0.8; }
        }
        .auto-widget-title {
            font-size: 1.05rem;
            font-weight: 700;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            color: #f1f5f9;
        }
        .auto-widget-stop-btn {
            background: rgba(239, 68, 68, 0.2);
            color: #ef4444;
            border: 1px solid rgba(239, 68, 68, 0.4);
            border-radius: 8px;
            padding: 5px 10px;
            font-size: 0.9rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            white-space: nowrap;
        }
        .auto-widget-stop-btn:hover {
            background: #ef4444;
            color: #fff;
        }
        .auto-widget-close-btn {
            background: rgba(255, 255, 255, 0.1);
            color: #94a3b8;
            border: none;
            border-radius: 8px;
            width: 30px;
            height: 30px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.1rem;
            cursor: pointer;
            transition: all 0.2s;
            line-height: 1;
        }
        .auto-widget-close-btn:hover {
            background: rgba(255, 255, 255, 0.25);
            color: #fff;
        }
        .auto-widget-progress-container {
            background: rgba(255, 255, 255, 0.12);
            border-radius: 999px;
            height: 8px;
            overflow: hidden;
            margin-bottom: 12px;
        }
        .auto-widget-progress-bar {
            background: linear-gradient(90deg, #6366f1, #a855f7);
            height: 100%;
            border-radius: 999px;
            transition: width 0.4s ease;
        }
        .auto-widget-info {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 12px;
            margin-bottom: 12px;
        }
        .auto-widget-status-text {
            font-size: 0.92rem;
            color: #cbd5e1;
            font-weight: 500;
            line-height: 1.45;
            word-break: break-word;
            flex: 1;
        }
        .auto-widget-pct-badge {
            font-size: 0.95rem;
            font-weight: 700;
            color: #c084fc;
            background: rgba(168, 85, 247, 0.15);
            padding: 2px 8px;
            border-radius: 6px;
            white-space: nowrap;
        }
        .auto-widget-logs {
            max-height: 110px;
            overflow-y: auto;
            background: rgba(0, 0, 0, 0.45);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 0.88rem;
            font-family: monospace;
            color: #cbd5e1;
            line-height: 1.5;
        }
        .auto-log-item {
            margin-bottom: 4px;
        }
        .auto-log-time {
            color: #64748b;
            margin-right: 6px;
        }
    `;
    document.head.appendChild(style);
}

/**
 * 啟動狀態輪詢 (每 3 秒一次)
 */
function startStatusPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollPipelineStatus, 3000);
    pollPipelineStatus();
}

async function pollPipelineStatus() {
    try {
        const data = await getAutonomousPipelineStatus();
        updateWidgetUI(data);
    } catch (e) {
        // 後端離線或尚未設定
    }
}

function updateWidgetUI(data) {
    const card = document.getElementById('auto-widget-card');
    const dot = document.getElementById('auto-pulse-dot');
    const title = document.getElementById('auto-widget-title');
    const stopBtn = document.getElementById('auto-widget-stop-btn');
    const progressBar = document.getElementById('auto-widget-progress-bar');
    const stageText = document.getElementById('auto-widget-stage');
    const progressText = document.getElementById('auto-widget-progress-text');
    const logsContainer = document.getElementById('auto-widget-logs');

    if (!card) return;

    if (!data || (!data.is_running && (!data.logs || data.logs.length === 0))) {
        card.style.display = 'none';
        return;
    }

    // 若背景從未運行轉為正在運行，自動重新顯示
    if (data.is_running && !lastSeenIsRunning) {
        isUserDismissed = false;
    }
    lastSeenIsRunning = !!data.is_running;

    if (isUserDismissed && !data.is_running) {
        card.style.display = 'none';
        return;
    }

    if (data.is_running || (data.current_stage && data.current_stage !== 'idle')) {
        card.style.display = 'block';

        if (data.is_running) {
            title.textContent = `🚀 《${data.novel_title || '小說'}》雲端自主創作中...`;
            if (dot) {
                dot.style.background = '#10b981';
                dot.style.boxShadow = '0 0 10px #10b981';
            }
            if (stopBtn) {
                stopBtn.style.display = 'inline-block';
                stopBtn.textContent = '🛑 中止';
                stopBtn.dataset.action = 'stop';
                stopBtn.className = 'auto-widget-stop-btn';
            }
        } else if (data.current_stage === 'completed') {
            title.textContent = `🎉 《${data.novel_title || '小說'}》生成完成！`;
            if (dot) {
                dot.style.background = '#3b82f6';
                dot.style.boxShadow = '0 0 10px #3b82f6';
            }
            if (stopBtn) {
                stopBtn.style.display = 'inline-block';
                stopBtn.textContent = '✕ 關閉';
                stopBtn.dataset.action = 'close';
                stopBtn.className = 'auto-widget-close-btn-styled';
            }
        } else if (data.error) {
            title.textContent = `⚠️ 《${data.novel_title || '小說'}》執行中斷`;
            if (dot) {
                dot.style.background = '#ef4444';
                dot.style.boxShadow = '0 0 10px #ef4444';
            }
            if (stopBtn) {
                stopBtn.style.display = 'inline-block';
                stopBtn.textContent = '✕ 關閉';
                stopBtn.dataset.action = 'close';
                stopBtn.className = 'auto-widget-close-btn-styled';
            }
        }

        const pct = Math.min(100, Math.max(0, data.progress_percent || 0));
        if (progressBar) progressBar.style.width = `${pct}%`;
        if (progressText) progressText.textContent = `${pct}%`;
        if (stageText) stageText.textContent = data.status_message || data.current_stage;

        // 更新日誌
        if (logsContainer && data.logs && Array.isArray(data.logs)) {
            const recentLogs = data.logs.slice(-5);
            logsContainer.innerHTML = recentLogs.map(l => `
                <div class="auto-log-item">
                    <span class="auto-log-time">[${l.time}]</span>
                    <span class="auto-log-msg">${l.msg}</span>
                </div>
            `).join('');
            logsContainer.scrollTop = logsContainer.scrollHeight;
        }

        // 若章節有推進或階段切換，自動重新載入小說細節以即時更新章節列表、編輯器與總監對話
        const isStageChanged = data.current_stage !== lastKnownStage;
        const isChapterChanged = data.current_chapter && data.current_chapter !== lastKnownChapter;

        if (isStageChanged || isChapterChanged) {
            lastKnownStage = data.current_stage;
            lastKnownChapter = data.current_chapter || lastKnownChapter;
            
            if (data.novel_id && state.currentNovelId === data.novel_id) {
                if (data.current_chapter) {
                    state.activeChapterIndex = data.current_chapter;
                }
                if (window.loadNovelDetails) {
                    window.loadNovelDetails(data.novel_id);
                }
            }
        }
    }
}
