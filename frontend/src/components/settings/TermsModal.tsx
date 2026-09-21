import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { StoryTerm } from '../../types';
import { Modal } from '../common/Modal';
import { Button } from '../common/Button';
import { Badge } from '../common/Badge';
import { listTerms, createTerm, deleteTerm, updateTerm } from '../../api/terms';
import { IconTag, IconPlus, IconTrash, IconInfo, IconEdit, IconCheck, IconX, IconSearch } from '../common/Icons';

interface TermsModalProps {
  isOpen: boolean;
  onClose: () => void;
  novelId: string | null;
}

// Canonical / high-frequency story term categories
const CANONICAL_CATEGORIES = [
  '道具',
  '地點',
  '角色',
  '功法',
  '勢力',
  '概念',
  '陣法',
  '術語',
  '設定',
  '設施',
];

// Helper: split composite categories like "道具/武器" or "功法/符籙" into individual facets
const parseCategoryFacets = (rawCat?: string): string[] => {
  if (!rawCat || !rawCat.trim()) return ['未分類'];
  const parts = rawCat
    .split(/[\/\-_、,\s]+/)
    .map((p) => p.trim())
    .filter(Boolean);
  return parts.length > 0 ? parts : ['未分類'];
};

export const TermsModal: React.FC<TermsModalProps> = ({ isOpen, onClose, novelId }) => {
  const [terms, setTerms] = useState<StoryTerm[]>([]);
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [searchKeyword, setSearchKeyword] = useState<string>('');
  const [displayLimit, setDisplayLimit] = useState<number>(60);
  const [isLoading, setIsLoading] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);

  // New term form state
  const [newTerm, setNewTerm] = useState('');
  const [newCategory, setNewCategory] = useState('道具');
  const [newDefinition, setNewDefinition] = useState('');
  const [newNotes, setNewNotes] = useState('');
  const [isCreating, setIsCreating] = useState(false);

  // Editing existing term state
  const [editingTermId, setEditingTermId] = useState<string | null>(null);
  const [editTerm, setEditTerm] = useState('');
  const [editCategory, setEditCategory] = useState('');
  const [editDefinition, setEditDefinition] = useState('');
  const [editNotes, setEditNotes] = useState('');
  const [isUpdating, setIsUpdating] = useState(false);

  const fetchTermsList = useCallback(async () => {
    if (!novelId) return;
    setIsLoading(true);
    try {
      const res = await listTerms(novelId);
      setTerms(res.terms || []);
    } catch (err) {
      console.error('載入術語庫失敗:', err);
    } finally {
      setIsLoading(false);
    }
  }, [novelId]);

  useEffect(() => {
    if (isOpen && novelId) {
      fetchTermsList();
      setCategoryFilter('all');
      setSearchKeyword('');
      setDisplayLimit(60);
      setEditingTermId(null);
      setShowAddForm(false);
    }
  }, [isOpen, novelId, fetchTermsList]);

  // Compute dynamic category tabs based on terms present in the active novel
  const { categoryTabs, specificCategoryKeys } = useMemo(() => {
    const facetCounts: Record<string, number> = {};
    terms.forEach((t) => {
      const facets = parseCategoryFacets(t.category);
      const uniqueFacets = Array.from(new Set(facets));
      uniqueFacets.forEach((f) => {
        facetCounts[f] = (facetCounts[f] || 0) + 1;
      });
    });

    const tabs: { key: string; label: string; count: number }[] = [
      { key: 'all', label: '全部', count: terms.length },
    ];
    const specificKeys: string[] = [];

    // 1. Canonical categories that exist in this novel's terms
    CANONICAL_CATEGORIES.forEach((cat) => {
      if (facetCounts[cat] && facetCounts[cat] > 0) {
        tabs.push({ key: cat, label: cat, count: facetCounts[cat] });
        specificKeys.push(cat);
      }
    });

    // 2. Extra dynamic categories with at least 2 occurrences, sorted by frequency
    const otherCats = Object.entries(facetCounts)
      .filter(([cat, count]) => !CANONICAL_CATEGORIES.includes(cat) && cat !== '未分類' && count >= 2)
      .sort((a, b) => b[1] - a[1]);

    otherCats.slice(0, 8).forEach(([cat, count]) => {
      tabs.push({ key: cat, label: cat, count });
      specificKeys.push(cat);
    });

    // 3. Count terms that fall under "其他" (do not match any of the specific tabs)
    let otherCount = 0;
    terms.forEach((t) => {
      const facets = parseCategoryFacets(t.category);
      if (!facets.some((f) => specificKeys.includes(f))) {
        otherCount++;
      }
    });

    if (otherCount > 0) {
      tabs.push({ key: '其他', label: '其他', count: otherCount });
    }

    return { categoryTabs: tabs, specificCategoryKeys: specificKeys };
  }, [terms]);

  // Filter terms by selected category and search keyword
  const filteredTerms = useMemo(() => {
    const kw = searchKeyword.trim().toLowerCase();

    return terms.filter((t) => {
      // 1. Category filter
      if (categoryFilter !== 'all') {
        const facets = parseCategoryFacets(t.category);
        if (categoryFilter === '其他') {
          if (facets.some((f) => specificCategoryKeys.includes(f))) {
            return false;
          }
        } else {
          if (!facets.includes(categoryFilter)) {
            return false;
          }
        }
      }

      // 2. Search keyword filter
      if (kw) {
        const matchName = (t.term || '').toLowerCase().includes(kw);
        const matchDef = (t.definition || '').toLowerCase().includes(kw);
        const matchNotes = (t.notes || '').toLowerCase().includes(kw);
        const matchCat = (t.category || '').toLowerCase().includes(kw);
        if (!matchName && !matchDef && !matchNotes && !matchCat) {
          return false;
        }
      }

      return true;
    });
  }, [terms, categoryFilter, searchKeyword, specificCategoryKeys]);

  // Sliced list for smooth performance
  const displayedTerms = useMemo(() => {
    return filteredTerms.slice(0, displayLimit);
  }, [filteredTerms, displayLimit]);

  const handleCreateTerm = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!novelId || !newTerm.trim() || !newDefinition.trim()) return;

    setIsCreating(true);
    try {
      await createTerm(novelId, {
        term: newTerm.trim(),
        category: newCategory.trim() || '道具',
        definition: newDefinition.trim(),
        notes: newNotes.trim() || undefined,
      });
      setNewTerm('');
      setNewDefinition('');
      setNewNotes('');
      setShowAddForm(false);
      await fetchTermsList();
    } catch (err) {
      console.error('建立術語失敗:', err);
    } finally {
      setIsCreating(false);
    }
  };

  const handleStartEdit = (item: StoryTerm) => {
    setEditingTermId(item.id);
    setEditTerm(item.term || '');
    setEditCategory(item.category || '道具');
    setEditDefinition(item.definition || '');
    setEditNotes(item.notes || '');
  };

  const handleSaveEdit = async (termId: string) => {
    if (!novelId || !editTerm.trim() || !editDefinition.trim()) return;

    setIsUpdating(true);
    try {
      await updateTerm(novelId, termId, {
        term: editTerm.trim(),
        category: editCategory.trim() || '道具',
        definition: editDefinition.trim(),
        notes: editNotes.trim() || undefined,
      });
      setEditingTermId(null);
      await fetchTermsList();
    } catch (err) {
      console.error('更新術語失敗:', err);
    } finally {
      setIsUpdating(false);
    }
  };

  const handleDeleteTerm = async (termId: string) => {
    if (!novelId) return;
    try {
      await deleteTerm(novelId, termId);
      await fetchTermsList();
    } catch (err) {
      console.error('刪除術語失敗:', err);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="故事專用術語庫 (Glossary Constraints)"
      maxWidth="lg"
      footer={
        <div className="modal-footer-actions">
          <Button variant="ghost" onClick={onClose}>
            關閉
          </Button>
        </div>
      }
    >
      <div className="terms-manager-container">
        <div className="terms-explainer-banner">
          <IconInfo size={16} className="text-accent" />
          <span>
            術語庫已自動對接後端 Prompt 約束注入引擎，創作各階段均會強制 AI 嚴格遵循定義，避免名詞漂移與設定矛盾。
          </span>
        </div>

        <div className="terms-action-bar">
          {/* Top toolbar: Search box + Stats + Add button */}
          <div className="terms-toolbar-row">
            <div className="terms-search-box">
              <IconSearch size={14} className="terms-search-icon" />
              <input
                type="text"
                className="terms-search-input"
                placeholder="搜尋術語名稱、定義或備註..."
                value={searchKeyword}
                onChange={(e) => {
                  setSearchKeyword(e.target.value);
                  setDisplayLimit(60);
                }}
              />
              {searchKeyword && (
                <button
                  type="button"
                  className="terms-search-clear"
                  onClick={() => {
                    setSearchKeyword('');
                    setDisplayLimit(60);
                  }}
                  title="清除搜尋"
                >
                  ✕
                </button>
              )}
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span className="terms-stats-badge">
                {searchKeyword || categoryFilter !== 'all'
                  ? `篩選出 ${filteredTerms.length} 筆 / 全庫 ${terms.length} 筆`
                  : `全庫共 ${terms.length} 個術語`}
              </span>
              <Button
                size="xs"
                variant={showAddForm ? 'ghost' : 'secondary'}
                onClick={() => setShowAddForm(!showAddForm)}
                icon={showAddForm ? <IconX size={12} /> : <IconPlus size={12} />}
              >
                {showAddForm ? '收合新增' : '新增術語'}
              </Button>
            </div>
          </div>

          {/* Dynamic Category Pill Tabs with term counts */}
          <div className="terms-category-pills">
            {categoryTabs.map((tab) => {
              const isActive = categoryFilter === tab.key;
              return (
                <button
                  key={tab.key}
                  type="button"
                  className={`category-pill-btn ${isActive ? 'active' : ''}`}
                  onClick={() => {
                    setCategoryFilter(tab.key);
                    setDisplayLimit(60);
                  }}
                  title={`篩選【${tab.label}】分類 (共 ${tab.count} 筆)`}
                >
                  <span>{tab.label}</span>
                  <span className="category-pill-count">{tab.count}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Add Term Inline Form */}
        {showAddForm && (
          <form className="add-term-inline-card" onSubmit={handleCreateTerm}>
            <div className="form-group">
              <label className="form-label font-bold">
                術語名稱 <span className="text-danger">*</span>
              </label>
              <input
                type="text"
                className="form-input"
                placeholder="例如: 乾坤九轉丹、星輝門閥、天火焚海訣"
                value={newTerm}
                onChange={(e) => setNewTerm(e.target.value)}
                autoFocus
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label font-bold">分類設定</label>
              <input
                type="text"
                className="form-input"
                placeholder="自訂或點選下方快捷分類（支援「/」子分類，如: 道具/武器）"
                value={newCategory}
                onChange={(e) => setNewCategory(e.target.value)}
                required
              />
              <div className="terms-quick-presets">
                {CANONICAL_CATEGORIES.map((preset) => (
                  <button
                    key={preset}
                    type="button"
                    className={`terms-quick-preset-btn ${newCategory === preset ? 'active' : ''}`}
                    onClick={() => setNewCategory(preset)}
                  >
                    {preset}
                  </button>
                ))}
              </div>
            </div>

            <div className="form-group">
              <label className="form-label font-bold">
                定義與嚴格約束規範 <span className="text-danger">*</span>
              </label>
              <textarea
                className="form-textarea"
                rows={3}
                placeholder="明確敘述該術語之具體特質、限制與使用情境（AI 流水線創作時將強制注入作為嚴格約束）..."
                value={newDefinition}
                onChange={(e) => setNewDefinition(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">備註與衍生說明 (選填)</label>
              <input
                type="text"
                className="form-input"
                placeholder="補充出現章節、特殊禁忌或關聯人物..."
                value={newNotes}
                onChange={(e) => setNewNotes(e.target.value)}
              />
            </div>

            <div className="inline-card-buttons">
              <Button size="xs" variant="primary" type="submit" isLoading={isCreating}>
                儲存術語
              </Button>
              <Button
                size="xs"
                variant="ghost"
                type="button"
                onClick={() => setShowAddForm(false)}
              >
                取消
              </Button>
            </div>
          </form>
        )}

        {/* Scrollable Terms List */}
        <div className="terms-scroll-list">
          {isLoading ? (
            <div className="terms-empty-hint">正在載入術語庫...</div>
          ) : filteredTerms.length === 0 ? (
            <div className="terms-empty-hint">
              {searchKeyword || categoryFilter !== 'all'
                ? `查無符合「${categoryFilter === 'all' ? '' : categoryFilter} ${searchKeyword}」條件的專用術語`
                : '暫無專用術語，請點擊上方「新增術語」或由 AI 導演流水線自動生成提取'}
            </div>
          ) : (
            <>
              {displayedTerms.map((item) => {
                const isEditingThis = editingTermId === item.id;

                if (isEditingThis) {
                  return (
                    <div key={item.id} className="add-term-inline-card">
                      <div className="form-group">
                        <label className="form-label font-bold">術語名稱</label>
                        <input
                          type="text"
                          className="form-input"
                          value={editTerm}
                          onChange={(e) => setEditTerm(e.target.value)}
                          required
                        />
                      </div>

                      <div className="form-group">
                        <label className="form-label font-bold">分類</label>
                        <input
                          type="text"
                          className="form-input"
                          value={editCategory}
                          onChange={(e) => setEditCategory(e.target.value)}
                          required
                        />
                        <div className="terms-quick-presets">
                          {CANONICAL_CATEGORIES.map((preset) => (
                            <button
                              key={preset}
                              type="button"
                              className={`terms-quick-preset-btn ${editCategory === preset ? 'active' : ''}`}
                              onClick={() => setEditCategory(preset)}
                            >
                              {preset}
                            </button>
                          ))}
                        </div>
                      </div>

                      <div className="form-group">
                        <label className="form-label font-bold">定義與嚴格約束規範</label>
                        <textarea
                          className="form-textarea"
                          rows={3}
                          value={editDefinition}
                          onChange={(e) => setEditDefinition(e.target.value)}
                          required
                        />
                      </div>

                      <div className="form-group">
                        <label className="form-label">備註</label>
                        <input
                          type="text"
                          className="form-input"
                          value={editNotes}
                          onChange={(e) => setEditNotes(e.target.value)}
                        />
                      </div>

                      <div className="inline-card-buttons">
                        <Button
                          size="xs"
                          variant="primary"
                          onClick={() => handleSaveEdit(item.id)}
                          isLoading={isUpdating}
                        >
                          確認更新
                        </Button>
                        <Button
                          size="xs"
                          variant="ghost"
                          onClick={() => setEditingTermId(null)}
                        >
                          取消
                        </Button>
                      </div>
                    </div>
                  );
                }

                return (
                  <div key={item.id} className="term-card">
                    <div className="term-card-header">
                      <div className="term-name-wrapper">
                        <IconTag size={13} className="text-accent" />
                        <span className="term-name">{item.term}</span>
                        {item.source_chapter ? (
                          <span className="char-entry-badge" style={{ marginLeft: 4 }}>
                            第 {item.source_chapter} 章
                          </span>
                        ) : null}
                      </div>
                      <div className="term-header-actions">
                        <Badge variant="accent">{item.category}</Badge>
                        <button
                          type="button"
                          className="btn btn-ghost btn-xs text-muted"
                          onClick={() => handleStartEdit(item)}
                          title="編輯術語"
                        >
                          <IconEdit size={12} />
                        </button>
                        <button
                          type="button"
                          className="btn btn-ghost btn-xs text-muted"
                          onClick={() => handleDeleteTerm(item.id)}
                          title="刪除術語"
                        >
                          <IconTrash size={12} />
                        </button>
                      </div>
                    </div>
                    <div className="term-definition">{item.definition}</div>
                    {item.notes && <div className="term-notes">備註：{item.notes}</div>}
                  </div>
                );
              })}

              {filteredTerms.length > displayLimit && (
                <button
                  type="button"
                  className="load-more-terms-btn"
                  onClick={() => setDisplayLimit((prev) => prev + 60)}
                >
                  載入更多術語 (已顯示 {displayLimit} / 共 {filteredTerms.length} 筆)
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </Modal>
  );
};
