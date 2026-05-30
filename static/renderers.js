// ==========================================
// RENDERERS - UI 渲染函式
// ==========================================

import { state } from './state.js';
import { el } from './dom.js';
import { showToast } from './toast.js';
import { requestAPI } from './api.js';
import { parseWorldviewJSON, renderMarkdown, parseDirectorDecisionText } from './utils.js';
// Escape backticks to prevent markdown code fence issues
function escapeBackticks(str) {
    return typeof str === 'string' ? str.replace(/`/g, '\\`') : str;
}

/**
 * 渲染當前激活的 Tab
 */
export function renderActiveTab() {
    // Hide all workpanels, activate correct nav tab
    el.navTabs.forEach(t => {
        if (t.dataset.tab === state.activeTab) {
            t.classList.add('active');
        } else {
            t.classList.remove('active');
        }
    });
    
    el.workpanels.forEach(p => {
        if (p.id === `panel-${state.activeTab}`) {
            p.classList.add('active');
        } else {
            p.classList.remove('active');
        }
    });
    
    if (!state.currentNovelData) return;
    
    // Call specific tab renderer
    if (state.activeTab === 'worldview') renderWorldviewTab();
    if (state.activeTab === 'characters') renderCharactersTab();
    if (state.activeTab === 'plot') renderPlotTab();
    if (state.activeTab === 'writer') renderWriterTab();
}

/**
 * 渲染世界觀 Tab
 */
export function renderWorldviewTab() {
    el.editorWorldview.value = state.currentNovelData.worldbuilding || '';
    // 渲染世界觀各區塊的視覺化列表
    renderWorldviewSections();
    
    // 確保 JSON sidebar 隱藏
    const jsonSidebar = document.querySelector('#panel-worldview .editor-sidebar-json');
    if (jsonSidebar) {
        jsonSidebar.style.display = 'none';
    }
}

/**
 * 渲染世界觀各區塊的視覺化 UI
 */
export function renderWorldviewSections() {
    const container = document.getElementById('worldview-sections-container');
    if (!container) return;
    
    const worldviewText = state.currentNovelData?.worldbuilding || '';
    const js = parseWorldviewJSON(worldviewText);
    
    const sections = [
        { id: 'theme', icon: '🎯', title: '核心主題', content: js.theme, badge: 'badge-primary' },
        { id: 'main_conflict', icon: '⚔️', title: '核心衝突', content: js.main_conflict, badge: 'badge-danger' },
        { id: 'worldview', icon: '🌍', title: '世界觀設定', content: js.worldview, badge: 'badge-success' },
        { id: 'macro_outline', icon: '📜', title: '整體故事大綱', content: js.macro_outline, badge: 'badge-info' }
    ];
    
    // 先渲染 4 個獨立世界觀核心卡片
    let html = sections.map(s => renderWorldviewSection(s.id, s.icon, s.title, s.content, s.badge)).join('');
    
    // 渲染策略卡片，並使用容器包裹以便 Grid/分欄控制
    let strategyHtml = '';
    
    // 多幕式結構 (data-section 映射為 three-act 配合 app.js)
    const threeActList = (js.multi_act_structure && js.multi_act_structure.length > 0) ? js.multi_act_structure : [
        { title: "第一幕 (Setup)", content: "" },
        { title: "第二幕 (Confrontation)", content: "" },
        { title: "第三幕 (Resolution)", content: "" }
    ];
    strategyHtml += `
        <div class="worldview-section-card" data-section="three-act">
            <div class="worldview-section-header">
                <div class="worldview-section-title">
                    <span class="worldview-section-badge badge-warning">🎭</span>
                    多幕式劇情起伏結構
                </div>
                <div class="worldview-section-actions">
                    <button onclick="toggleSectionExpand('three-act')" title="展開/收合">↕</button>
                    <button onclick="editWorldviewComplexList('multi_act_structure', '多幕式結構', '幕次')" title="編輯">✏️</button>
                </div>
            </div>
            <div class="worldview-section-content" id="content-three-act">
                ${threeActList.length > 0 ? `
                    <div class="worldview-sub-items-list" style="display: flex; flex-direction: column; gap: 8px;">
                        ${threeActList.map((item, idx) => `
                            <div class="worldview-sub-item" onclick="editWorldviewComplexList('multi_act_structure', '多幕式結構', '幕次')" style="cursor: pointer;">
                                <div class="worldview-sub-item-title">${item.title || `幕次 ${idx + 1}`}</div>
                                <div class="worldview-sub-item-content">${renderMarkdown(item.content) || '<em style="color:var(--text-muted)">尚無內容</em>'}</div>
                            </div>
                        `).join('')}
                    </div>
                ` : `
                    <div style="text-align:center; padding: 24px; color:var(--text-muted); font-style:italic;">🎭 尚無結構設定，請點擊編輯按鈕以新增</div>
                `}
            </div>
        </div>
    `;
    
    // 角色漸進規劃 (data-section 映射為 character-waves 配合 app.js)
    const charPlanList = (js.progressive_character_plan && js.progressive_character_plan.length > 0) ? js.progressive_character_plan : [
        { title: "第一波開篇 (Wave 1)", content: "" },
        { title: "第二波發展 (Wave 2)", content: "" },
        { title: "第三波高潮 (Wave 3)", content: "" }
    ];
    strategyHtml += `
        <div class="worldview-section-card" data-section="character-waves">
            <div class="worldview-section-header">
                <div class="worldview-section-title">
                    <span class="worldview-section-badge badge-purple">👥</span>
                    角色漸進登場規劃策略
                </div>
                <div class="worldview-section-actions">
                    <button onclick="toggleSectionExpand('character-waves')" title="展開/收合">↕</button>
                    <button onclick="editWorldviewComplexList('progressive_character_plan', '角色漸進規劃策略', '波次')" title="編輯">✏️</button>
                </div>
            </div>
            <div class="worldview-section-content" id="content-character-waves">
                ${charPlanList.length > 0 ? `
                    <div class="worldview-sub-items-list" style="display: flex; flex-direction: column; gap: 8px;">
                        ${charPlanList.map((item, idx) => `
                            <div class="worldview-sub-item" onclick="editWorldviewComplexList('progressive_character_plan', '角色漸進規劃策略', '波次')" style="cursor: pointer;">
                                <div class="worldview-sub-item-title">${item.title || `波次 ${idx + 1}`}</div>
                                <div class="worldview-sub-item-content">${renderMarkdown(item.content) || '<em style="color:var(--text-muted)">尚無內容</em>'}</div>
                            </div>
                        `).join('')}
                    </div>
                ` : `
                    <div style="text-align:center; padding: 24px; color:var(--text-muted); font-style:italic;">👥 尚無策略設定，請點擊編輯按鈕以新增</div>
                `}
            </div>
        </div>
    `;
    
    // 伏筆種子 (data-section 映射為 seeds 配合 app.js)
    const seedsList = js.foreshadowing_seeds || [];
    strategyHtml += `
        <div class="worldview-section-card" data-section="seeds">
            <div class="worldview-section-header">
                <div class="worldview-section-title">
                    <span class="worldview-section-badge badge-info">🌱</span>
                    伏筆種子
                </div>
                <div class="worldview-section-actions">
                    <button onclick="toggleSectionExpand('seeds')" title="展開/收合">↕</button>
                    <button onclick="editWorldviewList('foreshadowing_seeds', '伏筆種子')" title="編輯">✏️</button>
                </div>
            </div>
            <div class="worldview-section-content" id="content-seeds">
                ${seedsList.length > 0 ? `
                    <ul class="worldview-list">
                        ${seedsList.map((item, idx) => `
                            <li>${renderMarkdown(typeof item === 'string' ? item : JSON.stringify(item))}</li>
                        `).join('')}
                    </ul>
                ` : `
                    <div style="text-align:center; padding: 24px; color:var(--text-muted); font-style:italic;">🌱 尚無伏筆設定，請點擊編輯按鈕以新增</div>
                `}
            </div>
        </div>
    `;
    
    // 關鍵轉折點 (data-section 映射為 turning-points 配合 app.js)
    const tpList = js.key_turning_points || [];
    strategyHtml += `
        <div class="worldview-section-card" data-section="turning-points">
            <div class="worldview-section-header">
                <div class="worldview-section-title">
                    <span class="worldview-section-badge badge-danger">⚡</span>
                    關鍵轉折點
                </div>
                <div class="worldview-section-actions">
                    <button onclick="toggleSectionExpand('turning-points')" title="展開/收合">↕</button>
                    <button onclick="editWorldviewList('key_turning_points', '關鍵轉折點')" title="編輯">✏️</button>
                </div>
            </div>
            <div class="worldview-section-content" id="content-turning-points">
                ${tpList.length > 0 ? `
                    <ul class="worldview-list">
                        ${tpList.map((item, idx) => `
                            <li>${renderMarkdown(typeof item === 'string' ? item : JSON.stringify(item))}</li>
                        `).join('')}
                    </ul>
                ` : `
                    <div style="text-align:center; padding: 24px; color:var(--text-muted); font-style:italic;">⚡ 尚無轉折設定，請點擊編輯按鈕以新增</div>
                `}
            </div>
        </div>
    `;

    if (strategyHtml) {
        // 依據 state.strategyCardView 設定 Grid 排版樣式
        const viewModeClass = (state.strategyCardView === 'single') ? 'single-mode' : 'all-mode';
        html += `<div class="worldview-strategy-container ${viewModeClass}">${strategyHtml}</div>`;
    }
    
    container.innerHTML = html;

    // 如果當前處於單張檢視模式，主動套用隱藏邏輯
    if (state.strategyCardView === 'single') {
        const strategyNames = ['three-act', 'character-waves', 'turning-points', 'seeds'];
        const strategyCardsArray = strategyNames.map(id => 
            container.querySelector(`.worldview-section-card[data-section="${id}"]`)
        ).filter(Boolean);
        const activeIndex = state.currentCardIndex !== undefined ? state.currentCardIndex : 0;
        
        strategyCardsArray.forEach((card, index) => {
            if (index === activeIndex) {
                card.style.display = 'flex';
                card.classList.remove('collapsed');
                card.classList.add('expanded');
            } else {
                card.style.display = 'none';
                card.classList.remove('expanded');
                card.classList.add('collapsed');
            }
        });

        // 額外套用子章節/子項目顯示與標題狀態
        applySubSectionVisibility();
    }
}

/**
 * 獲取當前選中卡片的子章節數量
 * @param {number} cardIndex - 卡片索引 (0-3)
 * @returns {number} 子章節個數
 */
export function getSubSectionCount(cardIndex) {
    const worldviewText = state.currentNovelData?.worldbuilding || '';
    const js = parseWorldviewJSON(worldviewText);
    if (cardIndex === 0) return (js.multi_act_structure || []).length;
    if (cardIndex === 1) return (js.progressive_character_plan || []).length;
    if (cardIndex === 2) return (js.key_turning_points || []).length;
    if (cardIndex === 3) return (js.foreshadowing_seeds || []).length;
    return 0;
}

/**
 * 套用當前選中卡片內部子章節的隱藏與動態進度顯示邏輯
 */
export function applySubSectionVisibility() {
    const container = document.getElementById('worldview-sections-container');
    if (!container) return;

    const strategyNames = ['three-act', 'character-waves', 'turning-points', 'seeds'];
    const activeIndex = state.currentCardIndex !== undefined ? state.currentCardIndex : 0;
    const activeSectionName = strategyNames[activeIndex];
    const activeCard = container.querySelector(`.worldview-section-card[data-section="${activeSectionName}"]`);
    if (!activeCard) return;

    // 找出所有子項目元素
    let subItems = [];
    if (activeSectionName === 'three-act' || activeSectionName === 'character-waves') {
        subItems = Array.from(activeCard.querySelectorAll('.worldview-timeline-item, .worldview-sub-item'));
    } else {
        subItems = Array.from(activeCard.querySelectorAll('.worldview-list > li'));
    }

    const subIndex = state.currentSubSectionIndex !== undefined ? state.currentSubSectionIndex : 'all';

    // 套用 display 屬性與 active class
    subItems.forEach((item, idx) => {
        if (subIndex === 'all' || idx === subIndex) {
            item.style.display = '';
            item.classList.add('active-sub-item');
        } else {
            item.style.display = 'none';
            item.classList.remove('active-sub-item');
        }
    });

    // 獲取與更新標題文字 (加入子項目進度顯示，如 "1/3")
    const titleContainer = activeCard.querySelector('.worldview-section-title');
    if (titleContainer) {
        if (!titleContainer.dataset.originalText) {
            // 提取純文字節點 (不包括 emoji badge)
            const badgeSpan = titleContainer.querySelector('.worldview-section-badge');
            let baseText = '';
            if (badgeSpan) {
                baseText = titleContainer.innerText.replace(badgeSpan.innerText, '').trim();
            } else {
                baseText = titleContainer.innerText.trim();
            }
            titleContainer.dataset.originalText = baseText;
        }

        let statusText = '';
        if (state.strategyCardView === 'single') {
            if (subIndex === 'all') {
                statusText = ' (全部)';
            } else if (subItems.length > 0 && subIndex < subItems.length) {
                let itemTitle = `第 ${subIndex + 1} 部分`;
                const customTitleEl = subItems[subIndex].querySelector('.worldview-sub-item-title');
                if (customTitleEl) {
                    itemTitle = customTitleEl.innerText.trim();
                } else {
                    const textContent = subItems[subIndex].innerText || '';
                    itemTitle = textContent.split('\n')[0].substring(0, 12).trim();
                    if (textContent.length > 12) itemTitle += '...';
                }
                statusText = ` (${subIndex + 1}/${subItems.length}) ${itemTitle}`;
            }
        }

        // 重新組裝標題
        const badgeSpan = titleContainer.querySelector('.worldview-section-badge');
        titleContainer.innerHTML = '';
        if (badgeSpan) {
            titleContainer.appendChild(badgeSpan);
        }
        titleContainer.appendChild(document.createTextNode(' ' + titleContainer.dataset.originalText + statusText));
    }
}

/**
 * 渲染單個世界觀區塊（帶編輯/刪除按鈕，支援 Markdown 語法）
 */
export function renderWorldviewSection(sectionId, icon, title, content, badgeClass) {
    const safeContent = content || '';
    return `
        <div class="worldview-section-card" data-section="${sectionId}">
            <div class="worldview-section-header">
                <div class="worldview-section-title">
                    <span class="worldview-section-badge ${badgeClass}">${icon}</span>
                    ${title}
                </div>
                <div class="worldview-section-actions">
                    <button onclick="toggleSectionExpand('${sectionId}')" title="展開/收合">↕</button>
                    <button onclick="editWorldviewSection('${sectionId}', '${title}')" title="編輯">✏️</button>
                </div>
            </div>
            <div class="worldview-section-content" id="content-${sectionId}">
                ${renderMarkdown(safeContent) || '<em style="color:var(--text-muted)">尚無內容</em>'}
            </div>
        </div>
    `;
}

/**
 * 渲染角色 Tab
 */
export function renderCharactersTab() {
    const charactersData = state.currentNovelData?.characters;
    const characters = charactersData?.characters || [];
    
    el.editorCharactersJson.value = state.currentNovelData?.characters_raw || JSON.stringify({ characters: [] }, null, 2);
    
    // 渲染角色卡片
    if (el.charactersCardsGrid) {
        if (characters.length === 0) {
            el.charactersCardsGrid.innerHTML = '<div class="empty-placeholder">👥 尚無角色設定。請點擊上方「AI 自動設計角色」或「新增角色」開始建立。</div>';
        } else {
            el.charactersCardsGrid.innerHTML = characters.map((char, idx) => {
                // Parse personality traits
                let traits = [];
                if (Array.isArray(char.personality)) {
                    traits = char.personality;
                } else if (typeof char.personality === 'string') {
                    traits = char.personality.split(',').map(s => s.trim()).filter(Boolean);
                }
                
                // Parse flaws
                let flaws = [];
                if (Array.isArray(char.flaws)) {
                    flaws = char.flaws;
                } else if (typeof char.flaws === 'string') {
                    flaws = char.flaws.split(',').map(s => s.trim()).filter(Boolean);
                } else if (char.fatal_flaw) {
                    flaws = [char.fatal_flaw];
                }
                
                const personalityPills = traits.map(t => `<span class="char-pill pill-personality">${t}</span>`).join('');
                const flawsPills = flaws.map(f => `<span class="char-pill pill-flaw">${f}</span>`).join('');
                
                const roleClass = char.role === '主角' ? 'role-protagonist' :
                                  char.role === '反派' ? 'role-antagonist' :
                                  char.role === '導師' ? 'role-mentor' : 'role-secondary';

                const motivationText = char.motivation || char.want || '待設定';
                const arcText = char.arc || char.need || '待設定';
                const entryText = char.entry_phase ? `<span class="char-entry-phase">🚪 ${char.entry_phase}</span>` : '';

                return `
                <div class="character-card-modern" data-index="${idx}">
                    <div class="char-card-header">
                        <div class="char-meta-info">
                            <span class="char-role-badge ${roleClass}">${char.role || '配角'}</span>
                            ${entryText}
                        </div>
                        <div class="char-card-actions">
                            <button class="char-action-btn edit-btn" onclick="openCharacterEditModal(${idx})" title="編輯角色">
                                ✏️
                            </button>
                            <button class="char-action-btn delete-btn" onclick="deleteCharacter(${idx})" title="刪除角色">
                                🗑️
                            </button>
                        </div>
                    </div>
                    
                    <div class="char-card-title-section">
                        <h3 class="char-name-heading">${char.name || `角色 ${idx + 1}`}</h3>
                    </div>
                    
                    <div class="char-card-body-section">
                        <div class="char-detail-row">
                            <span class="char-detail-label">🎯 動機 / 欲求</span>
                            <p class="char-detail-text">${motivationText}</p>
                        </div>
                        
                        <div class="char-detail-row">
                            <span class="char-detail-label">🧬 內在需求 / 成長弧線</span>
                            <p class="char-detail-text">${arcText}</p>
                        </div>
                        
                        ${char.speech_style ? `
                        <div class="char-detail-row">
                            <span class="char-detail-label">🗣️ 語言風格</span>
                            <p class="char-detail-text speech-style-text">「${char.speech_style}」</p>
                        </div>
                        ` : ''}
                    </div>
                    
                    <div class="char-card-footer-section">
                        ${personalityPills ? `
                        <div class="char-pills-group">
                            <span class="pills-label">性格：</span>
                            <div class="pills-container">${personalityPills}</div>
                        </div>
                        ` : ''}
                        
                        ${flawsPills ? `
                        <div class="char-pills-group">
                            <span class="pills-label font-flaw-label">缺陷：</span>
                            <div class="pills-container">${flawsPills}</div>
                        </div>
                        ` : ''}
                    </div>
                </div>
                `;
            }).join('');
        }
    }
}

/**
 * 渲染大綱 Tab
 */
export function renderPlotTab() {
    const plotData = state.currentNovelData?.plot;
    const chapters = plotData?.chapters || [];
    let volumes = state.currentNovelData?.volumes || [];
    
    state.expandedVolumes = state.expandedVolumes || new Set();
    
    el.editorPlotJson.value = state.currentNovelData?.plot_raw || JSON.stringify({ chapters: [] }, null, 2);
    
    // Auto-generate virtual volumes and pad missing volume indexes (e.g., Vol 1 to Vol max)
    let maxVolIdx = 0;
    if (volumes.length > 0) {
        maxVolIdx = Math.max(...volumes.map(v => parseInt(v.volume_index) || 0));
    }
    if (chapters.length > 0) {
        const maxChIdx = Math.max(...chapters.map(c => parseInt(c.chapter_index) || 0));
        maxVolIdx = Math.max(maxVolIdx, Math.ceil(maxChIdx / 50) || 1);
    }
    
    if (maxVolIdx > 0) {
        const fullVolumes = [];
        for (let i = 1; i <= maxVolIdx; i++) {
            const existingVol = volumes.find(v => parseInt(v.volume_index) === i);
            if (existingVol) {
                fullVolumes.push(existingVol);
            } else {
                fullVolumes.push({
                    volume_index: i,
                    title: `第 ${i} 卷`,
                    summary: `本卷包含第 ${(i-1)*50 + 1} 章至第 ${i*50} 章。`,
                    factions: "全域陣列",
                    is_dirty: 0,
                    chapter_count: 50,
                    chapters_outline: []
                });
            }
        }
        volumes = fullVolumes;
    }
    
    // Expose scrollToVolume function globally
    window.scrollToVolume = function(volIdx) {
        // Step 3: 記錄當前活躍的卷數
        state.activeVolumeIdx = volIdx;
        
        const volCard = document.getElementById(`volume-card-${volIdx}`);
        if (volCard) {
            // Smooth scroll to card
            volCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
            
            // Highlight target card
            document.querySelectorAll('.volume-card').forEach(el => el.classList.remove('active-target-glow'));
            volCard.classList.add('active-target-glow');
            
            // Automatically expand if collapsed
            if (!volCard.classList.contains('expanded')) {
                window.toggleVolumeExpand(volIdx);
            }
            
            // Update active roadmap node
            document.querySelectorAll('.roadmap-node').forEach((node) => {
                if (parseInt(node.getAttribute('data-volume-index')) === volIdx) {
                    node.classList.add('active');
                } else {
                    node.classList.remove('active');
                }
            });
        }
        
        // Step 3: 切換篇卷時重新渲染世界觀區塊以套用過濾
        renderWorldviewSections();
        
        // 💡 核心修復：切換卷時主動刷新快捷時間軸，確保顯示當前活躍卷的章節
        if (typeof window.renderQuickTimelineNav === 'function') {
            window.renderQuickTimelineNav();
        }
    };

    // 點擊 volume-card 任意位置時，設定為當前活躍卷並刷新時間軸
    window.activateVolumeNav = function(volIdx) {
        state.activeVolumeIdx = volIdx;
        
        // 更新 roadmap 節點高亮
        document.querySelectorAll('.roadmap-node').forEach((node) => {
            if (parseInt(node.getAttribute('data-volume-index')) === volIdx) {
                node.classList.add('active');
            } else {
                node.classList.remove('active');
            }
        });
        
        // 重繪右側快捷時間軸（顯示當前活躍卷的章節）
        if (typeof window.renderQuickTimelineNav === 'function') {
            window.renderQuickTimelineNav();
        }
    };

    // Expose collapse function
    window.toggleVolumeExpand = function(volIdx) {
        const volCard = document.getElementById(`volume-card-${volIdx}`);
        if (volCard) {
            const chaptersList = volCard.querySelector('.volume-chapters-list');
            const toggleBtn = volCard.querySelector('.expand-toggle-btn');
            if (chaptersList) {
                state.expandedVolumes = state.expandedVolumes || new Set();
                const isExpanded = volCard.classList.contains('expanded');
                if (isExpanded) {
                    volCard.classList.remove('expanded');
                    chaptersList.style.setProperty('display', 'none', 'important');
                    if (toggleBtn) toggleBtn.innerText = '展開';
                    state.expandedVolumes.delete(volIdx);
                } else {
                    volCard.classList.add('expanded');
                    chaptersList.style.setProperty('display', 'flex', 'important');
                    if (toggleBtn) toggleBtn.innerText = '收合';
                    state.expandedVolumes.add(volIdx);
                    
                    // 💡 同步更新當前活躍卷，並重繪右側快捷導航條
                    state.activeVolumeIdx = volIdx;
                    if (typeof window.renderQuickTimelineNav === 'function') {
                        window.renderQuickTimelineNav();
                    }
                    
                    // 同步高亮對應的 roadmap 節點
                    document.querySelectorAll('.roadmap-node').forEach((node) => {
                        if (parseInt(node.getAttribute('data-volume-index')) === volIdx) {
                            node.classList.add('active');
                        } else {
                            node.classList.remove('active');
                        }
                    });
                }
            }
        }
    };
    
    // Helper to get emotional tone badge styling
    function getToneBadge(tone) {
        if (!tone) return '';
        let bgColor = 'rgba(156, 163, 175, 0.12)';
        let color = '#9ca3af';
        let borderColor = 'rgba(156, 163, 175, 0.2)';
        if (tone.includes('緊張') || tone.includes('紧张') || tone.includes('激烈') || tone.includes('衝突') || tone.includes('危險') || tone.includes('戰鬥')) {
            bgColor = 'rgba(239, 68, 68, 0.12)';
            color = '#ef4444';
            borderColor = 'rgba(239, 68, 68, 0.2)';
        } else if (tone.includes('舒緩') || tone.includes('舒缓') || tone.includes('溫馨') || tone.includes('日常') || tone.includes('輕鬆') || tone.includes('平靜') || tone.includes('放鬆')) {
            bgColor = 'rgba(16, 185, 129, 0.12)';
            color = '#10b981';
            borderColor = 'rgba(16, 185, 129, 0.2)';
        } else if (tone.includes('高潮') || tone.includes('爆發') || tone.includes('熱血') || tone.includes('反轉') || tone.includes('高能')) {
            bgColor = 'rgba(139, 92, 246, 0.12)';
            color = '#8b5cf6';
            borderColor = 'rgba(139, 92, 246, 0.2)';
        } else if (tone.includes('低谷') || tone.includes('悲傷') || tone.includes('壓抑') || tone.includes('絕望') || tone.includes('沉重')) {
            bgColor = 'rgba(59, 130, 246, 0.12)';
            color = '#3b82f6';
            borderColor = 'rgba(59, 130, 246, 0.2)';
        }
        return `<span class="chapter-tone-badge" style="background: ${bgColor}; color: ${color}; border: 1px solid ${borderColor}; padding: 2px 8px; border-radius: 12px; font-size: var(--font-2xs); font-weight: 600;">🎭 ${tone}</span>`;
    }

    // 渲染時間線
    if (el.plotTimeline) {
        if (volumes.length === 0) {
            el.plotTimeline.innerHTML = `
                <div class="empty-placeholder">
                    📋 尚無章節規劃。請點擊上方「一鍵生成全書」或「AI 自動拆分章節」來建立整本小說大綱，或手動建立第一章。
                    <button class="btn btn-primary btn-sm mt-4" onclick="openManualChapterInsertModal(0)">➕ 手動新增第一章</button>
                </div>`;
        } else {
            // Compute unique factions
            const uniqueFactions = new Set();
            volumes.forEach(vol => {
                let factionsArr = [];
                if (Array.isArray(vol.parsed_factions)) {
                    factionsArr = vol.parsed_factions;
                } else if (vol.factions) {
                    try {
                        const parsed = JSON.parse(vol.factions);
                        if (Array.isArray(parsed)) factionsArr = parsed;
                    } catch (e) {
                        factionsArr = String(vol.factions).split(/[,,，、\n]+/).map(f => f.trim()).filter(Boolean);
                    }
                }
                factionsArr.forEach(f => uniqueFactions.add(f));
            });
            const uniqueFactionsCount = uniqueFactions.size;

            // Generate Stats Dashboard and Volume Roadmap Track
            const statsHtml = `
                <div class="plot-metrics-dashboard" style="flex-shrink: 0;">
                    <div class="metric-tile">
                        <div class="metric-label">篇卷總數 (Volumes)</div>
                        <div class="metric-value">📚 ${volumes.length}</div>
                    </div>
                    <div class="metric-tile">
                        <div class="metric-label">對齊比例 (Aligned)</div>
                        <div class="metric-value">⚡ ${volumes.filter(v => v.is_dirty !== 1).length} / ${volumes.length}</div>
                    </div>
                    <div class="metric-tile">
                        <div class="metric-label">大綱章節 (Chapters)</div>
                        <div class="metric-value">📋 ${chapters.length}</div>
                    </div>
                    <div class="metric-tile">
                        <div class="metric-label">登場陣營 (Factions)</div>
                        <div class="metric-value">🛡️ ${uniqueFactionsCount}</div>
                    </div>
                </div>
            `;

            const roadmapHtml = `
                <div class="volume-roadmap-container" style="flex-shrink: 0;">
                    <div class="roadmap-title">
                        <span>🗺️ 篇卷導航圖 (Volume Roadmap Track)</span>
                        <span style="font-size: var(--font-2xs); color: var(--text-muted); font-weight: normal; text-transform: none;">可按住滑鼠左右拖曳或點擊定位</span>
                    </div>
                    <div class="roadmap-track">
                        ${volumes.map((vol) => {
                            const volIdx = vol.volume_index;
                            const isDirty = vol.is_dirty === 1;
                            const statusClass = isDirty ? 'dirty' : 'aligned';
                            return `
                                <div class="roadmap-node" data-volume-index="${volIdx}" onclick="event.stopPropagation(); window.scrollToVolume(${volIdx})">
                                    <span class="roadmap-node-index">Vol. ${volIdx}</span>
                                    <span class="roadmap-node-title">${vol.title || `第 ${volIdx} 卷`}</span>
                                    <span class="roadmap-node-status ${statusClass}"></span>
                                </div>
                            `;
                        }).join('')}
                    </div>
                </div>
            `;

            // 💡【核心修復】：建立動態篇卷範圍累加器（完美對齊後端 db.get_volume_chapter_range 邏輯）
            const sortedVols = [...volumes].sort((a, b) => parseInt(a.volume_index) - parseInt(b.volume_index));
            const volRanges = {};
            let currentGlobalStart = 1;

            sortedVols.forEach(v => {
                const vIdx = parseInt(v.volume_index);
                const vCount = parseInt(v.chapter_count) || 50;
                volRanges[vIdx] = {
                    start: currentGlobalStart,
                    end: currentGlobalStart + vCount - 1,
                    count: vCount
                };
                currentGlobalStart += vCount;
            });

            const timelineCardsHtml = volumes.map((vol) => {
                const volIdx = vol.volume_index;
                const isDirty = vol.is_dirty === 1;
                const isVolExpanded = state.expandedVolumes && state.expandedVolumes.has(volIdx);
                
                const factionsVal = Array.isArray(vol.parsed_factions) ? vol.parsed_factions.join(', ') : (vol.factions || '');
                const safeTitle = (vol.title || '').replace(/`/g, '\\`').replace(/\$/g, '\\$');
                const safeSummary = (vol.summary || '').replace(/`/g, '\\`').replace(/\$/g, '\\$');
                const safeFactions = factionsVal.replace(/`/g, '\\`').replace(/\$/g, '\\$');
                
                // 💡 獲取當前卷的精確動態章節範圍
                const myRange = volRanges[volIdx] || { start: (volIdx - 1) * 50 + 1, end: volIdx * 50, count: 50 };
                const vStart = myRange.start;
                const volChCount = myRange.count;
                
                // 1. 💡 使用動態範圍精確過濾高解像度微觀大綱章節
                const volMicroChapters = chapters.filter(c => {
                    const cIdx = parseInt(c.chapter_index);
                    // 💡 改用範圍區間判定，不再盲目除以 50
                    const isInVolumeRange = !isNaN(cIdx) && (cIdx >= myRange.start && cIdx <= myRange.end);
                    if (!isInVolumeRange) return false;
                    
                    const hasMicroStructure = Array.isArray(c.events) && c.events.length > 0 ||
                                              !!c.purpose || !!c.emotional_tone || !!c.cliffhanger;
                    const hasTitleOrSummary = c.title && c.title.trim() !== '' && c.title !== '待設定標題';
                    
                    // 💡 修復：改為「有詳細結構 → 是微觀章節」為主判斷。
                    // 即使有 brief_title（合併後骨架欄位仍保留），只要有詳細結構欄位就視為微觀大綱。
                    // 舊邏輯：isSkeleton = has brief_title → 從 microChapters 中排除（錯誤！）
                    const isDetailedChapter = hasMicroStructure || hasTitleOrSummary;
                    
                    return isDetailedChapter;
                });

                // 2. 💡【Step 1 修復】直接使用 chapters_outline 作為骨架渲染源
                let outl = [];
                try {
                    const raw = vol.chapters_outline;
                    if (Array.isArray(raw)) {
                        outl = raw;
                    } else if (typeof raw === 'string' && raw.trim()) {
                        outl = JSON.parse(raw);
                        if (!Array.isArray(outl)) outl = [];
                    }
                } catch(e) {
                    outl = [];
                }
                
                // 輔助函式：判斷一個章節是否已詳細化（有 events/purpose/cliffhanger 等詳細欄位）
                function isDetailedChapterObj(ch) {
                    return (Array.isArray(ch.events) && ch.events.length > 0) ||
                           !!ch.purpose || !!ch.emotional_tone || !!ch.cliffhanger ||
                           (ch.title && ch.title !== ch.brief_title && ch.title.trim() !== '' && ch.title !== '待設定標題');
                }

                // 3. 💡【核心修復點】：建立雙層 Map 緩衝區，進行逐章無縫融合
                // chapters_outline 可能同時含骨架章節和合併後的詳細章節（兩者都在）
                const skeletonMap = new Map();
                const outlineDetailMap = new Map(); // 來自 chapters_outline 的詳細章節

                outl.forEach(ch => {
                    const rawIdx = ch.chapter_index ?? ch.chapter ?? ch.chapter_number ?? ch.index ?? ch.id;
                    const idx = parseInt(rawIdx);
                    if (!isNaN(idx)) {
                        if (isDetailedChapterObj(ch)) {
                            // 已詳細化的章節 → 進 outlineDetailMap（優先被 plot.chapters 覆蓋）
                            outlineDetailMap.set(idx, ch);
                        } else {
                            // 純骨架章節（只有 brief_title/brief_summary）→ 進 skeletonMap
                            skeletonMap.set(idx, ch);
                        }
                    }
                });

                // microMap：優先從 plot.chapters（全局大綱）取，其次從 chapters_outline 的詳細部分取
                const microMap = new Map();
                // 先放 chapters_outline 中的詳細章節作底
                outlineDetailMap.forEach((ch, idx) => {
                    microMap.set(idx, ch);
                });
                // 再用 plot.chapters 覆蓋（plot.chapters 是主要來源，優先級更高）
                volMicroChapters.forEach(ch => {
                    const idx = parseInt(ch.chapter_index);
                    if (!isNaN(idx)) {
                        microMap.set(idx, ch);
                    }
                });
                
                // 4. 動態收集本卷需要呈現的所有章節全局序號集合
                //    優先收集骨架章節（Stage 2），再補足微觀大綱章節（Stage 4）
                const chapterIdxSet = new Set();
                
                // 4.1 收集骨架章節（Stage 2 產出）
                skeletonMap.forEach((_, idx) => chapterIdxSet.add(idx));
                
                // 4.2 收集微觀大綱章節（Stage 4 產出 + chapters_outline 合併的詳細章節）
                microMap.forEach((_, idx) => chapterIdxSet.add(idx));
                
                // 4.3 💡【Step 3 修復】：只有當有實際大綱內容時才填補格子，否則保持乾淨空狀態
                // 當 outl 為空時，不應該產生 50 個「待設定」的虛擬章節
                if (outl.length > 0) {
                    for (let i = 0; i < volChCount; i++) {
                        chapterIdxSet.add(vStart + i);
                    }
                }

                // 將序號由小到大排序（例如 1 ~ 48）
                const sortedIdxs = Array.from(chapterIdxSet).sort((a, b) => a - b);

                // 5. 🚀 混合陣列組裝：有微觀用微觀，沒微觀用骨架，都沒用空白保底
                const displayChapters = sortedIdxs.map(idx => {
                    if (microMap.has(idx)) {
                        return { ...microMap.get(idx), __renderMode: 'micro' };
                    } else if (skeletonMap.has(idx)) {
                        return { ...skeletonMap.get(idx), __renderMode: 'skeleton' };
                    } else {
                        return { chapter_index: idx, title: '待設定標題', summary: '待設定摘要', __renderMode: 'empty' };
                    }
                });


                // 重新校準總規劃章節數與百分比
                // 💡 修正點 1：總章數應該拿目前展示列表的長度（無論是微觀還是骨架），若皆無則拿該卷預設的 chapter_count
                const totalChaptersCount = displayChapters.length || parseInt(vol.chapter_count) || 50;
                const writtenChaptersCount = chapters.filter(c => {
                    const cIdx = parseInt(c.chapter_index);
                    if (Math.floor((cIdx - 1) / 50) + 1 !== volIdx) return false;
                    const existing = state.currentNovelData?.chapters?.find(ec => parseInt(ec.chapter_index) === cIdx);
                    return !!(existing && existing.content && existing.content.trim());
                }).length;
                const progressPercent = totalChaptersCount > 0 ? Math.round((writtenChaptersCount / totalChaptersCount) * 100) : 0;

                const dirtyBadge = isDirty ? `<span class="dirty-badge" style="background: rgba(245, 158, 11, 0.12); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.2); padding: 2px 8px; border-radius: 4px; font-size: var(--font-2xs); font-weight: 700; margin-left: 8px;">⚠️ 待對齊世界觀</span>` : `<span class="dirty-badge" style="background: rgba(16, 185, 129, 0.12); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.2); padding: 2px 8px; border-radius: 4px; font-size: var(--font-2xs); font-weight: 700; margin-left: 8px;">✓ 已對齊</span>`;
                const alignButton = isDirty ? `
                    <button class="btn btn-secondary btn-xs align-vol-btn" onclick="event.stopPropagation(); window.alignVolume(${volIdx})" style="background: var(--primary); color: white; border: none; border-radius: 4px; padding: 4px 10px; cursor: pointer; font-size: var(--font-2xs); font-weight: 600; transition: transform 0.2s;">
                        ⚡ 延遲對齊
                    </button>` : '';
                
                // 6. 進行 HTML 渲染對接
                const chaptersHtml = displayChapters.length === 0 ? `
                    <div class="empty-placeholder" style="padding: 16px; font-size: var(--font-2xs); text-align: center; color: var(--text-muted); display: flex; flex-direction: column; align-items: center; gap: 8px;">
                        <span>📭 此篇卷尚無章節大綱。${isDirty ? '請點擊「⚡ 延遲對齊」進行世界觀校準。' : ''}</span>
                        <button class="btn btn-secondary btn-xs" onclick="event.stopPropagation(); window.addChapterToVolume(${volIdx})" style="background: var(--primary); color: white; border: none; border-radius: 4px; padding: 4px 10px; cursor: pointer; font-size: var(--font-2xs); font-weight: 600;">➕ 新增本卷第一章</button>
                    </div>` : displayChapters.map((chapter, chIdx) => {
    
                    const chapterIndex = parseInt(chapter.chapter_index);
                    // 💡 基於全新的 __renderMode 屬性精確判定單個卡片外觀（需先宣告才能在 chIdxInVol 中使用）
                    const isSkeletonChapter = chapter.__renderMode === 'skeleton' || chapter.__renderMode === 'empty';
                    
                    // 💡 修正全局索引查找，防止編輯按鈕點擊錯位 Bug
                    const globalIdx = chapters.findIndex(c => parseInt(c.chapter_index) === chapterIndex);
                    
                    // 💡【核心修復】：對於骨架章節，正確計算卷內序號（使用動態範圍 vStart 計算）
                    // 如果 chapterIndex 落在本卷範圍內，計算相對章號：chapterIndex - vStart + 1
                    // 否則使用 displayChapters 陣列索引 + 1（fallback）
                    let chIdxInVol;
                    if (isSkeletonChapter) {
                        if (chapterIndex >= vStart && chapterIndex < vStart + volChCount) {
                            // chapterIndex 是正確的全局章節號，計算卷內相對編號
                            chIdxInVol = chapterIndex - vStart + 1;
                        } else {
                            // chapterIndex 可能是 LLM 錯誤的局部索引，使用 displayChapters 陣列索引 + 1
                            chIdxInVol = chIdx + 1;
                        }
                    } else {
                        // 微觀模式保持原本邏輯
                        chIdxInVol = (((chapterIndex - 1) % 50) + 1);
                    }
                    
                    const emotionalToneText = getToneBadge(chapter.emotional_tone);
                    
                    if (isSkeletonChapter) {
                        // 💡 修復：增加更多容錯邏輯，嘗試從多個可能的欄位取得標題/概要
                        const skeletonTitle = chapter.brief_title || chapter.title || chapter.name || '待設定標題';
                        const skeletonSummary = chapter.brief_summary || chapter.summary || (chapter.__renderMode === 'empty' ? '情節骨架待生成' : '');
                        const allocatedTasks = chapter.allocated_tasks || {};
                        const foreshadowPlants = allocatedTasks.foreshadowing_plants || [];
                        const foreshadowPayoffs = allocatedTasks.foreshadowing_payoffs || [];
                        const turningPoints = allocatedTasks.turning_points || [];
                        
                        return `
                        <div class="chapter-grid-item skeleton-chapter" data-chapter-index="${chapterIndex}" data-index="${globalIdx}" style="border-left: 3px solid var(--primary); opacity: 0.85; padding: 12px; background: rgba(255,255,255,0.01); border-radius: 6px; margin-bottom: 8px;">
                            <div class="chapter-title-row" style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">
                                <span class="chapter-index-badge" style="background: rgba(59, 130, 246, 0.15); color: #3b82f6; padding: 2px 8px; border-radius: 4px; font-size: var(--font-2xs); font-weight: 700;">🦴 第 ${chIdxInVol} 章</span>
                                <h3 class="chapter-title" style="margin: 0; font-size: var(--font-2xs); font-weight: 600; color: var(--text-primary);">${skeletonTitle}</h3>
                            </div>
                            ${skeletonSummary ? `<p style="font-size: var(--font-2xs); color: var(--text-secondary); margin: 0 0 8px 0; line-height: 1.5;">${skeletonSummary}</p>` : ''}
                            
                            ${(foreshadowPlants.length > 0 || foreshadowPayoffs.length > 0 || turningPoints.length > 0) ? `
                            <div style="display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px;">
                                ${foreshadowPlants.map(seed => `<span class="seed-pill" style="background: rgba(139, 92, 246, 0.12); color: #8b5cf6; padding: 2px 6px; border-radius: 4px; font-size: var(--font-2xs);">🌱 ${seed}</span>`).join('')}
                                ${foreshadowPayoffs.map(pay => `<span class="payoff-pill" style="background: rgba(245, 158, 11, 0.12); color: #f59e0b; padding: 2px 6px; border-radius: 4px; font-size: var(--font-2xs);">💥 回收: ${pay}</span>`).join('')}
                                ${turningPoints.map(tp => `<span class="turning-pill" style="background: rgba(239, 68, 68, 0.12); color: #ef4444; padding: 2px 6px; border-radius: 4px; font-size: var(--font-2xs);">⚡ 轉折: ${tp}</span>`).join('')}
                            </div>` : ''}
                            
                            <div class="chapter-actions" style="margin-top: 8px; text-align: right;">
                                <button class="btn btn-ghost btn-xs" onclick="event.stopPropagation(); if(${globalIdx} !== -1) { openChapterOutlineEditModal(${globalIdx}, window.state.currentNovelData.plot.chapters[${globalIdx}]) } else { showToast('請先將此章節推進至 Stage 4 細化大綱後再行微觀編輯') }" style="opacity: 0.6; padding: 2px 6px;">✏️</button>
                            </div>
                        </div>`;
                    }
                    
                    // 以下保持原本的高解像度微觀大綱卡片渲染 (Prose Mode) 不變
                    const purposeText = chapter.purpose ? `
                    <div class="chapter-grid-item">
                        <div class="chapter-grid-label">🎯 敘事目的</div>
                        <div class="chapter-grid-value" style="font-weight: 500; color: var(--text-primary);">${chapter.purpose}</div>
                    </div>` : '';
                    
                    let eventsHtml = '';
                    if (Array.isArray(chapter.events) && chapter.events.length > 0) {
                        const displayedEvents = chapter.events.slice(0, 4);
                        const remaining = chapter.events.length - 4;
                        eventsHtml = `
                        <div class="chapter-grid-item grid-col-span-2">
                            <div class="chapter-grid-label">🎬 核心情節事件流</div>
                            <div class="stepped-events" style="margin-top: 6px;">
                                ${displayedEvents.map((e, eIdx) => {
                                    const eventText = typeof e === 'string' ? e : [e.action, e.scene, e.consequence].filter(Boolean).join(' ➔ ') || JSON.stringify(e);
                                    return `
                                        <div class="stepped-event-item" style="padding-left: 24px; position: relative; margin-bottom: 6px; font-size: var(--font-2xs); line-height: 1.5; color: var(--text-secondary);">
                                            <span style="position: absolute; left: 0; top: 2px; width: 16px; height: 16px; border-radius: 50%; background: var(--primary); color: white; display: flex; align-items: center; justify-content: center; font-size: var(--font-2xs); font-weight: 800;">${eIdx + 1}</span>
                                            <span style="font-weight: 500; color: var(--text-primary);">${eventText}</span>
                                        </div>
                                    `;
                                }).join('')}
                                ${remaining > 0 ? `<div style="font-size: var(--font-2xs); color: var(--text-muted); padding-left: 24px; font-style: italic;">+ 還有 ${remaining} 個事件...</div>` : ''}
                            </div>
                        </div>`;
                    }

                    let foreshadowHtml = '';
                    if (Array.isArray(chapter.foreshadowing) && chapter.foreshadowing.length > 0) {
                        foreshadowHtml = `
                        <div class="chapter-grid-item grid-col-span-2">
                            <div class="chapter-grid-label">🌱 伏筆線索種子</div>
                            <div style="display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px;">
                                ${chapter.foreshadowing.map(f => `<span class="badge" style="background: rgba(16, 185, 129, 0.1); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.15); padding: 2px 8px; border-radius: 4px; font-size: var(--font-2xs); font-weight: 600;">${f}</span>`).join('')}
                            </div>
                        </div>`;
                    }
                    
                    // 💡 修復：優先使用微觀大綱欄位，若無則回退到骨架欄位
                    const skeletonTitle = chapter.title || chapter.brief_title || chapter.name || '待設定標題';
                    const skeletonSummary = chapter.summary || chapter.brief_summary || (chapter.__renderMode === 'empty' ? '情節骨架待生成' : '');
                    const cliffhangerHtml = chapter.cliffhanger && chapter.cliffhanger.trim() ? `
                        <div class="chapter-grid-item grid-col-span-2" style="background: rgba(239, 68, 68, 0.03); border-color: rgba(239, 68, 68, 0.15); border-radius: var(--radius-sm); padding: 10px 12px; margin-top: 4px;">
                            <div class="chapter-grid-label" style="color: #ef4444;">⚠️ 本章懸念 (Cliffhanger)</div>
                            <div class="chapter-grid-value" style="color: var(--text-primary); font-style: italic; font-weight: 500; margin-top: 4px;">🔥 ${chapter.cliffhanger}</div>
                        </div>` : '';

                    return `
                    <div class="plot-timeline-node-wrapper" style="margin-bottom: 16px; position: relative;">
                        <div class="plot-chapter-item" data-index="${globalIdx}" data-chapter-index="${chapterIndex}" onclick="event.stopPropagation(); if(${globalIdx} !== -1) openChapterOutlineEditModal(${globalIdx}, window.state.currentNovelData.plot.chapters[${globalIdx}])" style="cursor: pointer; border: 1px solid var(--border-color); border-radius: var(--radius-md); background: rgba(255, 255, 255, 0.015); padding: 16px; position: relative; transition: all 0.25s;">
                            <div class="plot-chapter-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                            <span class="chapter-number" style="font-weight: 800; color: var(--primary); font-size: var(--font-2xs); text-transform: uppercase; letter-spacing: 0.04em;">第 ${chapterIndex} 章</span>
                                <div class="chapter-card-actions" onclick="event.stopPropagation()">
                                    <button class="char-action-btn edit-btn" onclick="openChapterOutlineEditModal(${globalIdx}, window.state.currentNovelData.plot.chapters[${globalIdx}])" title="編輯大綱" style="background: none; border: none; cursor: pointer; padding: 4px;">✏️</button>
                                    <button class="char-action-btn delete-btn" onclick="deletePlotChapter(${chapterIndex})" title="刪除章節" style="background: none; border: none; cursor: pointer; padding: 4px;">🗑️</button>
                                </div>
                            </div>
                            <h3 class="chapter-title" style="margin: 4px 0 8px 0; font-size: var(--font-sm); font-weight: 700; color: var(--text-primary);">${skeletonTitle}</h3>
                            <div class="chapter-summary" style="font-size: var(--font-2xs); line-height: 1.6; color: var(--text-secondary); margin-bottom: 10px; padding-bottom: 10px; border-bottom: 1px dashed rgba(255,255,255,0.03);">${skeletonSummary}</div>
                            <div class="chapter-layout-grid" style="display: grid; grid-template-columns: 1fr; gap: 12px; margin-top: 8px;">
                                ${purposeText}
                                <div class="chapter-grid-item">
                                    <div class="chapter-grid-label">⏰ 時空座標</div>
                                    <div class="chapter-grid-value">${chapter.time_setting || '待設定'}</div>
                                </div>
                                <div class="chapter-grid-item">
                                    <div class="chapter-grid-label">📍 場景地點</div>
                                    <div class="chapter-grid-value">${chapter.scene || chapter.scene_setting || '待設定'}</div>
                                </div>
                                ${emotionalToneText ? `<div class="chapter-grid-item grid-col-span-2" style="display: flex; flex-direction: row; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap;"><div class="chapter-grid-label" style="margin:0;">🎭 情緒基調</div><div>${emotionalToneText}</div></div>` : ''}
                                ${eventsHtml}
                                ${foreshadowHtml}
                                ${cliffhangerHtml}
                            </div>
                        </div>
                        <div class="timeline-insert-divider">
                            <button class="btn btn-secondary btn-xs insert-btn" onclick="event.stopPropagation(); openManualChapterInsertModal(${chapterIndex})" title="在此章後插入新章節大綱">➕ 插入新章節大綱</button>
                        </div>
                    </div>`;
                }).join('');

                const factionBadges = (factionsVal || '全域勢力')
                    .split(/[,,，、\n]+/)
                    .map(f => f.trim())
                    .filter(Boolean)
                    .map(f => `<span class="badge" style="background: rgba(59, 130, 246, 0.1); color: #3b82f6; border: 1px solid rgba(59, 130, 246, 0.15); padding: 2px 8px; border-radius: 4px; font-size: var(--font-2xs); font-weight: 600;">${f}</span>`)
                    .join(' ');

                return `
                <div class="volume-card ${isVolExpanded ? 'expanded' : ''}" id="volume-card-${volIdx}" onclick="event.stopPropagation(); window.activateVolumeNav(${volIdx})" style="border: 1px solid var(--border-color); border-radius: var(--radius-lg); background: var(--bg-secondary); margin-bottom: 20px; padding: 18px; display: flex; flex-direction: column; gap: 12px; transition: all 0.25s; position: relative; overflow: hidden; box-shadow: var(--shadow-sm); flex-shrink: 0; cursor: pointer;">
                    <div style="position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, var(--primary), #8b5cf6); pointer-events: none;"></div>
                    
                    <div class="volume-header" onclick="event.stopPropagation(); window.toggleVolumeExpand(${volIdx})" style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.03); padding-bottom: 12px; cursor: pointer;">
                        <div class="volume-title-section" style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
                            <span class="volume-index-badge" style="background: rgba(59, 130, 246, 0.12); color: #3b82f6; border: 1px solid rgba(59, 130, 246, 0.2); padding: 2px 10px; border-radius: 6px; font-size: var(--font-2xs); font-weight: 800;">VOL. ${volIdx}</span>
                            <h3 class="volume-title" style="margin: 0; font-size: var(--font-base); font-weight: 700; color: var(--text-primary);">${vol.title}</h3>
                            ${dirtyBadge}
                        </div>
                        <div class="volume-actions-section" onclick="event.stopPropagation()" style="display: flex; align-items: center; gap: 12px;">
                            ${alignButton}
                            <button class="char-action-btn edit-btn" onclick="window.openVolumeEditModal(${volIdx}, \`${safeTitle}\`, \`${safeSummary}\`, \`${safeFactions}\`)" title="編輯篇卷" style="background: none; border: none; cursor: pointer; padding: 4px; font-size: var(--font-sm); transition: transform 0.2s;">
                                ✏️
                            </button>
                            <button class="char-action-btn delete-btn" onclick="window.deleteVolume(${volIdx})" title="刪除篇卷" style="background: none; border: none; cursor: pointer; padding: 4px; font-size: var(--font-sm); transition: transform 0.2s;">
                                🗑️
                            </button>
                            <button class="btn btn-ghost btn-xs expand-toggle-btn" style="font-size: var(--font-2xs); padding: 4px 10px; border-radius: 4px; border: 1px solid var(--border-color);">${isVolExpanded ? '收合' : '展開'}</button>
                        </div>
                    </div>

                    <!-- Mini Progress indicator -->
                    <div class="volume-progress-container" style="display: flex; flex-direction: column; gap: 4px; margin: 2px 0;">
                        <div style="display: flex; justify-content: space-between; font-size: var(--font-2xs); color: var(--text-muted); font-weight: 600;">
                            <span>✍️ 正文寫作進度</span>
                            <span>${writtenChaptersCount} / ${totalChaptersCount} 章 (${progressPercent}%)</span>
                        </div>
                        <div style="height: 4px; width: 100%; background: rgba(255,255,255,0.05); border-radius: 2px; overflow: hidden;">
                            <div style="height: 100%; width: ${progressPercent}%; background: linear-gradient(90deg, var(--primary), #10b981); border-radius: 2px; transition: width 0.4s ease;"></div>
                        </div>
                    </div>
                    
                    <div class="volume-summary-box" style="font-size: var(--font-2xs); line-height: 1.6; color: var(--text-secondary); background: rgba(0,0,0,0.12); padding: 12px 14px; border-radius: var(--radius-md); border: 1px solid rgba(255,255,255,0.02); display: flex; flex-direction: column; gap: 8px;">
                        <div><strong>📌 核心情節概要：</strong>${vol.summary || '尚無概要設定。'}</div>
                        <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                            <strong>🛡️ 登場勢力陣營：</strong>
                            ${factionBadges}
                        </div>
                    </div>
                    
                    <div class="volume-chapters-list" style="display: ${isVolExpanded ? 'flex' : 'none'}; border-top: 1px dashed var(--border-color); padding-top: 14px; margin-top: 6px; flex-direction: column; gap: 12px;">
                        ${chaptersHtml}
                    </div>
                </div>
                `;
            }).join('');

            el.plotTimeline.innerHTML = statsHtml + roadmapHtml + timelineCardsHtml;

            // ===== Step 4: 動態生成快捷時間軸導航 (僅顯示當前活躍卷) =====
            // 在渲染完大綱後，動態生成右側快捷時間軸的章節跳轉按鈕
            window.renderQuickTimelineNav = function() {
                const tlNav = document.getElementById('plot-quick-timeline');
                if (tlNav) {
                    tlNav.innerHTML = ''; // 清空舊內容
                    
                    // 💡 動態讀取最新的全局數據，並自動填充缺失的虛擬卷
                    let volumes = state.currentNovelData?.volumes || [];
                    const chapters = state.currentNovelData?.plot?.chapters || [];
                    
                    let maxVolIdx = 0;
                    if (volumes.length > 0) {
                        maxVolIdx = Math.max(...volumes.map(v => parseInt(v.volume_index) || 0));
                    }
                    if (chapters.length > 0) {
                        const maxChIdx = Math.max(...chapters.map(c => parseInt(c.chapter_index) || 0));
                        maxVolIdx = Math.max(maxVolIdx, Math.ceil(maxChIdx / 50) || 1);
                    }
                    
                    if (maxVolIdx > 0) {
                        const fullVolumes = [];
                        for (let i = 1; i <= maxVolIdx; i++) {
                            const existingVol = volumes.find(v => parseInt(v.volume_index) === i);
                            if (existingVol) {
                                fullVolumes.push(existingVol);
                            } else {
                                fullVolumes.push({
                                    volume_index: i,
                                    title: `第 ${i} 卷`,
                                    summary: `本卷包含第 ${(i-1)*50 + 1} 章至第 ${i*50} 章。`,
                                    factions: "全域陣列",
                                    is_dirty: 0,
                                    chapter_count: 50,
                                    chapters_outline: []
                                });
                            }
                        }
                        volumes = fullVolumes;
                    }
                    
                    // 💡 動態生成篇卷範圍累加器（完美對齊卡片渲染邏輯）
                    const sortedVols = [...volumes].sort((a, b) => parseInt(a.volume_index) - parseInt(b.volume_index));
                    const volRanges = {};
                    let currentGlobalStart = 1;

                    sortedVols.forEach(v => {
                        const vIdx = parseInt(v.volume_index);
                        const vCount = parseInt(v.chapter_count) || 50;
                        volRanges[vIdx] = {
                            start: currentGlobalStart,
                            end: currentGlobalStart + vCount - 1,
                            count: vCount
                        };
                        currentGlobalStart += vCount;
                    });
                    
                    // 收集當前活躍卷的章節（而非全書章節）
                    const allDisplayChapters = [];
                    const activeVolNum = state.activeVolumeIdx || 1;
                    const currentVol = volumes.find(v => parseInt(v.volume_index) === activeVolNum) || volumes[0];
                    if (currentVol) {
                        const outl = Array.isArray(currentVol.chapters_outline) ? currentVol.chapters_outline : JSON.parse(currentVol.chapters_outline || '[]');
                        const volSkeletonChapters = outl;
                        
                        // 獲取當前卷的精確動態章節範圍
                        const myRange = volRanges[activeVolNum] || { start: (activeVolNum - 1) * 50 + 1, end: activeVolNum * 50, count: 50 };
                        const vStart = myRange.start;
                        const volChCount = myRange.count;
                        
                        const volMicroChapters = chapters.filter(c => {
                            const cIdx = parseInt(c.chapter_index);
                            const isInVolumeRange = !isNaN(cIdx) && (cIdx >= myRange.start && cIdx <= myRange.end);
                            if (!isInVolumeRange) return false;
                            
                            const hasMicroStructure = Array.isArray(c.events) && c.events.length > 0 ||
                                                      !!c.purpose || !!c.emotional_tone || !!c.cliffhanger;
                            const hasTitleOrSummary = c.title && c.title.trim() !== '' && c.title !== '待設定標題';
                            
                            const isSkeleton = c.brief_title !== undefined && c.brief_title !== null;
                            return !isSkeleton && (hasMicroStructure || hasTitleOrSummary);
                        });
                        
                        const skeletonMap = new Map();
                        volSkeletonChapters.forEach(ch => {
                            const rawIdx = ch.chapter_index ?? ch.chapter ?? ch.chapter_number ?? ch.index ?? ch.id;
                            const idx = parseInt(rawIdx);
                            if (!isNaN(idx)) {
                                skeletonMap.set(idx, ch);
                            }
                        });

                        const microMap = new Map();
                        volMicroChapters.forEach(ch => {
                            const idx = parseInt(ch.chapter_index);
                            if (!isNaN(idx)) {
                                microMap.set(idx, ch);
                            }
                        });
                        
                        const chapterIdxSet = new Set();
                        skeletonMap.forEach((_, idx) => chapterIdxSet.add(idx));
                        volMicroChapters.forEach(ch => chapterIdxSet.add(parseInt(ch.chapter_index)));
                        
                        if (outl.length > 0) {
                            for (let i = 0; i < volChCount; i++) {
                                chapterIdxSet.add(vStart + i);
                            }
                        }
                        
                        const sortedIdxs = Array.from(chapterIdxSet).sort((a, b) => a - b);
                        const displayChapters = sortedIdxs.map(idx => {
                            if (microMap.has(idx)) {
                                return { ...microMap.get(idx), __renderMode: 'micro' };
                            } else if (skeletonMap.has(idx)) {
                                return { ...skeletonMap.get(idx), __renderMode: 'skeleton' };
                            } else {
                                return { chapter_index: idx, title: '待設定標題', summary: '待設定摘要', __renderMode: 'empty' };
                            }
                        });
                        
                        displayChapters.forEach((ch, idx) => {
                            const chIdx = parseInt(ch.chapter_index);
                            if (ch && chIdx) {
                                // 💡【骨架章節支持】：支持 brief_title 等
                                allDisplayChapters.push({
                                    index: chIdx,
                                    title: ch.title || ch.brief_title || ch.chapter_title || ch.name || `第 ${chIdx} 章`
                                });
                            }
                        });
                    }
                    
                    // 限制顯示數量，避免快捷時間軸過長（最多顯示100項）
                    const maxItems = 100;
                    const itemsToShow = allDisplayChapters.slice(0, maxItems);
                    
                    if (itemsToShow.length > 0) {
                        itemsToShow.forEach((item, idx) => {
                            const tlItem = document.createElement('div');
                            tlItem.className = 'timeline-nav-item';
                            tlItem.innerText = `Ch ${item.index}`;
                            tlItem.title = item.title;
                            tlItem.dataset.chapterIndex = item.index;
                            
                            // 點擊時平滑滾動到對應的章節卡片
                            tlItem.onclick = () => {
                                const targetEl = document.querySelector(`[data-chapter-index="${item.index}"]`);
                                if (targetEl) {
                                    targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                    targetEl.style.boxShadow = '0 0 0 3px var(--primary)';
                                    setTimeout(() => {
                                        targetEl.style.boxShadow = '';
                                    }, 1500);
                                }
                            };
                            
                            tlNav.appendChild(tlItem);
                        });
                        
                        if (allDisplayChapters.length > maxItems) {
                            const moreIndicator = document.createElement('div');
                            moreIndicator.className = 'timeline-nav-item';
                            moreIndicator.style.fontSize = '0.65rem';
                            moreIndicator.style.color = 'var(--text-muted)';
                            moreIndicator.innerText = `+${allDisplayChapters.length - maxItems} 更多...`;
                            moreIndicator.style.cursor = 'default';
                            tlNav.appendChild(moreIndicator);
                        }
                    } else {
                        tlNav.innerHTML = '<div style="font-size: var(--font-2xs); color: var(--text-muted); text-align: center; padding: 8px;">尚無章節</div>';
                    }
                }
            };

            // 💡 渲染完後主動執行一次以生成導航列表
            window.renderQuickTimelineNav();

            // Bind mouse drag-to-scroll for roadmap track
            const track = el.plotTimeline.querySelector('.roadmap-track');
            if (track) {
                let isDown = false;
                let startX;
                let scrollLeft;
                
                track.addEventListener('mousedown', (e) => {
                    isDown = true;
                    track.classList.add('grabbing');
                    startX = e.pageX - track.offsetLeft;
                    scrollLeft = track.scrollLeft;
                });
                
                track.addEventListener('mouseleave', () => {
                    isDown = false;
                    track.classList.remove('grabbing');
                });
                
                track.addEventListener('mouseup', () => {
                    isDown = false;
                    track.classList.remove('grabbing');
                });
                
                track.addEventListener('mousemove', (e) => {
                    if (!isDown) return;
                    e.preventDefault();
                    const x = e.pageX - track.offsetLeft;
                    const walk = (x - startX) * 1.5; // scroll speed multiplier
                    track.scrollLeft = scrollLeft - walk;
                });
            }
        }
    }
}

/**
 * 渲染寫作 Tab
 */
/**
 * 渲染寫作 Tab
 */
export function renderWriterTab() {
    const chapters = state.currentNovelData?.chapters || [];
    const plotChapters = state.currentNovelData?.plot?.chapters || [];
    
    // 渲染章節列表
    if (el.writerChaptersList) {
        if (plotChapters.length === 0) {
            el.writerChaptersList.innerHTML = '<li class="empty-placeholder">尚無大綱，請先生成大綱。</li>';
        } else {
            el.writerChaptersList.innerHTML = plotChapters.map((chapter, idx) => {
                const chapterIndex = parseInt(chapter.chapter_index) || (idx + 1);
                const existingChapter = chapters.find(c => parseInt(c.chapter_index) === chapterIndex);
                const isWritten = !!(existingChapter && existingChapter.content && existingChapter.content.trim());
                const isActive = state.activeChapterIndex === chapterIndex;
                
                // 【Step 2 修復】使用動態範圍計算，不再使用固定 50 章/卷
                const chapterIdx = parseInt(chapter.chapter_index) || (idx + 1);
                let volIdx = 1;
                let chIdxInVol = 1;
                let globalChapterNum = chapterIdx; // 預設為全局章節號
                
                // 嘗試使用動態範圍計算
                if (typeof window.getChapterVolumeIndexJS === 'function') {
                    volIdx = window.getChapterVolumeIndexJS(chapterIdx);
                }
                if (typeof window.getVolumeChapterRangeJS === 'function') {
                    const range = window.getVolumeChapterRangeJS(volIdx);
                    chIdxInVol = chapterIdx - range.start + 1;
                    globalChapterNum = chapterIdx;
                } else {
                    // Fallback to fixed 50 chapters per volume
                    volIdx = Math.floor((chapterIdx - 1) / 50) + 1;
                    chIdxInVol = ((chapterIdx - 1) % 50) + 1;
                }
                
                return `
                    <li class="chapter-list-item ${isWritten ? 'written' : ''} ${isActive ? 'active' : ''}" 
                        data-chapter-index="${chapterIdx}"
                        style="display: flex; flex-direction: column; align-items: flex-start; gap: 4px; padding: 10px 12px; width: 100%; border-radius: var(--radius-sm); cursor: pointer; transition: all 0.15s; margin-bottom: 4px; box-sizing: border-box;">
                        <div style="display: flex; justify-content: space-between; width: 100%; align-items: center; pointer-events: none;">
                            <span class="chapter-list-number" style="font-size: var(--font-2xs); font-weight: 700; opacity: 0.85; letter-spacing: 0.02em;">第 ${volIdx} 卷 第 ${chIdxInVol} 章 (全局第 ${globalChapterNum} 章)</span>
                            <span class="chapter-list-status" style="font-size: var(--font-2xs); font-weight: 800;">${isWritten ? '✓' : '○'}</span>
                        </div>
                        <div class="chapter-list-title" style="font-size: var(--font-2xs); font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; width: 100%; text-align: left; margin-top: 2px; pointer-events: none; opacity: 0.95;">
                            ${chapter.title || chapter.chapter_title || chapter.brief_title || '待設定標題'}
                        </div>
                    </li>
                `;
            }).join('');
            
            // 綁定點擊事件
            el.writerChaptersList.querySelectorAll('.chapter-list-item').forEach(item => {
                item.addEventListener('click', () => {
                    const chapterIndex = parseInt(item.dataset.chapterIndex);
                    selectWriterChapter(chapterIndex);
                });
            });
        }
    }
    
    // 如果有選中的章節，渲染章節內容
    if (state.activeChapterIndex) {
        renderActiveChapter();
    }
}

/**
 * 選擇並渲染指定章節
 * @param {number} chapterIndex - 章節索引（1-based）
 */
export function selectWriterChapter(chapterIndex) {
    // 若目前有正在寫作的章節且使用者切換至不同章節，則中斷寫作流
    if (state.currentlyWritingChapterIndex && state.currentlyWritingChapterIndex !== chapterIndex) {
        // 清除寫作指示，讓後續的串流不會誤寫入舊章節
        state.currentlyWritingChapterIndex = null;
        // 隱藏正在寫作的 processing indicator（若有顯示的話）
        try { hideAgentProcessingIndicator('writer'); } catch(e) {}
    }

    state.activeChapterIndex = chapterIndex;
    
    const chapters = state.currentNovelData?.chapters || [];
    const plotChapters = state.currentNovelData?.plot?.chapters || [];
    const chapter = chapters.find(c => parseInt(c.chapter_index) === parseInt(chapterIndex));
    const plotChapter = plotChapters.find(c => parseInt(c.chapter_index || plotChapters.indexOf(c) + 1) === parseInt(chapterIndex));
    
    // 【Step 2 修復】使用動態範圍計算，不再使用固定 50 章/卷
    let volIdx = Math.floor((chapterIndex - 1) / 50) + 1;
    let chIdxInVol = ((chapterIndex - 1) % 50) + 1;
    
    // 嘗試使用動態範圍計算
    if (typeof window.getChapterVolumeIndexJS === 'function') {
        volIdx = window.getChapterVolumeIndexJS(chapterIndex);
    }
    if (typeof window.getVolumeChapterRangeJS === 'function') {
        const range = window.getVolumeChapterRangeJS(volIdx);
        chIdxInVol = chapterIndex - range.start + 1;
    }
    
    // 更新標題和狀態
    if (el.activeChapterTitle) {
        el.activeChapterTitle.textContent = `第 ${volIdx} 卷 第 ${chIdxInVol} 章（全局第 ${chapterIndex} 章）：${plotChapter?.title || plotChapter?.chapter_title || plotChapter?.brief_title || '待設定標題'}`;
    }
    
    // --- AI Thinking Process separated rendering ---
    let thinkingPreview = document.getElementById('chapter-thinking-preview');
    if (!thinkingPreview) {
        const sheetContainer = document.querySelector('.sheet-container');
        if (sheetContainer) {
            thinkingPreview = document.createElement('div');
            thinkingPreview.id = 'chapter-thinking-preview';
            thinkingPreview.className = 'chapter-thinking-preview-box hidden';
            thinkingPreview.innerHTML = `
                <div class="thinking-header" onclick="window.toggleThinkingProcessCollapse()">
                    <span>🧠 AI 歷史思考過程紀錄 (點擊展開/收合)</span>
                    <span class="thinking-collapse-icon">▼</span>
                </div>
                <div class="thinking-content-body" id="chapter-thinking-preview-text" style="display:none; white-space:pre-wrap; padding:12px; font-size:0.8rem; line-height:1.6; color:var(--text-secondary); background:rgba(0,0,0,0.02); border-top:1px solid var(--border-color);"></div>
            `;
            sheetContainer.parentNode.insertBefore(thinkingPreview, sheetContainer);
        }
    }
    
    const thinkingPreviewText = document.getElementById('chapter-thinking-preview-text');
    if (thinkingPreview && thinkingPreviewText) {
        if (chapter && chapter.thinking && chapter.thinking.trim()) {
            thinkingPreview.classList.remove('hidden');
            thinkingPreviewText.textContent = chapter.thinking;
        } else {
            thinkingPreview.classList.add('hidden');
            thinkingPreviewText.textContent = '';
        }
    }
    
    const isWritten = !!(chapter && chapter.content && chapter.content.trim());
    if (el.activeChapterStatus) {
        el.activeChapterStatus.className = `status-pill ${isWritten ? 'status-written' : 'status-draft'}`;
        el.activeChapterStatus.textContent = isWritten ? '✓ 已撰寫' : '○ 尚未撰寫';
    }
    
    const previewBox = document.getElementById('chapter-outline-preview');
    if (previewBox) {
        if (!plotChapter) {
            previewBox.innerHTML = `
                <div class="inspector-empty">
                    <span>💡 選擇左側章節查看 AI 大綱事件...</span>
                </div>`;
        } else {
            const purposeHtml = plotChapter.purpose ? `
                <div class="insp-item purpose">
                    <span class="insp-label">🎬 敘事目的</span>
                    <p class="insp-val">${plotChapter.purpose}</p>
                </div>` : '';
            
            const timeSceneHtml = `
                <div class="insp-row" style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 12px;">
                    <div class="insp-item" style="margin-bottom: 0;">
                        <span class="insp-label">⏰ 時空座標</span>
                        <p class="insp-val">${plotChapter.time_setting || '待設定'} ${plotChapter.time_span ? `(${plotChapter.time_span})` : ''}</p>
                    </div>
                    <div class="insp-item" style="margin-bottom: 0;">
                        <span class="insp-label">📍 場景地點</span>
                        <p class="insp-val">${plotChapter.scene || plotChapter.scene_setting || '待設定'}</p>
                    </div>
                </div>`;
                
            const toneHtml = plotChapter.emotional_tone ? `
                <div class="insp-item">
                    <span class="insp-label">🎭 情緒基調</span>
                    <p class="insp-val"><span class="insp-tone-badge" style="background: rgba(139,92,246,0.12); color:#8b5cf6; padding: 2px 8px; border-radius:12px; font-size:0.75rem; border:1px solid rgba(139,92,246,0.15); font-weight:600;">${plotChapter.emotional_tone}</span></p>
                </div>` : '';
                
            const currentSummary = plotChapter.summary || plotChapter.chapter_summary || plotChapter.brief_summary || '';
            const summaryHtml = currentSummary ? `
                <div class="insp-item">
                    <span class="insp-label">📝 情節概要</span>
                    <p class="insp-val summary-text" style="line-height:1.6; font-size:0.8rem; color:var(--text-secondary); background:rgba(0,0,0,0.015); border-left:3px solid var(--primary); padding:6px 12px; border-radius:0 6px 6px 0;">${currentSummary}</p>
                </div>` : '';
                
            let eventsHtml = '';
            if (Array.isArray(plotChapter.events) && plotChapter.events.length > 0) {
                const formatEventItem = (e) => {
                    if (typeof e === 'string') return e;
                    if (typeof e === 'object' && e !== null) {
                        return [e.action, e.scene, e.consequence].filter(Boolean).join(' • ') || JSON.stringify(e);
                    }
                    return String(e);
                };
                eventsHtml = `
                <div class="insp-item">
                    <span class="insp-label">📌 核心事件線</span>
                    <ul class="insp-events-list" style="padding-left: 18px; margin: 4px 0; font-size: var(--font-2xs); line-height: 1.6; color: var(--text-secondary);">
                        ${plotChapter.events.map(e => `<li>${formatEventItem(e)}</li>`).join('')}
                    </ul>
                </div>`;
            }
            
            let foreshadowHtml = '';
            if (Array.isArray(plotChapter.foreshadowing) && plotChapter.foreshadowing.length > 0) {
                foreshadowHtml = `
                <div class="insp-item">
                    <span class="insp-label">🌱 伏筆線索</span>
                    <p class="insp-val foreshadows" style="font-size:0.8rem; color:#10b981; font-weight:500;">🌱 ${plotChapter.foreshadowing.join(' | ')}</p>
                </div>`;
            }
            
            const cliffhangerHtml = plotChapter.cliffhanger ? `
                <div class="insp-item cliffhanger" style="border-top: 1px dashed var(--border-color); padding-top: 10px;">
                    <span class="insp-label">🪝 章末鉤子/懸念</span>
                    <p class="insp-val" style="font-style: italic; color:#ff9f0a; font-size:0.8rem;">${plotChapter.cliffhanger}</p>
                </div>` : '';
                
            previewBox.innerHTML = `
                <div class="story-inspector-card" style="display:flex; flex-direction:column; gap:12px;">
                    <div class="inspector-card-header" style="border-bottom: 1px solid var(--border-color); padding-bottom: 8px;">
                        <h4 style="margin:0; font-size:0.85rem; font-weight:700; color:var(--primary); display:flex; align-items:center; gap:6px;">📋 第 ${chapterIndex} 章 故事排程藍圖</h4>
                    </div>
                    <div class="inspector-card-body" style="display:flex; flex-direction:column; gap:10px;">
                        ${purposeHtml}
                        ${timeSceneHtml}
                        ${toneHtml}
                        ${summaryHtml}
                        ${eventsHtml}
                        ${foreshadowHtml}
                        ${cliffhangerHtml}
                    </div>
                </div>
            `;
        }
    }
    
    // 更新正文編輯器
    if (el.editorProse) {
        const isCurrentChapterWriting = state.currentlyWritingChapterIndex === chapterIndex;
        if (isCurrentChapterWriting) {
            // 💡 核心優化：如果切換回到正在 AI 背景寫作的章節，直接讀取並銜接目前背景生成的緩衝區內容！
            el.editorProse.value = state.writingBuffer || chapter?.content || '';
        } else {
            // 否則，正常載入資料庫中已有的內容
            el.editorProse.value = chapter?.content || '';
        }
        el.editorProse.disabled = false;
    }
    
    // 啟用 AI 按鈕與手動按鈕
    if (el.btnWriteChapter) el.btnWriteChapter.disabled = false;
    if (el.btnEditChapter) el.btnEditChapter.disabled = false;
    if (el.btnProseSave) el.btnProseSave.disabled = false;
    
    // 更新列表中的選中狀態
    el.writerChaptersList?.querySelectorAll('.chapter-list-item').forEach(item => {
        if (parseInt(item.dataset.chapterIndex) === chapterIndex) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });
}

/**
 * 渲染當前選中的章節內容
 */
export function renderActiveChapter() {
    if (!state.activeChapterIndex) return;
    selectWriterChapter(state.activeChapterIndex);
}

/**
 * 渲染聊天訊息
 */
export function renderChatMessages() {
    if (!el.chatMessagesContainer) return;
    
    const messages = state.currentNovelData?.chat_memory || state.currentNovelData?.chat_messages || [];
    
    // Render the default system greeting first
    el.chatMessagesContainer.innerHTML = `
        <div class="message system-msg">
            <div class="msg-sender">AI Novel Director</div>
            <div class="msg-content">你好！我是你的小說創作協同總監。我擁有對當前小說的完整長期記憶 (SQLite)。<br><br>你可以對我發出指令，例如：<br>「幫我修改主角設定，讓他背景多一條伏筆」<br>「給我想 3 個世界觀的魔法限制」<br>「重寫第一章，讓氛圍更懸疑」<br><br>我會直接指導各個 Agent 配合，或是為你提供靈感！</div>
        </div>
    `;
    
    if (messages.length > 0) {
        messages.forEach((msg, idx) => {
            const msgDiv = document.createElement('div');
            const isUser = msg.role === 'user';
            const isSystem = msg.role === 'system';
            const className = isUser ? 'user-msg' : (isSystem ? 'system-msg' : 'assistant-msg');
            const sender = isUser ? 'You' : (isSystem ? 'System' : 'Novel Director');
            
            msgDiv.className = `message ${className}`;
            
            // Format timestamp if available
            const dateStr = msg.timestamp || msg.created_at;
            let formattedTime = "";
            if (dateStr) {
                try {
                    // 1. 將時間字串轉為 ISO 格式並補上 Z，確保 JavaScript 將其視為 UTC 時間
                    // 2. 使用 toLocaleTimeString 自動轉換為瀏覽器所在的本地時區 (台灣)
                    const d = new Date(dateStr.replace(' ', 'T') + 'Z'); 
                    
                    if (!isNaN(d.getTime())) {
                        formattedTime = d.toLocaleTimeString([], { 
                            hour: '2-digit', 
                            minute: '2-digit', 
                            hour12: false 
                        });
                    }
                } catch(e) {
                    console.error("時間格式化錯誤:", e);
                }
            }
            
            const isLatest = idx === messages.length - 1;
            if (isLatest && !isUser && !isSystem && !state.isAutoExecuteMode) {
                const parsed = parseDirectorDecisionText(msg.content, state.activeTab);
                if (parsed && parsed.action && parsed.action !== 'FINISH') {
                    const actionLabels = {
                        'CONTINUE': '繼續下一階段',
                        'AUTO_REGENERATE': '重新生成',
                        'GO_BACK_TO_WORLDVIEW': '回退到世界觀',
                        'GO_BACK_TO_CHARACTERS': '回退到角色',
                        'GO_BACK_TO_PLOT': '回退到大綱',
                        'WRITE_ALL_CHAPTERS': '開始寫全書',
                        'WAIT_USER': '等待確認',
                        'FINISH': '任務完成'
                    };
                    
                    const buttonsHtml = `
                        <div class="chat-action-buttons">
                            <button class="btn-chat-action" data-action="accept" title="執行總監建議的動作">✅ 接受總監決策${parsed.action ? ` (${actionLabels[parsed.action] || parsed.action})` : ''}</button>
                            <button class="btn-chat-action" data-action="continue">▶️ 強制繼續下一階段</button>
                            <button class="btn-chat-action" data-action="regen">🔄 重新生成此階段</button>
                            <button class="btn-chat-action" data-action="pause">⏸️ 暫停並手動修改</button>
                        </div>
                    `;
                    
                    let thinkingHtml = '';
                    if (msg.thinking && msg.thinking.trim()) {
                        thinkingHtml = `
                            <details class="thinking-details" style="margin-bottom: 8px; border: 1px solid var(--border-color); border-radius: 6px; background: rgba(255, 255, 255, 0.02); overflow: hidden;">
                                <summary style="cursor: pointer; font-size: var(--font-2xs); padding: 6px 10px; color: var(--text-muted); font-weight: 600; background: rgba(0, 0, 0, 0.05); user-select: none; display: flex; align-items: center; gap: 6px; outline: none;">
                                    <span>🧠 AI 思考過程 (點擊展開/收合)</span>
                                </summary>
                                <pre style="margin: 0; padding: 10px; font-family: 'SFMono-Regular', Consolas, monospace; font-size: var(--font-2xs); line-height: 1.5; color: var(--text-secondary); background: rgba(0, 0, 0, 0.1); white-space: pre-wrap; word-break: break-all;">${msg.thinking}</pre>
                            </details>
                        `;
                    }
                    
                    msgDiv.innerHTML = `
                        <div class="msg-sender-row">
                            <div class="msg-sender">${sender}</div>
                            ${formattedTime ? `<div class="msg-timestamp">${formattedTime}</div>` : ''}
                        </div>
                        <div class="msg-content">
                            ${thinkingHtml}
                <div class="msg-text-markdown">${renderMarkdown(escapeBackticks(msg.content))}</div>
                            ${buttonsHtml}
                        </div>
                    `;
                    
                    setTimeout(() => {
                        const buttonsContainer = msgDiv.querySelector('.chat-action-buttons');
                        if (buttonsContainer) {
                            buttonsContainer.querySelectorAll('.btn-chat-action').forEach(btn => {
                                btn.addEventListener('click', async function() {
                                    if (state.isPipelineRunning) {
                                        showToast('⚠️ 管道正在運行中，請稍候...');
                                        return;
                                    }
                                    const choice = this.dataset.action;
                                    buttonsContainer.querySelectorAll('.btn-chat-action').forEach(b => {
                                        b.disabled = true;
                                        b.style.opacity = '0.5';
                                    });
                                    this.style.opacity = '1';
                                    this.style.borderColor = 'var(--primary)';
                                    this.style.fontWeight = '700';
                                    
                                    if (typeof window.resumePipelineWithDecision === 'function') {
                                        await window.resumePipelineWithDecision(state.activeTab, parsed, choice);
                                    }
                                });
                            });
                        }
                    }, 0);
                    
                    el.chatMessagesContainer.appendChild(msgDiv);
                    return;
                }
            }
            
            let thinkingHtml = '';
            if (msg.thinking && msg.thinking.trim()) {
                thinkingHtml = `
                    <details class="thinking-details" style="margin-bottom: 8px; border: 1px solid var(--border-color); border-radius: 6px; background: rgba(255, 255, 255, 0.02); overflow: hidden;">
                        <summary style="cursor: pointer; font-size: var(--font-2xs); padding: 6px 10px; color: var(--text-muted); font-weight: 600; background: rgba(0, 0, 0, 0.05); user-select: none; display: flex; align-items: center; gap: 6px; outline: none;">
                            <span>🧠 AI 思考過程 (點擊展開/收合)</span>
                        </summary>
                        <pre style="margin: 0; padding: 10px; font-family: 'SFMono-Regular', Consolas, monospace; font-size: var(--font-2xs); line-height: 1.5; color: var(--text-secondary); background: rgba(0, 0, 0, 0.1); white-space: pre-wrap; word-break: break-all;">${msg.thinking}</pre>
                    </details>
                `;
            }

            msgDiv.innerHTML = `
                <div class="msg-sender-row">
                    <div class="msg-sender">${sender}</div>
                    ${formattedTime ? `<div class="msg-timestamp">${formattedTime}</div>` : ''}
                </div>
                <div class="msg-content">
                    ${thinkingHtml}
                <div class="msg-text-markdown">${renderMarkdown(escapeBackticks(msg.content))}</div>
                </div>
            `;
            el.chatMessagesContainer.appendChild(msgDiv);
        });
    }
    
    // 滾動到底部
    if (typeof window.smartScrollToBottom === 'function') {
        window.smartScrollToBottom(el.chatMessagesContainer, true);
    } else {
        el.chatMessagesContainer.scrollTop = el.chatMessagesContainer.scrollHeight;
    }
}

/**
 * 新增聊天訊息
 * @param {string} role - 角色（user / assistant / system）
 * @param {string} content - 訊息內容
 */
export function appendChatMessage(role, content) {
    if (!el.chatMessagesContainer) return;
    
    const msgDiv = document.createElement('div');
    const isUser = role === 'user';
    const isSystem = role === 'system';
    const className = isUser ? 'user-msg' : (isSystem ? 'system-msg' : 'assistant-msg');
    const sender = isUser ? 'You' : (isSystem ? 'System' : 'Novel Director');
    
    msgDiv.className = `message ${className}`;
    
    const now = new Date();
    const formattedTime = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
    
    msgDiv.innerHTML = `
        <div class="msg-sender-row">
            <div class="msg-sender">${sender}</div>
            <div class="msg-timestamp">${formattedTime}</div>
        </div>
        <div class="msg-content">
            <div class="msg-text-markdown">${renderMarkdown(content)}</div>
        </div>
    `;
    
    el.chatMessagesContainer.appendChild(msgDiv);
    if (typeof window.smartScrollToBottom === 'function') {
        window.smartScrollToBottom(el.chatMessagesContainer, true);
    } else {
        el.chatMessagesContainer.scrollTop = el.chatMessagesContainer.scrollHeight;
    }
}

