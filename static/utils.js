// ==========================================
// UTILITIES - 工具函式
// ==========================================

/**
 * 解析世界觀 JSON（支援新舊格式）
 * @param {string} text - 世界觀文字內容
 * @returns {object} 解析後的世界觀物件
 */
export function parseWorldviewJSON(text) {
    const defaultStructure = {
        theme: "",
        main_conflict: "",
        worldview: "",
        macro_outline: "",
        three_act_structure: [
            { title: "第一幕 (Setup)", content: "" },
            { title: "第二幕 (Confrontation)", content: "" },
            { title: "第三幕 (Resolution)", content: "" }
        ],
        progressive_character_plan: [
            { title: "第一波開篇 (Wave 1)", content: "" },
            { title: "第二波發展 (Wave 2)", content: "" },
            { title: "第三波高潮 (Wave 3)", content: "" }
        ],
        foreshadowing_seeds: [],
        key_turning_points: []
    };

    if (!text || text.trim().length === 0) {
        return defaultStructure;
    }

    const textStripped = text.trim();
    if (textStripped.startsWith("{") && textStripped.endsWith("}")) {
        try {
            const parsed = JSON.parse(textStripped);
            
            // Normalize three_act_structure
            let normalized_ta = [];
            const ta = parsed.three_act_structure;
            if (Array.isArray(ta)) {
                normalized_ta = ta.map((item, idx) => {
                    if (typeof item === 'object' && item !== null) {
                        return { title: item.title || `項目 #${idx + 1}`, content: item.content || '' };
                    } else {
                        return { title: `項目 #${idx + 1}`, content: String(item) };
                    }
                });
            } else if (typeof ta === 'object' && ta !== null) {
                normalized_ta = [
                    { title: '第一幕 (Setup)', content: ta.act1_setup || ta.act1 || '' },
                    { title: '第二幕 (Confrontation)', content: ta.act2_confrontation || ta.act2 || '' },
                    { title: '第三幕 (Resolution)', content: ta.act3_resolution || ta.act3 || '' }
                ];
            } else {
                normalized_ta = [
                    { title: '第一幕 (Setup)', content: '' },
                    { title: '第二幕 (Confrontation)', content: '' },
                    { title: '第三幕 (Resolution)', content: '' }
                ];
            }

            // Normalize progressive_character_plan
            let normalized_cp = [];
            const cp = parsed.progressive_character_plan;
            if (Array.isArray(cp)) {
                normalized_cp = cp.map((item, idx) => {
                    if (typeof item === 'object' && item !== null) {
                        return { title: item.title || `階段 #${idx + 1}`, content: item.content || '' };
                    } else {
                        return { title: `階段 #${idx + 1}`, content: String(item) };
                    }
                });
            } else if (typeof cp === 'object' && cp !== null) {
                normalized_cp = [
                    { title: '第一波開篇 (Wave 1)', content: cp.wave_1_opening || '' },
                    { title: '第二波發展 (Wave 2)', content: cp.wave_2_development || '' },
                    { title: '第三波高潮 (Wave 3)', content: cp.wave_3_climax || '' }
                ];
            } else {
                normalized_cp = [
                    { title: '第一波開篇 (Wave 1)', content: '' },
                    { title: '第二波發展 (Wave 2)', content: '' },
                    { title: '第三波高潮 (Wave 3)', content: '' }
                ];
            }

            return {
                theme: parsed.theme || "",
                main_conflict: parsed.main_conflict || "",
                worldview: parsed.worldview || "",
                macro_outline: parsed.macro_outline || "",
                three_act_structure: normalized_ta,
                progressive_character_plan: normalized_cp,
                foreshadowing_seeds: Array.isArray(parsed.foreshadowing_seeds) ? parsed.foreshadowing_seeds : [],
                key_turning_points: Array.isArray(parsed.key_turning_points) ? parsed.key_turning_points : []
            };
        } catch (e) {
            console.warn("parseWorldviewJSON parse failed, falling back to legacy parser", e);
        }
    }

    // --- 舊格式文字解析器 (平鋪相容備援) ---
    const result = JSON.parse(JSON.stringify(defaultStructure));
    const headers = [
        "【核心主題】",
        "【核心衝突】",
        "【世界觀設定】",
        "【整體故事大綱】",
        "【三幕式結構】",
        "【角色漸進規劃策略】",
        "【伏筆種子】",
        "【關鍵轉折點】"
    ];

    const pos = [];
    headers.forEach(h => {
        const idx = text.indexOf(h);
        if (idx !== -1) {
            pos.push({ idx, h });
        }
    });
    pos.sort((a, b) => a.idx - b.idx);

    const sections = {};
    for (let i = 0; i < pos.length; i++) {
        const startIdx = pos[i].idx + pos[i].h.length;
        const endIdx = (i + 1 < pos.length) ? pos[i + 1].idx : text.length;
        sections[pos[i].h] = text.substring(startIdx, endIdx).trim();
    }

    if (sections["【核心主題】"]) result.theme = sections["【核心主題】"];
    if (sections["【核心衝突】"]) result.main_conflict = sections["【核心衝突】"];
    if (sections["【世界觀設定】"]) result.worldview = sections["【世界觀設定】"];
    if (sections["【整體故事大綱】"]) result.macro_outline = sections["【整體故事大綱】"];

    if (sections["【三幕式結構】"]) {
        const lines = sections["【三幕式結構】"].split("\n");
        lines.forEach(line => {
            const l = line.trim();
            if (l.includes("第一幕") || l.includes("Setup")) {
                result.three_act_structure[0].content = l.split(/[：:]/).slice(1).join("：").trim() || l;
            } else if (l.includes("第二幕") || l.includes("Confrontation")) {
                result.three_act_structure[1].content = l.split(/[：:]/).slice(1).join("：").trim() || l;
            } else if (l.includes("第三幕") || l.includes("Resolution")) {
                result.three_act_structure[2].content = l.split(/[：:]/).slice(1).join("：").trim() || l;
            }
        });
    }

    if (sections["【角色漸進規劃策略】"]) {
        const lines = sections["【角色漸進規劃策略】"].split("\n");
        lines.forEach(line => {
            let l = line.trim();
            if (l.startsWith("-") || l.startsWith("•") || l.startsWith("*")) {
                l = l.substring(1).trim();
            }
            if (l.includes(":") || l.includes("：")) {
                const sep = l.includes("：") ? "：" : ":";
                const parts = l.split(sep);
                const k = parts[0].trim();
                const v = parts.slice(1).join(sep).trim();
                if (k.includes("wave_1") || k.includes("wave1") || k.includes("開篇") || k.includes("第一波")) {
                    result.progressive_character_plan[0].content = v;
                } else if (k.includes("wave_2") || k.includes("wave2") || k.includes("第二波") || k.includes("發展")) {
                    result.progressive_character_plan[1].content = v;
                } else if (k.includes("wave_3") || k.includes("wave3") || k.includes("第三波") || k.includes("高潮")) {
                    result.progressive_character_plan[2].content = v;
                }
            } else {
                if (l) {
                    if (!result.progressive_character_plan[0].content) {
                        result.progressive_character_plan[0].content = l;
                    } else if (!result.progressive_character_plan[1].content) {
                        result.progressive_character_plan[1].content = l;
                    } else if (!result.progressive_character_plan[2].content) {
                        result.progressive_character_plan[2].content = l;
                    }
                }
            }
        });
    }

    if (sections["【伏筆種子】"]) {
        const lines = sections["【伏筆種子】"].split("\n");
        lines.forEach(line => {
            let l = line.trim();
            if (l.startsWith("-") || l.startsWith("•") || l.startsWith("*")) {
                l = l.substring(1).trim();
            }
            if (l) {
                result.foreshadowing_seeds.push(l);
            }
        });
    }

    if (sections["【關鍵轉折點】"]) {
        const lines = sections["【關鍵轉折點】"].split("\n");
        lines.forEach(line => {
            let l = line.trim();
            if (l.startsWith("-") || l.startsWith("•") || l.startsWith("*")) {
                l = l.substring(1).trim();
            }
            if (l) {
                result.key_turning_points.push(l);
            }
        });
    }

    return result;
}

/**
 * 顯示自訂確認對話框
 * @param {string} message - 確認訊息
 * @returns {Promise<boolean>} 使用者點擊確認返回 true，否則返回 false
 */
export function showCustomConfirm(message) {
    return new Promise((resolve) => {
        let modal = document.getElementById('modal-confirm');
        if (!modal) {
            const html = `
            <div id="modal-confirm" class="modal-overlay">
                <div class="modal-card" style="max-width: 400px;">
                    <div class="modal-header">
                        <h2>⚠️ 確認操作</h2>
                        <button class="btn-close-modal">✕</button>
                    </div>
                    <div class="modal-body">
                        <p id="confirm-message" style="margin-bottom: 20px;"></p>
                        <div style="display: flex; gap: 12px; justify-content: flex-end;">
                            <button id="btn-confirm-cancel" class="btn btn-secondary">取消</button>
                            <button id="btn-confirm-ok" class="btn btn-danger">確認</button>
                        </div>
                    </div>
                </div>
            </div>`;
            document.body.insertAdjacentHTML('beforeend', html);
            modal = document.getElementById('modal-confirm');
            
            modal.querySelector('.btn-close-modal').addEventListener('click', () => {
                modal.classList.remove('active');
                resolve(false);
            });
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    modal.classList.remove('active');
                    resolve(false);
                }
            });
        }
        
        document.getElementById('confirm-message').textContent = message;
        
        const btnOk = document.getElementById('btn-confirm-ok');
        const btnCancel = document.getElementById('btn-confirm-cancel');
        
        const cleanup = () => {
            modal.classList.remove('active');
            btnOk.removeEventListener('click', handleOk);
            btnCancel.removeEventListener('click', handleCancel);
        };
        
        const handleOk = () => { cleanup(); resolve(true); };
        const handleCancel = () => { cleanup(); resolve(false); };
        
        btnOk.addEventListener('click', handleOk);
        btnCancel.addEventListener('click', handleCancel);
        
        modal.classList.add('active');
    });
}

/**
 * 去除文字開頭的列表前綴（如 "- "、"• "、"* "）
 * @param {string} text - 原始文字
 * @returns {string} 去除前綴後的文字
 */
export function stripBulletPrefix(text) {
    return text.replace(/^[\-\•\*]\s+/, '').trim();
}

/**
 * 格式化日期為 MM/DD
 * @param {Date|string} date - 日期物件或日期字串
 * @returns {string} 格式化後的日期字串
 */
export function formatDate(date) {
    const dateObj = date instanceof Date ? date : new Date(date);
    return `${dateObj.getMonth() + 1}/${dateObj.getDate()}`;
}

/**
 * 將 Markdown 語法渲染為 HTML
 * 支援：標題、粗體、斜體、清單、引用、分隔線、連結
 * @param {string} text - 原始 Markdown 文字
 * @returns {string} 渲染後的 HTML
 */
export function renderMarkdown(text) {
    if (!text) return '';

    let html = text
        // 轉義 HTML 特殊字元
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    // 標題 (h1-h3)
    html = html.replace(/^#{3}\s*(.+)$/gm, '<h5>$1</h5>');
    html = html.replace(/^#{2}\s*(.+)$/gm, '<h4>$1</h4>');
    html = html.replace(/^#{1}\s*(.+)$/gm, '<h3>$1</h3>');

    // 粗體與斜體
    html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // 刪除線
    html = html.replace(/~~(.+?)~~/g, '<del>$1</del>');

    // 連結 [文字](網址)
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');

    // 圖片 ![替代文字](網址)
    html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1" style="max-width:100%; height:auto; border-radius:8px;">');

    // 引用區塊
    html = html.replace(/^>\s*(.+)$/gm, '<blockquote style="border-left:3px solid var(--primary); padding-left:12px; margin:8px 0; color:var(--text-secondary); font-style:italic;">$1</blockquote>');

    // 分隔線
    html = html.replace(/^[\s]*-{3,}[\s]*$/gm, '<hr style="border:none; border-top:1px solid var(--border-color); margin:16px 0;">');
    html = html.replace(/^[\s]*\*{3,}[\s]*$/gm, '<hr style="border:none; border-top:1px solid var(--border-color); margin:16px 0;">');

    // 無序清單
    const lines = html.split('\n');
    let inList = false;
    let result = [];
    for (const line of lines) {
        const match = line.match(/^(\s*)[-*•]\s+(.+)$/);
        if (match) {
            if (!inList) {
                result.push('<ul style="list-style:none; padding:0; margin:8px 0;">');
                inList = true;
            }
            result.push(`<li style="padding:4px 0; padding-left:20px; position:relative;"><span style="position:absolute; left:0; color:var(--primary);">•</span>${match[2]}</li>`);
        } else if (inList && line.trim() === '') {
            result.push('</ul>');
            inList = false;
            result.push(line);
        } else {
            if (inList) {
                result.push('</ul>');
                inList = false;
            }
            result.push(line);
        }
    }
    if (inList) result.push('</ul>');

    // 有序清單
    html = result.join('\n');
    let inOrderedList = false;
    const orderedLines = [];
    for (const line of html.split('\n')) {
        const match = line.match(/^(\s*)\d+\.(\s+.+)$/);
        if (match) {
            if (!inOrderedList) {
                orderedLines.push('<ol style="list-style:none; padding:0; margin:8px 0; counter-reset:item;">');
                inOrderedList = true;
            }
            orderedLines.push(`<li style="padding:4px 0; padding-left:28px; position:relative; counter-increment:item;"><span style="position:absolute; left:0; color:var(--primary); font-weight:600; font-size:0.85rem;">${match[0].match(/^\s*(\d+)\./)[1]}.</span>${match[2].trim()}</li>`);
        } else if (inOrderedList && line.trim() === '') {
            orderedLines.push('</ol>');
            inOrderedList = false;
            orderedLines.push(line);
        } else {
            if (inOrderedList) {
                orderedLines.push('</ol>');
                inOrderedList = false;
            }
            orderedLines.push(line);
        }
    }
    if (inOrderedList) orderedLines.push('</ol>');
    html = orderedLines.join('\n');

    // 內聯程式碼
    html = html.replace(/`([^`]+)`/g, '<code style="background:var(--bg-tertiary); padding:2px 6px; border-radius:4px; font-family:\'SFMono-Regular\', Consolas, monospace; font-size:0.85em; color:var(--primary);">$1</code>');

    // 程式碼區塊
    html = html.replace(/```([\s\S]*?)```/g, '<pre style="background:var(--bg-tertiary); padding:12px; border-radius:8px; border:1px solid var(--border-color); overflow-x:auto; font-family:\'SFMono-Regular\', Consolas, monospace; font-size:0.85rem; line-height:1.6; margin:8px 0;"><code>$1</code></pre>');

    // 自動換行處理段落
    const paragraphLines = html.split('\n').map(line => {
        line = line.trim();
        if (!line) return '';
        // 如果已經是 HTML 標籤，不包裝
        if (line.startsWith('<') && (line.endsWith('>') || line.includes('</'))) return line;
        return `<p style="margin:4px 0; line-height:1.6;">${line}</p>`;
    });

    return paragraphLines.join('\n');
}