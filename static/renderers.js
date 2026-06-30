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

// Compatible renderer for Foreshadowing Seeds (🌱)
function formatForeshadowingSeed(item) {
    if (typeof item === 'string') {
        const trimmed = item.trim();
        if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
            try {
                return formatForeshadowingSeed(JSON.parse(trimmed));
            } catch(e) {}
        }
        return renderMarkdown(item);
    }
    if (typeof item === 'object' && item !== null) {
        const id = item.id !== undefined ? `Seed-${item.id}` : '';
        const name = item.name || item.title || '未命名伏筆';
        const description = item.description || item.detail || item.content || item.summary || item.seed || '';
        const setupHint = item.setup_hint || item.setup || '';
        const payoffHint = item.payoff_hint || item.payoff || '';
        const relatedChars = Array.isArray(item.related_characters) ? item.related_characters.join(', ') : (item.related_characters || '');
        const thematicLink = item.thematic_link || '';

        return `
            <div class="strategy-subcard" style="background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 6px; padding: 12px; margin-bottom: 10px; box-shadow: var(--shadow-sm);">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; border-bottom: 1px solid var(--border-color); padding-bottom: 6px;">
                    <span style="font-weight: 700; color: var(--info); font-size: 0.95rem; display: flex; align-items: center; gap: 4px;">🌱 ${name}</span>
                    ${id ? `<span style="font-family: monospace; font-size: 0.8rem; background: rgba(59, 130, 246, 0.1); color: var(--primary); padding: 2px 6px; border-radius: 4px; font-weight: 600;">${id}</span>` : ''}
                </div>
                <div style="font-size: 0.85rem; line-height: 1.5; color: var(--text-secondary); margin-bottom: 8px;">
                    ${renderMarkdown(description)}
                </div>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 8px; font-size: 0.8rem; border-top: 1px dashed var(--border-color); padding-top: 8px;">
                    ${setupHint ? `<div><span style="color: var(--text-muted); font-weight: 600;">📍 埋設契機: </span>${setupHint}</div>` : ''}
                    ${payoffHint ? `<div><span style="color: var(--text-muted); font-weight: 600;">🔑 回收反轉: </span>${payoffHint}</div>` : ''}
                    ${relatedChars ? `<div><span style="color: var(--text-muted); font-weight: 600;">👥 關聯角色: </span>${relatedChars}</div>` : ''}
                    ${thematicLink ? `<div style="grid-column: 1 / -1;"><span style="color: var(--text-muted); font-weight: 600;">🎯 主題連結: </span>${thematicLink}</div>` : ''}
                </div>
            </div>
        `;
    }
    return String(item);
}

// Compatible renderer for Key Turning Points (⚡)
function formatKeyTurningPoint(item) {
    const safeHtml = (str) => {
        if (!str) return '';
        return str
            .replace(/javascript:/gi, '')
            .replace(/on\w+=/gi, '')
            .replace(/<script[\s\S]*?<\/script>/gi, '')
            .replace(/<style[\s\S]*?<\/style>/gi, '');
    };

    if (typeof item === 'string') {
        const trimmed = item.trim();
        if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
            try {
                return formatKeyTurningPoint(JSON.parse(trimmed));
            } catch(e) {}
        }
        const hasUnescapedHtml = /<[a-z][\s\S]*>/i.test(item);
        if (hasUnescapedHtml) {
            return safeHtml(item);
        }
        return renderMarkdown(item);
    }
    if (typeof item === 'object' && item !== null) {
        const id = item.id !== undefined ? `Turn-${item.id}` : '';
        const name = item.name || item.turning_point_name || item.title || '未命名轉折點';
        const trigger = item.trigger_condition || item.trigger || '';
        const structuralImpact = item.structural_impact || item.impact || '';
        const emotionalStakes = item.emotional_stakes || '';
        const relatedSeeds = Array.isArray(item.related_seeds) ? item.related_seeds.join(', ') : (item.related_seeds || '');
        const globalImpact = item.global_impact || item.detail || item.summary || item.description || '';

        return `
            <div class="strategy-subcard" style="background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 6px; padding: 12px; margin-bottom: 10px; box-shadow: var(--shadow-sm);">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; border-bottom: 1px solid var(--border-color); padding-bottom: 6px;">
                    <span style="font-weight: 700; color: var(--danger); font-size: 0.95rem; display: flex; align-items: center; gap: 4px;">⚡ ${name}</span>
                    ${id ? `<span style="font-family: monospace; font-size: 0.8rem; background: rgba(239, 68, 68, 0.1); color: var(--danger); padding: 2px 6px; border-radius: 4px; font-weight: 600;">${id}</span>` : ''}
                </div>
                ${trigger ? `<div style="font-size: 0.85rem; line-height: 1.5; color: var(--text-primary); margin-bottom: 8px;"><span style="font-weight: 600; color: var(--text-muted);">💥 觸發條件: </span>${trigger}</div>` : ''}
                ${globalImpact ? `<div style="font-size: 0.85rem; line-height: 1.5; color: var(--text-secondary); margin-bottom: 8px;">${renderMarkdown(globalImpact)}</div>` : ''}
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 8px; font-size: 0.8rem; border-top: 1px dashed var(--border-color); padding-top: 8px;">
                    ${structuralImpact ? `<div><span style="color: var(--text-muted); font-weight: 600;">📜 結構影響: </span>${structuralImpact}</div>` : ''}
                    ${emotionalStakes ? `<div><span style="color: var(--text-muted); font-weight: 600;">💔 情感代價: </span>${emotionalStakes}</div>` : ''}
                    ${relatedSeeds ? `<div><span style="color: var(--text-muted); font-weight: 600;">🌱 關聯伏筆: </span>${relatedSeeds}</div>` : ''}
                </div>
            </div>
        `;
    }
    return String(item);
}

function extractForeshadowSeedId(value) {
    const raw = String(value ?? '');
    const explicit = raw.match(/(?:\bFS|\bSeed|\[Seed-)\s*-?\s*0*(\d{1,4})\]?/i);
    if (explicit) return String(parseInt(explicit[1], 10)).padStart(3, '0');
    const fallback = raw.match(/0*(\d{1,4})/);
    return fallback ? String(parseInt(fallback[1], 10)).padStart(3, '0') : '';
}

// Helper to look up detailed seed description from worldview
function getSeedDescription(idOrString, worldviewJs) {
    if (typeof idOrString === 'object' && idOrString !== null) {
        const id = parseInt(idOrString.id);
        if (!isNaN(id)) {
            const seeds = worldviewJs?.foreshadowing_seeds || [];
            for (const seed of seeds) {
                if (typeof seed === 'object' && seed !== null && parseInt(seed.id) === id) {
                    const val = seed.detail || seed.content || seed.summary || seed.description || seed.seed;
                    return typeof val === 'string' ? val : JSON.stringify(seed);
                }
            }
            return `伏筆種子 #${id}`;
        }
        return JSON.stringify(idOrString);
    }
    const idStr = extractForeshadowSeedId(idOrString);
    const idNum = parseInt(idStr, 10);
    if (isNaN(idNum)) {
        return String(idOrString);
    }
    const seeds = worldviewJs?.foreshadowing_seeds || [];
    for (const seed of seeds) {
        if (typeof seed === 'object' && seed !== null) {
            if (parseInt(seed.id) === idNum) {
                const val = seed.detail || seed.content || seed.summary || seed.description || seed.seed;
                return typeof val === 'string' ? val : JSON.stringify(seed);
            }
        } else if (typeof seed === 'string') {
            const indexMatch = seed.match(/\[Seed-(\d+)\]/i);
            if (indexMatch && parseInt(indexMatch[1]) === idNum) {
                return seed.replace(/\[Seed-\d+\]/gi, '').trim();
            }
        }
    }
    if (idNum > 0 && idNum <= seeds.length) {
        const fallbackSeed = seeds[idNum - 1];
        if (typeof fallbackSeed === 'string') {
            return fallbackSeed.replace(/\[Seed-\d+\]/gi, '').trim();
        } else if (typeof fallbackSeed === 'object' && fallbackSeed !== null) {
            const val = fallbackSeed.detail || fallbackSeed.content || fallbackSeed.summary || fallbackSeed.seed;
            return typeof val === 'string' ? val : JSON.stringify(fallbackSeed);
        }
    }
    return `伏筆種子 #${idNum}`;
}

// Helper to look up detailed turning point description from worldview
function getTurningPointDescription(idOrString, worldviewJs) {
    const safeStr = (v) => typeof v === 'string' ? v : (v && typeof v === 'object' ? JSON.stringify(v) : String(v));
    if (typeof idOrString === 'object' && idOrString !== null) {
        const id = parseInt(idOrString.id);
        if (!isNaN(id)) {
            const turns = worldviewJs?.key_turning_points || [];
            for (const turn of turns) {
                if (typeof turn === 'object' && turn !== null && parseInt(turn.id) === id) {
                    const trigger = safeStr(turn.trigger || turn.name || turn.title || '');
                    const impact = turn.global_impact ? safeStr(turn.global_impact) : '';
                    return impact ? `${trigger}: ${impact}` : trigger;
                }
            }
            return `關鍵轉折點 #${id}`;
        }
        return JSON.stringify(idOrString);
    }
    const idStr = String(idOrString).replace(/[^\d]/g, '');
    const idNum = parseInt(idStr);
    if (isNaN(idNum)) {
        return String(idOrString);
    }
    const turns = worldviewJs?.key_turning_points || [];
    for (const turn of turns) {
        if (typeof turn === 'object' && turn !== null) {
            if (parseInt(turn.id) === idNum) {
                const trigger = safeStr(turn.trigger || turn.name || turn.title || '');
                const impact = turn.global_impact ? safeStr(turn.global_impact) : '';
                return impact ? `${trigger}: ${impact}` : trigger;
            }
        } else if (typeof turn === 'string') {
            const indexMatch = turn.match(/\[Turn-(\d+)\]/i);
            if (indexMatch && parseInt(indexMatch[1]) === idNum) {
                return turn.replace(/\[Turn-\d+\]/gi, '').trim();
            }
        }
    }
    if (idNum > 0 && idNum <= turns.length) {
        const fallbackTurn = turns[idNum - 1];
        if (typeof fallbackTurn === 'string') {
            return fallbackTurn.replace(/\[Turn-\d+\]/gi, '').trim();
        } else if (typeof fallbackTurn === 'object' && fallbackTurn !== null) {
            const trigger = safeStr(fallbackTurn.trigger || fallbackTurn.name || fallbackTurn.title || '');
            const impact = fallbackTurn.global_impact ? safeStr(fallbackTurn.global_impact) : '';
            return impact ? `${trigger}: ${impact}` : trigger;
        }
    }
    return `關鍵轉折點 #${idNum}`;
}

/**
 * 渲染當前激活的 Tab
 */
export function renderActiveTab() {
    // Normalize: 'editor' has no dedicated panel/tab, map to 'writer'
    const activePanel = state.activeTab === 'editor' ? 'writer' : state.activeTab;

    // Hide all workpanels, activate correct nav tab
    el.navTabs.forEach(t => {
        if (t.dataset.tab === activePanel) {
            t.classList.add('active');
        } else {
            t.classList.remove('active');
        }
    });
    
    el.workpanels.forEach(p => {
        if (p.id === `panel-${activePanel}`) {
            p.classList.add('active');
        } else {
            p.classList.remove('active');
        }
    });
    
    if (!state.currentNovelData) return;
    
    // Call specific tab renderer
    if (activePanel === 'worldview') renderWorldviewTab();
    if (activePanel === 'characters') renderCharactersTab();
    if (activePanel === 'plot') renderPlotTab();
    if (activePanel === 'writer') renderWriterTab();
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
                    <div style="display: flex; flex-direction: column; gap: 4px; width: 100%;">
                        ${seedsList.map((item, idx) => formatForeshadowingSeed(item)).join('')}
                    </div>
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
                    <div style="display: flex; flex-direction: column; gap: 4px; width: 100%;">
                        ${tpList.map((item, idx) => formatKeyTurningPoint(item)).join('')}
                    </div>
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
 * 渲染結構化 JSON 內容為美觀的 HTML 卡片與列表
 */
function renderStructuredContent(data) {
    if (data === null || data === undefined) return '';
    if (typeof data !== 'object') return renderMarkdown(String(data));

    // 1. 如果是陣列
    if (Array.isArray(data)) {
        return `
            <ul style="padding-left: 20px; margin: 8px 0; display: flex; flex-direction: column; gap: 6px;">
                ${data.map(item => `
                    <li style="font-size: 0.9rem; color: var(--text-secondary); line-height: 1.4;">
                        ${typeof item === 'object' ? renderStructuredContent(item) : renderMarkdown(String(item))}
                    </li>
                `).join('')}
            </ul>
        `;
    }

    // 2. 如果是核心衝突結構 ( factions, core_tension )
    if (data.factions || data.core_tension) {
        let html = '';
        if (data.core_tension) {
            html += `
                <div class="conflict-core-tension" style="background: rgba(239, 68, 68, 0.05); border-left: 4px solid var(--danger); padding: 12px; border-radius: 6px; margin-bottom: 16px; font-weight: 500; font-size: 0.9rem; line-height: 1.5; color: var(--text-primary);">
                    ${renderMarkdown(data.core_tension)}
                </div>
            `;
        }
        if (Array.isArray(data.factions)) {
            html += `
                <div class="factions-container" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; margin-top: 8px;">
                    ${data.factions.map(fac => `
                        <div class="faction-card" style="background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 6px; padding: 12px; box-shadow: var(--shadow-sm);">
                            <div style="font-weight: 700; color: var(--danger); font-size: 0.95rem; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
                                🛡️ ${fac.name || '未命名勢力'}
                            </div>
                            ${fac.stance ? `<div style="font-size: 0.85rem; margin-bottom: 4px; line-height: 1.4;"><span style="color: var(--text-muted); font-weight: 600;">立場: </span>${fac.stance}</div>` : ''}
                            ${fac.secret_goal ? `<div style="font-size: 0.85rem; margin-bottom: 4px; line-height: 1.4;"><span style="color: var(--text-muted); font-weight: 600;">秘密意圖: </span>${fac.secret_goal}</div>` : ''}
                            ${fac.conflict_root ? `<div style="font-size: 0.85rem; line-height: 1.4;"><span style="color: var(--text-muted); font-weight: 600;">衝突根源: </span>${fac.conflict_root}</div>` : ''}
                        </div>
                    `).join('')}
                </div>
            `;
        }
        return html;
    }

    // 3. 如果是世界觀設定結構 ( geography, power_system, society, atmosphere )
    if (data.geography || data.power_system || data.society || data.atmosphere) {
        let html = '';
        if (data.geography) {
            html += `
                <div style="margin-bottom: 16px;">
                    <h5 style="color: var(--primary); margin-bottom: 6px; font-size: 0.95rem; display: flex; align-items: center; gap: 6px; font-weight: 600;">🗺️ 地理環境</h5>
                    <p style="font-size: 0.9rem; line-height: 1.5; color: var(--text-secondary); margin: 0; padding-left: 4px;">${data.geography}</p>
                </div>
            `;
        }
        if (data.power_system) {
            html += `
                <div style="margin-bottom: 16px;">
                    <h5 style="color: var(--primary); margin-bottom: 6px; font-size: 0.95rem; display: flex; align-items: center; gap: 6px; font-weight: 600;">⚡ 力量體系</h5>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 8px; padding-left: 4px;">
            `;
            if (typeof data.power_system === 'object') {
                html += Object.entries(data.power_system).map(([key, val]) => `
                    <div style="background: var(--bg-secondary); border-radius: 6px; padding: 10px; border: 1px dashed var(--border-color);">
                        <strong style="color: var(--text-primary); font-size: 0.85rem; display: block; margin-bottom: 4px;">🔸 ${key}</strong>
                        <span style="font-size: 0.8rem; color: var(--text-secondary); line-height: 1.4; display: block;">${val}</span>
                    </div>
                `).join('');
            } else {
                html += `<div style="font-size: 0.9rem; color: var(--text-secondary); line-height: 1.5;">${data.power_system}</div>`;
            }
            html += `</div></div>`;
        }
        if (data.society) {
            html += `
                <div style="margin-bottom: 16px;">
                    <h5 style="color: var(--primary); margin-bottom: 6px; font-size: 0.95rem; display: flex; align-items: center; gap: 6px; font-weight: 600;">🏛️ 社會與生態</h5>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 8px; padding-left: 4px;">
            `;
            if (typeof data.society === 'object') {
                html += Object.entries(data.society).map(([key, val]) => `
                    <div style="background: var(--bg-secondary); border-radius: 6px; padding: 10px; border: 1px dashed var(--border-color);">
                        <strong style="color: var(--text-primary); font-size: 0.85rem; display: block; margin-bottom: 4px;">🔹 ${key}</strong>
                        <span style="font-size: 0.8rem; color: var(--text-secondary); line-height: 1.4; display: block;">${val}</span>
                    </div>
                `).join('');
            } else {
                html += `<div style="font-size: 0.9rem; color: var(--text-secondary); line-height: 1.5;">${data.society}</div>`;
            }
            html += `</div></div>`;
        }
        if (data.atmosphere) {
            html += `
                <div style="margin-bottom: 8px;">
                    <h5 style="color: var(--primary); margin-bottom: 6px; font-size: 0.95rem; display: flex; align-items: center; gap: 6px; font-weight: 600;">🎬 世界氛圍</h5>
                    <p style="font-size: 0.9rem; line-height: 1.5; color: var(--text-secondary); margin: 0; font-style: italic; padding-left: 4px;">${data.atmosphere}</p>
                </div>
            `;
        }
        return html;
    }

    // 4. 通用物件鍵值渲染
    return `
        <div style="display: flex; flex-direction: column; gap: 8px;">
            ${Object.entries(data).map(([key, value]) => `
                <div style="font-size: 0.9rem; line-height: 1.4;">
                    <strong style="color: var(--text-primary);">${key}:</strong>
                    <div style="padding-left: 12px; margin-top: 4px; color: var(--text-secondary);">
                        ${typeof value === 'object' ? renderStructuredContent(value) : renderMarkdown(String(value))}
                    </div>
                </div>
            `).join('')}
        </div>
    `;
}

/**
 * 渲染單個世界觀區塊（帶編輯/刪除按鈕，支援 Markdown 語法與 JSON 美化）
 */
export function renderWorldviewSection(sectionId, icon, title, content, badgeClass) {
    let safeContent = content || '';
    let isJSON = false;
    let parsedData = null;

    if (typeof safeContent === 'string' && safeContent.trim()) {
        const trimmed = safeContent.trim();
        if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
            try {
                parsedData = JSON.parse(trimmed);
                isJSON = true;
            } catch (e) {
                // Keep as string
            }
        }
    } else if (safeContent && typeof safeContent === 'object') {
        parsedData = safeContent;
        isJSON = true;
    }

    const renderedHTML = isJSON 
        ? renderStructuredContent(parsedData)
        : (renderMarkdown(String(safeContent)) || '<em style="color:var(--text-muted)">尚無內容</em>');

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
                ${renderedHTML}
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
    const worldviewJs = parseWorldviewJSON(state.currentNovelData?.worldbuilding || '');
    
    state.expandedVolumes = state.expandedVolumes || new Set();
    
    el.editorPlotJson.value = state.currentNovelData?.plot_raw || JSON.stringify({ chapters: [] }, null, 2);
    
    // Simply sort volumes sequentially based on volume_index (no virtual placeholder padding)
    volumes = [...volumes].sort((a, b) => (parseInt(a.volume_index) || 0) - (parseInt(b.volume_index) || 0));
    
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

                const skeletonMap = new Map();
                outl.forEach(ch => {
                    const rawIdx = ch.chapter_index ?? ch.chapter ?? ch.chapter_number ?? ch.index ?? ch.id;
                    const idx = parseInt(rawIdx);
                    if (!isNaN(idx)) {
                        skeletonMap.set(idx, ch);
                    }
                });

                const chapterIdxSet = new Set();
                skeletonMap.forEach((_, idx) => chapterIdxSet.add(idx));
                if (outl.length > 0) {
                    for (let i = 0; i < volChCount; i++) {
                        chapterIdxSet.add(vStart + i);
                    }
                }

                const sortedIdxs = Array.from(chapterIdxSet).sort((a, b) => a - b);

                const displayChapters = sortedIdxs.map(idx => {
                    if (skeletonMap.has(idx)) {
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
                    const range = volRanges[volIdx] || { start: (volIdx - 1) * 50 + 1, end: volIdx * 50 };
                    if (cIdx < range.start || cIdx > range.end) return false;
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
                    const chIdxInVol = chapterIndex - vStart + 1;
                    
                    let globalIdx = -1;
                    if (window.state.currentNovelData && window.state.currentNovelData.plot && Array.isArray(window.state.currentNovelData.plot.chapters)) {
                        globalIdx = window.state.currentNovelData.plot.chapters.findIndex(c => parseInt(c.chapter_index || c.chapter || c.chapter_number || c.index || -1) === chapterIndex);
                    }

                    // 💡 基於全新的 __renderMode 屬性精確判定單個卡片外觀（需先宣告才能在 chIdxInVol 中使用）
                    // 💡 修復：優先使用骨架欄位
                    const skeletonTitle = chapter.chapter_title || chapter.brief_title || chapter.title || chapter.name || '待設定標題';
                    const skeletonSummary = chapter.chapter_summary || chapter.brief_summary || chapter.summary || (chapter.__renderMode === 'empty' ? '情節骨架待生成' : '');
                    const allocatedTasks = chapter.allocated_tasks || {};
                    const foreshadowPlants = allocatedTasks.foreshadowing_plants || allocatedTasks.foreshadowing_plant || chapter.foreshadowing_plants || chapter.foreshadowing_plant || chapter.foreshadowing || [];
                    const foreshadowPayoffs = allocatedTasks.foreshadowing_payoffs || allocatedTasks.foreshadowing_payoff || chapter.foreshadowing_payoffs || chapter.foreshadowing_payoff || [];
                    const turningPoints = allocatedTasks.turning_points || allocatedTasks.turning_point || chapter.turning_points || chapter.turning_point || [];
                    
                    const skeletonTime = chapter.time_setting || '';
                    const skeletonTone = chapter.emotional_tone || '';
                    const skeletonCliff = chapter.cliffhanger || '';
                    const arrSkeletonChars = Array.isArray(chapter.characters_active) ? chapter.characters_active : (chapter.characters_active ? [chapter.characters_active] : []);
                    const arrSkeletonEvents = Array.isArray(chapter.events) ? chapter.events : [];
                    
                    const arrSkeletonPlants = Array.isArray(foreshadowPlants) ? foreshadowPlants : (foreshadowPlants ? [foreshadowPlants] : []);
                    const arrSkeletonPayoffs = Array.isArray(foreshadowPayoffs) ? foreshadowPayoffs : (foreshadowPayoffs ? [foreshadowPayoffs] : []);
                    const arrSkeletonTurns = Array.isArray(turningPoints) ? turningPoints : (turningPoints ? [turningPoints] : []);
                    
                    return `
                    <div class="plot-timeline-node-wrapper" style="margin-bottom: 16px; position: relative;">
                        <div class="plot-chapter-item skeleton-chapter" data-chapter-index="${chapterIndex}" data-index="${globalIdx}" onclick="event.stopPropagation(); if(${globalIdx} !== -1) openChapterOutlineEditModal(${globalIdx}, window.state.currentNovelData.plot.chapters[${globalIdx}])" style="cursor: pointer; border-left: 3px solid var(--primary); opacity: 0.85; padding: 12px; background: rgba(255,255,255,0.015); border-radius: 6px; position: relative; transition: all 0.25s;">
                            <div class="chapter-title-row" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <span class="chapter-index-badge" style="background: rgba(59, 130, 246, 0.15); color: #3b82f6; padding: 2px 8px; border-radius: 4px; font-size: var(--font-2xs); font-weight: 700;">🦴 第 ${chIdxInVol} 章 (全局 ${chapterIndex})</span>
                                    <h3 class="chapter-title" style="margin: 0; font-size: var(--font-sm); font-weight: 700; color: var(--text-primary);">${skeletonTitle}</h3>
                                </div>
                                <div class="chapter-card-actions" onclick="event.stopPropagation()">
                                    <button class="char-action-btn edit-btn" onclick="openChapterOutlineEditModal(${globalIdx}, window.state.currentNovelData.plot.chapters[${globalIdx}])" title="編輯骨架" style="background: none; border: none; cursor: pointer; padding: 4px;">✏️</button>
                                    <button class="char-action-btn delete-btn" onclick="deletePlotChapter(${chapterIndex})" title="刪除章節" style="background: none; border: none; cursor: pointer; padding: 4px;">🗑️</button>
                                </div>
                            </div>
                            
                            ${skeletonSummary ? `<p style="font-size: var(--font-2xs); color: var(--text-secondary); margin: 0 0 8px 0; line-height: 1.5; padding-bottom: 10px; border-bottom: 1px dashed rgba(255,255,255,0.03);">${skeletonSummary}</p>` : ''}
                            
                            ${skeletonTime || skeletonTone || skeletonCliff || arrSkeletonChars.length > 0 || arrSkeletonEvents.length > 0 ? `
                            <div class="skeleton-details" style="display: flex; flex-direction: column; gap: 8px; margin-top: 10px; padding-bottom: 10px; border-bottom: 1px dashed rgba(255,255,255,0.05); font-size: var(--font-2xs);">
                                ${skeletonTone ? `<div style="color: var(--text-secondary);">${getToneBadge(skeletonTone)}</div>` : ''}
                                ${skeletonTime ? `<div style="color: var(--text-secondary);"><strong style="color:var(--primary);">🕒 時間:</strong> ${skeletonTime}</div>` : ''}
                                ${arrSkeletonChars.length > 0 ? `<div style="color: var(--text-secondary);"><strong style="color:var(--primary);">👥 活躍角色:</strong> ${arrSkeletonChars.join(', ')}</div>` : ''}
                                ${arrSkeletonEvents.length > 0 ? `
                                <div style="color: var(--text-secondary);"><strong style="color:var(--primary);">🎬 事件:</strong>
                                    <ul style="margin: 4px 0 0 20px; padding: 0; color: var(--text-muted);">
                                        ${arrSkeletonEvents.map(e => `<li>${typeof e === 'object' ? `[${e.location || '未知'}] ${e.content || ''}` : e}</li>`).join('')}
                                    </ul>
                                </div>` : ''}
                                ${skeletonCliff ? `<div style="color: var(--text-secondary);"><strong style="color:var(--primary);">❓ 懸念:</strong> ${skeletonCliff}</div>` : ''}
                            </div>
                            ` : ''}
                            
                            ${(arrSkeletonPlants.length > 0 || arrSkeletonPayoffs.length > 0 || arrSkeletonTurns.length > 0) ? `
                            <div class="skeleton-tasks" style="display: flex; flex-direction: column; gap: 6px; margin-top: 10px; padding-top: 8px;">
                                ${arrSkeletonPlants.map(seed => {
                                    const desc = getSeedDescription(seed, worldviewJs);
                                    const cleanId = extractForeshadowSeedId(seed);
                                    const idBadge = cleanId ? `<strong style="color:var(--primary);">[Seed-${cleanId}]</strong> ` : '';
                                    return `
                                    <div class="task-item seed-item" style="display: flex; align-items: flex-start; gap: 6px; font-size: var(--font-2xs); color: #c084fc; line-height: 1.4;">
                                        <span style="flex-shrink: 0; font-size: 1.1em;">🌱</span>
                                        <span>${idBadge}${desc}</span>
                                    </div>
                                    `;
                                }).join('')}
                                ${arrSkeletonPayoffs.map(pay => {
                                    const desc = getSeedDescription(pay, worldviewJs);
                                    const cleanId = extractForeshadowSeedId(pay);
                                    const idBadge = cleanId ? `<strong style="color:var(--primary);">[Seed-${cleanId}]</strong> ` : '';
                                    return `
                                    <div class="task-item payoff-item" style="display: flex; align-items: flex-start; gap: 6px; font-size: var(--font-2xs); color: #fbbf24; line-height: 1.4;">
                                        <span style="flex-shrink: 0; font-size: 1.1em;">💥</span>
                                        <span>回收: ${idBadge}${desc}</span>
                                    </div>
                                    `;
                                }).join('')}
                                ${arrSkeletonTurns.map(tp => {
                                    const desc = getTurningPointDescription(tp, worldviewJs);
                                    const cleanId = String(tp).replace(/[^\d]/g, '');
                                    const idBadge = cleanId ? `<strong style="color:var(--status-unwritten);">[Turn-${cleanId}]</strong> ` : '';
                                    return `
                                    <div class="task-item turning-item" style="display: flex; align-items: flex-start; gap: 6px; font-size: var(--font-2xs); color: #f87171; line-height: 1.4;">
                                        <span style="flex-shrink: 0; font-size: 1.1em;">⚡</span>
                                        <span>轉折: ${idBadge}${desc}</span>
                                    </div>
                                    `;
                                }).join('')}
                            </div>` : ''}
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
                        <div style="white-space: pre-wrap;"><strong>📌 核心情節概要：</strong>${(vol.summary || '尚無概要設定。').replace(/\\n/g, '\n')}</div>
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
                    
                    // Simply sort volumes sequentially based on volume_index (no virtual placeholder padding)
                    volumes = [...volumes].sort((a, b) => (parseInt(a.volume_index) || 0) - (parseInt(b.volume_index) || 0));
                    
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
                    <p class="insp-val foreshadows" style="font-size:0.8rem; color:#10b981; font-weight:500;">🌱 ${plotChapter.foreshadowing.map(f => typeof f === 'string' ? f : JSON.stringify(f)).join(' | ')}</p>
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
    
    // 清空舊對話框內容以利刷新
    el.chatMessagesContainer.innerHTML = '';
    
    // 初始化默認系統歡迎消息，確保清空後能重新加入
    const systemWelcome = document.createElement('div');
    systemWelcome.className = 'message system-msg';
    systemWelcome.innerHTML = `
        <div class="msg-sender">AI Novel Director</div>
        <div class="msg-content">你好！我是你的小說創作協同總監。我擁有對當前小說的完整長期記憶 (SQLite)。<br><br>你可以對我發出指令，我會直接指導各個 Agent 配合，或是為你提供靈感！</div>
    `;
    el.chatMessagesContainer.appendChild(systemWelcome);
    
    const messages = state.currentNovelData?.chat_memory || state.currentNovelData?.chat_messages || [];
    
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

