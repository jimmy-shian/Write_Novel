// ==========================================
// NOVEL LIFECYCLE - 小說生命週期管理
// ==========================================

import { state } from '../core/state.js';
import { el } from '../core/dom.js';
import { showToast } from '../core/toast.js';
import { requestAPI } from '../api/api.js';
import { renderActiveTab, renderChatMessages } from '../ui/renderers.js';

/**
 * 載入小說列表
 */
export async function loadNovels() {
    try {
        state.novels = await requestAPI('/api/novels');
        renderNovelsList();
    } catch (e) {
        console.error("Failed to load novels list");
    }
}

/**
 * 載入指定小說的詳細資料
 * @param {string} novelId - 小說 ID
 */
    export async function loadNovelDetails(novelId) {
    if (!novelId) return;
    try {
        el.currentNovelTitle.textContent = "載入中...";
        const data = await requestAPI(`/api/novels/${novelId}`);
        const isProjectSwitch = state.currentNovelId !== novelId;
        const isDefaultIndex = state.activeChapterIndex === 1 || !state.activeChapterIndex;
        state.currentNovelId = novelId;
        // 持久化保存當前選中的小說
        localStorage.setItem('currentNovelId', novelId);
        state.currentNovelData = data;
        
        if (isProjectSwitch || isDefaultIndex) {
            const chapters = data.chapters || [];
            const writtenIndexes = new Set(
                chapters
                    .filter(c => {
                        const content = c.content || '';
                        const isPlaceholder = content.includes('保底') || 
                                              content.includes('占位') || 
                                              content.trim().length < 100;
                        const isDirty = c.is_dirty === 1 || c.is_dirty === true;
                        return !isPlaceholder && !isDirty;
                    })
                    .map(c => Number(c.chapter_index))
            );
            
            const vols = data.volumes || [];
            const totalPlanned = vols.reduce((sum, v) => {
                const count = Number.parseInt(v.chapter_count, 10);
                return sum + (Number.isFinite(count) && count > 0 ? count : 0);
            }, 0) || 50;
            
            let earliestMissing = null;
            for (let i = 1; i <= totalPlanned; i++) {
                if (!writtenIndexes.has(i)) {
                    earliestMissing = i;
                    break;
                }
            }
            
            if (earliestMissing !== null) {
                state.activeChapterIndex = earliestMissing;
                // 同步更新 activeVolumeIndex
                if (typeof window.getChapterVolumeIndexJS === 'function') {
                    const matchedVol = window.getChapterVolumeIndexJS(earliestMissing);
                    if (matchedVol) {
                        state.activeVolumeIndex = matchedVol;
                    }
                } else {
                    let startCh = 1;
                    const sortedVols = [...vols].sort((a, b) => (parseInt(a.volume_index) || 0) - (parseInt(b.volume_index) || 0));
                    for (let i = 0; i < sortedVols.length; i++) {
                        const v = sortedVols[i];
                        const count = parseInt(v.chapter_count) || 50;
                        const endCh = startCh + count - 1;
                        if (earliestMissing >= startCh && earliestMissing <= endCh) {
                            state.activeVolumeIndex = parseInt(v.volume_index);
                            break;
                        }
                        startCh = endCh + 1;
                    }
                }
                console.log(`[Lifecycle] Auto-initialized activeChapterIndex to earliest missing: ${earliestMissing}`);
            }
        }
        
        // Update header UI
        el.currentNovelTitle.textContent = data.novel.title;
        el.currentNovelGenre.textContent = `${data.novel.genre} • Style: ${data.novel.style}`;
        if (el.novelHeaderActions) el.novelHeaderActions.style.display = 'flex';
        
        // Always render all tabs to ensure worldview data is visible when switching tabs
        renderActiveTab();
        renderChatMessages();
        
        // 確保 worldview sections 被渲染（無論當前在哪個 tab）
        // 這樣當用戶切換到 worldview tab 時就能看到最新的世界觀數據
        const worldviewSectionsContainer = document.getElementById('worldview-sections-container');
        if (worldviewSectionsContainer) {
            // 使用 requestAnimationFrame 確保在 DOM 更新後執行
            requestAnimationFrame(() => {
                import('../ui/renderers.js').then(module => {
                    if (module.renderWorldviewSections) {
                        module.renderWorldviewSections();
                    }
                });
            });
        }
        
        // Select active item in sidebar list
        document.querySelectorAll('#novels-list li').forEach(li => {
            if (li.dataset.id === novelId) {
                li.classList.add('active');
            } else {
                li.classList.remove('active');
            }
        });
    } catch (e) {
        el.currentNovelTitle.textContent = "載入錯誤";
    }
}

/**
 * 清除工作區（當沒有選擇小說時）
 */
export function clearWorkspace() {
    state.currentNovelId = null;
    localStorage.removeItem('currentNovelId');
    state.currentNovelData = null;
    
    // Header
    el.currentNovelTitle.textContent = "請選擇或建立一部小說";
    el.currentNovelGenre.textContent = "小說類型";
    if (el.novelHeaderActions) el.novelHeaderActions.style.display = 'none';
    
    // Worldview Tab
    if (el.editorWorldview) el.editorWorldview.value = '';
    
    // Characters Tab
    if (el.editorCharactersJson) el.editorCharactersJson.value = '{\n  "characters": []\n}';
    if (el.charactersCardsGrid) el.charactersCardsGrid.innerHTML = '<div class="empty-placeholder">請建立或選擇小說以查看角色。</div>';
    
    // Plot Tab
    if (el.editorPlotJson) el.editorPlotJson.value = '{\n  "chapters": []\n}';
    if (el.plotTimeline) el.plotTimeline.innerHTML = '<div class="empty-placeholder">請建立或選擇小說以查看大綱。</div>';
    
    // Writer Tab
    if (el.writerChaptersList) el.writerChaptersList.innerHTML = '<li class="loading-placeholder">請建立或選擇小說。</li>';
    if (el.activeChapterTitle) el.activeChapterTitle.textContent = "請選擇章節";
    if (el.activeChapterStatus) el.activeChapterStatus.textContent = "";
    if (el.chapterOutlineSummaryText) el.chapterOutlineSummaryText.textContent = "等待選擇章節大綱...";
    if (el.editorProse) el.editorProse.value = "";
    if (el.aiThinkingStream) el.aiThinkingStream.classList.add('hidden');
    if (el.aiThinkingText) el.aiThinkingText.textContent = "";
    
    // Chat messages
    if (el.chatMessagesContainer) el.chatMessagesContainer.innerHTML = '<div class="chat-message system"><div class="msg-content">💡 選擇一部小說開始討論。</div></div>';
}

/**
 * 渲染小說列表（側邊欄）
 */
export function renderNovelsList() {
    el.novelsList.innerHTML = '';
    if (state.novels.length === 0) {
        el.novelsList.innerHTML = '<li class="loading-placeholder">目前尚無創作專案</li>';
        return;
    }
    state.novels.forEach(n => {
        const li = document.createElement('li');
        li.dataset.id = n.id;
        if (state.currentNovelId === n.id) {
            li.className = 'active';
        }
        
        const dateObj = new Date(n.created_at);
        const formattedDate = `${dateObj.getMonth() + 1}/${dateObj.getDate()}`;
        
        li.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span class="novel-title-text" style="font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:160px;">${n.title}</span>
                <span class="delete-novel-btn" style="color:var(--text-muted); cursor:pointer; font-size:0.8rem; padding: 2px 6px;" title="刪除小說">✕</span>
            </div>
            <div class="novel-meta">
                <span>${n.genre}</span>
                <span>${formattedDate}</span>
            </div>
        `;
        
        // Delete novel handler
        li.querySelector('.delete-novel-btn').addEventListener('click', async (e) => {
            e.stopPropagation();
            if (await showCustomConfirm(`確定要刪除「${n.title}」專案嗎？此操作無法還原！`)) {
                try {
                    await requestAPI(`/api/novels/${n.id}`, 'DELETE');
                    if (state.currentNovelId === n.id) {
                        clearWorkspace();
                        // 刪除當前選中的小說後，刷新頁面以清除殘留內容
                        window.location.reload();
                    } else {
                        await loadNovels();
                        showToast("專案已成功刪除");
                    }
                } catch (err) {
                    showToast("刪除失敗: " + err.message);
                }
            }
        });
        
        // Select novel handler
        li.addEventListener('click', (e) => {
            if (e.target.closest('.delete-novel-btn')) {
                return;
            }
            loadNovelDetails(n.id);
        });
        
        el.novelsList.appendChild(li);
    });
}

