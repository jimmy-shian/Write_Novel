import React from 'react';
import { Button } from '../common/Button';
import { IconCheck, IconEdit, IconPlus, IconTrash, IconUsers } from '../common/Icons';
import type { ParsedCharacter } from './WorldviewPane';

interface CharacterDeleteConfirmation {
  title: string;
  message: string;
  onConfirm: () => void | Promise<void>;
}

interface WorldviewCharactersTabProps {
  parsedCharacters: ParsedCharacter[];
  charViewMode: 'card' | 'raw';
  visibleCharCount: number;
  charSentinelRef: React.RefObject<HTMLDivElement>;
  editingCharName: string | null;
  editCharForm: Partial<ParsedCharacter>;
  charsText: string;
  fontSize: number;
  handleCleanEmptyChars: () => void | Promise<void>;
  handleAddCharacter: () => void;
  handleSaveCharEdit: (oldCharName: string, updatedFields: Partial<ParsedCharacter>) => void | Promise<void>;
  handleDeleteCharacter: (charName: string) => void | Promise<void>;
  setEditingCharName: React.Dispatch<React.SetStateAction<string | null>>;
  setEditCharForm: React.Dispatch<React.SetStateAction<Partial<ParsedCharacter>>>;
  setDeleteConfirm: (confirmation: CharacterDeleteConfirmation) => void;
  setCharsText: React.Dispatch<React.SetStateAction<string>>;
  setVisibleCharCount: React.Dispatch<React.SetStateAction<number>>;
}

export const WorldviewCharactersTab: React.FC<WorldviewCharactersTabProps> = ({
  parsedCharacters,
  charViewMode,
  visibleCharCount,
  charSentinelRef,
  editingCharName,
  editCharForm,
  charsText,
  fontSize,
  handleCleanEmptyChars,
  handleAddCharacter,
  handleSaveCharEdit,
  handleDeleteCharacter,
  setEditingCharName,
  setEditCharForm,
  setDeleteConfirm,
  setCharsText,
  setVisibleCharCount,
}) => (
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
);

