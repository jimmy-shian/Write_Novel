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
        multi_act_structure: [
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
            
            // Normalize multi_act_structure
            let normalized_ta = [];
            const ta = parsed.multi_act_structure;
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
                multi_act_structure: normalized_ta,
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
        "【多幕式結構】",
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

    if (sections["【多幕式結構】"]) {
        const lines = sections["【多幕式結構】"].split("\n");
        const parsedItems = [];
        lines.forEach(line => {
            const l = line.trim();
            if (!l) return;
            const cleanLine = l.startsWith("-") || l.startsWith("•") || l.startsWith("*") ? l.substring(1).trim() : l;
            if (cleanLine.includes(":") || cleanLine.includes("：")) {
                const sep = cleanLine.includes("：") ? "：" : ":";
                const parts = cleanLine.split(sep);
                const title = parts[0].trim();
                const content = parts.slice(1).join(sep).trim();
                parsedItems.push({ title, content });
            } else {
                parsedItems.push({ title: `項目 #${parsedItems.length + 1}`, content: cleanLine });
            }
        });
        if (parsedItems.length > 0) {
            result.multi_act_structure = parsedItems;
        }
    }

    if (sections["【角色漸進規劃策略】"]) {
        const lines = sections["【角色漸進規劃策略】"].split("\n");
        const parsedItems = [];
        lines.forEach(line => {
            const l = line.trim();
            if (!l) return;
            const cleanLine = l.startsWith("-") || l.startsWith("•") || l.startsWith("*") ? l.substring(1).trim() : l;
            if (cleanLine.includes(":") || cleanLine.includes("：")) {
                const sep = cleanLine.includes("：") ? "：" : ":";
                const parts = cleanLine.split(sep);
                const title = parts[0].trim();
                const content = parts.slice(1).join(sep).trim();
                parsedItems.push({ title, content });
            } else {
                parsedItems.push({ title: `階段 #${parsedItems.length + 1}`, content: cleanLine });
            }
        });
        if (parsedItems.length > 0) {
            result.progressive_character_plan = parsedItems;
        }
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
    if (window.showCustomConfirm) {
        return window.showCustomConfirm(message);
    }
    if (window.showCustomDialog) {
        return window.showCustomDialog({ title: '確認操作', message: message, type: 'confirm' });
    }
    return new Promise((resolve) => {
        let modal = document.getElementById('modal-confirm');
        if (!modal) {
            const html = `
            <div id="modal-confirm" class="modal-overlay">
                <div class="modal-card modal-small" style="max-width: 420px; border: 1px solid rgba(255, 255, 255, 0.08); background: rgba(22, 22, 33, 0.85); backdrop-filter: blur(16px); box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4); border-radius: 16px;">
                    <div class="modal-header" style="border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
                        <h2 style="font-size: var(--font-base); font-weight: 600; display: flex; align-items: center; gap: 8px; color: #fff;">⚠️ 確認操作</h2>
                        <button class="btn-close-modal" style="background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: var(--font-xs); padding: 4px; transition: color 0.2s;">✕</button>
                    </div>
                    <div class="modal-body" style="padding: 20px;">
                        <p id="confirm-message" style="margin-bottom: 16px; font-size: var(--font-2xs); line-height: 1.6; color: rgba(255, 255, 255, 0.7); white-space: pre-wrap;"></p>
                        <div style="display: flex; gap: 12px; margin-top: 24px;">
                            <button id="btn-confirm-cancel" class="btn btn-ghost" style="flex: 1; padding: 12px; border-radius: 8px; font-weight: 500;">取消</button>
                            <button id="btn-confirm-ok" class="btn btn-primary" style="flex: 1; padding: 12px; border-radius: 8px; font-weight: 500;">確認</button>
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

    // 將字串中的字面量 \n 轉義符號還原為真實的換行字元，以利 Markdown 換行解析與 pre-wrap 渲染
    const normalizedText = String(text).replace(/\\n/g, '\n');

    let html = normalizedText
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

    // 自動換行處理段落：將非塊級 HTML 區塊按連續空行分段，並對每段中的單行換行使用 <br>
    const isBlockHTML = (line) => {
        return /^\s*<\/?(h[3-5]|blockquote|hr|ul|ol|li|pre|code|div|p)\b/i.test(line);
    };

    const paragraphLines = html.split('\n');
    let currentParagraph = [];
    const finalBlocks = [];

    const flushParagraph = () => {
        if (currentParagraph.length > 0) {
            const content = currentParagraph.join('<br>');
            finalBlocks.push(`<p style="margin:6px 0; line-height:1.6;">${content}</p>`);
            currentParagraph = [];
        }
    };

    for (let line of paragraphLines) {
        const trimmed = line.trim();
        if (trimmed === '') {
            flushParagraph();
        } else if (isBlockHTML(trimmed)) {
            // 如果是塊級 HTML 標籤，先清空當前段落，再直接放入標籤
            flushParagraph();
            finalBlocks.push(trimmed);
        } else {
            // 普通文字行，加入當前段落中
            currentParagraph.push(trimmed);
        }
    }
    flushParagraph();

    return finalBlocks.join('\n');
}

/**
 * 解析總監回覆中的執行指令區塊 (共用於即時 Stream 及歷史載入畫面)
 */
export function parseDirectorDecisionText(responseText, currentStage) {
    let action = null;
    let target = null;
    let hint = '';
    let reason = '';
    let volume_index = null;
    let chapter_index = null;
    let insert_after_index = null;
    
    // 1) 嘗試解析 JSON 區塊（新格式：```json { "action": "...", ... } ```）
    const jsonBlockMatch = responseText.match(/```json\s*(\{[\s\S]*?\})\s*```/);
    if (jsonBlockMatch) {
        try {
            const jsonCmd = JSON.parse(jsonBlockMatch[1]);
            action = (jsonCmd.action || '').toUpperCase();
            target = jsonCmd.target || null;
            hint = jsonCmd.hint || jsonCmd.reason || '';
            reason = jsonCmd.reason || '';
            
            if (jsonCmd.volume_index !== undefined && jsonCmd.volume_index !== null) {
                volume_index = parseInt(jsonCmd.volume_index);
            }
            if (jsonCmd.chapter_index !== undefined && jsonCmd.chapter_index !== null) {
                chapter_index = parseInt(jsonCmd.chapter_index);
            }
            if (jsonCmd.insert_after_index !== undefined && jsonCmd.insert_after_index !== null) {
                insert_after_index = parseInt(jsonCmd.insert_after_index);
            }
        } catch (e) {
            console.warn('Failed to parse Director JSON command:', e);
        }
    }
    
    // 2) 回退：解析舊格式【執行指令】ACTION: XXX
    if (!action) {
        const actionMatch = responseText.match(/【執行指令】[\s\S]*?ACTION:\s*(\w+)/) || responseText.match(/【執行指令\][\s\S]*?ACTION:\s*(\w+)/);
        if (actionMatch) {
            action = actionMatch[1].trim().toUpperCase();
        }
        const targetMatch = responseText.match(/TARGET:\s*(\w+)/);
        if (targetMatch) target = targetMatch[1].trim();
        const hintMatch = responseText.match(/HINT:\s*([\s\S]*?)(?=```|【|$)/);
        if (hintMatch) hint = hintMatch[1].trim();
        const reasonMatch = responseText.match(/REASON:\s*([\s\S]*?)(?=```|【|$)/);
        if (reasonMatch) reason = reasonMatch[1].trim();
        
        // 嘗試從舊格式文字中正則匹配 volume_index / chapter_index / insert_after_index
        const volMatch = responseText.match(/volume_index["\s:]+(\d+)/i) || responseText.match(/篇卷序號["\s:]+(\d+)/);
        if (volMatch) volume_index = parseInt(volMatch[1]);
        
        const chMatch = responseText.match(/chapter_index["\s:]+(\d+)/i) || responseText.match(/章節序號["\s:]+(\d+)/);
        if (chMatch) chapter_index = parseInt(chMatch[1]);
        
        const insMatch = responseText.match(/insert_after_index["\s:]+(\d+)/i) || responseText.match(/插入章節後["\s:]+(\d+)/);
        if (insMatch) insert_after_index = parseInt(insMatch[1]);
    }
    
    // 2.5) 額外解析：如果 AI 直接輸出原始 JSON 物件，嘗試從整體字串中解析第一個 JSON 對象
    if (!action) {
        const rawJsonMatch = responseText.match(/\{[\s\S]*\}/);
        if (rawJsonMatch) {
            try {
                const rawJson = JSON.parse(rawJsonMatch[0]);
                action = (rawJson.action || '').toUpperCase() || action;
                target = rawJson.target || target;
                hint = rawJson.hint || rawJson.reason || hint;
                reason = rawJson.reason || reason;
                if (rawJson.volume_index !== undefined && rawJson.volume_index !== null) {
                    volume_index = parseInt(rawJson.volume_index);
                }
                if (rawJson.chapter_index !== undefined && rawJson.chapter_index !== null) {
                    chapter_index = parseInt(rawJson.chapter_index);
                }
                if (rawJson.insert_after_index !== undefined && rawJson.insert_after_index !== null) {
                    insert_after_index = parseInt(rawJson.insert_after_index);
                }
            } catch (e) {
                // 无效 JSON，不处理
            }
        }
    }
    
    // 3) 最後回退：關鍵字啟發式（當 AI 完全不遵循格式時）
    if (!action) {
        if (responseText.includes('WRITE_ALL_CHAPTERS') || responseText.includes('開始寫作所有章節')) {
            action = 'WRITE_ALL_CHAPTERS';
        } else if (responseText.includes('FINISH') || responseText.includes('全部完成')) {
            action = 'FINISH';
        } else if (responseText.includes('繼續') && !responseText.includes('暫停')) {
            action = 'CONTINUE';
        } else if (responseText.includes('暫停') || responseText.includes('等待用戶')) {
            action = 'WAIT_USER';
        }
    }
    
    return { 
        continue: action === 'CONTINUE' || action === 'WRITE_ALL_CHAPTERS' || action === 'LOCAL_ALIGN_VOLUME' || action === 'INCREMENTAL_INSERT_PLOT',
        response: responseText,
        shouldPause: action === 'WAIT_USER',
        action: action,
        target: target,
        hint: hint,
        reason: reason,
        regenerate: action === 'AUTO_REGENERATE',
        regenerateStage: action === 'AUTO_REGENERATE' ? (target || currentStage) : null,
        volume_index: volume_index,
        chapter_index: chapter_index,
        insert_after_index: insert_after_index
    };
}

