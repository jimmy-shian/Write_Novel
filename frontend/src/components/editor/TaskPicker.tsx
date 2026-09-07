import React, { useState, useMemo, useRef, useEffect } from 'react';
import { IconCheck, IconPlus, IconX } from '../common/Icons';

export type TaskPickerType = 'turning_points' | 'foreshadowing_plants' | 'foreshadowing_payoffs';

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

    allVolumes.forEach((v: any, vIdx: number) => {
      const volNum = v.volume_index ?? vIdx + 1;
      const outlines = Array.isArray(v.chapters_outline) ? v.chapters_outline : [];
      outlines.forEach((ch: any, cIdx: number) => {
        const chNum = ch.chapter_index ?? cIdx + 1;
        const tasks = ch.allocated_tasks || {};

        // Turning points in this chapter
        const tps = Array.isArray(tasks.turning_points) ? tasks.turning_points : [];
        tps.forEach((tp: any) => {
          const key = typeof tp === 'string' ? tp : tp.id || tp.name;
          if (!key) return;
          if (!map.has(key)) map.set(key, { usedChapters: [], plantedChapters: [], payoffChapters: [] });
          map.get(key)!.usedChapters.push({ vol: volNum, ch: chNum });
        });

        // Foreshadowing plants
        const plants = Array.isArray(tasks.foreshadowing_plants) ? tasks.foreshadowing_plants : [];
        plants.forEach((p: any) => {
          const key = typeof p === 'string' ? p : p.id || p.name;
          if (!key) return;
          if (!map.has(key)) map.set(key, { usedChapters: [], plantedChapters: [], payoffChapters: [] });
          map.get(key)!.plantedChapters.push({ vol: volNum, ch: chNum });
        });

        // Foreshadowing payoffs
        const payoffs = Array.isArray(tasks.foreshadowing_payoffs) ? tasks.foreshadowing_payoffs : [];
        payoffs.forEach((p: any) => {
          const key = typeof p === 'string' ? p : p.id || p.name;
          if (!key) return;
          if (!map.has(key)) map.set(key, { usedChapters: [], plantedChapters: [], payoffChapters: [] });
          map.get(key)!.payoffChapters.push({ vol: volNum, ch: chNum });
        });
      });
    });

    return map;
  }, [allVolumes]);

  // Compute status for a specific item
  const getItemStatus = (id: string, name: string) => {
    const keysToCheck = [id, name].filter(Boolean);
    let usedChapters: Array<{ vol: number; ch: number }> = [];
    let plantedChapters: Array<{ vol: number; ch: number }> = [];
    let payoffChapters: Array<{ vol: number; ch: number }> = [];

    keysToCheck.forEach((k) => {
      const data = usageMap.get(k);
      if (data) {
        usedChapters = [...usedChapters, ...data.usedChapters];
        plantedChapters = [...plantedChapters, ...data.plantedChapters];
        payoffChapters = [...payoffChapters, ...data.payoffChapters];
      }
    });

    const isCurrentCh = (list: Array<{ vol: number; ch: number }>) =>
      list.some((item) => item.vol === currentVolNum && item.ch === currentChNum);

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
      const name = item.turning_point_name || item.name || '';
      const id = item.id || '';
      const desc = item.description || item.trigger_condition || '';
      return (
        name.toLowerCase().includes(q) ||
        id.toLowerCase().includes(q) ||
        desc.toLowerCase().includes(q)
      );
    });
  }, [availableItems, search]);

  const handleToggle = (itemKey: string) => {
    if (selected.includes(itemKey)) {
      onChange(selected.filter((s) => s !== itemKey));
    } else {
      onChange([...selected, itemKey]);
    }
  };

  const handleRemove = (itemKey: string, e: React.MouseEvent) => {
    e.stopPropagation();
    onChange(selected.filter((s) => s !== itemKey));
  };

  const handleAddCustom = () => {
    const trimmed = search.trim();
    if (!trimmed || selected.includes(trimmed)) return;
    onChange([...selected, trimmed]);
    setSearch('');
  };

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
            selected.map((itemKey) => {
              // Lookup name if possible
              const match = availableItems.find(
                (item) =>
                  item.id === itemKey ||
                  item.turning_point_name === itemKey ||
                  item.name === itemKey
              );
              const displayName = match
                ? match.turning_point_name || match.name || itemKey
                : itemKey;

              return (
                <span key={itemKey} className={`task-picker-chip chip-${type}`}>
                  <span className="chip-text">{displayName}</span>
                  <button
                    type="button"
                    className="chip-remove-btn"
                    onClick={(e) => handleRemove(itemKey, e)}
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
        <div className="task-picker-dropdown">
          <div className="task-picker-search-bar">
            <input
              type="text"
              className="task-picker-search-input"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜尋名稱或 ID..."
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
                const id = item.id || '';
                const name = item.turning_point_name || item.name || `項目 #${idx + 1}`;
                const key = id || name;
                const isSelected = selected.includes(key) || selected.includes(name) || (id ? selected.includes(id) : false);
                const status = getItemStatus(id, name);

                return (
                  <div
                    key={key}
                    className={`task-picker-item ${isSelected ? 'selected' : ''}`}
                    onClick={() => handleToggle(key)}
                  >
                    <div className="task-picker-item-left">
                      <span className={`task-picker-checkbox ${isSelected ? 'checked' : ''}`}>
                        {isSelected && <IconCheck size={11} />}
                      </span>
                      {id && <span className="task-picker-item-id">{id}</span>}
                      <span className="task-picker-item-name">{name}</span>
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
