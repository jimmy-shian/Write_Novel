import React, { useState, useMemo, useRef, useEffect } from 'react';
import { IconCheck, IconPlus, IconX } from '../common/Icons';

export type TaskPickerType = 'turning_points' | 'foreshadowing_plants' | 'foreshadowing_payoffs';

export interface ResolvedTaskItem {
  key: string;        // canonical storage string, e.g. 'TP001', 'FS018'
  code: string;       // e.g. 'TP001', 'FS018', or ''
  num: number | null; // e.g. 1, 18, or null
  name: string;       // human readable name
  desc?: string;      // description / hint
  raw?: any;          // original object if matched
}

/**
 * Standardize any task representation (integer ID, 'TP001', 'FS018', name string, or object)
 * into a uniform ResolvedTaskItem with code, name, and tooltip description.
 */
export function resolveTaskItem(
  raw: any,
  taskType: TaskPickerType,
  availableItems: any[] = []
): ResolvedTaskItem {
  if (raw === null || raw === undefined) {
    return { key: '', code: '', num: null, name: '', raw };
  }

  const prefix = taskType === 'turning_points' ? 'TP' : 'FS';
  let num: number | null = null;
  let codeStr = '';
  let rawStr = '';

  if (typeof raw === 'number') {
    num = raw;
    rawStr = String(raw);
  } else if (typeof raw === 'string') {
    rawStr = raw.trim();
    const m = rawStr.match(/^(?:TP|FS)?0*(\d+)$/i);
    if (m && (rawStr.toUpperCase().startsWith('TP') || rawStr.toUpperCase().startsWith('FS') || /^\d+$/.test(rawStr))) {
      num = parseInt(m[1], 10);
    }
  } else if (typeof raw === 'object') {
    const rawId = raw.id ?? raw.code;
    if (typeof rawId === 'number') {
      num = rawId;
    } else if (typeof rawId === 'string') {
      const m = rawId.trim().match(/^(?:TP|FS)?0*(\d+)$/i);
      if (m && (rawId.toUpperCase().startsWith('TP') || rawId.toUpperCase().startsWith('FS') || /^\d+$/.test(rawId))) {
        num = parseInt(m[1], 10);
      } else {
        rawStr = rawId.trim();
      }
    }
    if (!rawStr) {
      rawStr = raw.turning_point_name || raw.name || '';
    }
  }

  if (num !== null && !isNaN(num)) {
    codeStr = `${prefix}${String(num).padStart(3, '0')}`;
  } else if (/^(TP|FS)/i.test(rawStr)) {
    codeStr = rawStr.toUpperCase();
  }

  // Match in availableItems
  let match: any = null;
  for (const item of availableItems) {
    if (!item) continue;
    const itemId = item.id;
    if (num !== null && (itemId === num || String(itemId) === String(num))) {
      match = item;
      break;
    }
    if (codeStr && (item.code === codeStr || String(itemId).toUpperCase() === codeStr)) {
      match = item;
      break;
    }
    const itemName = (item.turning_point_name || item.name || '').trim();
    if (rawStr && (itemName === rawStr || String(itemId) === rawStr)) {
      match = item;
      break;
    }
  }

  let name = '';
  let desc = '';
  if (match) {
    name = match.turning_point_name || match.name || '';
    desc = match.description || match.trigger_condition || match.setup_hint || match.payoff_hint || '';
    if (num === null && match.id !== undefined && match.id !== null) {
      const n = parseInt(String(match.id).replace(/\D/g, ''), 10);
      if (!isNaN(n)) {
        num = n;
        codeStr = `${prefix}${String(num).padStart(3, '0')}`;
      }
    }
  } else if (rawStr && !/^(?:TP|FS)?\d+$/i.test(rawStr)) {
    name = rawStr;
  }

  if (!name && codeStr) {
    name = codeStr;
  } else if (!name) {
    name = rawStr || (num !== null ? `${prefix} #${num}` : '未命名');
  }

  const key = codeStr || rawStr || name;

  return {
    key,
    code: codeStr,
    num,
    name,
    desc,
    raw: match || raw,
  };
}

interface TaskPickerProps {
  type: TaskPickerType;
  label: string;
  selected: string[];
  onChange: (items: string[]) => void;
  availableItems: any[];
  allVolumes: any[];
  currentVolNum: number;
  currentChNum: number;
  placeholder?: string;
}

export const TaskPicker: React.FC<TaskPickerProps> = ({
  type,
  label,
  selected = [],
  onChange,
  availableItems = [],
  allVolumes = [],
  currentVolNum,
  currentChNum,
  placeholder,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState('');
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    if (!isOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  // Compute global usage status of all items across chapters
  const usageMap = useMemo(() => {
    const map = new Map<
      string,
      {
        usedChapters: Array<{ vol: number; ch: number }>;
        plantedChapters: Array<{ vol: number; ch: number }>;
        payoffChapters: Array<{ vol: number; ch: number }>;
      }
    >();

    const registerItem = (
      rawItem: any,
      itemType: TaskPickerType,
      category: 'usedChapters' | 'plantedChapters' | 'payoffChapters',
      volNum: number,
      chNum: number
    ) => {
      if (rawItem === null || rawItem === undefined || rawItem === '') return;
      const res = resolveTaskItem(rawItem, itemType, availableItems);
      const keys = new Set<string>();
      if (res.code) keys.add(res.code);
      if (res.num !== null) {
        keys.add(String(res.num));
        keys.add(`${itemType === 'turning_points' ? 'TP' : 'FS'}${res.num}`);
      }
      if (res.name) keys.add(res.name);
      if (typeof rawItem === 'string' && rawItem.trim()) keys.add(rawItem.trim());
      if (typeof rawItem === 'number') keys.add(String(rawItem));

      keys.forEach((k) => {
        if (!map.has(k)) {
          map.set(k, { usedChapters: [], plantedChapters: [], payoffChapters: [] });
        }
        const bucket = map.get(k)!;
        if (!bucket[category].some((c) => c.vol === volNum && c.ch === chNum)) {
          bucket[category].push({ vol: volNum, ch: chNum });
        }
      });
    };

    allVolumes.forEach((v: any, vIdx: number) => {
      const volNum = v.volume_index ?? vIdx + 1;
      const outlines = Array.isArray(v.chapters_outline) ? v.chapters_outline : [];
      outlines.forEach((ch: any, cIdx: number) => {
        const chNum = ch.chapter_index ?? cIdx + 1;
        const tasks = ch.allocated_tasks || {};

        const tps = Array.isArray(tasks.turning_points) ? tasks.turning_points : [];
        tps.forEach((tp: any) => registerItem(tp, 'turning_points', 'usedChapters', volNum, chNum));

        const plants = Array.isArray(tasks.foreshadowing_plants) ? tasks.foreshadowing_plants : [];
        plants.forEach((p: any) => registerItem(p, 'foreshadowing_plants', 'plantedChapters', volNum, chNum));

        const payoffs = Array.isArray(tasks.foreshadowing_payoffs) ? tasks.foreshadowing_payoffs : [];
        payoffs.forEach((p: any) => registerItem(p, 'foreshadowing_payoffs', 'payoffChapters', volNum, chNum));
      });
    });

    return map;
  }, [allVolumes, availableItems, type]);

  // Compute status for a specific item
  const getItemStatus = (item: any) => {
    const res = resolveTaskItem(item, type, availableItems);
    const keysToCheck = [
      res.code,
      res.num !== null ? String(res.num) : '',
      res.name,
      typeof item === 'string' ? item : '',
      item?.id ? String(item.id) : '',
    ].filter(Boolean);

    let usedChapters: Array<{ vol: number; ch: number }> = [];
    let plantedChapters: Array<{ vol: number; ch: number }> = [];
    let payoffChapters: Array<{ vol: number; ch: number }> = [];

    keysToCheck.forEach((k) => {
      const data = usageMap.get(k);
      if (data) {
        data.usedChapters.forEach((c) => {
          if (!usedChapters.some((x) => x.vol === c.vol && x.ch === c.ch)) usedChapters.push(c);
        });
        data.plantedChapters.forEach((c) => {
          if (!plantedChapters.some((x) => x.vol === c.vol && x.ch === c.ch)) plantedChapters.push(c);
        });
        data.payoffChapters.forEach((c) => {
          if (!payoffChapters.some((x) => x.vol === c.vol && x.ch === c.ch)) payoffChapters.push(c);
        });
      }
    });

    const isCurrentCh = (list: Array<{ vol: number; ch: number }>) =>
      list.some((it) => it.vol === currentVolNum && it.ch === currentChNum);

    if (type === 'turning_points') {
      if (isCurrentCh(usedChapters)) {
        return { text: '本章已選取', variant: 'current' as const };
      }
      if (usedChapters.length > 0) {
        const first = usedChapters[0];
        return { text: `已在第 ${first.ch} 章使用`, variant: 'used' as const };
      }
      return { text: '未指派', variant: 'free' as const };
    }

    if (type === 'foreshadowing_plants') {
      if (isCurrentCh(plantedChapters)) {
        return { text: '本章已佈局', variant: 'current' as const };
      }
      if (plantedChapters.length > 0) {
        const first = plantedChapters[0];
        return { text: `已在第 ${first.ch} 章佈局`, variant: 'used' as const };
      }
      return { text: '未佈局', variant: 'free' as const };
    }

    // type === 'foreshadowing_payoffs'
    if (isCurrentCh(payoffChapters)) {
      return { text: '本章已回收', variant: 'current' as const };
    }
    if (payoffChapters.length > 0) {
      const first = payoffChapters[0];
      return { text: `已在第 ${first.ch} 章回收`, variant: 'used' as const };
    }
    if (plantedChapters.length > 0) {
      const first = plantedChapters[0];
      return { text: `第 ${first.ch} 章已佈局・未回收`, variant: 'ready' as const };
    }
    return { text: '尚未在任何章節佈局', variant: 'unplanted' as const };
  };

  // Filtered available items for search
  const filteredItems = useMemo(() => {
    if (!search.trim()) return availableItems;
    const q = search.toLowerCase();
    return availableItems.filter((item) => {
      const res = resolveTaskItem(item, type, availableItems);
      return (
        res.name.toLowerCase().includes(q) ||
        res.code.toLowerCase().includes(q) ||
        (res.desc && res.desc.toLowerCase().includes(q))
      );
    });
  }, [availableItems, search, type]);

  const isItemSelected = (target: any) => {
    const targetRes = resolveTaskItem(target, type, availableItems);
    return selected.some((s) => {
      const sRes = resolveTaskItem(s, type, availableItems);
      if (targetRes.code && sRes.code && targetRes.code === sRes.code) return true;
      if (targetRes.num !== null && sRes.num !== null && targetRes.num === sRes.num) return true;
      if (targetRes.name && sRes.name && targetRes.name === sRes.name) return true;
      return s === targetRes.key || s === targetRes.code || s === targetRes.name;
    });
  };

  const handleToggle = (item: any) => {
    const targetRes = resolveTaskItem(item, type, availableItems);
    if (isItemSelected(item)) {
      onChange(
        selected.filter((s) => {
          const sRes = resolveTaskItem(s, type, availableItems);
          if (targetRes.code && sRes.code && targetRes.code === sRes.code) return false;
          if (targetRes.num !== null && sRes.num !== null && targetRes.num === sRes.num) return false;
          if (targetRes.name && sRes.name && targetRes.name === sRes.name) return false;
          return s !== targetRes.key && s !== targetRes.code && s !== targetRes.name;
        })
      );
    } else {
      const storeKey = targetRes.code || targetRes.name || targetRes.key;
      onChange([...selected, storeKey]);
    }
  };

  const handleRemove = (itemVal: any, e: React.MouseEvent) => {
    e.stopPropagation();
    const targetRes = resolveTaskItem(itemVal, type, availableItems);
    onChange(
      selected.filter((s) => {
        const sRes = resolveTaskItem(s, type, availableItems);
        if (targetRes.code && sRes.code && targetRes.code === sRes.code) return false;
        if (targetRes.num !== null && sRes.num !== null && targetRes.num === sRes.num) return false;
        if (targetRes.name && sRes.name && targetRes.name === sRes.name) return false;
        return s !== targetRes.key && s !== targetRes.code && s !== targetRes.name;
      })
    );
  };

  const handleAddCustom = () => {
    const trimmed = search.trim();
    if (!trimmed || selected.includes(trimmed)) return;
    onChange([...selected, trimmed]);
    setSearch('');
  };

  const isRightAligned = type === 'foreshadowing_payoffs';

  return (
    <div className="task-picker-wrapper" ref={dropdownRef}>
      <label className="card-inline-label">{label}:</label>

      {/* Chips Area and Dropdown Trigger */}
      <div
        className="task-picker-input-box"
        onClick={() => setIsOpen(true)}
        role="button"
        tabIndex={0}
      >
        <div className="task-picker-chips">
          {selected.length === 0 ? (
            <span className="task-picker-placeholder">
              {placeholder || '點擊展開選單或手動選擇...'}
            </span>
          ) : (
            selected.map((itemVal, idx) => {
              const res = resolveTaskItem(itemVal, type, availableItems);
              const displayLabel = res.code ? `[${res.code}] ${res.name}` : res.name;
              const tooltip = `${res.code ? `[${res.code}] ` : ''}${res.name}${res.desc ? `\n說明: ${res.desc}` : ''}`;

              return (
                <span
                  key={idx}
                  className={`task-picker-chip chip-${type}`}
                  title={tooltip}
                >
                  <span className="chip-text">{displayLabel}</span>
                  <button
                    type="button"
                    className="chip-remove-btn"
                    onClick={(e) => handleRemove(itemVal, e)}
                    title="移除"
                  >
                    <IconX size={10} />
                  </button>
                </span>
              );
            })
          )}
        </div>

        <button
          type="button"
          className="task-picker-toggle-btn"
          title="切換選單"
          onClick={(e) => {
            e.stopPropagation();
            setIsOpen((prev) => !prev);
          }}
        >
          <IconPlus size={12} />
          <span>選擇</span>
        </button>
      </div>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className={`task-picker-dropdown ${isRightAligned ? 'align-right' : ''}`}>
          <div className="task-picker-search-bar">
            <input
              type="text"
              className="task-picker-search-input"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜尋名稱、標號或描述..."
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleAddCustom();
                }
              }}
            />
            {search.trim() && (
              <button
                type="button"
                className="task-picker-add-custom-btn"
                onClick={handleAddCustom}
              >
                新增自訂
              </button>
            )}
          </div>

          <div className="task-picker-list">
            {filteredItems.length === 0 ? (
              <div className="task-picker-empty-hint">
                <span>無符合項目</span>
                {search.trim() && (
                  <button
                    type="button"
                    className="task-picker-create-link"
                    onClick={handleAddCustom}
                  >
                    按此新增「{search.trim()}」
                  </button>
                )}
              </div>
            ) : (
              filteredItems.map((item, idx) => {
                const res = resolveTaskItem(item, type, availableItems);
                const isSelected = isItemSelected(item);
                const status = getItemStatus(item);
                const tooltipText = `${res.code ? `[${res.code}] ` : ''}${res.name}${
                  res.desc ? `\n說明: ${res.desc}` : ''
                }\n狀態: ${status.text}`;

                return (
                  <div
                    key={res.code || res.name || idx}
                    className={`task-picker-item ${isSelected ? 'selected' : ''}`}
                    onClick={() => handleToggle(item)}
                    title={tooltipText}
                  >
                    <div className="task-picker-item-left">
                      <span className={`task-picker-checkbox ${isSelected ? 'checked' : ''}`}>
                        {isSelected && <IconCheck size={11} />}
                      </span>
                      {res.code && <span className="task-picker-item-code">{res.code}</span>}
                      <span className="task-picker-item-name" title={res.name}>
                        {res.name}
                      </span>
                    </div>

                    <div className="task-picker-item-right">
                      <span className={`task-status-badge status-${status.variant}`}>
                        {status.text}
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
};
