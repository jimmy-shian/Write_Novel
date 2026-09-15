import { useState, useEffect, useCallback, useRef } from 'react';
import { Novel, Chapter } from '../types';
import {
  listNovels,
  getNovel,
  createNovel,
  deleteNovel,
  resetNovelContent,
  saveChapter,
  saveWorldbuilding,
  saveCharacters,
  saveVolumes,
  getChatMemory,
  clearChatMemory,
  deleteChatMessage,
  updateNovel,
  NovelDetailResponse,
} from '../api/novels';

export function useNovel() {
  const [novels, setNovels] = useState<Novel[]>([]);
  const [activeNovelId, setActiveNovelId] = useState<string | null>(() => {
    return localStorage.getItem('writenovel_last_novel_id') || null;
  });
  const [novelDetail, setNovelDetail] = useState<NovelDetailResponse | null>(null);
  const [activeChapterIndex, setActiveChapterIndex] = useState<number>(() => {
    const savedNovel = localStorage.getItem('writenovel_last_novel_id');
    if (savedNovel) {
      const savedCh = localStorage.getItem(`writenovel_last_chapter_${savedNovel}`);
      if (savedCh) {
        const num = parseInt(savedCh, 10);
        if (num > 0) return num;
      }
    }
    return 1;
  });
  const [editorContent, setEditorContent] = useState<string>('');
  const [originalContent, setOriginalContent] = useState<string>('');
  const [isDirty, setIsDirty] = useState<boolean>(false);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load novel list on mount
  const refreshNovels = useCallback(async () => {
    try {
      setErrorMessage(null);
      const list = await listNovels();
      setNovels(list);
      if (list.length > 0) {
        const savedId = localStorage.getItem('writenovel_last_novel_id');
        const match = savedId && list.some((n) => n.id === savedId);
        const targetId = match ? (savedId as string) : list[0].id;
        if (!activeNovelId || !list.some((n) => n.id === activeNovelId)) {
          setActiveNovelId(targetId);
        }
      }
    } catch (err: any) {
      setErrorMessage(err.message || '無法取得小說清單');
    }
  }, [activeNovelId]);

  useEffect(() => {
    refreshNovels();
  }, [refreshNovels]);

  // Load novel detail when activeNovelId changes
  const refreshActiveNovel = useCallback(async () => {
    if (!activeNovelId) {
      setNovelDetail(null);
      return;
    }
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const data = await getNovel(activeNovelId);
      setNovelDetail(data);

      // Find current chapter content
      const ch = data.chapters?.find((c) => c.chapter_index === activeChapterIndex);
      const text = ch ? ch.content : '';
      setEditorContent(text);
      setOriginalContent(text);
      setIsDirty(false);
    } catch (err: any) {
      setErrorMessage(err.message || '無法取得小說詳情');
    } finally {
      setIsLoading(false);
    }
  }, [activeNovelId, activeChapterIndex]);

  const refreshChatMemory = useCallback(async () => {
    if (!activeNovelId) return;
    try {
      const res = await getChatMemory(activeNovelId);
      setNovelDetail((prev) => (prev ? { ...prev, chat_memory: res.chat_memory } : prev));
    } catch (err: any) {
      console.warn('無法重新整理對話與指令紀錄:', err);
    }
  }, [activeNovelId]);

  const handleDeleteChatMessage = useCallback(
    async (messageId: number) => {
      if (!activeNovelId) return;
      try {
        await deleteChatMessage(activeNovelId, messageId);
        setNovelDetail((prev) => {
          if (!prev || !prev.chat_memory) return prev;
          return {
            ...prev,
            chat_memory: prev.chat_memory.filter((m: any) => m.id !== messageId),
          };
        });
      } catch (err: any) {
        setErrorMessage(err.message || '刪除對話紀錄失敗');
        throw err;
      }
    },
    [activeNovelId]
  );

  const handleClearChatMemory = useCallback(
    async (messageType?: string) => {
      if (!activeNovelId) return;
      try {
        await clearChatMemory(activeNovelId, messageType);
        if (messageType && messageType !== 'all') {
          setNovelDetail((prev) => {
            if (!prev || !prev.chat_memory) return prev;
            return {
              ...prev,
              chat_memory: prev.chat_memory.filter((m: any) => {
                if (messageType === 'director') {
                  return !(m.message_type === 'director' || m.role === 'director' || (m.content && m.content.includes('【總監')));
                }
                if (messageType === 'pipeline') {
                  return !(m.message_type === 'pipeline' || (m.content && (m.content.includes('自主寫作') || m.content.includes('章節') || m.content.includes('骨架'))));
                }
                if (messageType === 'system') {
                  return !(m.role === 'system' || (m.content && m.content.includes('【系統通報】')));
                }
                return m.message_type !== messageType;
              }),
            };
          });
        } else {
          setNovelDetail((prev) => (prev ? { ...prev, chat_memory: [] } : prev));
        }
      } catch (err: any) {
        setErrorMessage(err.message || '清空對話紀錄失敗');
        throw err;
      }
    },
    [activeNovelId]
  );

  useEffect(() => {
    if (activeNovelId) {
      localStorage.setItem('writenovel_last_novel_id', activeNovelId);
      const savedCh = localStorage.getItem(`writenovel_last_chapter_${activeNovelId}`);
      if (savedCh) {
        const num = parseInt(savedCh, 10);
        if (num > 0) setActiveChapterIndex(num);
      }
    }
    refreshActiveNovel();
  }, [activeNovelId]);

  // When changing chapter index
  const selectChapter = useCallback(
    (chapterIdx: number) => {
      if (chapterIdx === activeChapterIndex) return;

      // Auto-save previous chapter if dirty
      if (isDirty && activeNovelId) {
        saveChapter(activeNovelId, activeChapterIndex, editorContent).catch(console.error);
      }

      setActiveChapterIndex(chapterIdx);
      if (activeNovelId) {
        localStorage.setItem(`writenovel_last_chapter_${activeNovelId}`, String(chapterIdx));
      }
      if (novelDetail) {
        const ch = novelDetail.chapters?.find((c) => c.chapter_index === chapterIdx);
        const text = ch ? ch.content : '';
        setEditorContent(text);
        setOriginalContent(text);
        setIsDirty(false);
      }
    },
    [activeChapterIndex, isDirty, activeNovelId, editorContent, novelDetail]
  );

  // Update editor text with dirty check
  const setContent = useCallback(
    (text: string) => {
      setEditorContent(text);
      setIsDirty(text !== originalContent);
    },
    [originalContent]
  );

  // Manual or triggered save
  const saveActiveChapter = useCallback(async () => {
    if (!activeNovelId) return;
    setIsSaving(true);
    try {
      await saveChapter(activeNovelId, activeChapterIndex, editorContent);
      setOriginalContent(editorContent);
      setIsDirty(false);
      setLastSavedAt(new Date());

      // Update chapters array in memory to avoid full re-fetch
      setNovelDetail((prev) => {
        if (!prev) return null;
        const exists = prev.chapters.some((c) => c.chapter_index === activeChapterIndex);
        const updatedChapters = exists
          ? prev.chapters.map((c) =>
              c.chapter_index === activeChapterIndex ? { ...c, content: editorContent } : c
            )
          : [
              ...prev.chapters,
              {
                novel_id: activeNovelId,
                chapter_index: activeChapterIndex,
                content: editorContent,
              },
            ];
        return {
          ...prev,
          chapters: updatedChapters,
        };
      });
    } catch (err: any) {
      setErrorMessage(err.message || '儲存章節失敗');
    } finally {
      setIsSaving(false);
    }
  }, [activeNovelId, activeChapterIndex, editorContent]);

  // Create new chapter
  const createChapter = useCallback(() => {
    if (!novelDetail) return;
    let maxIdx = (novelDetail.chapters || []).reduce(
      (max, c) => (c.chapter_index > max ? c.chapter_index : max),
      0
    );
    if (Array.isArray(novelDetail.volumes)) {
      for (const v of novelDetail.volumes) {
        if (Array.isArray(v.chapters_outline)) {
          for (const co of v.chapters_outline) {
            const num = Number(co.chapter_index);
            if (!isNaN(num) && num > maxIdx) maxIdx = num;
          }
        }
      }
    }
    const newIdx = maxIdx + 1;
    selectChapter(newIdx);
    setEditorContent('');
    setOriginalContent('');
    setIsDirty(false);
  }, [novelDetail, selectChapter]);

  // Create novel
  const handleCreateNovel = useCallback(
    async (title: string, genre: string, style: string, synopsis?: string) => {
      try {
        const res = await createNovel(title, genre, style, synopsis);
        await refreshNovels();
        setActiveNovelId(res.novel_id);
        setActiveChapterIndex(1);
        return res.novel_id;
      } catch (err: any) {
        setErrorMessage(err.message || '建立小說失敗');
        throw err;
      }
    },
    [refreshNovels]
  );

  // Delete current novel
  const handleDeleteNovel = useCallback(
    async (id: string) => {
      try {
        await deleteNovel(id);
        await refreshNovels();
        if (activeNovelId === id) {
          setActiveNovelId(null);
          setNovelDetail(null);
        }
      } catch (err: any) {
        setErrorMessage(err.message || '刪除小說失敗');
        throw err;
      }
    },
    [activeNovelId, refreshNovels]
  );

  // Reset novel generated content (selective scopes supported)
  const handleResetNovelContent = useCallback(
    async (id: string, scopes?: string[]) => {
      try {
        await resetNovelContent(id, scopes);
        await refreshActiveNovel();
        await refreshNovels();
      } catch (err: any) {
        setErrorMessage(err.message || '清空小說生成內容失敗');
        throw err;
      }
    },
    [refreshActiveNovel, refreshNovels]
  );

  // Modular auto-persisting mutations for Worldbuilding
  const saveWorldbuildingData = useCallback(
    async (updaterOrData: any) => {
      if (!activeNovelId) return;
      try {
        let currentWb: any = {};
        if (novelDetail?.worldbuilding) {
          try {
            currentWb = JSON.parse(novelDetail.worldbuilding);
          } catch {
            currentWb = {};
          }
        }
        const updated = typeof updaterOrData === 'function' ? updaterOrData(currentWb) : updaterOrData;
        const jsonStr = typeof updated === 'string' ? updated : JSON.stringify(updated, null, 2);

        // Optimistic update
        setNovelDetail((prev) => (prev ? { ...prev, worldbuilding: jsonStr } : prev));

        // Persist to backend database
        await saveWorldbuilding(activeNovelId, jsonStr);
        return updated;
      } catch (err: any) {
        setErrorMessage(err.message || '儲存世界觀失敗');
        throw err;
      }
    },
    [activeNovelId, novelDetail?.worldbuilding]
  );

  // Modular auto-persisting mutations for Characters
  const saveCharactersData = useCallback(
    async (updaterOrData: any) => {
      if (!activeNovelId) return;
      try {
        let currentChars: any = novelDetail?.characters;
        if (!currentChars && novelDetail?.characters_raw) {
          try {
            currentChars = JSON.parse(novelDetail.characters_raw);
          } catch {
            currentChars = [];
          }
        }
        const updated = typeof updaterOrData === 'function' ? updaterOrData(currentChars) : updaterOrData;
        const jsonStr = typeof updated === 'string' ? updated : JSON.stringify(updated, null, 2);
        let parsed = updated;
        if (typeof updated === 'string') {
          try {
            parsed = JSON.parse(updated);
          } catch {
            parsed = updated;
          }
        }

        // Optimistic update
        setNovelDetail((prev) =>
          prev
            ? {
                ...prev,
                characters: parsed,
                characters_raw: jsonStr,
              }
            : prev
        );

        // Persist to backend database
        await saveCharacters(activeNovelId, parsed);
        return parsed;
      } catch (err: any) {
        setErrorMessage(err.message || '儲存角色失敗');
        throw err;
      }
    },
    [activeNovelId, novelDetail?.characters, novelDetail?.characters_raw]
  );

  // Modular auto-persisting mutations for Volumes
  const saveVolumesData = useCallback(
    async (updaterOrData: any) => {
      if (!activeNovelId) return;
      try {
        const currentVols = novelDetail?.volumes || [];
        const updated = typeof updaterOrData === 'function' ? updaterOrData(currentVols) : updaterOrData;

        // Optimistic update
        setNovelDetail((prev) => (prev ? { ...prev, volumes: updated } : prev));

        // Persist to backend database
        await saveVolumes(activeNovelId, updated);
        return updated;
      } catch (err: any) {
        setErrorMessage(err.message || '儲存分卷架構失敗');
        throw err;
      }
    },
    [activeNovelId, novelDetail?.volumes]
  );

  // Modular delete operations
  const deleteTurningPoint = useCallback(
    async (tpIndex: number) => {
      return await saveWorldbuildingData((wb: any) => {
        if (Array.isArray(wb.key_turning_points)) {
          wb.key_turning_points = wb.key_turning_points.filter((_: any, i: number) => i !== tpIndex);
        }
        return wb;
      });
    },
    [saveWorldbuildingData]
  );

  const deleteForeshadowingSeed = useCallback(
    async (seedIndex: number) => {
      return await saveWorldbuildingData((wb: any) => {
        if (Array.isArray(wb.foreshadowing_seeds)) {
          wb.foreshadowing_seeds = wb.foreshadowing_seeds.filter((_: any, i: number) => i !== seedIndex);
        }
        return wb;
      });
    },
    [saveWorldbuildingData]
  );

  const deleteCharacter = useCallback(
    async (charName: string) => {
      return await saveCharactersData((chars: any) => {
        const list = Array.isArray(chars)
          ? chars
          : Array.isArray(chars?.characters)
          ? chars.characters
          : [];
        const filtered = list.filter((c: any) => c && c.name !== charName);
        return Array.isArray(chars?.characters) ? { ...chars, characters: filtered } : filtered;
      });
    },
    [saveCharactersData]
  );

  const deleteVolume = useCallback(
    async (volNum: number) => {
      return await saveVolumesData((vols: any[]) => {
        return (vols || []).filter((v: any, i: number) => (v.volume_index ?? i + 1) !== volNum);
      });
    },
    [saveVolumesData]
  );

  const deleteChapterOutline = useCallback(
    async (volIndex: number, chIndex: number) => {
      return await saveVolumesData((vols: any[]) => {
        return (vols || []).map((v: any, i: number) => {
          if ((v.volume_index ?? i + 1) === volIndex && Array.isArray(v.chapters_outline)) {
            return {
              ...v,
              chapters_outline: v.chapters_outline.filter(
                (c: any, ci: number) => (c.chapter_index ?? ci + 1) !== chIndex
              ),
            };
          }
          return v;
        });
      });
    },
    [saveVolumesData]
  );

  // Modular clean operations
  const cleanEmptyTurningPoints = useCallback(async () => {
    let removed = 0;
    await saveWorldbuildingData((wb: any) => {
      if (Array.isArray(wb.key_turning_points)) {
        const before = wb.key_turning_points.length;
        wb.key_turning_points = wb.key_turning_points.filter((tp: any) => {
          const name = (tp?.turning_point_name || tp?.name || '').trim();
          const desc = (tp?.description || tp?.trigger_condition || '').trim();
          if (!name && !desc) return false;
          if ((name.startsWith('新轉折點') || name.startsWith('未命名')) && !desc) return false;
          return true;
        });
        removed = before - wb.key_turning_points.length;
      }
      return wb;
    });
    return removed;
  }, [saveWorldbuildingData]);

  const cleanEmptySeeds = useCallback(async () => {
    let removed = 0;
    await saveWorldbuildingData((wb: any) => {
      if (Array.isArray(wb.foreshadowing_seeds)) {
        const before = wb.foreshadowing_seeds.length;
        wb.foreshadowing_seeds = wb.foreshadowing_seeds.filter((s: any) => {
          const name = (s?.name || '').trim();
          const desc = (s?.description || s?.setup_hint || '').trim();
          if (!name && !desc) return false;
          if ((name.startsWith('新伏筆種子') || name.startsWith('未命名')) && !desc) return false;
          return true;
        });
        removed = before - wb.foreshadowing_seeds.length;
      }
      return wb;
    });
    return removed;
  }, [saveWorldbuildingData]);

  const cleanEmptyCharacters = useCallback(async () => {
    let removed = 0;
    await saveCharactersData((chars: any) => {
      const list = Array.isArray(chars)
        ? chars
        : Array.isArray(chars?.characters)
        ? chars.characters
        : [];
      const before = list.length;
      const filtered = list.filter((c: any) => {
        const name = (c?.name || '').trim();
        if (!name || name.startsWith('未命名')) return false;
        if (name.startsWith('新角色') && !c.role && !c.want && !c.background) return false;
        return true;
      });
      removed = before - filtered.length;
      return Array.isArray(chars?.characters) ? { ...chars, characters: filtered } : filtered;
    });
    return removed;
  }, [saveCharactersData]);

  const handleUpdateNovel = useCallback(async (
    novelId: string,
    title: string,
    genre: string,
    style: string,
    synopsis?: string
  ) => {
    const res = await updateNovel(novelId, {
      title,
      genre,
      style,
      pipeline_prompt: synopsis,
    });
    if (res.novel) {
      setNovels((prev) =>
        prev.map((n) => (n.id === novelId ? { ...n, ...res.novel } : n))
      );
      setNovelDetail((prev) =>
        prev ? { ...prev, novel: { ...prev.novel, ...res.novel } } : prev
      );
    }
    return res;
  }, []);

  return {
    novels,
    activeNovelId,
    setActiveNovelId,
    novelDetail,
    activeChapterIndex,
    editorContent,
    originalContent,
    setContent,
    isDirty,
    isSaving,
    isLoading,
    lastSavedAt,
    errorMessage,
    selectChapter,
    saveActiveChapter,
    createChapter,
    handleCreateNovel,
    handleDeleteNovel,
    handleResetNovelContent,
    handleUpdateNovel,
    refreshActiveNovel,
    refreshChatMemory,
    refreshNovels,
    handleDeleteChatMessage,
    handleClearChatMemory,
    saveWorldbuildingData,
    saveCharactersData,
    saveVolumesData,
    deleteTurningPoint,
    deleteForeshadowingSeed,
    deleteCharacter,
    deleteVolume,
    deleteChapterOutline,
    cleanEmptyTurningPoints,
    cleanEmptySeeds,
    cleanEmptyCharacters,
  };
};
