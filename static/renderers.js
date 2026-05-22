// ==========================================
// RENDERERS - UI 渲染函式
// ==========================================

import { state } from './state.js';
import { el } from './dom.js';
import { showToast } from './toast.js';
import { requestAPI } from './api.js';
import { parseWorldviewJSON, renderMarkdown } from './utils.js';

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
    
    // 三幕式結構 (data-section 映射為 three-act 配合 app.js)
    if (js.three_act_structure && js.three_act_structure.length > 0) {
        strategyHtml += `
            <div class="worldview-section-card" data-section="three-act">
                <div class="worldview-section-header">
                    <div class="worldview-section-title">
                        <span class="worldview-section-badge badge-warning">🎭</span>
                        三幕式結構
                    </div>
                    <div class="worldview-section-actions">
                        <button onclick="toggleSectionExpand('three-act')" title="展開/收合">↕</button>
                        <button onclick="editWorldviewComplexList('three_act_structure', '三幕式結構', 'title', 'content')" title="編輯">✏️</button>
                    </div>
                </div>
                <div class="worldview-section-content" id="content-three-act">
                    ${js.three_act_structure.map((item, idx) => `
                        <div class="worldview-sub-item">
                            <div class="worldview-sub-item-title">${item.title || `項目 ${idx + 1}`}</div>
                            <div class="worldview-sub-item-content">${renderMarkdown(item.content) || '<em style="color:var(--text-muted)">尚無內容</em>'}</div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }
    
    // 角色漸進規劃 (data-section 映射為 character-waves 配合 app.js)
    if (js.progressive_character_plan && js.progressive_character_plan.length > 0) {
        strategyHtml += `
            <div class="worldview-section-card" data-section="character-waves">
                <div class="worldview-section-header">
                    <div class="worldview-section-title">
                        <span class="worldview-section-badge badge-purple">👥</span>
                        角色漸進規劃策略
                    </div>
                    <div class="worldview-section-actions">
                        <button onclick="toggleSectionExpand('character-waves')" title="展開/收合">↕</button>
                        <button onclick="editWorldviewComplexList('progressive_character_plan', '角色漸進規劃策略', 'title', 'content')" title="編輯">✏️</button>
                    </div>
                </div>
                <div class="worldview-section-content" id="content-character-waves">
                    ${js.progressive_character_plan.map((item, idx) => `
                        <div class="worldview-sub-item">
                            <div class="worldview-sub-item-title">${item.title || `階段 ${idx + 1}`}</div>
                            <div class="worldview-sub-item-content">${renderMarkdown(item.content) || '<em style="color:var(--text-muted)">尚無內容</em>'}</div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }
    
    // 伏筆種子 (data-section 映射為 seeds 配合 app.js)
    if (js.foreshadowing_seeds && js.foreshadowing_seeds.length > 0) {
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
                    <ul class="worldview-list">
                        ${js.foreshadowing_seeds.map((item, idx) => `
                            <li>${renderMarkdown(typeof item === 'string' ? item : JSON.stringify(item))}</li>
                        `).join('')}
                    </ul>
                </div>
            </div>
        `;
    }
    
    // 關鍵轉折點 (data-section 映射為 turning-points 配合 app.js)
    if (js.key_turning_points && js.key_turning_points.length > 0) {
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
                    <ul class="worldview-list">
                        ${js.key_turning_points.map((item, idx) => `
                            <li>${renderMarkdown(typeof item === 'string' ? item : JSON.stringify(item))}</li>
                        `).join('')}
                    </ul>
                </div>
            </div>
        `;
    }

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
    if (cardIndex === 0) return (js.three_act_structure || []).length;
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
        subItems = Array.from(activeCard.querySelectorAll('.worldview-sub-item'));
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
    return `
        <div class="worldview-section-card" data-section="${sectionId}">
            <div class="worldview-section-header">
                <div class="worldview-section-title">
                    <span class="worldview-section-badge ${badgeClass}">${icon}</span>
                    ${title}
                </div>
                <div class="worldview-section-actions">
                    <button onclick="toggleSectionExpand('${sectionId}')" title="展開/收合">↕</button>
                    <button onclick="editWorldviewSection('${sectionId}', '${title}', \`${content.replace(/`/g, '\\`').replace(/\$/g, '\\$')}\`)" title="編輯">✏️</button>
                </div>
            </div>
            <div class="worldview-section-content" id="content-${sectionId}">
                ${renderMarkdown(content)}
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
                            <button class="char-action-btn edit-btn" onclick="openCharacterEditModal(${idx}, state.currentNovelData.characters.characters[${idx}])" title="編輯角色">
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
    
    el.editorPlotJson.value = state.currentNovelData?.plot_raw || JSON.stringify({ chapters: [] }, null, 2);
    
    // 渲染時間線
    if (el.plotTimeline) {
        if (chapters.length === 0) {
            el.plotTimeline.innerHTML = `
                <div class="empty-placeholder">
                    📋 尚無章節規劃。請點擊上方「AI 自動拆分章節」來建立整本小說大綱，或手動建立第一章。
                    <button class="btn btn-primary btn-sm mt-4" onclick="openManualChapterInsertModal(0)">➕ 手動新增第一章</button>
                </div>`;
        } else {
            el.plotTimeline.innerHTML = chapters.map((chapter, idx) => {
                const emotionalToneText = chapter.emotional_tone ? `<span class="chapter-tone-badge">🎭 ${chapter.emotional_tone}</span>` : '';
                const purposeText = chapter.purpose ? `<div class="chapter-purpose-text">🎬 <strong>目標:</strong> ${chapter.purpose}</div>` : '';
                
                // Bulleted list of events (limit to first 3 and show +N more if many)
                let eventsList = '';
                if (Array.isArray(chapter.events) && chapter.events.length > 0) {
                    const formatEventItem = (e) => {
                        if (typeof e === 'string') return e;
                        if (typeof e === 'object' && e !== null) {
                            return [e.action, e.scene, e.consequence].filter(Boolean).join(' • ') || JSON.stringify(e);
                        }
                        return String(e);
                    };
                    const displayedEvents = chapter.events.slice(0, 3);
                    const remaining = chapter.events.length - 3;
                    eventsList = `
                    <ul class="chapter-events-bullets">
                        ${displayedEvents.map(e => `<li>${formatEventItem(e)}</li>`).join('')}
                        ${remaining > 0 ? `<li class="more-events">+ ${remaining} 個事件...</li>` : ''}
                    </ul>`;
                }

                // Bulleted list of foreshadowings
                let foreshadowList = '';
                if (Array.isArray(chapter.foreshadowing) && chapter.foreshadowing.length > 0) {
                    foreshadowList = `
                    <div class="chapter-foreshadow-bullets">
                        🌱 ${chapter.foreshadowing.join(' | ')}
                    </div>`;
                }

                return `
                <div class="plot-timeline-node-wrapper">
                    <div class="plot-chapter-item" data-index="${idx}" onclick="openChapterOutlineEditModal(${idx}, state.currentNovelData.plot.chapters[${idx}])">
                        <div class="plot-chapter-header">
                            <span class="chapter-number">第 ${chapter.chapter_index || (idx + 1)} 章</span>
                            <div class="chapter-card-actions" onclick="event.stopPropagation()">
                                <button class="char-action-btn edit-btn" onclick="openChapterOutlineEditModal(${idx}, state.currentNovelData.plot.chapters[${idx}])" title="編輯大綱">
                                    ✏️
                                </button>
                                <button class="char-action-btn delete-btn" onclick="deletePlotChapter(${idx})" title="刪除章節">
                                    🗑️
                                </button>
                            </div>
                        </div>
                        
                        <h3 class="chapter-title">${chapter.title || '待設定標題'}</h3>
                        
                        <div class="chapter-summary">${chapter.summary || '待設定摘要'}</div>
                        
                        ${purposeText}
                        ${eventsList}
                        ${foreshadowList}
                        
                        <div class="chapter-meta">
                            <span class="chapter-time">⏰ ${chapter.time_setting || '待設定'}</span>
                            <span class="chapter-scene">📍 ${chapter.scene || chapter.scene_setting || '待設定'}</span>
                            ${emotionalToneText}
                        </div>
                    </div>
                    
                    <div class="timeline-insert-divider">
                        <button class="btn btn-secondary btn-xs insert-btn" onclick="event.stopPropagation(); openManualChapterInsertModal(${chapter.chapter_index || (idx + 1)})" title="在此章後插入新章節大綱">
                            ➕ 插入新章節大綱
                        </button>
                    </div>
                </div>
                `;
            }).join('');
        }
    }
}

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
                const chapterIndex = chapter.chapter_index || (idx + 1);
                const existingChapter = chapters.find(c => c.chapter_index === chapterIndex);
                const isWritten = !!existingChapter;
                const isActive = state.activeChapterIndex === chapterIndex;
                
                return `
                    <li class="chapter-list-item ${isWritten ? 'written' : ''} ${isActive ? 'active' : ''}" 
                        data-chapter-index="${chapterIndex}">
                        <div class="chapter-list-item-header">
                            <span class="chapter-list-number">第 ${chapterIndex} 章</span>
                            <span class="chapter-list-status">${isWritten ? '✓' : '○'}</span>
                        </div>
                        <div class="chapter-list-title">${chapter.title || '待設定標題'}</div>
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
    state.activeChapterIndex = chapterIndex;
    
    const chapters = state.currentNovelData?.chapters || [];
    const plotChapters = state.currentNovelData?.plot?.chapters || [];
    const chapter = chapters.find(c => c.chapter_index === chapterIndex);
    const plotChapter = plotChapters.find(c => (c.chapter_index || plotChapters.indexOf(c) + 1) === chapterIndex);
    
    // 更新標題和狀態
    if (el.activeChapterTitle) {
        el.activeChapterTitle.textContent = `第 ${chapterIndex} 章：${plotChapter?.title || '待設定標題'}`;
    }
    
    if (el.activeChapterStatus) {
        el.activeChapterStatus.className = `status-pill ${chapter ? 'status-written' : 'status-draft'}`;
        el.activeChapterStatus.textContent = chapter ? '✓ 已撰寫' : '○ 尚未撰寫';
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
                
            const summaryHtml = plotChapter.summary ? `
                <div class="insp-item">
                    <span class="insp-label">📝 情節概要</span>
                    <p class="insp-val summary-text" style="line-height:1.6; font-size:0.8rem; color:var(--text-secondary); background:rgba(0,0,0,0.015); border-left:3px solid var(--primary); padding:6px 12px; border-radius:0 6px 6px 0;">${plotChapter.summary}</p>
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
                    <ul class="insp-events-list" style="padding-left: 18px; margin: 4px 0; font-size: 0.8rem; line-height: 1.6; color: var(--text-secondary);">
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
        el.editorProse.value = chapter?.content || '';
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
    
    const messages = state.currentNovelData?.chat_messages || [];
    
    if (messages.length === 0) {
        el.chatMessagesContainer.innerHTML = `
            <div class="chat-message system">
                <div class="msg-content">💡 選擇一部小說開始討論。</div>
            </div>
        `;
        return;
    }
    
    el.chatMessagesContainer.innerHTML = messages.map(msg => `
        <div class="chat-message ${msg.role}">
            <div class="msg-content">${msg.content}</div>
        </div>
    `).join('');
    
    // 滾動到底部
    el.chatMessagesContainer.scrollTop = el.chatMessagesContainer.scrollHeight;
}

/**
 * 新增聊天訊息
 * @param {string} role - 角色（user / assistant / system）
 * @param {string} content - 訊息內容
 */
export function appendChatMessage(role, content) {
    if (!el.chatMessagesContainer) return;
    
    const msgDiv = document.createElement('div');
    msgDiv.className = `chat-message ${role}`;
    msgDiv.innerHTML = `<div class="msg-content">${content}</div>`;
    
    el.chatMessagesContainer.appendChild(msgDiv);
    el.chatMessagesContainer.scrollTop = el.chatMessagesContainer.scrollHeight;
}