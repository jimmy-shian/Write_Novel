import React, { useState, useEffect } from 'react';
import { Modal } from '../common/Modal';
import { Button } from '../common/Button';
import { Novel } from '../../types';
import { GENRE_PRESETS, STYLE_PRESETS } from './CreateNovelModal';

interface EditNovelModalProps {
  isOpen: boolean;
  onClose: () => void;
  novel: Novel | null;
  pipelinePrompt?: string;
  onSubmit: (title: string, genre: string, style: string, synopsis?: string) => Promise<void> | void;
}

export const EditNovelModal: React.FC<EditNovelModalProps> = ({
  isOpen,
  onClose,
  novel,
  pipelinePrompt = '',
  onSubmit,
}) => {
  const [title, setTitle] = useState('');
  const [genres, setGenres] = useState<string[]>([]);
  const [genreInput, setGenreInput] = useState('');

  const [styles, setStyles] = useState<string[]>([]);
  const [styleInput, setStyleInput] = useState('');

  const [synopsis, setSynopsis] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  // Helper: parse raw string into clean tokens based on delimiters
  const extractTokens = (raw: string): string[] => {
    return raw
      .split(/[\s,，、；;]+/)
      .map((t) => t.trim())
      .filter((t) => t.length > 0);
  };

  // Synchronize initial state when modal opens or novel changes
  useEffect(() => {
    if (isOpen && novel) {
      setTitle(novel.title || '');
      const parsedGenres = novel.genre ? extractTokens(novel.genre) : ['奇幻'];
      setGenres(parsedGenres);
      setGenreInput('');

      const parsedStyles = novel.style ? extractTokens(novel.style) : ['爽文快節奏'];
      setStyles(parsedStyles);
      setStyleInput('');

      setSynopsis(pipelinePrompt || novel.pipeline_prompt || '');
      setErrorMsg('');
    }
  }, [isOpen, novel, pipelinePrompt]);

  const handleAddGenre = (val: string) => {
    const tokens = extractTokens(val);
    if (tokens.length === 0) return;
    setGenres((prev) => {
      const next = [...prev];
      tokens.forEach((t) => {
        if (!next.includes(t)) next.push(t);
      });
      return next;
    });
    setGenreInput('');
  };

  const handleRemoveGenre = (token: string) => {
    setGenres((prev) => prev.filter((g) => g !== token));
  };

  const handleToggleGenrePreset = (preset: string) => {
    setGenres((prev) =>
      prev.includes(preset) ? prev.filter((g) => g !== preset) : [...prev, preset]
    );
  };

  const handleAddStyle = (val: string) => {
    const tokens = extractTokens(val);
    if (tokens.length === 0) return;
    setStyles((prev) => {
      const next = [...prev];
      tokens.forEach((t) => {
        if (!next.includes(t)) next.push(t);
      });
      return next;
    });
    setStyleInput('');
  };

  const handleRemoveStyle = (token: string) => {
    setStyles((prev) => prev.filter((s) => s !== token));
  };

  const handleToggleStylePreset = (preset: string) => {
    setStyles((prev) =>
      prev.includes(preset) ? prev.filter((s) => s !== preset) : [...prev, preset]
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setErrorMsg('請輸入小說書名');
      return;
    }

    // Flush any pending text in inputs
    const finalGenres = [...genres];
    if (genreInput.trim()) {
      extractTokens(genreInput).forEach((t) => {
        if (!finalGenres.includes(t)) finalGenres.push(t);
      });
    }

    const finalStyles = [...styles];
    if (styleInput.trim()) {
      extractTokens(styleInput).forEach((t) => {
        if (!finalStyles.includes(t)) finalStyles.push(t);
      });
    }

    const genreString = finalGenres.length > 0 ? finalGenres.join('、') : '奇幻';
    const styleString = finalStyles.length > 0 ? finalStyles.join('、') : '爽文快節奏';

    setIsSubmitting(true);
    setErrorMsg('');
    try {
      await onSubmit(title.trim(), genreString, styleString, synopsis.trim());
      onClose();
    } catch (err: any) {
      setErrorMsg(err?.message || '更新小說設定失敗，請稍後重試');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="編輯小說基本設定"
      maxWidth="lg"
      closeOnOverlayClick={false}
      footer={
        <div className="modal-footer-actions">
          <Button variant="ghost" onClick={onClose} disabled={isSubmitting}>
            取消
          </Button>
          <Button
            variant="primary"
            onClick={handleSubmit}
            isLoading={isSubmitting}
            disabled={!title.trim() || isSubmitting}
          >
            儲存設定變更
          </Button>
        </div>
      }
    >
      <form className="create-novel-modal-form" onSubmit={handleSubmit}>
        {errorMsg && <div className="form-feedback-banner text-danger">{errorMsg}</div>}

        <div className="form-group">
          <label className="form-label font-bold">
            作品書名 <span className="text-danger">*</span>
          </label>
          <input
            type="text"
            className="form-input"
            placeholder="例如: 萬古天帝、深海餘燼、星河帝國之崛起"
            value={title}
            onChange={(e) => {
              setTitle(e.target.value);
              if (errorMsg) setErrorMsg('');
            }}
            autoFocus
            required
          />
        </div>

        <div className="form-row">
          {/* Genre Multi-Select Pill Box */}
          <div className="form-group flex-1">
            <label className="form-label">
              題材類型（支援多選、以「、」分隔）
            </label>
            <div className="tag-input-container">
              {genres.map((g) => (
                <span key={g} className="tag-pill">
                  {g}
                  <button
                    type="button"
                    className="tag-pill-remove"
                    onClick={() => handleRemoveGenre(g)}
                    title={`移除 ${g}`}
                  >
                    ✕
                  </button>
                </span>
              ))}
              <input
                type="text"
                className="tag-text-input"
                placeholder={genres.length === 0 ? "輸入自訂題材（空白或頓號分隔）..." : "+ 題材..."}
                value={genreInput}
                onChange={(e) => {
                  const val = e.target.value;
                  if (/[\s,，、；;]/.test(val)) {
                    handleAddGenre(val);
                  } else {
                    setGenreInput(val);
                  }
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === 'Tab') {
                    e.preventDefault();
                    handleAddGenre(genreInput);
                  } else if (e.key === 'Backspace' && !genreInput && genres.length > 0) {
                    handleRemoveGenre(genres[genres.length - 1]);
                  }
                }}
                onBlur={() => {
                  if (genreInput.trim()) handleAddGenre(genreInput);
                }}
              />
            </div>
            <div className="preset-tags-list">
              {GENRE_PRESETS.map((preset) => {
                const isSelected = genres.includes(preset);
                return (
                  <button
                    key={preset}
                    type="button"
                    className={`preset-tag-btn ${isSelected ? 'active' : ''}`}
                    onClick={() => handleToggleGenrePreset(preset)}
                  >
                    {isSelected ? `✓ ${preset}` : preset}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Style Multi-Select Pill Box */}
          <div className="form-group flex-1">
            <label className="form-label">
              文風基調（支援多選、以「、」分隔）
            </label>
            <div className="tag-input-container">
              {styles.map((s) => (
                <span key={s} className="tag-pill">
                  {s}
                  <button
                    type="button"
                    className="tag-pill-remove"
                    onClick={() => handleRemoveStyle(s)}
                    title={`移除 ${s}`}
                  >
                    ✕
                  </button>
                </span>
              ))}
              <input
                type="text"
                className="tag-text-input"
                placeholder={styles.length === 0 ? "輸入自訂文風（空白或頓號分隔）..." : "+ 文風..."}
                value={styleInput}
                onChange={(e) => {
                  const val = e.target.value;
                  if (/[\s,，、；;]/.test(val)) {
                    handleAddStyle(val);
                  } else {
                    setStyleInput(val);
                  }
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === 'Tab') {
                    e.preventDefault();
                    handleAddStyle(styleInput);
                  } else if (e.key === 'Backspace' && !styleInput && styles.length > 0) {
                    handleRemoveStyle(styles[styles.length - 1]);
                  }
                }}
                onBlur={() => {
                  if (styleInput.trim()) handleAddStyle(styleInput);
                }}
              />
            </div>
            <div className="preset-tags-list">
              {STYLE_PRESETS.map((preset) => {
                const isSelected = styles.includes(preset);
                return (
                  <button
                    key={preset}
                    type="button"
                    className={`preset-tag-btn ${isSelected ? 'active' : ''}`}
                    onClick={() => handleToggleStylePreset(preset)}
                  >
                    {isSelected ? `✓ ${preset}` : preset}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">
            故事簡述 / 大綱靈感 (Pipeline Prompt)
          </label>
          <textarea
            className="form-textarea novel-synopsis-textarea"
            rows={5}
            placeholder="輸入故事核心構想、主角人設與金手指、核心衝突或開局情境...&#10;（AI 導演流水線在構建世界觀、分卷骨架與角色聖經時，將以此靈感作為核心指引）"
            value={synopsis}
            onChange={(e) => setSynopsis(e.target.value)}
          />
          <div className="form-hint">
            提示：可留空或由 AI 導演自由發揮，亦可輸入詳細背景以精確錨定世界觀。
          </div>
        </div>
      </form>
    </Modal>
  );
};
