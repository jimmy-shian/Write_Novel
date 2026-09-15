import React, { useState, useEffect, useMemo, useRef, useTransition, useCallback } from 'react';
import { Novel } from '../../types';
import { Button } from '../common/Button';
import { Badge } from '../common/Badge';
import { ConfirmModal } from '../common/ConfirmModal';
import { showToast } from '../common/Toast';
import { TaskPicker, resolveTaskItem } from './TaskPicker';
import {
  IconCopy,
  IconBookOpen,
  IconUsers,
  IconLayers,
  IconSparkles,
  IconEdit,
  IconCheck,
  IconX,
  IconPlus,
  IconTrash,
} from '../common/Icons';
import { copyToClipboard } from '../../utils/clipboard';
import { saveWorldbuilding, saveCharacters, savePlot, saveVolumes, savePipelinePrompt, updateNovel } from '../../api/novels';
import { EditNovelModal } from '../novel/EditNovelModal';
import { ExpansionSyncState } from '../../hooks/useExpansionSync';

export type WorldviewTab = 'worldview' | 'characters' | 'plot';

export interface TargetElement {
  type: 'character' | 'volume';
  id: string | number;
}

export interface WorldviewActionPayload {
  type: 'section' | 'character' | 'volume' | 'tp' | 'seed' | 'chapter_outline';
  id?: string | number;
  action?: 'add' | 'edit' | 'delete' | 'clean' | 'scroll';
  volIndex?: number;
  chIndex?: number;
  timestamp: number;
}

interface WorldviewPaneProps {
  novel: Novel | null;
  worldbuilding: string;
  charactersRaw: string;
  plotRaw: string;
  volumes?: any[];
  defaultTab?: WorldviewTab;
  activeTabProp?: WorldviewTab;
  targetElement?: TargetElement | null;
  actionTrigger?: WorldviewActionPayload | null;
  fontSize?: number;
  expansionSync?: ExpansionSyncState;
  onFontSizeChange?: (size: number) => void;
  onTabChange?: (tab: WorldviewTab) => void;
  onRefresh?: () => void;
  onLog?: (msg: string) => void;
  onUpdateNovel?: (novelId: string, title: string, genre: string, style: string, synopsis?: string) => Promise<any> | any;
  onDeleteTurningPoint?: (tpIndex: number) => Promise<any> | any;
  onDeleteForeshadowingSeed?: (seedIndex: number) => Promise<any> | any;
  onDeleteCharacter?: (charName: string) => Promise<any> | any;
  onDeleteVolume?: (volNum: number) => Promise<any> | any;
  onDeleteChapterOutline?: (volIndex: number, chIndex: number) => Promise<any> | any;
  onCleanEmptyTurningPoints?: () => Promise<any> | any;
  onCleanEmptySeeds?: () => Promise<any> | any;
  onCleanEmptyCharacters?: () => Promise<any> | any;
}

interface ParsedCharacter {
  name: string;
  role?: string;
  faction?: string;
  entry_phase?: string;
  personality?: string[] | string;
  want?: string;
  need?: string;
  fatal_flaw?: string;
  secret?: string;
  want_need_conflict?: string;
  speech_style?: string;
  speech_profile?: {
    default_register?: string;
    sentence_length?: string;
    directness?: string;
    under_pressure?: string;
    taboo_topics?: string[];
  };
  appearance?: string;
  arc?: string;
  background?: string;
  relationships?: any[];
}

interface ParsedVolume {
  volume_index?: number;
  title?: string;
  summary?: string;
  chapter_count?: number;
  factions?: string[];
  time_timeline?: string;
  turning_points?: any[];
  chapters_outline?: any[];
  foreshadowing_plants?: any[];
}

export function reindexVolumesChapters(vols: ParsedVolume[]): ParsedVolume[] {
  let currentChapterIndex = 1;
  return vols.map((v, vIdx) => {
    const volNum = v.volume_index ?? vIdx + 1;
    if (!Array.isArray(v.chapters_outline) || v.chapters_outline.length === 0) {
      return {
        ...v,
        volume_index: volNum,
        chapter_count: typeof v.chapter_count === 'number' && v.chapter_count > 0 ? v.chapter_count : 50,
      };
    }
    const updatedOutlines = v.chapters_outline.map((ch: any) => {
      const oldIndex = ch.chapter_index;
      const newIndex = currentChapterIndex++;
      let newTitle = (ch.chapter_title || '').trim();
      if (!newTitle) {
        newTitle = `第 ${newIndex} 章`;
      } else {
        const prefixRegex = /^第\s*\d+\s*章([：:\s]*)/;
        if (prefixRegex.test(newTitle)) {
          newTitle = newTitle.replace(prefixRegex, `第 ${newIndex} 章$1`);
        }
      }
      return {
        ...ch,
        chapter_index: newIndex,
        chapter_title: newTitle,
      };
    });
    return {
      ...v,
      volume_index: volNum,
      chapter_count: updatedOutlines.length,
      chapters_outline: updatedOutlines,
    };
  });
}

export function normalizeVolume(v: any, idx: number): ParsedVolume {
  if (!v || typeof v !== 'object') {
    return {
      volume_index: idx + 1,
      title: `第 ${idx + 1} 卷`,
      summary: '',
      chapter_count: 50,
      factions: [],
      time_timeline: '',
      turning_points: [],
      chapters_outline: [],
    };
  }

  // 1. factions normalization: guarantee string[]
  let rawFactions: any[] = [];
  if (Array.isArray(v.parsed_factions)) {
    rawFactions = v.parsed_factions;
  } else if (Array.isArray(v.factions)) {
    rawFactions = v.factions;
  } else if (typeof v.factions === 'string' && v.factions.trim()) {
    try {
      const parsed = JSON.parse(v.factions);
      if (Array.isArray(parsed)) {
        rawFactions = parsed;
      } else {
        rawFactions = v.factions.split(/[,，、]/).map((s: string) => s.trim()).filter(Boolean);
      }
    } catch {
      rawFactions = v.factions.split(/[,，、]/).map((s: string) => s.trim()).filter(Boolean);
    }
  }

  const factions: string[] = rawFactions
    .map((item: any) => {
      if (typeof item === 'string') return item.trim();
      if (typeof item === 'number') return String(item);
      if (item && typeof item === 'object') {
        const name = item.name || item.title || item.faction_name || item.faction || '';
        const alignment = item.alignment ? ` (${item.alignment})` : '';
        return name ? `${name}${alignment}` : (item.summary ? String(item.summary) : JSON.stringify(item));
      }
      return '';
    })
    .filter(Boolean);

  // 2. chapters_outline normalization: guarantee Array
  let chaptersOutline: any[] = [];
  let rawOutlines = v.chapters_outline;
  if (typeof rawOutlines === 'string' && rawOutlines.trim()) {
    try {
      rawOutlines = JSON.parse(rawOutlines);
    } catch {
      rawOutlines = [];
    }
  }
  if (Array.isArray(rawOutlines)) {
    chaptersOutline = rawOutlines;
  } else if (rawOutlines && typeof rawOutlines === 'object' && Array.isArray(rawOutlines.chapters)) {
    chaptersOutline = rawOutlines.chapters;
  }

  // 3. turning_points normalization
  let turningPoints: any[] = [];
  if (Array.isArray(v.turning_points)) {
    turningPoints = v.turning_points;
  } else if (typeof v.turning_points === 'string' && v.turning_points.trim()) {
    try {
      const parsed = JSON.parse(v.turning_points);
      if (Array.isArray(parsed)) turningPoints = parsed;
    } catch {
      turningPoints = [];
    }
  }

  const volNum = v.volume_index ?? idx + 1;
  return {
    volume_index: volNum,
    title: typeof v.title === 'string' && v.title.trim() ? v.title.trim() : (v.title ? String(v.title) : `第 ${volNum} 卷`),
    summary: typeof v.summary === 'string' ? v.summary : (v.summary ? String(v.summary) : ''),
    chapter_count: typeof v.chapter_count === 'number' && v.chapter_count > 0 ? v.chapter_count : (chaptersOutline.length || 50),
    factions,
    time_timeline: typeof v.time_timeline === 'string' ? v.time_timeline : (v.time_timeline ? String(v.time_timeline) : ''),
    turning_points: turningPoints,
    chapters_outline: chaptersOutline,
  };
}

export const WorldviewPane: React.FC<WorldviewPaneProps> = ({
  novel,
  worldbuilding,
  charactersRaw,
  plotRaw,
  volumes,
  defaultTab = 'worldview',
  activeTabProp,
  targetElement,
  actionTrigger,
  fontSize = 16,
  expansionSync,
  onFontSizeChange,
  onTabChange,
  onRefresh,
  onLog,
  onDeleteTurningPoint,
  onDeleteForeshadowingSeed,
  onDeleteCharacter,
  onDeleteVolume,
  onDeleteChapterOutline,
  onCleanEmptyTurningPoints,
  onCleanEmptySeeds,
  onCleanEmptyCharacters,
  onUpdateNovel,
}) => {
  const [internalTab, setInternalTab] = useState<WorldviewTab>(activeTabProp || defaultTab);
  const activeTab = activeTabProp !== undefined ? activeTabProp : internalTab;
  const [, startTransition] = useTransition();

  const [wbText, setWbText] = useState(worldbuilding || '');
  const [charsText, setCharsText] = useState(charactersRaw || '');
  const [plotText, setPlotText] = useState(plotRaw || '');

  // View modes
  const [wbViewMode, setWbViewMode] = useState<'card' | 'raw'>('card');
  const [charViewMode, setCharViewMode] = useState<'card' | 'raw'>('card');
  const [plotViewMode, setPlotViewMode] = useState<'card' | 'raw'>('card');

  // Incremental Lazy Loading Slices (delegated to expansionSync if provided)
  const [localVisibleCharCount, setLocalVisibleCharCount] = useState<number>(8);
  const [localVisibleVolumeCount, setLocalVisibleVolumeCount] = useState<number>(4);
  const [localVisibleSeedCount, setLocalVisibleSeedCount] = useState<number>(8);
  const [localVisibleTpCount, setLocalVisibleTpCount] = useState<number>(8);

  const visibleCharCount = expansionSync ? expansionSync.visibleCharCount : localVisibleCharCount;
  const visibleVolumeCount = expansionSync ? expansionSync.visibleVolumeCount : localVisibleVolumeCount;
  const visibleSeedCount = expansionSync ? expansionSync.visibleSeedCount : localVisibleSeedCount;
  const visibleTpCount = expansionSync ? expansionSync.visibleTpCount : localVisibleTpCount;

  const setVisibleCharCount = useCallback((val: number | ((prev: number) => number)) => {
    if (expansionSync) {
      const next = typeof val === 'function' ? val(expansionSync.visibleCharCount) : val;
      expansionSync.syncCharCount(next);
    } else {
      setLocalVisibleCharCount(val);
    }
  }, [expansionSync]);

  const setVisibleVolumeCount = useCallback((val: number | ((prev: number) => number)) => {
    if (expansionSync) {
      const next = typeof val === 'function' ? val(expansionSync.visibleVolumeCount) : val;
      expansionSync.syncVolumeCount(next);
    } else {
      setLocalVisibleVolumeCount(val);
    }
  }, [expansionSync]);

  const setVisibleSeedCount = useCallback((val: number | ((prev: number) => number)) => {
    if (expansionSync) {
      const next = typeof val === 'function' ? val(expansionSync.visibleSeedCount) : val;
      expansionSync.syncSeedCount(next);
    } else {
      setLocalVisibleSeedCount(val);
    }
  }, [expansionSync]);

  const setVisibleTpCount = useCallback((val: number | ((prev: number) => number)) => {
    if (expansionSync) {
      const next = typeof val === 'function' ? val(expansionSync.visibleTpCount) : val;
      expansionSync.syncTpCount(next);
    } else {
      setLocalVisibleTpCount(val);
    }
  }, [expansionSync]);

  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [copiedContent, setCopiedContent] = useState(false);

  // Novel Basic Settings Edit Modal State
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);

  const handleUpdateNovel = async (newTitle: string, newGenre: string, newStyle: string, newSynopsis?: string) => {
    if (!novel) return;
    try {
      if (onUpdateNovel) {
        await onUpdateNovel(novel.id, newTitle, newGenre, newStyle, newSynopsis);
      } else {
        await updateNovel(novel.id, {
          title: newTitle,
          genre: newGenre,
          style: newStyle,
          pipeline_prompt: newSynopsis,
        });
      }
      showToast('小說基本設定已成功更新！', 'success');
      onRefresh?.();
    } catch (err: any) {
      showToast(err?.message || '更新失敗', 'danger');
      throw err;
    }
  };

  // Card Inline Editing States - Tab 1 (Worldview)
  const [isEditingPipelinePrompt, setIsEditingPipelinePrompt] = useState(false);
  const [editPipelinePrompt, setEditPipelinePrompt] = useState('');
  const [isSavingPrompt, setIsSavingPrompt] = useState(false);

  const [isEditingTheme, setIsEditingTheme] = useState(false);
  const [editTheme, setEditTheme] = useState('');
  const [editConflict, setEditConflict] = useState('');

  const [isEditingWorldviewText, setIsEditingWorldviewText] = useState(false);
  const [editWorldviewText, setEditWorldviewText] = useState('');

  const [isEditingMacroOutline, setIsEditingMacroOutline] = useState(false);
  const [editMacroOutline, setEditMacroOutline] = useState('');

  const [editingActIndex, setEditingActIndex] = useState<number | null>(null);
  const [editActForm, setEditActForm] = useState<{ title: string; content: string }>({ title: '', content: '' });

  const [editingTpIndex, setEditingTpIndex] = useState<number | null>(null);
  const [editTpForm, setEditTpForm] = useState<{
    turning_point_name: string;
    trigger_condition: string;
    structural_impact: string;
    id?: string;
  }>({ turning_point_name: '', trigger_condition: '', structural_impact: '', id: '' });

  const [editingSeedIndex, setEditingSeedIndex] = useState<number | null>(null);
  const [editSeedForm, setEditSeedForm] = useState<{
    name: string;
    description: string;
    setup_hint: string;
    payoff_hint: string;
    id?: string;
  }>({ name: '', description: '', setup_hint: '', payoff_hint: '', id: '' });

  // Card Inline Editing States - Tab 2 (Characters)
  const [editingCharName, setEditingCharName] = useState<string | null>(null);
  const [editCharForm, setEditCharForm] = useState<Partial<ParsedCharacter>>({});

  // Card Inline Editing States - Tab 3 (Volumes)
  const [editingVolNum, setEditingVolNum] = useState<number | null>(null);
  const [editVolForm, setEditVolForm] = useState<Partial<ParsedVolume>>({});
  const [expandedVolChapters, setExpandedVolChapters] = useState<number[]>([]);

  // Card Inline Editing States - Chapters Outline in Volume
  const [editingChapterOutline, setEditingChapterOutline] = useState<{ volIndex: number; chIndex: number } | null>(null);
  const [editChapterOutlineForm, setEditChapterOutlineForm] = useState<any>({});

  // Delete Confirm Modal
  const [deleteConfirm, setDeleteConfirm] = useState<{
    title: string;
    message: string;
    onConfirm: () => void;
  } | null>(null);

  // Sentinel refs for IntersectionObserver infinite scrolling
  const tpSentinelRef = useRef<HTMLDivElement | null>(null);
  const seedSentinelRef = useRef<HTMLDivElement | null>(null);
  const charSentinelRef = useRef<HTMLDivElement | null>(null);
  const volSentinelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (activeTabProp) {
      startTransition(() => {
        setInternalTab(activeTabProp);
      });
    }
  }, [activeTabProp]);

  useEffect(() => {
    setWbText(worldbuilding || '');
  }, [worldbuilding]);

  useEffect(() => {
    setCharsText(charactersRaw || '');
  }, [charactersRaw]);

  useEffect(() => {
    setPlotText(plotRaw || '');
  }, [plotRaw]);

  // Parse Worldbuilding JSON safely
  const parsedWorldview = useMemo(() => {
    if (!wbText.trim()) return null;
    try {
      const data = JSON.parse(wbText);
      if (typeof data === 'object' && data !== null && !Array.isArray(data)) {
        return data;
      }
    } catch {
      // Not JSON
    }
    return null;
  }, [wbText]);

  // Parse Characters JSON safely
  const parsedCharacters: ParsedCharacter[] = useMemo(() => {
    if (!charsText.trim()) return [];
    try {
      const data = JSON.parse(charsText);
      if (Array.isArray(data)) return data;
      if (data && Array.isArray(data.characters)) return data.characters;
      if (typeof data === 'object' && data !== null) {
        return Object.values(data).filter(
          (item: any) => item && typeof item === 'object' && item.name
        );
      }
    } catch {
      // Not valid JSON
    }
    return [];
  }, [charsText]);

  // Parse Plot / Volumes JSON safely with fallback to volumes prop
  const parsedVolumes: ParsedVolume[] = useMemo(() => {
    // 1. If user edited plotText in raw mode (different from initial plotRaw), parse and use that
    if (plotText.trim() && plotText !== plotRaw) {
      try {
        const data = JSON.parse(plotText);
        if (Array.isArray(data) && data.length > 0) {
          return data.map((v: any, idx: number) => normalizeVolume(v, idx));
        }
        if (data && Array.isArray(data.volumes) && data.volumes.length > 0) {
          return data.volumes.map((v: any, idx: number) => normalizeVolume(v, idx));
        }
      } catch {
        // Fall through
      }
    }

    // 2. Authoritative: if volumes prop from DB exists and is non-empty, use it!
    if (volumes && Array.isArray(volumes) && volumes.length > 0) {
      return volumes.map((v: any, idx: number) => normalizeVolume(v, idx));
    }

    // 3. Fallback to parsing plotText
    if (plotText.trim()) {
      try {
        const data = JSON.parse(plotText);
        if (Array.isArray(data) && data.length > 0) {
          return data.map((v: any, idx: number) => normalizeVolume(v, idx));
        }
        if (data && Array.isArray(data.volumes) && data.volumes.length > 0) {
          return data.volumes.map((v: any, idx: number) => normalizeVolume(v, idx));
        }
        if (data && Array.isArray(data.macro_outline_volumes) && data.macro_outline_volumes.length > 0) {
          return data.macro_outline_volumes.map((v: any, idx: number) => normalizeVolume(v, idx));
        }
        if (typeof data === 'object' && data !== null) {
          const list = Object.values(data).filter(
            (item: any) => item && typeof item === 'object' && (item.volume_index || item.title)
          );
          if (list.length > 0) {
            return list.map((v: any, idx: number) => normalizeVolume(v, idx));
          }
        }
      } catch {
        // Not valid JSON
      }
    }
    return [];
  }, [plotText, plotRaw, volumes]);

  // IntersectionObserver for auto-expanding lists when scrolled to bottom
  useEffect(() => {
    if (activeTab !== 'worldview') return;
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            if (entry.target === tpSentinelRef.current && parsedWorldview?.key_turning_points) {
              setVisibleTpCount((prev) => Math.min(prev + 8, parsedWorldview.key_turning_points.length));
            }
            if (entry.target === seedSentinelRef.current && parsedWorldview?.foreshadowing_seeds) {
              setVisibleSeedCount((prev) => Math.min(prev + 8, parsedWorldview.foreshadowing_seeds.length));
            }
          }
        });
      },
      { rootMargin: '200px' }
    );

    const tpEl = tpSentinelRef.current;
    const seedEl = seedSentinelRef.current;
    if (tpEl) observer.observe(tpEl);
    if (seedEl) observer.observe(seedEl);

    return () => {
      if (tpEl) observer.unobserve(tpEl);
      if (seedEl) observer.unobserve(seedEl);
      observer.disconnect();
    };
  }, [activeTab, parsedWorldview]);

  useEffect(() => {
    if (activeTab !== 'characters') return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          setVisibleCharCount((prev) => Math.min(prev + 8, parsedCharacters.length));
        }
      },
      { rootMargin: '200px' }
    );

    const charEl = charSentinelRef.current;
    if (charEl) observer.observe(charEl);

    return () => {
      if (charEl) observer.unobserve(charEl);
      observer.disconnect();
    };
  }, [activeTab, parsedCharacters.length]);

  useEffect(() => {
    if (activeTab !== 'plot') return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          setVisibleVolumeCount((prev) => Math.min(prev + 4, parsedVolumes.length));
        }
      },
      { rootMargin: '200px' }
    );

    const volEl = volSentinelRef.current;
    if (volEl) observer.observe(volEl);

    return () => {
      if (volEl) observer.unobserve(volEl);
      observer.disconnect();
    };
  }, [activeTab, parsedVolumes.length]);

  // Handle smooth scroll to target character or volume from left sidebar
  useEffect(() => {
    if (!targetElement) return;

    if (targetElement.type === 'character') {
      const idx = parsedCharacters.findIndex((c) => c.name === targetElement.id);
      if (idx !== -1 && idx >= visibleCharCount) {
        setVisibleCharCount(idx + 5);
      }
      setTimeout(() => {
        const el = document.getElementById(`char-card-${targetElement.id}`);
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          el.classList.add('card-highlight-pulse');
          setTimeout(() => el.classList.remove('card-highlight-pulse'), 2200);
        }
      }, 150);
    } else if (targetElement.type === 'volume') {
      const volNum = Number(targetElement.id);
      const idx = parsedVolumes.findIndex((v, i) => (v.volume_index ?? i + 1) === volNum);
      if (idx !== -1 && idx >= visibleVolumeCount) {
        setVisibleVolumeCount(idx + 3);
      }
      setTimeout(() => {
        const el = document.getElementById(`vol-card-${volNum}`);
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          el.classList.add('card-highlight-pulse');
          setTimeout(() => el.classList.remove('card-highlight-pulse'), 2200);
        }
      }, 150);
    }
  }, [targetElement, parsedCharacters, parsedVolumes, visibleCharCount, visibleVolumeCount]);

  const handleTabChange = (tab: WorldviewTab) => {
    startTransition(() => {
      setInternalTab(tab);
    });
    onTabChange?.(tab);
  };

  const currentContent =
    activeTab === 'worldview'
      ? wbText
      : activeTab === 'characters'
      ? charsText
      : plotText;

  const handleCopyContent = async () => {
    if (!currentContent) return;
    const ok = await copyToClipboard(currentContent);
    if (ok) {
      setCopiedContent(true);
      setTimeout(() => setCopiedContent(false), 2000);
    }
  };

  const handleSave = async () => {
    if (!novel) return;
    setIsSaving(true);
    setSaveSuccess(false);
    try {
      if (activeTab === 'worldview') {
        await saveWorldbuilding(novel.id, wbText);
        onLog?.(`世界觀設定已儲存 (長度: ${wbText.length} 字)`);
      } else if (activeTab === 'characters') {
        let parsed = charsText;
        try {
          parsed = JSON.parse(charsText);
        } catch {
          // keep string if not json
        }
        await saveCharacters(novel.id, parsed);
        onLog?.(`角色聖經已儲存 (長度: ${charsText.length} 字)`);
      } else if (activeTab === 'plot') {
        let parsed: any = plotText;
        try {
          parsed = JSON.parse(plotText);
        } catch {
          // keep string if not json
        }
        if (Array.isArray(parsed)) {
          parsed = reindexVolumesChapters(parsed);
          setPlotText(JSON.stringify(parsed, null, 2));
        }
        await saveVolumes(novel.id, parsed);
        onLog?.(`大綱分卷骨架已儲存 (長度: ${plotText.length} 字)`);
      }
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2500);
      onRefresh?.();
    } catch (err: any) {
      onLog?.(`儲存失敗: ${err?.message || err}`);
    } finally {
      setIsSaving(false);
    }
  };

  const scrollAndHighlight = useCallback((elementId: string) => {
    let attempts = 0;
    const tryScroll = () => {
      attempts++;
      const el = document.getElementById(elementId);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.classList.add('card-highlight-pulse');
        setTimeout(() => el.classList.remove('card-highlight-pulse'), 2200);
      } else if (attempts < 8) {
        setTimeout(tryScroll, 120);
      }
    };
    setTimeout(tryScroll, 80);
  }, []);

  const updateWorldviewData = useCallback((updater: (data: any) => any) => {
    try {
      const base = parsedWorldview ? JSON.parse(JSON.stringify(parsedWorldview)) : {};
      const updated = updater(base) || base;
      setWbText(JSON.stringify(updated, null, 2));
    } catch (err) {
      console.error('更新世界觀失敗:', err);
    }
  }, [parsedWorldview]);

  // Inline edit handlers for Tab 1 (Worldview)
  const handleSavePipelinePrompt = useCallback(
    async (newPrompt: string) => {
      if (!novel?.id) {
        showToast('未選取作品，無法儲存', 'warning');
        return;
      }
      setIsSavingPrompt(true);
      try {
        await savePipelinePrompt(novel.id, newPrompt.trim());
        if (novel) {
          novel.pipeline_prompt = newPrompt.trim();
        }
        setIsEditingPipelinePrompt(false);
        showToast('故事簡述與大綱靈感已成功更新！', 'success');
        onLog?.('已更新故事簡述 / 大綱靈感 (Pipeline Prompt)');
        onRefresh?.();
      } catch (err: any) {
        showToast(`儲存失敗: ${err.message}`, 'danger');
      } finally {
        setIsSavingPrompt(false);
      }
    },
    [novel, onRefresh, onLog]
  );

  const handleSaveThemeConflict = (themeVal: string, conflictVal: string) => {
    try {
      const data = parsedWorldview ? { ...parsedWorldview } : {};
      data.theme = themeVal;
      data.main_conflict = conflictVal;
      setWbText(JSON.stringify(data, null, 2));
    } catch {
      setWbText(JSON.stringify({ theme: themeVal, main_conflict: conflictVal }, null, 2));
    }
    setIsEditingTheme(false);
  };

  const handleSaveWorldviewField = (textVal: string) => {
    try {
      const data = parsedWorldview ? { ...parsedWorldview } : {};
      data.worldview = textVal;
      setWbText(JSON.stringify(data, null, 2));
    } catch {
      setWbText(textVal);
    }
    setIsEditingWorldviewText(false);
  };

  const handleSaveMacroOutline = (macroVal: string) => {
    try {
      const data = parsedWorldview ? { ...parsedWorldview } : {};
      data.macro_outline = macroVal;
      setWbText(JSON.stringify(data, null, 2));
    } catch {
      setWbText(macroVal);
    }
    setIsEditingMacroOutline(false);
  };

  // Tab 1 Act Structure Handlers
  const handleAddAct = useCallback(() => {
    let newIdx = 0;
    updateWorldviewData((data) => {
      const list = Array.isArray(data.multi_act_structure) ? [...data.multi_act_structure] : [];
      newIdx = list.length;
      const newAct = {
        title: `第 ${newIdx + 1} 幕`,
        content: '',
      };
      list.push(newAct);
      data.multi_act_structure = list;
      return data;
    });
    setEditingActIndex(newIdx);
    setEditActForm({ title: `第 ${newIdx + 1} 幕`, content: '' });
    scrollAndHighlight(`wb-act-item-${newIdx}`);
    onLog?.(`已新增第 ${newIdx + 1} 幕戲劇弧線`);
  }, [updateWorldviewData, scrollAndHighlight, onLog]);

  const handleSaveAct = useCallback((actIndex: number, updated: { title: string; content: string }) => {
    updateWorldviewData((data) => {
      if (Array.isArray(data.multi_act_structure)) {
        data.multi_act_structure = data.multi_act_structure.map((item: any, i: number) => {
          if (i === actIndex) {
            return typeof item === 'object' && item !== null
              ? { ...item, title: updated.title, content: updated.content }
              : updated;
          }
          return item;
        });
      }
      return data;
    });
    setEditingActIndex(null);
  }, [updateWorldviewData]);

  const handleDeleteAct = useCallback((actIndex: number) => {
    updateWorldviewData((data) => {
      if (Array.isArray(data.multi_act_structure)) {
        data.multi_act_structure = data.multi_act_structure.filter((_: any, i: number) => i !== actIndex);
      }
      return data;
    });
    if (editingActIndex === actIndex) setEditingActIndex(null);
    onLog?.(`已刪除第 ${actIndex + 1} 幕`);
  }, [updateWorldviewData, editingActIndex, onLog]);

  // Tab 1 Turning Points Handlers
  const handleAddTp = useCallback(() => {
    let newIdx = 0;
    updateWorldviewData((data) => {
      const list = Array.isArray(data.key_turning_points) ? [...data.key_turning_points] : [];
      newIdx = list.length;
      const newId = `TP_${String(newIdx + 1).padStart(2, '0')}`;
      const newTp = {
        id: newId,
        turning_point_name: `新轉折點 #${newIdx + 1}`,
        description: '',
        trigger_condition: '',
        structural_impact: '',
      };
      list.push(newTp);
      data.key_turning_points = list;
      return data;
    });
    setVisibleTpCount((prev) => Math.max(prev, newIdx + 5));
    setEditingTpIndex(newIdx);
    setEditTpForm({
      id: `TP_${String(newIdx + 1).padStart(2, '0')}`,
      turning_point_name: `新轉折點 #${newIdx + 1}`,
      trigger_condition: '',
      structural_impact: '',
    });
    scrollAndHighlight(`wb-tp-item-${newIdx}`);
    onLog?.('已新增一處重大轉折點');
  }, [updateWorldviewData, scrollAndHighlight, onLog]);

  const handleSaveTp = useCallback((tpIndex: number, updatedForm: any) => {
    updateWorldviewData((data) => {
      if (Array.isArray(data.key_turning_points)) {
        data.key_turning_points = data.key_turning_points.map((item: any, i: number) => {
          if (i === tpIndex) {
            return { ...item, ...updatedForm };
          }
          return item;
        });
      }
      return data;
    });
    setEditingTpIndex(null);
  }, [updateWorldviewData]);

  const handleDeleteTp = useCallback(
    async (tpIndex: number) => {
      updateWorldviewData((data) => {
        if (Array.isArray(data.key_turning_points)) {
          data.key_turning_points = data.key_turning_points.filter((_: any, i: number) => i !== tpIndex);
        }
        return data;
      });
      if (editingTpIndex === tpIndex) setEditingTpIndex(null);

      try {
        if (onDeleteTurningPoint) {
          await onDeleteTurningPoint(tpIndex);
        } else if (novel?.id) {
          const base = parsedWorldview ? JSON.parse(JSON.stringify(parsedWorldview)) : {};
          if (Array.isArray(base.key_turning_points)) {
            base.key_turning_points = base.key_turning_points.filter((_: any, i: number) => i !== tpIndex);
          }
          await saveWorldbuilding(novel.id, JSON.stringify(base, null, 2));
          onRefresh?.();
        }
        showToast(`已刪除轉折點 #${tpIndex + 1}`, 'info');
        onLog?.(`已刪除轉折點 #${tpIndex + 1}`);
      } catch (err: any) {
        showToast(`刪除轉折點失敗: ${err.message || err}`, 'danger');
      }
    },
    [updateWorldviewData, editingTpIndex, onDeleteTurningPoint, novel?.id, parsedWorldview, onRefresh, showToast, onLog]
  );

  // Tab 1 Foreshadowing Seeds Handlers
  const handleAddSeed = useCallback(() => {
    let newIdx = 0;
    updateWorldviewData((data) => {
      const list = Array.isArray(data.foreshadowing_seeds) ? [...data.foreshadowing_seeds] : [];
      newIdx = list.length;
      const newId = `SEED_${String(newIdx + 1).padStart(2, '0')}`;
      const newSeed = {
        id: newId,
        name: `新伏筆種子 #${newIdx + 1}`,
        description: '',
        setup_hint: '',
        payoff_hint: '',
      };
      list.push(newSeed);
      data.foreshadowing_seeds = list;
      return data;
    });
    setVisibleSeedCount((prev) => Math.max(prev, newIdx + 5));
    setEditingSeedIndex(newIdx);
    setEditSeedForm({
      id: `SEED_${String(newIdx + 1).padStart(2, '0')}`,
      name: `新伏筆種子 #${newIdx + 1}`,
      description: '',
      setup_hint: '',
      payoff_hint: '',
    });
    scrollAndHighlight(`wb-seed-item-${newIdx}`);
    onLog?.('已新增一處伏筆種子');
  }, [updateWorldviewData, scrollAndHighlight, onLog]);

  const handleSaveSeed = useCallback((seedIndex: number, updatedForm: any) => {
    updateWorldviewData((data) => {
      if (Array.isArray(data.foreshadowing_seeds)) {
        data.foreshadowing_seeds = data.foreshadowing_seeds.map((item: any, i: number) => {
          if (i === seedIndex) {
            return { ...item, ...updatedForm };
          }
          return item;
        });
      }
      return data;
    });
    setEditingSeedIndex(null);
  }, [updateWorldviewData]);

  const handleDeleteSeed = useCallback(
    async (seedIndex: number) => {
      updateWorldviewData((data) => {
        if (Array.isArray(data.foreshadowing_seeds)) {
          data.foreshadowing_seeds = data.foreshadowing_seeds.filter((_: any, i: number) => i !== seedIndex);
        }
        return data;
      });
      if (editingSeedIndex === seedIndex) setEditingSeedIndex(null);

      try {
        if (onDeleteForeshadowingSeed) {
          await onDeleteForeshadowingSeed(seedIndex);
        } else if (novel?.id) {
          const base = parsedWorldview ? JSON.parse(JSON.stringify(parsedWorldview)) : {};
          if (Array.isArray(base.foreshadowing_seeds)) {
            base.foreshadowing_seeds = base.foreshadowing_seeds.filter((_: any, i: number) => i !== seedIndex);
          }
          await saveWorldbuilding(novel.id, JSON.stringify(base, null, 2));
          onRefresh?.();
        }
        showToast(`已刪除伏筆種子 #${seedIndex + 1}`, 'info');
        onLog?.(`已刪除伏筆種子 #${seedIndex + 1}`);
      } catch (err: any) {
        showToast(`刪除伏筆種子失敗: ${err.message || err}`, 'danger');
      }
    },
    [updateWorldviewData, editingSeedIndex, onDeleteForeshadowingSeed, novel?.id, parsedWorldview, onRefresh, showToast, onLog]
  );

  const handleCleanEmptyWorldview = useCallback(async () => {
    let cleanedCount = 0;
    try {
      if (onCleanEmptyTurningPoints && onCleanEmptySeeds) {
        const tpCleaned = (await onCleanEmptyTurningPoints()) || 0;
        const sCleaned = (await onCleanEmptySeeds()) || 0;
        cleanedCount = tpCleaned + sCleaned;
      } else {
        updateWorldviewData((data) => {
          if (Array.isArray(data.key_turning_points)) {
            const before = data.key_turning_points.length;
            data.key_turning_points = data.key_turning_points.filter((tp: any) => {
              const name = (tp?.turning_point_name || tp?.name || '').trim();
              const desc = (tp?.description || tp?.trigger_condition || '').trim();
              if (!name && !desc) return false;
              if ((name.startsWith('新轉折點') || name.startsWith('未命名')) && !desc) return false;
              return true;
            });
            cleanedCount += before - data.key_turning_points.length;
          }
          if (Array.isArray(data.foreshadowing_seeds)) {
            const before = data.foreshadowing_seeds.length;
            data.foreshadowing_seeds = data.foreshadowing_seeds.filter((s: any) => {
              const name = (s?.name || '').trim();
              const desc = (s?.description || s?.setup_hint || '').trim();
              if (!name && !desc) return false;
              if ((name.startsWith('新伏筆') || name.startsWith('未命名')) && !desc) return false;
              return true;
            });
            cleanedCount += before - data.foreshadowing_seeds.length;
          }
          return data;
        });

        if (novel?.id && parsedWorldview) {
          const base = JSON.parse(JSON.stringify(parsedWorldview));
          if (Array.isArray(base.key_turning_points)) {
            base.key_turning_points = base.key_turning_points.filter((tp: any) => {
              const name = (tp?.turning_point_name || tp?.name || '').trim();
              const desc = (tp?.description || tp?.trigger_condition || '').trim();
              if (!name && !desc) return false;
              if ((name.startsWith('新轉折點') || name.startsWith('未命名')) && !desc) return false;
              return true;
            });
          }
          if (Array.isArray(base.foreshadowing_seeds)) {
            base.foreshadowing_seeds = base.foreshadowing_seeds.filter((s: any) => {
              const name = (s?.name || '').trim();
              const desc = (s?.description || s?.setup_hint || '').trim();
              if (!name && !desc) return false;
              if ((name.startsWith('新伏筆') || name.startsWith('未命名')) && !desc) return false;
              return true;
            });
          }
          await saveWorldbuilding(novel.id, JSON.stringify(base, null, 2));
          onRefresh?.();
        }
      }

      if (cleanedCount > 0) {
        showToast(`已成功清除 ${cleanedCount} 個空白世界觀項目`, 'success');
        onLog?.(`已清除 ${cleanedCount} 個空白世界觀項目`);
      } else {
        showToast('目前無空白世界觀項目需要清理', 'info');
      }
    } catch (err: any) {
      showToast(`清理失敗: ${err.message || err}`, 'danger');
    }
  }, [onCleanEmptyTurningPoints, onCleanEmptySeeds, updateWorldviewData, novel?.id, parsedWorldview, onRefresh, showToast, onLog]);

  const handleCleanEmptyTurningPoints = useCallback(async () => {
    let cleanedCount = 0;
    try {
      if (onCleanEmptyTurningPoints) {
        cleanedCount = (await onCleanEmptyTurningPoints()) || 0;
      } else {
        updateWorldviewData((data) => {
          if (Array.isArray(data.key_turning_points)) {
            const before = data.key_turning_points.length;
            data.key_turning_points = data.key_turning_points.filter((tp: any) => {
              const name = (tp?.turning_point_name || tp?.name || '').trim();
              const desc = (tp?.description || tp?.trigger_condition || '').trim();
              if (!name && !desc) return false;
              if ((name.startsWith('新轉折點') || name.startsWith('未命名')) && !desc) return false;
              return true;
            });
            cleanedCount = before - data.key_turning_points.length;
          }
          return data;
        });

        if (novel?.id && parsedWorldview) {
          const base = JSON.parse(JSON.stringify(parsedWorldview));
          if (Array.isArray(base.key_turning_points)) {
            base.key_turning_points = base.key_turning_points.filter((tp: any) => {
              const name = (tp?.turning_point_name || tp?.name || '').trim();
              const desc = (tp?.description || tp?.trigger_condition || '').trim();
              if (!name && !desc) return false;
              if ((name.startsWith('新轉折點') || name.startsWith('未命名')) && !desc) return false;
              return true;
            });
          }
          await saveWorldbuilding(novel.id, JSON.stringify(base, null, 2));
          onRefresh?.();
        }
      }

      if (cleanedCount > 0) {
        showToast(`已成功清除 ${cleanedCount} 個空白轉折點`, 'success');
        onLog?.(`已清除 ${cleanedCount} 個空白轉折點`);
      } else {
        showToast('目前無空白轉折點需要清理', 'info');
      }
    } catch (err: any) {
      showToast(`清理失敗: ${err.message || err}`, 'danger');
    }
  }, [onCleanEmptyTurningPoints, updateWorldviewData, novel?.id, parsedWorldview, onRefresh, showToast, onLog]);

  const handleCleanEmptySeeds = useCallback(async () => {
    let cleanedCount = 0;
    try {
      if (onCleanEmptySeeds) {
        cleanedCount = (await onCleanEmptySeeds()) || 0;
      } else {
        updateWorldviewData((data) => {
          if (Array.isArray(data.foreshadowing_seeds)) {
            const before = data.foreshadowing_seeds.length;
            data.foreshadowing_seeds = data.foreshadowing_seeds.filter((s: any) => {
              const name = (s?.name || '').trim();
              const desc = (s?.description || s?.setup_hint || '').trim();
              if (!name && !desc) return false;
              if ((name.startsWith('新伏筆') || name.startsWith('未命名')) && !desc) return false;
              return true;
            });
            cleanedCount = before - data.foreshadowing_seeds.length;
          }
          return data;
        });

        if (novel?.id && parsedWorldview) {
          const base = JSON.parse(JSON.stringify(parsedWorldview));
          if (Array.isArray(base.foreshadowing_seeds)) {
            base.foreshadowing_seeds = base.foreshadowing_seeds.filter((s: any) => {
              const name = (s?.name || '').trim();
              const desc = (s?.description || s?.setup_hint || '').trim();
              if (!name && !desc) return false;
              if ((name.startsWith('新伏筆') || name.startsWith('未命名')) && !desc) return false;
              return true;
            });
          }
          await saveWorldbuilding(novel.id, JSON.stringify(base, null, 2));
          onRefresh?.();
        }
      }

      if (cleanedCount > 0) {
        showToast(`已成功清除 ${cleanedCount} 個空白伏筆種子`, 'success');
        onLog?.(`已清除 ${cleanedCount} 個空白伏筆種子`);
      } else {
        showToast('目前無空白伏筆種子需要清理', 'info');
      }
    } catch (err: any) {
      showToast(`清理失敗: ${err.message || err}`, 'danger');
    }
  }, [onCleanEmptySeeds, updateWorldviewData, novel?.id, parsedWorldview, onRefresh, showToast, onLog]);

  // Inline edit handler for Tab 2 (Characters)
  const handleAddCharacter = useCallback(() => {
    const newName = `新角色 ${parsedCharacters.length + 1}`;
    const newChar: ParsedCharacter = {
      name: newName,
      role: '重要配角',
      faction: '',
      entry_phase: '',
      personality: [],
      want: '',
      need: '',
      want_need_conflict: '',
      fatal_flaw: '',
      secret: '',
      appearance: '',
      speech_style: '',
      arc: '',
      background: '',
    };
    const nextChars = [...parsedCharacters, newChar];
    setCharsText(JSON.stringify(nextChars, null, 2));
    setVisibleCharCount((prev) => Math.max(prev, nextChars.length));
    setEditingCharName(newName);
    setEditCharForm({ ...newChar });
    scrollAndHighlight(`char-card-${newName}`);
    showToast(`已新增角色《${newName}》`, 'success');
    onLog?.(`已新增角色《${newName}》`);
  }, [parsedCharacters, scrollAndHighlight, onLog]);

  const handleDeleteCharacter = useCallback(
    async (charName: string) => {
      const nextChars = parsedCharacters.filter((c) => c.name !== charName);
      setCharsText(JSON.stringify(nextChars, null, 2));
      if (editingCharName === charName) setEditingCharName(null);

      try {
        if (onDeleteCharacter) {
          await onDeleteCharacter(charName);
        } else if (novel?.id) {
          await saveCharacters(novel.id, nextChars);
          onRefresh?.();
        }
        showToast(`已刪除角色《${charName}》`, 'info');
        onLog?.(`已刪除角色《${charName}》`);
      } catch (err: any) {
        showToast(`刪除角色失敗: ${err.message || err}`, 'danger');
      }
    },
    [parsedCharacters, editingCharName, onDeleteCharacter, novel?.id, onRefresh, showToast, onLog]
  );

  const handleCleanEmptyChars = useCallback(async () => {
    try {
      let removed = 0;
      if (onCleanEmptyCharacters) {
        removed = (await onCleanEmptyCharacters()) || 0;
      } else {
        const before = parsedCharacters.length;
        const nextChars = parsedCharacters.filter((c) => {
          const name = (c.name || '').trim();
          if (!name || name.startsWith('未命名')) return false;
          if (name.startsWith('新角色') && !c.role && !c.want && !c.background) return false;
          return true;
        });
        removed = before - nextChars.length;
        setCharsText(JSON.stringify(nextChars, null, 2));
        if (novel?.id) {
          await saveCharacters(novel.id, nextChars);
          onRefresh?.();
        }
      }

      if (removed > 0) {
        showToast(`已清除 ${removed} 個空白角色`, 'success');
        onLog?.(`已清除 ${removed} 個空白角色`);
      } else {
        showToast('目前無空白角色需要清理', 'info');
      }
    } catch (err: any) {
      showToast(`清理失敗: ${err.message || err}`, 'danger');
    }
  }, [onCleanEmptyCharacters, parsedCharacters, novel?.id, onRefresh, showToast, onLog]);

  const handleSaveCharEdit = useCallback((oldCharName: string, updatedFields: Partial<ParsedCharacter>) => {
    const nextChars = parsedCharacters.map((c) => {
      if (c.name === oldCharName) {
        return { ...c, ...updatedFields };
      }
      return c;
    });
    setCharsText(JSON.stringify(nextChars, null, 2));
    setEditingCharName(null);
    showToast(`角色《${updatedFields.name || oldCharName}》資料已更新`, 'success');
  }, [parsedCharacters]);

  // Inline edit handler for Tab 3 (Volumes)
  const handleAddVolume = useCallback(() => {
    const nextIdx = parsedVolumes.length + 1;
    const newVol: ParsedVolume = {
      volume_index: nextIdx,
      title: `第 ${nextIdx} 卷`,
      summary: '',
      chapter_count: 50,
      factions: [],
      time_timeline: '',
      turning_points: [],
      chapters_outline: [],
    };
    const nextVols = [...parsedVolumes, newVol];
    setPlotText(JSON.stringify(nextVols, null, 2));
    setVisibleVolumeCount((prev) => Math.max(prev, nextVols.length));
    setEditingVolNum(nextIdx);
    setEditVolForm({ ...newVol });
    scrollAndHighlight(`vol-card-${nextIdx}`);
    showToast(`已新增第 ${nextIdx} 卷骨架`, 'success');
    onLog?.(`已新增第 ${nextIdx} 卷骨架`);
    if (novel?.id) {
      saveVolumes(novel.id, nextVols)
        .then(() => onRefresh?.())
        .catch((err) => console.error('新增分卷保存失敗:', err));
    }
  }, [parsedVolumes, scrollAndHighlight, onLog, novel?.id, onRefresh]);

  const handleDeleteVolume = useCallback((volNum: number) => {
    const rawVols = parsedVolumes.filter((v, i) => (v.volume_index ?? i + 1) !== volNum);
    const nextVols = reindexVolumesChapters(rawVols);
    setPlotText(JSON.stringify(nextVols, null, 2));
    if (editingVolNum === volNum) setEditingVolNum(null);
    showToast(`已刪除第 ${volNum} 卷`, 'info');
    onLog?.(`已刪除第 ${volNum} 卷`);
    if (novel?.id) {
      saveVolumes(novel.id, nextVols)
        .then(() => onRefresh?.())
        .catch((err) => console.error('刪除分卷保存失敗:', err));
    }
  }, [parsedVolumes, editingVolNum, onLog, novel?.id, onRefresh]);

  const handleCleanEmptyVolumes = useCallback(() => {
    const before = parsedVolumes.length;
    const filtered = parsedVolumes.filter((v) => {
      const title = (v.title || '').trim();
      const summary = (v.summary || '').trim();
      if (!title && !summary) return false;
      if (title.startsWith('第') && title.endsWith('卷') && !summary && (!v.chapters_outline || v.chapters_outline.length === 0)) return false;
      return true;
    });
    const removed = before - filtered.length;
    const nextVols = reindexVolumesChapters(filtered);
    setPlotText(JSON.stringify(nextVols, null, 2));
    if (removed > 0) {
      showToast(`已清除 ${removed} 個空白分卷`, 'success');
      onLog?.(`已清除 ${removed} 個空白分卷`);
      if (novel?.id) {
        saveVolumes(novel.id, nextVols)
          .then(() => onRefresh?.())
          .catch((err) => console.error('清理分卷保存失敗:', err));
      }
    } else {
      showToast('目前無空白分卷需要清理', 'info');
    }
  }, [parsedVolumes, onLog, novel?.id, onRefresh]);

  const handleSaveVolEdit = useCallback((volIndex: number, updatedFields: Partial<ParsedVolume>) => {
    const nextVols = parsedVolumes.map((v, i) => {
      const num = v.volume_index ?? i + 1;
      if (num === volIndex) {
        return { ...v, ...updatedFields };
      }
      return v;
    });
    setPlotText(JSON.stringify(nextVols, null, 2));
    setEditingVolNum(null);
    showToast(`第 ${volIndex} 卷資料已更新`, 'success');
    if (novel?.id) {
      saveVolumes(novel.id, nextVols)
        .then(() => onRefresh?.())
        .catch((err) => console.error('儲存分卷失敗:', err));
    }
  }, [parsedVolumes, novel?.id, onRefresh]);

  const handleAddChapterOutline = useCallback((volIndex: number) => {
    let nextChIndex = 1;
    const rawAdded = parsedVolumes.map((v, i) => {
      const num = v.volume_index ?? i + 1;
      if (num === volIndex) {
        const existing = Array.isArray(v.chapters_outline) ? v.chapters_outline : [];
        if (existing.length > 0) {
          const maxExisting = Math.max(
            ...existing.map((c: any, idx: number) => Number(c.chapter_index) || idx + 1)
          );
          nextChIndex = maxExisting + 1;
        } else {
          // Find max chapter_index in preceding volumes
          let precedingMax = 0;
          for (let pIdx = 0; pIdx < i; pIdx++) {
            const prevVol = parsedVolumes[pIdx];
            if (prevVol && Array.isArray(prevVol.chapters_outline)) {
              prevVol.chapters_outline.forEach((c: any, idx: number) => {
                const chNum = Number(c.chapter_index) || idx + 1;
                if (chNum > precedingMax) precedingMax = chNum;
              });
            }
          }
          nextChIndex = precedingMax > 0 ? precedingMax + 1 : 1;
        }

        const newOutline = {
          chapter_index: nextChIndex,
          chapter_title: `第 ${nextChIndex} 章`,
          chapter_summary: '',
          scene_conflict: '',
          cliffhanger: '',
          allocated_tasks: {
            turning_points: [],
            foreshadowing_plants: [],
            foreshadowing_payoffs: [],
          },
        };
        return { ...v, chapters_outline: [...existing, newOutline] };
      }
      return v;
    });

    const nextVols = reindexVolumesChapters(rawAdded);
    setPlotText(JSON.stringify(nextVols, null, 2));
    setExpandedVolChapters((prev) => (prev.includes(volIndex) ? prev : [...prev, volIndex]));
    setEditingChapterOutline({ volIndex, chIndex: nextChIndex });
    setEditChapterOutlineForm({
      chapter_index: nextChIndex,
      chapter_title: `第 ${nextChIndex} 章`,
      chapter_summary: '',
      scene_conflict: '',
      cliffhanger: '',
      allocated_tasks: {
        turning_points: [],
        foreshadowing_plants: [],
        foreshadowing_payoffs: [],
      },
    });
    showToast(`已為第 ${volIndex} 卷新增第 ${nextChIndex} 章細綱`, 'success');
    scrollAndHighlight(`vol-${volIndex}-ch-${nextChIndex}`);
    onLog?.(`已為第 ${volIndex} 卷新增第 ${nextChIndex} 章細綱`);
    if (novel?.id) {
      saveVolumes(novel.id, nextVols)
        .then(() => onRefresh?.())
        .catch((err) => console.error('新增章綱保存失敗:', err));
    }
  }, [parsedVolumes, scrollAndHighlight, onLog, novel?.id, onRefresh]);

  const handleDeleteChapterOutline = useCallback((volIndex: number, chIndex: number) => {
    const rawFiltered = parsedVolumes.map((v, i) => {
      const num = v.volume_index ?? i + 1;
      if (num === volIndex && Array.isArray(v.chapters_outline)) {
        const outlines = v.chapters_outline.filter(
          (ch: any, idx: number) => (ch.chapter_index ?? idx + 1) !== chIndex
        );
        return { ...v, chapters_outline: outlines };
      }
      return v;
    });
    const nextVols = reindexVolumesChapters(rawFiltered);
    setPlotText(JSON.stringify(nextVols, null, 2));
    if (editingChapterOutline?.volIndex === volIndex && editingChapterOutline?.chIndex === chIndex) {
      setEditingChapterOutline(null);
    }
    showToast(`已從第 ${volIndex} 卷刪除第 ${chIndex} 章細綱，後續章節已自動重排`, 'success');
    onLog?.(`已從第 ${volIndex} 卷刪除第 ${chIndex} 章細綱，後續章節已自動重排`);
    if (novel?.id) {
      saveVolumes(novel.id, nextVols)
        .then(() => onRefresh?.())
        .catch((err) => console.error('刪除章綱保存失敗:', err));
    }
  }, [parsedVolumes, editingChapterOutline, onLog, novel?.id, onRefresh]);

  const handleSaveChapterOutline = useCallback((volIndex: number, chIndex: number, form: any) => {
    const rawSaved = parsedVolumes.map((v, i) => {
      const num = v.volume_index ?? i + 1;
      if (num === volIndex && Array.isArray(v.chapters_outline)) {
        const outlines = v.chapters_outline.map((ch: any, idx: number) => {
          const curChNum = ch.chapter_index ?? idx + 1;
          if (curChNum === chIndex) {
            return { ...ch, ...form };
          }
          return ch;
        });
        return { ...v, chapters_outline: outlines };
      }
      return v;
    });
    const nextVols = reindexVolumesChapters(rawSaved);
    setPlotText(JSON.stringify(nextVols, null, 2));
    setEditingChapterOutline(null);
    showToast(`已更新第 ${volIndex} 卷第 ${chIndex} 章細綱`, 'success');
    onLog?.(`已更新第 ${volIndex} 卷第 ${chIndex} 章細綱`);
    if (novel?.id) {
      saveVolumes(novel.id, nextVols)
        .then(() => onRefresh?.())
        .catch((err) => console.error('儲存章綱失敗:', err));
    }
  }, [parsedVolumes, novel?.id, onRefresh, onLog]);

  const toggleExpandVolumeChapters = (volNum: number) => {
    setExpandedVolChapters((prev) =>
      prev.includes(volNum) ? prev.filter((n) => n !== volNum) : [...prev, volNum]
    );
  };

  // Bi-directional action trigger handler from Left Explorer Tree
  useEffect(() => {
    if (!actionTrigger) return;
    const { type, id, action, volIndex, chIndex } = actionTrigger;

    if (type === 'section') {
      if (id === 'clean-empty') {
        handleCleanEmptyWorldview();
      } else if (id) {
        scrollAndHighlight(String(id));
      }
    } else if (type === 'tp') {
      if (action === 'add') {
        handleAddTp();
      } else if (action === 'clean') {
        handleCleanEmptyTurningPoints();
      } else if (id !== undefined) {
        let tpIdx = typeof id === 'number' ? id : -1;
        if (tpIdx === -1 && typeof id === 'string' && Array.isArray(parsedWorldview?.key_turning_points)) {
          tpIdx = parsedWorldview.key_turning_points.findIndex((tp: any) => tp.id === id);
        }
        if (tpIdx >= 0) {
          if (tpIdx >= visibleTpCount) {
            setVisibleTpCount(tpIdx + 5);
          }
          if (action === 'delete') {
            handleDeleteTp(tpIdx);
          } else if (action === 'edit') {
            const tp = parsedWorldview?.key_turning_points?.[tpIdx];
            if (tp) {
              setEditingTpIndex(tpIdx);
              setEditTpForm({
                turning_point_name: tp.turning_point_name || tp.name || '',
                trigger_condition: tp.description || tp.trigger_condition || '',
                structural_impact: tp.structural_impact || tp.impact || '',
                id: tp.id || '',
              });
            }
            scrollAndHighlight(`wb-tp-item-${tpIdx}`);
          } else {
            scrollAndHighlight(`wb-tp-item-${tpIdx}`);
          }
        }
      }
    } else if (type === 'seed') {
      if (action === 'add') {
        handleAddSeed();
      } else if (action === 'clean') {
        handleCleanEmptySeeds();
      } else if (id !== undefined) {
        let sIdx = typeof id === 'number' ? id : -1;
        if (sIdx === -1 && typeof id === 'string' && Array.isArray(parsedWorldview?.foreshadowing_seeds)) {
          sIdx = parsedWorldview.foreshadowing_seeds.findIndex((s: any) => s.id === id);
        }
        if (sIdx >= 0) {
          if (sIdx >= visibleSeedCount) {
            setVisibleSeedCount(sIdx + 5);
          }
          if (action === 'delete') {
            handleDeleteSeed(sIdx);
          } else if (action === 'edit') {
            const s = parsedWorldview?.foreshadowing_seeds?.[sIdx];
            if (s) {
              setEditingSeedIndex(sIdx);
              setEditSeedForm({
                name: s.name || '',
                description: s.description || '',
                setup_hint: s.setup_hint || '',
                payoff_hint: s.payoff_hint || '',
                id: s.id || '',
              });
            }
            scrollAndHighlight(`wb-seed-item-${sIdx}`);
          } else {
            scrollAndHighlight(`wb-seed-item-${sIdx}`);
          }
        }
      }
    } else if (type === 'character') {
      if (action === 'add') {
        handleAddCharacter();
      } else if (action === 'clean') {
        handleCleanEmptyChars();
      } else if (id) {
        const charName = String(id);
        const charIdx = parsedCharacters.findIndex((c) => c.name === charName);
        if (charIdx >= 0 && charIdx >= visibleCharCount) {
          setVisibleCharCount(charIdx + 5);
        }
        if (action === 'delete') {
          handleDeleteCharacter(charName);
        } else if (action === 'edit') {
          const c = parsedCharacters.find((ch) => ch.name === charName);
          if (c) {
            setEditingCharName(charName);
            setEditCharForm({ ...c });
          }
          scrollAndHighlight(`char-card-${charName}`);
        } else {
          scrollAndHighlight(`char-card-${charName}`);
        }
      }
    } else if (type === 'volume') {
      if (action === 'add') {
        handleAddVolume();
      } else if (action === 'clean') {
        handleCleanEmptyVolumes();
      } else if (typeof id === 'number') {
        const vNum = id;
        if (action === 'delete') {
          handleDeleteVolume(vNum);
        } else if (action === 'edit') {
          const v = parsedVolumes.find((vol, i) => (vol.volume_index ?? i + 1) === vNum);
          if (v) {
            setEditingVolNum(vNum);
            setEditVolForm({ ...v });
          }
          scrollAndHighlight(`vol-card-${vNum}`);
        } else {
          scrollAndHighlight(`vol-card-${vNum}`);
        }
      }
    } else if (type === 'chapter_outline') {
      if (volIndex !== undefined) {
        const targetChIndex = chIndex ?? (typeof id === 'number' ? id : undefined);
        const targetVolIdx = parsedVolumes.findIndex((v, i) => (v.volume_index ?? i + 1) === volIndex);
        if (targetVolIdx !== -1 && targetVolIdx >= visibleVolumeCount) {
          setVisibleVolumeCount(targetVolIdx + 3);
        }
        setExpandedVolChapters((prev) => (prev.includes(volIndex) ? prev : [...prev, volIndex]));

        if (action === 'add') {
          handleAddChapterOutline(volIndex);
        } else if (typeof targetChIndex === 'number') {
          if (action === 'delete') {
            handleDeleteChapterOutline(volIndex, targetChIndex);
          } else if (action === 'edit') {
            const vol = parsedVolumes.find((v, i) => (v.volume_index ?? i + 1) === volIndex);
            const ch = vol?.chapters_outline?.find(
              (c: any, i: number) => (c.chapter_index ?? i + 1) === targetChIndex
            );
            if (ch) {
              setEditingChapterOutline({ volIndex, chIndex: targetChIndex });
              setEditChapterOutlineForm({ ...ch });
            }
            setTimeout(() => {
              scrollAndHighlight(`vol-${volIndex}-ch-${targetChIndex}`);
            }, 120);
          } else {
            setTimeout(() => {
              scrollAndHighlight(`vol-${volIndex}-ch-${targetChIndex}`);
            }, 120);
          }
        }
      }
    }
  }, [actionTrigger]);

  if (!novel) {
    return (
      <div className="worldview-empty-state">
        <span className="badge badge-neutral">[未選取作品]</span>
        <p>請先從左側選擇一部作品，以檢視或編輯世界觀設定、角色聖經與分卷骨架。</p>
      </div>
    );
  }

  return (
    <div
      className="worldview-pane-container"
      style={{ '--editor-font-size': `${fontSize}px` } as React.CSSProperties}
    >
      {/* Tab Navigation Header */}
      <div className="worldview-header">
        <div className="worldview-tabs">
          <button
            type="button"
            className={`worldview-tab-btn ${activeTab === 'worldview' ? 'active' : ''}`}
            onClick={() => handleTabChange('worldview')}
          >
            世界觀構建
          </button>
          <button
            type="button"
            className={`worldview-tab-btn ${activeTab === 'characters' ? 'active' : ''}`}
            onClick={() => handleTabChange('characters')}
          >
            角色聖經 {parsedCharacters.length > 0 && `(${parsedCharacters.length})`}
          </button>
          <button
            type="button"
            className={`worldview-tab-btn ${activeTab === 'plot' ? 'active' : ''}`}
            onClick={() => handleTabChange('plot')}
          >
            分卷骨架與大綱 {parsedVolumes.length > 0 && `(${parsedVolumes.length}卷)`}
          </button>
        </div>

        <div className="worldview-actions">
          {activeTab === 'worldview' && (
            <>
              <Button
                size="xs"
                variant="secondary"
                onClick={() => setWbViewMode(wbViewMode === 'card' ? 'raw' : 'card')}
                title="切換卡片或純文字檢視"
              >
                {wbViewMode === 'card' ? '切換純文字 / JSON' : '切換結構化卡片'}
              </Button>
              <span className="btn-divider" />
            </>
          )}

          {activeTab === 'characters' && (
            <>
              <Button
                size="xs"
                variant="secondary"
                onClick={() => setCharViewMode(charViewMode === 'card' ? 'raw' : 'card')}
                title="切換卡片清單或純文字檢視"
              >
                {charViewMode === 'card' ? '切換純文字 / JSON' : '切換卡片清單'}
              </Button>
              <span className="btn-divider" />
            </>
          )}

          {activeTab === 'plot' && (
            <>
              <Button
                size="xs"
                variant="secondary"
                onClick={() => setPlotViewMode(plotViewMode === 'card' ? 'raw' : 'card')}
                title="切換分卷骨架或純文字檢視"
              >
                {plotViewMode === 'card' ? '切換純文字 / JSON' : '切換分卷骨架'}
              </Button>
              <span className="btn-divider" />
            </>
          )}

          <Button
            size="xs"
            variant="secondary"
            onClick={onRefresh}
            title="重新整理資料"
          >
            重新整理
          </Button>
          <span className="btn-divider" />
          <Button
            size="xs"
            variant="primary"
            onClick={handleSave}
            isLoading={isSaving}
            disabled={isSaving}
            title="儲存變更至資料庫"
          >
            {saveSuccess ? '已儲存' : '儲存變更'}
          </Button>
        </div>
      </div>

      {/* Quick Summary Info Card */}
      <div className="worldview-quick-card">
        <div className="quick-card-left">
          <div className="quick-card-title-row" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span
              className="quick-card-title clickable-title"
              onClick={() => setIsEditModalOpen(true)}
              title="點擊編輯小說名稱、題材與文風"
              style={{ cursor: 'pointer' }}
            >
              {novel.title}
            </span>
            <button
              type="button"
              className="btn btn-ghost btn-xs edit-meta-btn"
              onClick={() => setIsEditModalOpen(true)}
              title="重新編輯小說名稱、題材與文風設定"
              style={{ padding: '2px 6px', fontSize: '11px', color: 'var(--text-muted)' }}
            >
              <IconEdit size={12} />
              <span>編輯設定</span>
            </button>
          </div>
          <div className="quick-card-meta-line">
            <span className="meta-label">題材：</span>
            <span className="meta-val">{novel.genre ? `【${novel.genre}】` : '未設定'}</span>
          </div>
          <div className="quick-card-meta-line">
            <span className="meta-label">文風：</span>
            <span className="meta-val">{novel.style || '未設定'}</span>
          </div>
        </div>
        <div className="quick-card-right" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {onFontSizeChange && (
            <div className="font-size-stepper" title="調整中間區塊文字大小">
              <button
                type="button"
                className="stepper-btn"
                onClick={() => onFontSizeChange(Math.max(14, fontSize - 1))}
                disabled={fontSize <= 14}
                title="縮小文字 (A-)"
              >
                A-
              </button>
              <span className="stepper-val">{fontSize}px</span>
              <button
                type="button"
                className="stepper-btn"
                onClick={() => onFontSizeChange(Math.min(24, fontSize + 1))}
                disabled={fontSize >= 24}
                title="放大文字 (A+)"
              >
                A+
              </button>
            </div>
          )}
          <button
            type="button"
            className="btn btn-secondary btn-xs copy-content-btn"
            onClick={handleCopyContent}
            title="一鍵複製本區文字"
          >
            <IconCopy size={13} />
            <span>{copiedContent ? '已複製！' : '一鍵複製'}</span>
          </button>
        </div>
      </div>

      {/* Editor & Viewer Canvas */}
      <div className="worldview-editor-wrapper">
        {/* ================= 1. Worldbuilding Tab ================= */}
        {activeTab === 'worldview' && (
          <div className="worldview-content-area">
            {wbViewMode === 'card' ? (
              <div className="worldview-cards-board">
                {/* Card 0: Pipeline Prompt / 故事簡述與大綱靈感 */}
                <div className="worldview-section-card" id="wb-card-prompt">
                  <div className="worldview-card-header">
                    <h4 className="worldview-card-title">
                      <IconBookOpen size={16} className="text-accent" />
                      故事簡述 / 大綱靈感 (Pipeline Prompt)
                    </h4>
                    <Button
                      size="xs"
                      variant="ghost"
                      className="card-edit-btn"
                      onClick={() => {
                        if (isEditingPipelinePrompt) {
                          handleSavePipelinePrompt(editPipelinePrompt);
                        } else {
                          setEditPipelinePrompt(novel?.pipeline_prompt || '');
                          setIsEditingPipelinePrompt(true);
                        }
                      }}
                    >
                      {isEditingPipelinePrompt ? (
                        <>
                          <IconCheck size={12} />
                          <span>完成</span>
                        </>
                      ) : (
                        <>
                          <IconEdit size={12} />
                          <span>編輯</span>
                        </>
                      )}
                    </Button>
                  </div>

                  {isEditingPipelinePrompt ? (
                    <div className="card-inline-edit-box">
                      <textarea
                        className="card-inline-textarea"
                        rows={6}
                        value={editPipelinePrompt}
                        onChange={(e) => setEditPipelinePrompt(e.target.value)}
                        placeholder="輸入故事核心構想、主角人設與金手指、核心衝突或開局情境...&#10;（AI 導演流水線在構建世界觀、分卷骨架與角色聖經時，將以此靈感作為最高優先級核心指引）"
                      />
                      <div className="card-inline-actions">
                        <Button
                          size="xs"
                          variant="primary"
                          onClick={() => handleSavePipelinePrompt(editPipelinePrompt)}
                          disabled={isSavingPrompt}
                        >
                          {isSavingPrompt ? '儲存中...' : '確認修改'}
                        </Button>
                        <Button size="xs" variant="ghost" onClick={() => setIsEditingPipelinePrompt(false)}>
                          取消
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="worldview-card-body">
                      <p style={{ whiteSpace: 'pre-wrap', lineHeight: '1.6', margin: 0 }}>
                        {novel?.pipeline_prompt?.trim() ||
                          '尚未填寫故事簡述或大綱靈感（建立小說時填寫的創作核心指引）。點擊右上角「編輯」即可隨時補充或修改，AI 導演管線在構建全書時將以此作為最高指導方針。'}
                      </p>
                    </div>
                  )}
                </div>

                {parsedWorldview ? (
                  <>
                    {/* Card 1: Theme & Main Conflict */}
                    <div className="worldview-section-card" id="wb-card-theme">
                    <div className="worldview-card-header">
                      <h4 className="worldview-card-title">
                        <IconBookOpen size={16} className="text-accent" />
                        故事核心主題與衝突立意
                      </h4>
                      <Button
                        size="xs"
                        variant="ghost"
                        className="card-edit-btn"
                        onClick={() => {
                          if (isEditingTheme) {
                            handleSaveThemeConflict(editTheme, editConflict);
                          } else {
                            setEditTheme(parsedWorldview.theme || '');
                            setEditConflict(parsedWorldview.main_conflict || '');
                            setIsEditingTheme(true);
                          }
                        }}
                      >
                        {isEditingTheme ? (
                          <>
                            <IconCheck size={12} />
                            <span>完成</span>
                          </>
                        ) : (
                          <>
                            <IconEdit size={12} />
                            <span>編輯</span>
                          </>
                        )}
                      </Button>
                    </div>

                    {isEditingTheme ? (
                      <div className="card-inline-edit-box">
                        <label className="card-inline-label">核心主題 (Theme):</label>
                        <input
                          type="text"
                          className="card-inline-input"
                          value={editTheme}
                          onChange={(e) => setEditTheme(e.target.value)}
                          placeholder="輸入故事核心主題..."
                        />
                        <label className="card-inline-label">核心對抗與主要矛盾 (Main Conflict):</label>
                        <textarea
                          className="card-inline-textarea"
                          rows={4}
                          value={editConflict}
                          onChange={(e) => setEditConflict(e.target.value)}
                          placeholder="輸入故事主要矛盾與對抗力量..."
                        />
                        <div className="card-inline-actions">
                          <Button
                            size="xs"
                            variant="primary"
                            onClick={() => handleSaveThemeConflict(editTheme, editConflict)}
                          >
                            確認修改
                          </Button>
                          <Button size="xs" variant="ghost" onClick={() => setIsEditingTheme(false)}>
                            取消
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <div className="worldview-sub-item">
                          <span className="worldview-sub-title">核心主題 (Theme)</span>
                          <p className="worldview-sub-desc">{parsedWorldview.theme || '尚未設定核心主題'}</p>
                        </div>
                        <div className="worldview-sub-item">
                          <span className="worldview-sub-title">核心對抗與主要矛盾 (Main Conflict)</span>
                          <p className="worldview-sub-desc">
                            {parsedWorldview.main_conflict || '尚未設定主要對抗矛盾'}
                          </p>
                        </div>
                      </>
                    )}
                  </div>

                  {/* Card 2: Worldview & Systems */}
                  <div className="worldview-section-card" id="wb-card-rules">
                    <div className="worldview-card-header">
                      <h4 className="worldview-card-title">
                        <IconSparkles size={16} className="text-accent" />
                        世界觀底層法則與力量修煉體系
                      </h4>
                      <Button
                        size="xs"
                        variant="ghost"
                        className="card-edit-btn"
                        onClick={() => {
                          if (isEditingWorldviewText) {
                            handleSaveWorldviewField(editWorldviewText);
                          } else {
                            setEditWorldviewText(parsedWorldview.worldview || '');
                            setIsEditingWorldviewText(true);
                          }
                        }}
                      >
                        {isEditingWorldviewText ? (
                          <>
                            <IconCheck size={12} />
                            <span>完成</span>
                          </>
                        ) : (
                          <>
                            <IconEdit size={12} />
                            <span>編輯</span>
                          </>
                        )}
                      </Button>
                    </div>

                    {isEditingWorldviewText ? (
                      <div className="card-inline-edit-box">
                        <textarea
                          className="card-inline-textarea"
                          rows={8}
                          value={editWorldviewText}
                          onChange={(e) => setEditWorldviewText(e.target.value)}
                          placeholder="輸入世界觀法則、力量層級與地理修煉設定..."
                        />
                        <div className="card-inline-actions">
                          <Button
                            size="xs"
                            variant="primary"
                            onClick={() => handleSaveWorldviewField(editWorldviewText)}
                          >
                            確認修改
                          </Button>
                          <Button size="xs" variant="ghost" onClick={() => setIsEditingWorldviewText(false)}>
                            取消
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div className="worldview-card-body">
                        {parsedWorldview.worldview || '尚未填寫世界觀體系設定'}
                      </div>
                    )}
                  </div>

                  {/* Card 3: Macro Outline */}
                  <div className="worldview-section-card" id="wb-card-macro">
                    <div className="worldview-card-header">
                      <h4 className="worldview-card-title">
                        <IconLayers size={16} className="text-accent" />
                        全書宏觀主線大綱
                      </h4>
                      <Button
                        size="xs"
                        variant="ghost"
                        className="card-edit-btn"
                        onClick={() => {
                          if (isEditingMacroOutline) {
                            handleSaveMacroOutline(editMacroOutline);
                          } else {
                            setEditMacroOutline(parsedWorldview.macro_outline || '');
                            setIsEditingMacroOutline(true);
                          }
                        }}
                      >
                        {isEditingMacroOutline ? (
                          <>
                            <IconCheck size={12} />
                            <span>完成</span>
                          </>
                        ) : (
                          <>
                            <IconEdit size={12} />
                            <span>編輯</span>
                          </>
                        )}
                      </Button>
                    </div>

                    {isEditingMacroOutline ? (
                      <div className="card-inline-edit-box">
                        <textarea
                          className="card-inline-textarea"
                          rows={8}
                          value={editMacroOutline}
                          onChange={(e) => setEditMacroOutline(e.target.value)}
                          placeholder="輸入全書宏觀總綱、起承轉合與主線推進..."
                        />
                        <div className="card-inline-actions">
                          <Button
                            size="xs"
                            variant="primary"
                            onClick={() => handleSaveMacroOutline(editMacroOutline)}
                          >
                            確認修改
                          </Button>
                          <Button size="xs" variant="ghost" onClick={() => setIsEditingMacroOutline(false)}>
                            取消
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div className="worldview-card-body">
                        {parsedWorldview.macro_outline || '尚未填寫全書宏觀主線大綱'}
                      </div>
                    )}
                  </div>

                  {/* Card 4: Multi-act Structure */}
                  <div className="worldview-section-card" id="wb-card-acts">
                    <div className="worldview-card-header">
                      <h4 className="worldview-card-title">
                        <IconBookOpen size={16} className="text-accent" />
                        多幕戲劇弧線架構 {Array.isArray(parsedWorldview.multi_act_structure) && `(${parsedWorldview.multi_act_structure.length} 幕)`}
                      </h4>
                      <div className="flex items-center gap-2">
                        <Button
                          size="xs"
                          variant="secondary"
                          onClick={handleAddAct}
                          title="新增戲劇幕"
                        >
                          <IconPlus size={12} />
                          <span>新增幕</span>
                        </Button>
                      </div>
                    </div>
                    {Array.isArray(parsedWorldview.multi_act_structure) && parsedWorldview.multi_act_structure.length > 0 ? (
                      <div className="worldview-grid-cards">
                        {parsedWorldview.multi_act_structure.map((act: any, aIdx: number) => {
                          const actTitle = typeof act === 'string' ? `第 ${aIdx + 1} 幕` : act.title || act.act_name || `第 ${aIdx + 1} 幕`;
                          const actContent = typeof act === 'string' ? act : act.content || act.description || '';
                          const isEditingAct = editingActIndex === aIdx;

                          return (
                            <div key={aIdx} id={`wb-act-item-${aIdx}`} className="worldview-sub-item">
                              {isEditingAct ? (
                                <div className="card-inline-edit-box" style={{ margin: 0 }}>
                                  <label className="card-inline-label">幕次名稱 / 標題:</label>
                                  <input
                                    type="text"
                                    className="card-inline-input"
                                    value={editActForm.title}
                                    onChange={(e) => setEditActForm({ ...editActForm, title: e.target.value })}
                                    placeholder={`第 ${aIdx + 1} 幕`}
                                  />
                                  <label className="card-inline-label">戲劇任務與故事弧線:</label>
                                  <textarea
                                    className="card-inline-textarea"
                                    rows={3}
                                    value={editActForm.content}
                                    onChange={(e) => setEditActForm({ ...editActForm, content: e.target.value })}
                                    placeholder="描述本幕的主要情節推進、矛盾爆發與高潮轉折..."
                                  />
                                  <div className="card-inline-actions">
                                    <Button
                                      size="xs"
                                      variant="primary"
                                      onClick={() => handleSaveAct(aIdx, editActForm)}
                                    >
                                      確認修改
                                    </Button>
                                    <Button size="xs" variant="ghost" onClick={() => setEditingActIndex(null)}>
                                      取消
                                    </Button>
                                  </div>
                                </div>
                              ) : (
                                <>
                                  <div className="sub-item-header">
                                    <span className="worldview-sub-title">{actTitle}</span>
                                    <div className="sub-item-actions">
                                      <button
                                        type="button"
                                        className="action-icon-btn"
                                        title="編輯此幕"
                                        onClick={() => {
                                          setEditingActIndex(aIdx);
                                          setEditActForm({ title: actTitle, content: actContent });
                                        }}
                                      >
                                        <IconEdit size={12} />
                                      </button>
                                      <button
                                        type="button"
                                        className="action-icon-btn danger"
                                        title="刪除此幕"
                                        onClick={() => {
                                          setDeleteConfirm({
                                            title: `刪除《${actTitle}》`,
                                            message: `確定要刪除第 ${aIdx + 1} 幕嗎？此操作將從戲劇結構中移除該幕。`,
                                            onConfirm: () => handleDeleteAct(aIdx),
                                          });
                                        }}
                                      >
                                        <IconTrash size={12} />
                                      </button>
                                    </div>
                                  </div>
                                  <p className="worldview-sub-desc">{actContent || '(尚未填寫內容)'}</p>
                                </>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="text-muted text-xs p-3">尚未建立戲劇幕結構，可點擊上方按鈕新增。</div>
                    )}
                  </div>

                  {/* Card 5: Key Turning Points with Scroll Viewport */}
                  <div className="worldview-section-card" id="wb-card-tps">
                    <div className="worldview-card-header">
                      <div className="flex items-center gap-2">
                        <h4 className="worldview-card-title">
                          <IconSparkles size={16} className="text-accent" />
                          全書核心重大轉折點 {Array.isArray(parsedWorldview.key_turning_points) && `(${parsedWorldview.key_turning_points.length})`}
                        </h4>
                        {Array.isArray(parsedWorldview.key_turning_points) && (
                          <span className="text-muted text-xs font-mono">
                            顯示 {Math.min(visibleTpCount, parsedWorldview.key_turning_points.length)} / 共{' '}
                            {parsedWorldview.key_turning_points.length} 處
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          size="xs"
                          variant="secondary"
                          onClick={handleCleanEmptyTurningPoints}
                          title="清除空白/未填寫的轉折點"
                        >
                          清除空白轉折
                        </Button>
                        <Button
                          size="xs"
                          variant="primary"
                          onClick={handleAddTp}
                          title="新增轉折點 (+)"
                        >
                          <IconPlus size={12} />
                          <span>新增轉折點</span>
                        </Button>
                      </div>
                    </div>

                    {Array.isArray(parsedWorldview.key_turning_points) && parsedWorldview.key_turning_points.length > 0 ? (
                      <div className="worldview-scroll-viewport">
                        <div className="worldview-grid-cards">
                          {parsedWorldview.key_turning_points
                            .slice(0, visibleTpCount)
                            .map((tp: any, tpIdx: number) => {
                              const isEditing = editingTpIndex === tpIdx;
                              const name = tp.turning_point_name || tp.name || `轉折點 #${tpIdx + 1}`;
                              const desc = tp.description || tp.trigger_condition || '';
                              const impact = tp.structural_impact || tp.impact || '';

                              return (
                                <div key={tp.id || tpIdx} id={`wb-tp-item-${tpIdx}`} className="worldview-sub-item">
                                  {isEditing ? (
                                    <div className="card-inline-edit-box" style={{ margin: 0 }}>
                                      <div className="form-row-2col">
                                        <div>
                                          <label className="card-inline-label">轉折點名稱:</label>
                                          <input
                                            type="text"
                                            className="card-inline-input"
                                            value={editTpForm.turning_point_name}
                                            onChange={(e) =>
                                              setEditTpForm({ ...editTpForm, turning_point_name: e.target.value })
                                            }
                                            placeholder="如: 宗門覆滅 / 身份暴露"
                                          />
                                        </div>
                                        <div>
                                          <label className="card-inline-label">編號識別 (ID):</label>
                                          <input
                                            type="text"
                                            className="card-inline-input"
                                            value={editTpForm.id || ''}
                                            onChange={(e) => setEditTpForm({ ...editTpForm, id: e.target.value })}
                                            placeholder="如: TP_01"
                                          />
                                        </div>
                                      </div>
                                      <label className="card-inline-label">觸發條件與情節描述:</label>
                                      <textarea
                                        className="card-inline-textarea"
                                        rows={3}
                                        value={editTpForm.trigger_condition}
                                        onChange={(e) =>
                                          setEditTpForm({ ...editTpForm, trigger_condition: e.target.value })
                                        }
                                        placeholder="情節如何引發、核心觸發情境..."
                                      />
                                      <label className="card-inline-label">結構性震撼與影響 (Impact):</label>
                                      <input
                                        type="text"
                                        className="card-inline-input"
                                        value={editTpForm.structural_impact}
                                        onChange={(e) =>
                                          setEditTpForm({ ...editTpForm, structural_impact: e.target.value })
                                        }
                                        placeholder="對主線、各方勢力或人物關係的衝擊..."
                                      />
                                      <div className="card-inline-actions">
                                        <Button
                                          size="xs"
                                          variant="primary"
                                          onClick={() => handleSaveTp(tpIdx, editTpForm)}
                                        >
                                          確認修改
                                        </Button>
                                        <Button size="xs" variant="ghost" onClick={() => setEditingTpIndex(null)}>
                                          取消
                                        </Button>
                                      </div>
                                    </div>
                                  ) : (
                                    <>
                                      <div className="sub-item-header">
                                        <div className="worldview-sub-title">
                                          <span>{name}</span>
                                          {tp.id && <span className="badge">#{tp.id}</span>}
                                        </div>
                                        <div className="sub-item-actions">
                                          <button
                                            type="button"
                                            className="action-icon-btn"
                                            title="編輯此轉折點"
                                            onClick={() => {
                                              setEditingTpIndex(tpIdx);
                                              setEditTpForm({
                                                turning_point_name: name,
                                                trigger_condition: desc,
                                                structural_impact: impact,
                                                id: tp.id || '',
                                              });
                                            }}
                                          >
                                            <IconEdit size={12} />
                                          </button>
                                          <button
                                            type="button"
                                            className="action-icon-btn danger"
                                            title="刪除此轉折點"
                                            onClick={() => {
                                              setDeleteConfirm({
                                                title: `刪除《${name}》`,
                                                message: `確定要刪除轉折點「${name}」嗎？`,
                                                onConfirm: () => handleDeleteTp(tpIdx),
                                              });
                                            }}
                                          >
                                            <IconTrash size={12} />
                                          </button>
                                        </div>
                                      </div>
                                      <p className="worldview-sub-desc">{desc || '(尚未填寫描述)'}</p>
                                      {impact && (
                                        <div className="worldview-sub-meta">
                                          <strong>影響: </strong>
                                          {impact}
                                        </div>
                                      )}
                                    </>
                                  )}
                                </div>
                              );
                            })}
                        </div>
                        {/* Auto-scroll Sentinel */}
                        <div ref={tpSentinelRef} className="lazy-sentinel" />
                        {visibleTpCount < parsedWorldview.key_turning_points.length && (
                          <div className="lazy-load-action-bar">
                            <Button
                              size="sm"
                              variant="secondary"
                              onClick={() =>
                                setVisibleTpCount((prev) =>
                                  Math.min(prev + 8, parsedWorldview.key_turning_points.length)
                                )
                              }
                            >
                              載入更多轉折點 (+8)
                            </Button>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="text-muted text-xs p-3">尚未設定重大轉折點，可點擊上方按鈕新增。</div>
                    )}
                  </div>

                  {/* Card 6: Foreshadowing Seeds with Scroll Viewport */}
                  <div className="worldview-section-card" id="wb-card-seeds">
                    <div className="worldview-card-header">
                      <div className="flex items-center gap-2">
                        <h4 className="worldview-card-title">
                          <IconBookOpen size={16} className="text-accent" />
                          全書深層伏筆種子庫 {Array.isArray(parsedWorldview.foreshadowing_seeds) && `(${parsedWorldview.foreshadowing_seeds.length})`}
                        </h4>
                        {Array.isArray(parsedWorldview.foreshadowing_seeds) && (
                          <span className="text-muted text-xs font-mono">
                            顯示 {Math.min(visibleSeedCount, parsedWorldview.foreshadowing_seeds.length)} / 共{' '}
                            {parsedWorldview.foreshadowing_seeds.length} 個
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          size="xs"
                          variant="secondary"
                          onClick={handleCleanEmptySeeds}
                          title="清除空白/未填寫的伏筆種子"
                        >
                          清除空白伏筆
                        </Button>
                        <Button
                          size="xs"
                          variant="primary"
                          onClick={handleAddSeed}
                          title="新增伏筆種子 (+)"
                        >
                          <IconPlus size={12} />
                          <span>新增伏筆種子</span>
                        </Button>
                      </div>
                    </div>

                    {Array.isArray(parsedWorldview.foreshadowing_seeds) && parsedWorldview.foreshadowing_seeds.length > 0 ? (
                      <div className="worldview-scroll-viewport">
                        <div className="worldview-grid-cards">
                          {parsedWorldview.foreshadowing_seeds
                            .slice(0, visibleSeedCount)
                            .map((seed: any, sIdx: number) => {
                              const isEditing = editingSeedIndex === sIdx;
                              const seedName = seed.name || `伏筆 #${sIdx + 1}`;
                              const desc = seed.description || '';
                              const setup = seed.setup_hint || '';
                              const payoff = seed.payoff_hint || '';

                              return (
                                <div key={seed.id || sIdx} id={`wb-seed-item-${sIdx}`} className="worldview-sub-item">
                                  {isEditing ? (
                                    <div className="card-inline-edit-box" style={{ margin: 0 }}>
                                      <div className="form-row-2col">
                                        <div>
                                          <label className="card-inline-label">伏筆名稱:</label>
                                          <input
                                            type="text"
                                            className="card-inline-input"
                                            value={editSeedForm.name}
                                            onChange={(e) =>
                                              setEditSeedForm({ ...editSeedForm, name: e.target.value })
                                            }
                                            placeholder="如: 斷劍中的殘魂"
                                          />
                                        </div>
                                        <div>
                                          <label className="card-inline-label">編號識別 (ID):</label>
                                          <input
                                            type="text"
                                            className="card-inline-input"
                                            value={editSeedForm.id || ''}
                                            onChange={(e) =>
                                              setEditSeedForm({ ...editSeedForm, id: e.target.value })
                                            }
                                            placeholder="如: SEED_01"
                                          />
                                        </div>
                                      </div>
                                      <label className="card-inline-label">伏筆設定與暗線說明:</label>
                                      <textarea
                                        className="card-inline-textarea"
                                        rows={3}
                                        value={editSeedForm.description}
                                        onChange={(e) =>
                                          setEditSeedForm({ ...editSeedForm, description: e.target.value })
                                        }
                                        placeholder="該伏筆的真實背景與暗線意義..."
                                      />
                                      <div className="form-row-2col">
                                        <div>
                                          <label className="card-inline-label">佈局階段 (Setup Hint):</label>
                                          <input
                                            type="text"
                                            className="card-inline-input"
                                            value={editSeedForm.setup_hint}
                                            onChange={(e) =>
                                              setEditSeedForm({ ...editSeedForm, setup_hint: e.target.value })
                                            }
                                            placeholder="如: 第 1 卷第 3 章偶然拾獲"
                                          />
                                        </div>
                                        <div>
                                          <label className="card-inline-label">回收爆點 (Payoff Hint):</label>
                                          <input
                                            type="text"
                                            className="card-inline-input"
                                            value={editSeedForm.payoff_hint}
                                            onChange={(e) =>
                                              setEditSeedForm({ ...editSeedForm, payoff_hint: e.target.value })
                                            }
                                            placeholder="如: 第 3 卷決戰時覺醒"
                                          />
                                        </div>
                                      </div>
                                      <div className="card-inline-actions">
                                        <Button
                                          size="xs"
                                          variant="primary"
                                          onClick={() => handleSaveSeed(sIdx, editSeedForm)}
                                        >
                                          確認修改
                                        </Button>
                                        <Button size="xs" variant="ghost" onClick={() => setEditingSeedIndex(null)}>
                                          取消
                                        </Button>
                                      </div>
                                    </div>
                                  ) : (
                                    <>
                                      <div className="sub-item-header">
                                        <div className="worldview-sub-title">
                                          <span>{seedName}</span>
                                          {seed.id && <span className="badge">#{seed.id}</span>}
                                        </div>
                                        <div className="sub-item-actions">
                                          <button
                                            type="button"
                                            className="action-icon-btn"
                                            title="編輯此伏筆"
                                            onClick={() => {
                                              setEditingSeedIndex(sIdx);
                                              setEditSeedForm({
                                                name: seedName,
                                                description: desc,
                                                setup_hint: setup,
                                                payoff_hint: payoff,
                                                id: seed.id || '',
                                              });
                                            }}
                                          >
                                            <IconEdit size={12} />
                                          </button>
                                          <button
                                            type="button"
                                            className="action-icon-btn danger"
                                            title="刪除此伏筆"
                                            onClick={() => {
                                              setDeleteConfirm({
                                                title: `刪除《${seedName}》`,
                                                message: `確定要刪除伏筆「${seedName}」嗎？`,
                                                onConfirm: () => handleDeleteSeed(sIdx),
                                              });
                                            }}
                                          >
                                            <IconTrash size={12} />
                                          </button>
                                        </div>
                                      </div>
                                      <p className="worldview-sub-desc">{desc || '(尚未填寫說明)'}</p>
                                      {(setup || payoff) && (
                                        <div className="worldview-sub-meta">
                                          {setup && (
                                            <div>
                                              <strong>佈局: </strong>
                                              {setup}
                                            </div>
                                          )}
                                          {payoff && (
                                            <div>
                                              <strong>回收: </strong>
                                              {payoff}
                                            </div>
                                          )}
                                        </div>
                                      )}
                                    </>
                                  )}
                                </div>
                              );
                            })}
                        </div>
                        {/* Auto-scroll Sentinel */}
                        <div ref={seedSentinelRef} className="lazy-sentinel" />
                        {visibleSeedCount < parsedWorldview.foreshadowing_seeds.length && (
                          <div className="lazy-load-action-bar">
                            <Button
                              size="sm"
                              variant="secondary"
                              onClick={() =>
                                setVisibleSeedCount((prev) =>
                                  Math.min(prev + 8, parsedWorldview.foreshadowing_seeds.length)
                                )
                              }
                            >
                              載入更多伏筆種子 (+8)
                            </Button>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="text-muted text-xs p-3">尚未設定伏筆種子，可點擊上方按鈕新增。</div>
                    )}
                  </div>
                </>
              ) : wbText.trim() ? (
                <div className="worldview-section-card">
                  <div className="worldview-card-header">
                    <h4 className="worldview-card-title">世界觀架構內容</h4>
                  </div>
                  <div className="worldview-card-body">{wbText}</div>
                </div>
              ) : (
                <div className="empty-blueprint-guide">
                  <IconBookOpen size={24} className="text-muted" />
                  <p>目前尚未生成世界觀設定。</p>
                  <span className="text-xs text-muted">
                    可在右側 AI 導演面板選擇【世界觀構建】流水線生成，或切換為純文字直接編輯輸入。
                  </span>
                </div>
              )}
            </div>
          ) : (
              <textarea
                className="worldview-textarea font-mono"
                style={{ fontSize: `${fontSize}px` }}
                value={wbText}
                onChange={(e) => setWbText(e.target.value)}
                placeholder="此處為作品世界觀設定（包含修煉體系、力量階層、核心衝突、地理疆界、社會法規等）...&#10;支援結構化 JSON 或純文字大綱。"
              />
            )}
          </div>
        )}

        {/* ================= 2. Character Bible Tab ================= */}
        {activeTab === 'characters' && (
          <div className="worldview-content-area">
            {/* Tab 2 Action Toolbar */}
            <div className="tab-action-bar">
              <div className="tab-action-bar-left">
                <IconUsers size={16} className="text-accent" />
                <span>角色聖經名冊 {parsedCharacters.length > 0 && `(${parsedCharacters.length} 位)`}</span>
              </div>
              <div className="tab-action-bar-right">
                <Button
                  size="xs"
                  variant="secondary"
                  onClick={handleCleanEmptyChars}
                  title="清除空白/未命名角色"
                >
                  清除空白角色
                </Button>
                <Button
                  size="xs"
                  variant="primary"
                  onClick={handleAddCharacter}
                  title="新增角色 (+)"
                >
                  <IconPlus size={12} />
                  <span>新增角色</span>
                </Button>
              </div>
            </div>

            {charViewMode === 'card' ? (
              parsedCharacters.length > 0 ? (
                <div className="character-cards-board">
                  <div className="character-cards-grid">
                    {parsedCharacters.slice(0, visibleCharCount).map((char, index) => {
                      const isEditing = editingCharName === char.name;
                      const personalities = Array.isArray(char.personality)
                        ? char.personality
                        : char.personality
                        ? [String(char.personality)]
                        : [];

                      return (
                        <div
                          key={char.name || index}
                          id={`char-card-${char.name}`}
                          className="character-roster-card"
                        >
                          <div className="char-card-header">
                            <div className="char-card-name-group">
                              <h4 className="char-name">{char.name}</h4>
                              {char.role && <span className="char-role-badge">[{char.role}]</span>}
                              {char.faction && (
                                <span className="char-faction-badge">
                                  {typeof (char.faction as any) === 'object' && char.faction !== null
                                    ? ((char.faction as any).name || (char.faction as any).title || JSON.stringify(char.faction))
                                    : String(char.faction)}
                                </span>
                              )}
                            </div>
                            <div className="char-card-actions">
                              {char.entry_phase && (
                                <span className="char-entry-badge">{char.entry_phase}</span>
                              )}
                              <button
                                type="button"
                                className="action-icon-btn"
                                title="編輯角色"
                                onClick={() => {
                                  if (isEditing) {
                                    handleSaveCharEdit(char.name, editCharForm);
                                  } else {
                                    setEditingCharName(char.name);
                                    setEditCharForm({ ...char });
                                  }
                                }}
                              >
                                {isEditing ? <IconCheck size={12} /> : <IconEdit size={12} />}
                              </button>
                              <button
                                type="button"
                                className="action-icon-btn danger"
                                title="刪除角色"
                                onClick={() => {
                                  setDeleteConfirm({
                                    title: `刪除角色《${char.name}》`,
                                    message: `確定要刪除角色「${char.name}」嗎？此操作將從名冊中永久移除。`,
                                    onConfirm: () => handleDeleteCharacter(char.name),
                                  });
                                }}
                              >
                                <IconTrash size={12} />
                              </button>
                            </div>
                          </div>

                          {isEditing ? (
                            <div className="card-inline-edit-box">
                              <div className="form-row-2col">
                                <div>
                                  <label className="card-inline-label">角色姓名 (Name):</label>
                                  <input
                                    type="text"
                                    className="card-inline-input"
                                    value={editCharForm.name || ''}
                                    onChange={(e) =>
                                      setEditCharForm({ ...editCharForm, name: e.target.value })
                                    }
                                    placeholder="如: 林尋 / 沈清雪"
                                  />
                                </div>
                                <div>
                                  <label className="card-inline-label">角色定位 (Role):</label>
                                  <input
                                    type="text"
                                    className="card-inline-input"
                                    value={editCharForm.role || ''}
                                    onChange={(e) =>
                                      setEditCharForm({ ...editCharForm, role: e.target.value })
                                    }
                                    placeholder="如: 主角 / 宿敵 / 導師 / 同伴"
                                  />
                                </div>
                              </div>

                              <div className="form-row-2col">
                                <div>
                                  <label className="card-inline-label">門派陣營 (Faction):</label>
                                  <input
                                    type="text"
                                    className="card-inline-input"
                                    value={editCharForm.faction || ''}
                                    onChange={(e) =>
                                      setEditCharForm({ ...editCharForm, faction: e.target.value })
                                    }
                                    placeholder="如: 青州沈氏 / 九陽宗"
                                  />
                                </div>
                                <div>
                                  <label className="card-inline-label">登場階段 (Entry Phase):</label>
                                  <input
                                    type="text"
                                    className="card-inline-input"
                                    value={editCharForm.entry_phase || ''}
                                    onChange={(e) =>
                                      setEditCharForm({ ...editCharForm, entry_phase: e.target.value })
                                    }
                                    placeholder="如: 第 1 卷第 1 章開局"
                                  />
                                </div>
                              </div>

                              <label className="card-inline-label">性格特質標籤 (頓號或逗號分隔):</label>
                              <input
                                type="text"
                                className="card-inline-input"
                                value={
                                  Array.isArray(editCharForm.personality)
                                    ? editCharForm.personality.join('、')
                                    : editCharForm.personality || ''
                                }
                                onChange={(e) =>
                                  setEditCharForm({
                                    ...editCharForm,
                                    personality: e.target.value
                                      .split(/[,，、]/)
                                      .map((s) => s.trim())
                                      .filter(Boolean),
                                  })
                                }
                                placeholder="沉著冷靜、隱忍堅毅、護短"
                              />

                              <div className="form-row-2col">
                                <div>
                                  <label className="card-inline-label">外在追求 (Want):</label>
                                  <input
                                    type="text"
                                    className="card-inline-input"
                                    value={editCharForm.want || ''}
                                    onChange={(e) =>
                                      setEditCharForm({ ...editCharForm, want: e.target.value })
                                    }
                                    placeholder="外在明確慾望與行動目標"
                                  />
                                </div>
                                <div>
                                  <label className="card-inline-label">內在渴望 (Need):</label>
                                  <input
                                    type="text"
                                    className="card-inline-input"
                                    value={editCharForm.need || ''}
                                    onChange={(e) =>
                                      setEditCharForm({ ...editCharForm, need: e.target.value })
                                    }
                                    placeholder="真正心靈欠缺與救贖"
                                  />
                                </div>
                              </div>

                              <label className="card-inline-label">衝突拉扯 (Want vs Need):</label>
                              <input
                                type="text"
                                className="card-inline-input"
                                value={editCharForm.want_need_conflict || ''}
                                onChange={(e) =>
                                  setEditCharForm({
                                    ...editCharForm,
                                    want_need_conflict: e.target.value,
                                  })
                                }
                                placeholder="外在目標與內心道德的拉扯..."
                              />

                              <div className="form-row-2col">
                                <div>
                                  <label className="card-inline-label">致命缺陷 (Fatal Flaw):</label>
                                  <input
                                    type="text"
                                    className="card-inline-input"
                                    value={editCharForm.fatal_flaw || ''}
                                    onChange={(e) =>
                                      setEditCharForm({
                                        ...editCharForm,
                                        fatal_flaw: e.target.value,
                                      })
                                    }
                                    placeholder="致命弱點或性格盲區"
                                  />
                                </div>
                                <div>
                                  <label className="card-inline-label">伏筆秘密 (Secret):</label>
                                  <input
                                    type="text"
                                    className="card-inline-input"
                                    value={editCharForm.secret || ''}
                                    onChange={(e) =>
                                      setEditCharForm({ ...editCharForm, secret: e.target.value })
                                    }
                                    placeholder="身世隱秘或深層伏筆"
                                  />
                                </div>
                              </div>

                              <div className="form-row-2col">
                                <div>
                                  <label className="card-inline-label">外貌體徵與穿著 (Appearance):</label>
                                  <input
                                    type="text"
                                    className="card-inline-input"
                                    value={editCharForm.appearance || ''}
                                    onChange={(e) =>
                                      setEditCharForm({ ...editCharForm, appearance: e.target.value })
                                    }
                                    placeholder="容貌身材、特殊標記、衣著偏好..."
                                  />
                                </div>
                                <div>
                                  <label className="card-inline-label">對話口吻風格 (Speech Style):</label>
                                  <input
                                    type="text"
                                    className="card-inline-input"
                                    value={editCharForm.speech_style || ''}
                                    onChange={(e) =>
                                      setEditCharForm({ ...editCharForm, speech_style: e.target.value })
                                    }
                                    placeholder="冷冽簡潔、溫潤文雅、口癖..."
                                  />
                                </div>
                              </div>

                              <label className="card-inline-label">人物成長弧線 (Arc):</label>
                              <textarea
                                className="card-inline-textarea"
                                rows={3}
                                value={editCharForm.arc || ''}
                                onChange={(e) =>
                                  setEditCharForm({ ...editCharForm, arc: e.target.value })
                                }
                                placeholder="全書角色性格蛻變歷程..."
                              />

                              <label className="card-inline-label">身世背景與淵源 (Background):</label>
                              <textarea
                                className="card-inline-textarea"
                                rows={3}
                                value={editCharForm.background || ''}
                                onChange={(e) =>
                                  setEditCharForm({ ...editCharForm, background: e.target.value })
                                }
                                placeholder="家族身世、過去重大變故與歷史淵源..."
                              />

                              <div className="card-inline-actions">
                                <Button
                                  size="xs"
                                  variant="primary"
                                  onClick={() => handleSaveCharEdit(char.name, editCharForm)}
                                >
                                  確認修改
                                </Button>
                                <Button
                                  size="xs"
                                  variant="ghost"
                                  onClick={() => setEditingCharName(null)}
                                >
                                  取消
                                </Button>
                              </div>
                            </div>
                          ) : (
                            <>
                              {personalities.length > 0 && (
                                <div className="char-personality-tags">
                                  {personalities.map((trait, tIdx) => (
                                    <span key={tIdx} className="char-trait-pill">
                                      {trait}
                                    </span>
                                  ))}
                                </div>
                              )}

                              <div className="char-card-body">
                                {(char.want || char.need) && (
                                  <div className="char-motivation-box">
                                    {char.want && (
                                      <div className="motivation-item">
                                        <span className="mot-label">外在追求 (Want):</span>
                                        <span className="mot-val">{char.want}</span>
                                      </div>
                                    )}
                                    {char.need && (
                                      <div className="motivation-item">
                                        <span className="mot-label">內在渴望 (Need):</span>
                                        <span className="mot-val">{char.need}</span>
                                      </div>
                                    )}
                                    {char.want_need_conflict && (
                                      <div className="motivation-conflict">
                                        <span className="conflict-tag">衝突拉扯:</span>
                                        <span>{char.want_need_conflict}</span>
                                      </div>
                                    )}
                                  </div>
                                )}

                                {(char.fatal_flaw || char.secret) && (
                                  <div className="char-flaw-box">
                                    {char.fatal_flaw && (
                                      <div className="flaw-item">
                                        <span className="flaw-label">致命缺陷:</span>
                                        <span>{char.fatal_flaw}</span>
                                      </div>
                                    )}
                                    {char.secret && (
                                      <div className="secret-item">
                                        <span className="secret-label">伏筆秘密:</span>
                                        <span>{char.secret}</span>
                                      </div>
                                    )}
                                  </div>
                                )}

                                {char.appearance && (
                                  <div className="char-flaw-box" style={{ marginTop: '6px' }}>
                                    <div className="flaw-item">
                                      <span className="flaw-label">外貌氣質:</span>
                                      <span>{char.appearance}</span>
                                    </div>
                                  </div>
                                )}

                                {(char.speech_style || char.speech_profile) && (
                                  <div className="char-voice-box">
                                    <span className="voice-title">對白風格:</span>
                                    <div className="voice-details">
                                      {char.speech_style && <span>{char.speech_style}</span>}
                                      {char.speech_profile?.default_register && (
                                        <span>語域: {char.speech_profile.default_register}</span>
                                      )}
                                      {char.speech_profile?.under_pressure && (
                                        <span>受壓語態: {char.speech_profile.under_pressure}</span>
                                      )}
                                    </div>
                                  </div>
                                )}

                                {char.arc && (
                                  <div className="char-arc-box">
                                    <span className="arc-label">人物成長弧線:</span>
                                    <p className="arc-val">{char.arc}</p>
                                  </div>
                                )}

                                {char.background && (
                                  <div className="char-arc-box" style={{ marginTop: '6px' }}>
                                    <span className="arc-label">身世背景:</span>
                                    <p className="arc-val">{char.background}</p>
                                  </div>
                                )}
                              </div>
                            </>
                          )}
                        </div>
                      );
                    })}
                  </div>

                  {/* Auto-scroll Sentinel for Characters */}
                  <div ref={charSentinelRef} className="lazy-sentinel" />

                  {visibleCharCount < parsedCharacters.length && (
                    <div className="lazy-load-action-bar">
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() =>
                          setVisibleCharCount((prev) =>
                            Math.min(prev + 8, parsedCharacters.length)
                          )
                        }
                      >
                        載入後續角色 (目前顯示 {visibleCharCount} / 共 {parsedCharacters.length} 位)
                      </Button>
                    </div>
                  )}
                </div>
              ) : (
                <div className="empty-blueprint-guide">
                  <IconUsers size={24} className="text-muted" />
                  <p>目前尚未建立角色聖經 (Character Bible)。</p>
                  <span className="text-xs text-muted mb-3">
                    可在上方點擊【新增角色】手動建立，或在右側 AI 導演面板選擇【角色聖經】階段自動生成。
                  </span>
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={handleAddCharacter}
                  >
                    <IconPlus size={14} />
                    <span>立即新增第一位角色</span>
                  </Button>
                </div>
              )
            ) : (
              <textarea
                className="worldview-textarea font-mono"
                style={{ fontSize: `${fontSize}px` }}
                value={charsText}
                onChange={(e) => setCharsText(e.target.value)}
                placeholder="此處為角色聖經（包含主角、反派、配角群性格、慾望衝突與關係網）...&#10;支援結構化 JSON 或純文字格式。"
              />
            )}
          </div>
        )}

        {/* ================= 3. Volumes & Plot Tab ================= */}
        {activeTab === 'plot' && (
          <div className="worldview-content-area">
            {plotViewMode === 'card' ? (
              parsedVolumes.length > 0 ? (
                <div className="volume-cards-board">
                  <div className="tab-action-bar">
                    <div className="tab-action-bar-left">
                      <span className="text-xs text-muted">共 {parsedVolumes.length} 篇卷骨架</span>
                    </div>
                    <div className="tab-action-bar-right">
                      <Button
                        size="xs"
                        variant="secondary"
                        onClick={handleCleanEmptyVolumes}
                        title="清除空白分卷"
                      >
                        <IconTrash size={12} />
                        <span>清除空白分卷</span>
                      </Button>
                      <Button
                        size="xs"
                        variant="primary"
                        onClick={handleAddVolume}
                        title="新增分卷"
                      >
                        <IconPlus size={12} />
                        <span>新增分卷</span>
                      </Button>
                    </div>
                  </div>

                  <div className="volume-cards-grid">
                    {parsedVolumes.slice(0, visibleVolumeCount).map((vol, vIdx) => {
                      const volNum = vol.volume_index || vIdx + 1;
                      const chCount = vol.chapter_count || 50;
                      const isEditing = editingVolNum === volNum;

                      return (
                        <div
                          key={volNum}
                          id={`vol-card-${volNum}`}
                          className="volume-skeleton-card"
                        >
                          <div className="vol-card-header">
                            <div className="vol-title-group">
                              <span className="vol-badge">第 {volNum} 卷</span>
                              <h4 className="vol-title">{vol.title || `第 ${volNum} 篇卷`}</h4>
                            </div>
                            <div className="vol-card-actions">
                              <span className="vol-chapters-range">{vol.chapters_outline?.length || vol.chapter_count || chCount} 章</span>
                              <button
                                type="button"
                                className="action-icon-btn"
                                title="編輯分卷"
                                onClick={() => {
                                  if (isEditing) {
                                    handleSaveVolEdit(volNum, editVolForm);
                                  } else {
                                    setEditingVolNum(volNum);
                                    setEditVolForm({ ...vol });
                                  }
                                }}
                              >
                                {isEditing ? <IconCheck size={12} /> : <IconEdit size={12} />}
                              </button>
                              <button
                                type="button"
                                className="action-icon-btn danger"
                                title="刪除分卷"
                                onClick={() => {
                                  setDeleteConfirm({
                                    title: `刪除分卷《第 ${volNum} 卷 ${vol.title || ''}》`,
                                    message: `確定要刪除第 ${volNum} 卷嗎？包含本卷已規劃的所有章節細綱。`,
                                    onConfirm: () => handleDeleteVolume(volNum),
                                  });
                                }}
                              >
                                <IconTrash size={12} />
                              </button>
                            </div>
                          </div>

                          {isEditing ? (
                            <div className="card-inline-edit-box">
                              <div className="form-row-2col">
                                <div>
                                  <label className="card-inline-label">分卷標題:</label>
                                  <input
                                    type="text"
                                    className="card-inline-input"
                                    value={editVolForm.title || ''}
                                    onChange={(e) =>
                                      setEditVolForm({ ...editVolForm, title: e.target.value })
                                    }
                                    placeholder="分卷名稱"
                                  />
                                </div>
                                <div>
                                  <label className="card-inline-label">預估章節數:</label>
                                  <input
                                    type="number"
                                    className="card-inline-input"
                                    value={editVolForm.chapter_count || chCount}
                                    onChange={(e) =>
                                      setEditVolForm({
                                        ...editVolForm,
                                        chapter_count: Number(e.target.value),
                                      })
                                    }
                                  />
                                </div>
                              </div>

                              <label className="card-inline-label">主線大綱梗概 (Summary):</label>
                              <textarea
                                className="card-inline-textarea"
                                rows={4}
                                value={editVolForm.summary || ''}
                                onChange={(e) =>
                                    setEditVolForm({ ...editVolForm, summary: e.target.value })
                                }
                                placeholder="本卷主線故事大綱與推進..."
                              />

                              <div className="form-row-2col">
                                <div>
                                  <label className="card-inline-label">活躍勢力門派 (頓號或逗號分隔):</label>
                                  <input
                                    type="text"
                                    className="card-inline-input"
                                    value={
                                      Array.isArray(editVolForm.factions)
                                        ? editVolForm.factions
                                            .map((f: any) =>
                                              typeof f === 'object' && f !== null
                                                ? (f.name || f.title || JSON.stringify(f))
                                                : String(f || '')
                                            )
                                            .filter(Boolean)
                                            .join('、')
                                        : editVolForm.factions || ''
                                    }
                                    onChange={(e) =>
                                      setEditVolForm({
                                        ...editVolForm,
                                        factions: e.target.value
                                          .split(/[,，、]/)
                                          .map((s) => s.trim())
                                          .filter(Boolean),
                                      })
                                    }
                                    placeholder="青州沈氏、天劍門、九陽宗"
                                  />
                                </div>
                                <div>
                                  <label className="card-inline-label">時間線 / 歷史時期 (Timeline):</label>
                                  <input
                                    type="text"
                                    className="card-inline-input"
                                    value={editVolForm.time_timeline || ''}
                                    onChange={(e) =>
                                      setEditVolForm({ ...editVolForm, time_timeline: e.target.value })
                                    }
                                    placeholder="如: 開局初期 / 大爭之世前夕"
                                  />
                                </div>
                              </div>

                              <div className="card-inline-actions">
                                <Button
                                  size="xs"
                                  variant="primary"
                                  onClick={() => handleSaveVolEdit(volNum, editVolForm)}
                                >
                                  確認修改
                                </Button>
                                <Button
                                  size="xs"
                                  variant="ghost"
                                  onClick={() => setEditingVolNum(null)}
                                >
                                  取消
                                </Button>
                              </div>
                            </div>
                          ) : (
                            <>
                              {vol.summary && (
                                <div className="vol-summary-box">
                                  <p className="vol-summary-text">{vol.summary}</p>
                                </div>
                              )}

                              {vol.factions && vol.factions.length > 0 && (
                                <div className="vol-factions-box">
                                  <span className="factions-label">核心活躍勢力:</span>
                                  <div className="faction-tags">
                                    {vol.factions.map((f: any, fIdx: number) => {
                                      const fText = typeof f === 'object' && f !== null
                                        ? `${f.name || f.title || f.faction || '勢力'}${f.alignment ? ` (${f.alignment})` : ''}`
                                        : String(f ?? '');
                                      if (!fText) return null;
                                      return (
                                        <span
                                          key={fIdx}
                                          className="faction-pill"
                                          title={typeof f === 'object' && f !== null ? f.summary : undefined}
                                        >
                                          {fText}
                                        </span>
                                      );
                                    })}
                                  </div>
                                </div>
                              )}

                              {vol.time_timeline && (
                                <div className="vol-timeline-box" style={{ marginTop: '4px' }}>
                                  <span className="text-xs text-muted">歷史時間線: {vol.time_timeline}</span>
                                </div>
                              )}

                              {vol.turning_points && vol.turning_points.length > 0 && (
                                <div className="vol-tp-box">
                                  <span className="tp-label">
                                    本卷重大轉折點 ({vol.turning_points.length}):
                                  </span>
                                  <ul className="tp-list">
                                    {vol.turning_points.map((tp: any, tpIdx: number) => {
                                      if (typeof tp === 'string') {
                                        return <li key={tpIdx}>{tp}</li>;
                                      }
                                      const tpTitle = tp && typeof tp === 'object'
                                        ? (tp.turning_point_name || tp.name || tp.title || tp.turn || `轉折 #${tpIdx + 1}`)
                                        : String(tp ?? `轉折 #${tpIdx + 1}`);
                                      const tpDesc = tp && typeof tp === 'object'
                                        ? (tp.description || tp.trigger_condition || tp.summary || '')
                                        : '';
                                      return (
                                        <li key={tpIdx}>
                                          <strong>{typeof tpTitle === 'object' ? JSON.stringify(tpTitle) : String(tpTitle)}:</strong>{' '}
                                          {typeof tpDesc === 'object' ? JSON.stringify(tpDesc) : String(tpDesc)}
                                        </li>
                                      );
                                    })}
                                  </ul>
                                </div>
                              )}

                              {/* Detailed Chapter Outlines with Foreshadowing & Turning Points allocation */}
                              <div className="vol-chapters-outline-section">
                                <div
                                  className={`vol-ch-header cursor-pointer ${expandedVolChapters.includes(volNum) ? 'open' : ''}`}
                                  onClick={() => toggleExpandVolumeChapters(volNum)}
                                  role="button"
                                  tabIndex={0}
                                >
                                  <span className="vol-ch-header-title">
                                    本卷各章細目大綱與演算法任務分配 ({Array.isArray(vol.chapters_outline) ? vol.chapters_outline.length : 0} 章)
                                  </span>
                                  <div className="vol-ch-item-actions" onClick={(e) => e.stopPropagation()}>
                                    <Button
                                      size="xs"
                                      variant="secondary"
                                      onClick={() => handleAddChapterOutline(volNum)}
                                      title="新增本卷章綱細目"
                                    >
                                      <IconPlus size={12} />
                                      <span>新增章綱</span>
                                    </Button>
                                    <span
                                      className={`tree-arrow ${expandedVolChapters.includes(volNum) ? 'open' : ''}`}
                                      onClick={() => toggleExpandVolumeChapters(volNum)}
                                      style={{ marginLeft: '6px' }}
                                    >
                                      ▾
                                    </span>
                                  </div>
                                </div>

                                <div className={`tree-accordion-collapsible ${expandedVolChapters.includes(volNum) ? 'open' : ''}`}>
                                  <div className="tree-accordion-inner">
                                    <div className="vol-ch-outline-list">
                                    {(!Array.isArray(vol.chapters_outline) || vol.chapters_outline.length === 0) ? (
                                      <div className="p-3 text-center text-xs text-muted">
                                        本卷尚未規劃章節細目大綱。點擊上方【新增章綱】開始編排。
                                      </div>
                                    ) : (
                                      vol.chapters_outline.map((ch: any, chIdx: number) => {
                                        const cIdx = ch.chapter_index ?? chIdx + 1;
                                        const title = typeof ch.chapter_title === 'string' ? ch.chapter_title : (ch.chapter_title ? String(ch.chapter_title) : `第 ${cIdx} 章`);
                                        const isChEditing =
                                          editingChapterOutline?.volIndex === volNum &&
                                          editingChapterOutline?.chIndex === cIdx;
                                        const summary = typeof ch.chapter_summary === 'string' ? ch.chapter_summary : (ch.chapter_summary ? String(ch.chapter_summary) : '');
                                        const tasks = ch.allocated_tasks || {};
                                        const tps = Array.isArray(tasks.turning_points) ? tasks.turning_points : [];
                                        const plants = Array.isArray(tasks.foreshadowing_plants) ? tasks.foreshadowing_plants : [];
                                        const payoffs = Array.isArray(tasks.foreshadowing_payoffs) ? tasks.foreshadowing_payoffs : [];
                                        const conflict = ch.scene_conflict;
                                        const cliff = ch.cliffhanger;

                                        return (
                                          <div
                                            key={cIdx}
                                            id={`vol-${volNum}-ch-${cIdx}`}
                                            className="vol-ch-outline-item"
                                          >
                                            <div className="vol-ch-item-head">
                                              <div className="vol-ch-item-title-group">
                                                <span className="vol-ch-num">第 {cIdx} 章</span>
                                                <span className="vol-ch-title">{title}</span>
                                              </div>
                                              <div className="vol-ch-item-actions">
                                                <button
                                                  type="button"
                                                  className="action-icon-btn"
                                                  title="編輯章綱"
                                                  onClick={() => {
                                                    if (isChEditing) {
                                                      handleSaveChapterOutline(volNum, cIdx, editChapterOutlineForm);
                                                    } else {
                                                      setEditingChapterOutline({ volIndex: volNum, chIndex: cIdx });
                                                      setEditChapterOutlineForm({
                                                        ...ch,
                                                        scene_conflict: typeof ch.scene_conflict === 'object' && ch.scene_conflict !== null
                                                          ? (ch.scene_conflict.description || ch.scene_conflict.content || JSON.stringify(ch.scene_conflict))
                                                          : (ch.scene_conflict || ''),
                                                        cliffhanger: typeof ch.cliffhanger === 'object' && ch.cliffhanger !== null
                                                          ? (ch.cliffhanger.hook || ch.cliffhanger.description || JSON.stringify(ch.cliffhanger))
                                                          : (ch.cliffhanger || ''),
                                                      });
                                                    }
                                                  }}
                                                >
                                                  {isChEditing ? <IconCheck size={12} /> : <IconEdit size={12} />}
                                                </button>
                                                <button
                                                  type="button"
                                                  className="action-icon-btn danger"
                                                  title="刪除章綱"
                                                  onClick={() => {
                                                    setDeleteConfirm({
                                                      title: `刪除第 ${volNum} 卷第 ${cIdx} 章大綱`,
                                                      message: `確定要刪除「第 ${cIdx} 章 ${title}」的細部大綱與任務嗎？`,
                                                      onConfirm: () => handleDeleteChapterOutline(volNum, cIdx),
                                                    });
                                                  }}
                                                >
                                                  <IconTrash size={12} />
                                                </button>
                                              </div>
                                            </div>

                                            {isChEditing ? (
                                              <div className="card-inline-edit-box" style={{ marginTop: '8px' }}>
                                                <div className="form-row-2col">
                                                  <div>
                                                    <label className="card-inline-label">章節名稱:</label>
                                                    <input
                                                      type="text"
                                                      className="card-inline-input"
                                                      value={editChapterOutlineForm.chapter_title || ''}
                                                      onChange={(e) =>
                                                        setEditChapterOutlineForm({
                                                          ...editChapterOutlineForm,
                                                          chapter_title: e.target.value,
                                                        })
                                                      }
                                                      placeholder="章節名稱"
                                                    />
                                                  </div>
                                                  <div>
                                                    <label className="card-inline-label">章節序號:</label>
                                                    <input
                                                      type="number"
                                                      className="card-inline-input"
                                                      value={editChapterOutlineForm.chapter_index ?? cIdx}
                                                      onChange={(e) =>
                                                        setEditChapterOutlineForm({
                                                          ...editChapterOutlineForm,
                                                          chapter_index: Number(e.target.value),
                                                        })
                                                      }
                                                    />
                                                  </div>
                                                </div>

                                                <label className="card-inline-label">章節梗概 (Summary):</label>
                                                <textarea
                                                  className="card-inline-textarea"
                                                  rows={3}
                                                  value={editChapterOutlineForm.chapter_summary || ''}
                                                  onChange={(e) =>
                                                    setEditChapterOutlineForm({
                                                      ...editChapterOutlineForm,
                                                      chapter_summary: e.target.value,
                                                    })
                                                  }
                                                  placeholder="本章情節概要與主要事件推展..."
                                                />

                                                <div className="form-row-2col">
                                                  <div>
                                                    <label className="card-inline-label">核心衝突 (Scene Conflict):</label>
                                                    <input
                                                      type="text"
                                                      className="card-inline-input"
                                                      value={
                                                        typeof editChapterOutlineForm.scene_conflict === 'object' && editChapterOutlineForm.scene_conflict !== null
                                                          ? (editChapterOutlineForm.scene_conflict.description || editChapterOutlineForm.scene_conflict.content || JSON.stringify(editChapterOutlineForm.scene_conflict))
                                                          : (editChapterOutlineForm.scene_conflict || '')
                                                      }
                                                      onChange={(e) =>
                                                        setEditChapterOutlineForm({
                                                          ...editChapterOutlineForm,
                                                          scene_conflict: e.target.value,
                                                        })
                                                      }
                                                      placeholder="本章核心對立或危機"
                                                    />
                                                  </div>
                                                  <div>
                                                    <label className="card-inline-label">章末鉤子 (Cliffhanger):</label>
                                                    <input
                                                      type="text"
                                                      className="card-inline-input"
                                                      value={
                                                        typeof editChapterOutlineForm.cliffhanger === 'object' && editChapterOutlineForm.cliffhanger !== null
                                                          ? (editChapterOutlineForm.cliffhanger.hook || editChapterOutlineForm.cliffhanger.description || JSON.stringify(editChapterOutlineForm.cliffhanger))
                                                          : (editChapterOutlineForm.cliffhanger || '')
                                                      }
                                                      onChange={(e) =>
                                                        setEditChapterOutlineForm({
                                                          ...editChapterOutlineForm,
                                                          cliffhanger: e.target.value,
                                                        })
                                                      }
                                                      placeholder="章末懸念、危機或反轉"
                                                    />
                                                  </div>
                                                </div>

                                                <div className="form-row-3col" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px' }}>
                                                  <TaskPicker
                                                    type="turning_points"
                                                    label="分配轉折"
                                                    selected={editChapterOutlineForm.allocated_tasks?.turning_points || []}
                                                    onChange={(items) =>
                                                      setEditChapterOutlineForm({
                                                        ...editChapterOutlineForm,
                                                        allocated_tasks: {
                                                          ...(editChapterOutlineForm.allocated_tasks || {}),
                                                          turning_points: items,
                                                        },
                                                      })
                                                    }
                                                    availableItems={parsedWorldview?.key_turning_points || []}
                                                    allVolumes={parsedVolumes}
                                                    currentVolNum={volNum}
                                                    currentChNum={cIdx}
                                                    placeholder="點擊選擇轉折..."
                                                  />
                                                  <TaskPicker
                                                    type="foreshadowing_plants"
                                                    label="伏筆佈局"
                                                    selected={editChapterOutlineForm.allocated_tasks?.foreshadowing_plants || []}
                                                    onChange={(items) =>
                                                      setEditChapterOutlineForm({
                                                        ...editChapterOutlineForm,
                                                        allocated_tasks: {
                                                          ...(editChapterOutlineForm.allocated_tasks || {}),
                                                          foreshadowing_plants: items,
                                                        },
                                                      })
                                                    }
                                                    availableItems={parsedWorldview?.foreshadowing_seeds || []}
                                                    allVolumes={parsedVolumes}
                                                    currentVolNum={volNum}
                                                    currentChNum={cIdx}
                                                    placeholder="點擊選擇佈局伏筆..."
                                                  />
                                                  <TaskPicker
                                                    type="foreshadowing_payoffs"
                                                    label="伏筆回收"
                                                    selected={editChapterOutlineForm.allocated_tasks?.foreshadowing_payoffs || []}
                                                    onChange={(items) =>
                                                      setEditChapterOutlineForm({
                                                        ...editChapterOutlineForm,
                                                        allocated_tasks: {
                                                          ...(editChapterOutlineForm.allocated_tasks || {}),
                                                          foreshadowing_payoffs: items,
                                                        },
                                                      })
                                                    }
                                                    availableItems={parsedWorldview?.foreshadowing_seeds || []}
                                                    allVolumes={parsedVolumes}
                                                    currentVolNum={volNum}
                                                    currentChNum={cIdx}
                                                    placeholder="點擊選擇回收伏筆..."
                                                  />
                                                </div>

                                                <div className="card-inline-actions">
                                                  <Button
                                                    size="xs"
                                                    variant="primary"
                                                    onClick={() => handleSaveChapterOutline(volNum, cIdx, editChapterOutlineForm)}
                                                  >
                                                    確認修改
                                                  </Button>
                                                  <Button
                                                    size="xs"
                                                    variant="ghost"
                                                    onClick={() => setEditingChapterOutline(null)}
                                                  >
                                                    取消
                                                  </Button>
                                                </div>
                                              </div>
                                            ) : (
                                              <>
                                                {summary && (
                                                  <p className="vol-ch-summary">{summary}</p>
                                                )}
                                                <div className="vol-ch-tasks">
                                                  {tps.length > 0 && (
                                                    <div className="vol-task-group tp-task">
                                                      <span className="vol-task-label">轉折點:</span>
                                                      <div className="vol-task-badges">
                                                        {tps.map((tp: any, i: number) => {
                                                          const res = resolveTaskItem(tp, 'turning_points', parsedWorldview?.key_turning_points || []);
                                                          const label = res.code ? `[${res.code}] ${res.name}` : res.name;
                                                          const tip = `${res.code ? `[${res.code}] ` : ''}${res.name}${res.desc ? `\n說明: ${res.desc}` : ''}`;
                                                          return (
                                                            <span
                                                              key={i}
                                                              className="vol-task-badge tp-badge"
                                                              title={tip}
                                                            >
                                                              ⚡ {label}
                                                            </span>
                                                          );
                                                        })}
                                                      </div>
                                                    </div>
                                                  )}
                                                  {plants.length > 0 && (
                                                    <div className="vol-task-group plant-task">
                                                      <span className="vol-task-label">伏筆佈局:</span>
                                                      <div className="vol-task-badges">
                                                        {plants.map((p: any, i: number) => {
                                                          const res = resolveTaskItem(p, 'foreshadowing_plants', parsedWorldview?.foreshadowing_seeds || []);
                                                          const label = res.code ? `[${res.code}] ${res.name}` : res.name;
                                                          const tip = `${res.code ? `[${res.code}] ` : ''}${res.name}${res.desc ? `\n說明: ${res.desc}` : ''}`;
                                                          return (
                                                            <span
                                                              key={i}
                                                              className="vol-task-badge plant-badge"
                                                              title={tip}
                                                            >
                                                              🌱 {label}
                                                            </span>
                                                          );
                                                        })}
                                                      </div>
                                                    </div>
                                                  )}
                                                  {payoffs.length > 0 && (
                                                    <div className="vol-task-group payoff-task">
                                                      <span className="vol-task-label">伏筆回收:</span>
                                                      <div className="vol-task-badges">
                                                        {payoffs.map((p: any, i: number) => {
                                                          const res = resolveTaskItem(p, 'foreshadowing_payoffs', parsedWorldview?.foreshadowing_seeds || []);
                                                          const label = res.code ? `[${res.code}] ${res.name}` : res.name;
                                                          const tip = `${res.code ? `[${res.code}] ` : ''}${res.name}${res.desc ? `\n說明: ${res.desc}` : ''}`;
                                                          return (
                                                            <span
                                                              key={i}
                                                              className="vol-task-badge payoff-badge"
                                                              title={tip}
                                                            >
                                                              🎯 {label}
                                                            </span>
                                                          );
                                                        })}
                                                      </div>
                                                    </div>
                                                  )}
                                                  {conflict && (
                                                    <div className="vol-task-group conflict-task">
                                                      <span className="vol-task-label">核心衝突:</span>
                                                      <span className="vol-ch-meta-text">
                                                        {typeof conflict === 'object' && conflict !== null
                                                          ? (conflict.description || conflict.content || conflict.summary || JSON.stringify(conflict))
                                                          : String(conflict)}
                                                      </span>
                                                    </div>
                                                  )}
                                                  {cliff && (
                                                    <div className="vol-task-group cliff-task">
                                                      <span className="vol-task-label">章末鉤子:</span>
                                                      <span className="vol-ch-meta-text">
                                                        {typeof cliff === 'object' && cliff !== null
                                                          ? (cliff.hook || cliff.description || cliff.content || JSON.stringify(cliff))
                                                          : String(cliff)}
                                                      </span>
                                                    </div>
                                                  )}
                                                </div>
                                              </>
                                            )}
                                          </div>
                                        );
                                      })
                                    )}
                                    </div>
                                  </div>
                                </div>
                              </div>
                            </>
                          )}
                        </div>
                      );
                    })}
                  </div>

                  {/* Auto-scroll Sentinel for Volumes */}
                  <div ref={volSentinelRef} className="lazy-sentinel" />

                  {visibleVolumeCount < parsedVolumes.length && (
                    <div className="lazy-load-action-bar">
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() =>
                          setVisibleVolumeCount((prev) =>
                            Math.min(prev + 4, parsedVolumes.length)
                          )
                        }
                      >
                        載入後續篇卷 (目前顯示 {visibleVolumeCount} / 共 {parsedVolumes.length} 卷)
                      </Button>
                    </div>
                  )}
                </div>
              ) : (
                <div className="empty-blueprint-guide">
                  <IconLayers size={24} className="text-muted" />
                  <p>目前尚未規劃分卷骨架大綱 (Volume Skeleton)。</p>
                  <span className="text-xs text-muted mb-3">
                    長篇百萬字小說由數十卷組成。可在右側 AI 導演面板選擇【篇卷骨架】階段生成，或切換為純文字直接編輯。
                  </span>
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={handleAddVolume}
                  >
                    <IconPlus size={14} />
                    <span>立即新增第一卷</span>
                  </Button>
                </div>
              )
            ) : (
              <textarea
                className="worldview-textarea font-mono"
                style={{ fontSize: `${fontSize}px` }}
                value={plotText}
                onChange={(e) => setPlotText(e.target.value)}
                placeholder="此處為分卷骨架與宏觀大綱（支援數十卷、上百至千章節之起承轉合、伏筆佈局與重大轉折點）...&#10;支援結構化 JSON 或純文字大綱。"
              />
            )}
          </div>
        )}
      </div>

      {/* Confirmation Modal for element deletion */}
      {deleteConfirm && (
        <ConfirmModal
          isOpen={true}
          title={deleteConfirm.title}
          message={deleteConfirm.message}
          confirmText="確認刪除"
          variant="danger"
          onConfirm={() => {
            deleteConfirm.onConfirm();
            setDeleteConfirm(null);
          }}
          onClose={() => setDeleteConfirm(null)}
        />
      )}

      {/* Edit Novel Metadata Modal */}
      <EditNovelModal
        isOpen={isEditModalOpen}
        onClose={() => setIsEditModalOpen(false)}
        novel={novel}
        pipelinePrompt={novel?.pipeline_prompt || ''}
        onSubmit={handleUpdateNovel}
      />
    </div>
  );
};