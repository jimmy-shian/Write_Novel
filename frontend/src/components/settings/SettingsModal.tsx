import React, { useState, useEffect } from 'react';
import { Modal } from '../common/Modal';
import { Button } from '../common/Button';
import { ModelChip } from '../common/ModelChip';
import {
  getSettings,
  saveSettings,
  fetchAvailableModels,
  testLlmConnection,
  getCloudSyncStatus,
  saveCloudSyncConfig,
  triggerCloudBackup,
  CloudSyncStatus,
} from '../../api/settings';
import { APP_VERSION, APP_NAME } from '../../config/version';
import { parseCloudEndpoint } from '../../platform';
import { savePreferences } from '../../services/preferences';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  theme: 'light' | 'neutral' | 'dark';
  onThemeChange: (theme: 'light' | 'neutral' | 'dark') => void;
  editorFontSize?: number;
  onFontSizeChange?: (size: number) => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  theme,
  onThemeChange,
  editorFontSize,
  onFontSizeChange,
}) => {
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [directorModel, setDirectorModel] = useState('');
  const [writerModel, setWriterModel] = useState('');
  const [separateModels, setSeparateModels] = useState(false);
  const [activeModelTarget, setActiveModelTarget] = useState<'director' | 'writer'>('director');
  const [temperature, setTemperature] = useState(0.7);
  const [enableThinking, setEnableThinking] = useState(1);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isFetchingModels, setIsFetchingModels] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  // Middle Editor Font Size Setting (14px ~ 24px)
  const [internalFontSize, setInternalFontSize] = useState<number>(() => {
    const saved = localStorage.getItem('editor_font_size');
    return saved ? parseInt(saved, 10) || 16 : 16;
  });

  const fontSize = editorFontSize !== undefined ? editorFontSize : internalFontSize;

  const handleFontSizeChange = (size: number) => {
    setInternalFontSize(size);
    document.documentElement.style.setProperty('--editor-font-size', `${size}px`);
    localStorage.setItem('editor_font_size', String(size));
    onFontSizeChange?.(size);
  };

  // Cloud Sync & Server Database Path
  const [syncStatus, setSyncStatus] = useState<CloudSyncStatus | null>(null);
  const [serverDbPath, setServerDbPath] = useState<string>('');
  const [syncLoading, setSyncLoading] = useState<boolean>(true);
  const [cloudBucket, setCloudBucket] = useState('');
  const [cloudToken, setCloudToken] = useState('');
  const [enableCloudSync, setEnableCloudSync] = useState(false);
  const [isBackingUp, setIsBackingUp] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [isTestingLlm, setIsTestingLlm] = useState(false);
  const [backupMessage, setBackupMessage] = useState<string | null>(null);

  const isWebDeploy = typeof window !== 'undefined' && (
    window.location.protocol === 'https:' ||
    window.location.hostname.includes('huggingface') ||
    window.location.hostname.includes('hf.space') ||
    window.location.hostname.includes('github.io') ||
    window.location.hostname.includes('pages.dev')
  );

  // 本地端 (localhost / 127.0.0.1) 預設不自動勾選雲端備份
  const isLocalRun = typeof window !== 'undefined' && (
    window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1' ||
    window.location.hostname === '[::1]'
  );

  useEffect(() => {
    if (!isOpen) return;
    setIsLoading(true);
    setStatusMessage(null);

    // 1. 優先從 localStorage 載入持久化設定 (保證跨重新整理、雲端部署絕不丟失使用者輸入)
    const savedHost = localStorage.getItem('NOVEL_FACTORY_API_HOST') || '';
    const savedBucket = localStorage.getItem('NOVEL_FACTORY_CLOUD_BUCKET') || '';
    const savedToken = localStorage.getItem('NOVEL_FACTORY_API_TOKEN') || '';

    const savedBaseUrl = localStorage.getItem('NOVEL_FACTORY_LLM_BASE_URL');
    const savedApiKey = localStorage.getItem('NOVEL_FACTORY_API_KEY');
    const savedDirectorModel = localStorage.getItem('NOVEL_FACTORY_DIRECTOR_MODEL');
    const savedWriterModel = localStorage.getItem('NOVEL_FACTORY_WRITER_MODEL');
    const savedSeparateModels = localStorage.getItem('NOVEL_FACTORY_SEPARATE_MODELS');
    const savedTemperature = localStorage.getItem('NOVEL_FACTORY_TEMPERATURE');
    const savedEnableThinking = localStorage.getItem('NOVEL_FACTORY_ENABLE_THINKING');

    if (savedBaseUrl !== null) setBaseUrl(savedBaseUrl);
    if (savedApiKey !== null) setApiKey(savedApiKey);
    if (savedDirectorModel !== null) setDirectorModel(savedDirectorModel);
    if (savedWriterModel !== null) setWriterModel(savedWriterModel);
    if (savedSeparateModels !== null) setSeparateModels(savedSeparateModels === 'true');
    if (savedTemperature !== null) setTemperature(parseFloat(savedTemperature));
    if (savedEnableThinking !== null) setEnableThinking(parseInt(savedEnableThinking, 10));

    if (savedBucket) setCloudBucket(savedBucket);
    if (savedToken) setCloudToken(savedToken);

    // 2. 從後端獲取目前運行的 DB 設定 (僅在 localStorage 無該項紀錄時作為預設填充)
    getSettings()
      .then((data) => {
        const agents = data?.agents || data;
        const globalAgent = agents?.global;
        const architectAgent = agents?.architect || agents?.copilot;
        const writerAgent = agents?.writer;

        const baseEndpoint = globalAgent?.base_url || architectAgent?.base_url || writerAgent?.base_url || '';
        const baseKey = globalAgent?.api_key || architectAgent?.api_key || writerAgent?.api_key || '';
        const dModel = architectAgent?.model || globalAgent?.model || '';
        const wModel = writerAgent?.model || dModel;

        if (savedBaseUrl === null && baseEndpoint) setBaseUrl(baseEndpoint);
        if (savedApiKey === null && baseKey) setApiKey(baseKey);
        if (savedDirectorModel === null && dModel) setDirectorModel(dModel);
        if (savedWriterModel === null && wModel) setWriterModel(wModel);
        if (savedSeparateModels === null && (wModel && dModel && wModel !== dModel)) {
          setSeparateModels(true);
        }

        const temp = architectAgent?.temperature ?? globalAgent?.temperature ?? writerAgent?.temperature ?? 0.7;
        const thinking = architectAgent?.enable_thinking ?? globalAgent?.enable_thinking ?? writerAgent?.enable_thinking ?? 1;
        if (data?._dbPath) {
          setServerDbPath(data._dbPath);
        }

        if (savedTemperature === null) setTemperature(temp);
        if (savedEnableThinking === null) setEnableThinking(thinking);
      })
      .catch((err) => {
        console.warn('載入後端設定失敗 (使用本機已儲存之偏好):', err);
      })
      .finally(() => setIsLoading(false));

    // 3. Load Cloud Sync Status
    setSyncLoading(true);
    getCloudSyncStatus()
      .then((s) => {
        setSyncStatus(s);
        if (s?.db_path) {
          setServerDbPath(s.db_path);
        }
        if (!savedBucket && (s.storage_bucket || s.dataset_repo)) {
          setCloudBucket(s.storage_bucket || s.dataset_repo);
        }
        if (!savedToken && s.token) {
          setCloudToken(s.token);
        }
        setEnableCloudSync(Boolean(isWebDeploy || (!isLocalRun && (s.storage_bucket || s.dataset_repo || s.has_token))));
      })
      .catch(() => {})
      .finally(() => {
        setSyncLoading(false);
      });
  }, [isOpen]);

  const handleFetchModels = async () => {
    if (!baseUrl) {
      setStatusMessage('請先填寫 API Base URL');
      return;
    }
    setIsFetchingModels(true);
    setStatusMessage(null);
    try {
      const res = await fetchAvailableModels(baseUrl, apiKey);
      setAvailableModels(res.models || []);
      if (res.models && res.models.length > 0) {
        if (!directorModel) setDirectorModel(res.models[0]);
        if (!writerModel) setWriterModel(res.models[0]);
      }
      setStatusMessage(`成功獲取 ${res.models?.length || 0} 個可用模型`);
    } catch (err: any) {
      setStatusMessage(`獲取模型列表失敗: ${err.message}`);
    } finally {
      setIsFetchingModels(false);
    }
  };

  const handleTestLlm = async () => {
    if (!baseUrl || !baseUrl.trim()) {
      setStatusMessage('請先填寫 API Base URL');
      return;
    }
    setIsTestingLlm(true);
    setStatusMessage(null);
    try {
      const targetModel = directorModel.trim() || writerModel.trim() || 'gemini-web/pro';
      const res = await testLlmConnection(baseUrl.trim(), apiKey.trim(), targetModel);
      setStatusMessage(res.message);
    } catch (err: any) {
      setStatusMessage(`LLM 連線測試發生異常: ${err.message || err}`);
    } finally {
      setIsTestingLlm(false);
    }
  };

  const handleTestConnection = async () => {
    setIsTesting(true);
    setStatusMessage(null);
    try {
      const trimmedBucket = cloudBucket.trim();
      const trimmedToken = cloudToken.trim();
      const { host: targetHost, bucket: targetBucket } = parseCloudEndpoint(trimmedBucket);

      if (targetHost) {
        localStorage.setItem('NOVEL_FACTORY_API_HOST', targetHost);
      }
      if (targetBucket) {
        localStorage.setItem('NOVEL_FACTORY_CLOUD_BUCKET', targetBucket);
      }
      if (trimmedToken) {
        localStorage.setItem('NOVEL_FACTORY_API_TOKEN', trimmedToken);
      }

      const s = await getCloudSyncStatus();
      setSyncStatus(s);

      setStatusMessage('✅ 雲端伺服器連線成功！正在重新整理頁面以載入作品與設定...');
      setTimeout(() => {
        window.location.reload();
      }, 1000);
    } catch (err: any) {
      setStatusMessage(`連線測試失敗: ${err.message || err}`);
    } finally {
      setIsTesting(false);
    }
  };

  const handleTriggerBackup = async () => {
    setIsBackingUp(true);
    setBackupMessage(null);
    try {
      const res = await triggerCloudBackup(true);
      setBackupMessage(res.message || '雲端備份已啟動 (零 Git 歷史覆蓋)');
      setTimeout(async () => {
        try {
          const s = await getCloudSyncStatus();
          setSyncStatus(s);
        } catch {}
      }, 3000);
    } catch (err: any) {
      setBackupMessage(`備份失敗: ${err?.message || err}`);
    } finally {
      setIsBackingUp(false);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    setStatusMessage(null);
    try {
      const trimmedBucket = cloudBucket.trim();
      const trimmedToken = cloudToken.trim();
      const { host: targetHost, bucket: targetBucket } = parseCloudEndpoint(trimmedBucket);

      const directorModelToSave = directorModel.trim();
      const writerModelToSave = separateModels ? writerModel.trim() : directorModelToSave;

      // 確實將 LLM 與連線資訊保存至瀏覽器 localStorage (SSOT，保證重整不丟失)
      localStorage.setItem('NOVEL_FACTORY_LLM_BASE_URL', baseUrl.trim());
      localStorage.setItem('NOVEL_FACTORY_API_KEY', apiKey.trim());
      localStorage.setItem('NOVEL_FACTORY_DIRECTOR_MODEL', directorModelToSave);
      localStorage.setItem('NOVEL_FACTORY_WRITER_MODEL', writerModelToSave);
      localStorage.setItem('NOVEL_FACTORY_SEPARATE_MODELS', String(separateModels));
      localStorage.setItem('NOVEL_FACTORY_TEMPERATURE', String(temperature));
      localStorage.setItem('NOVEL_FACTORY_ENABLE_THINKING', String(enableThinking));

      if (targetHost) {
        localStorage.setItem('NOVEL_FACTORY_API_HOST', targetHost);
      }
      if (targetBucket) {
        localStorage.setItem('NOVEL_FACTORY_CLOUD_BUCKET', targetBucket);
      }
      if (trimmedToken) {
        localStorage.setItem('NOVEL_FACTORY_API_TOKEN', trimmedToken);
      }

      const directorPayload = {
        api_key: apiKey,
        base_url: baseUrl,
        model: directorModelToSave,
        temperature,
        enable_thinking: enableThinking,
      };

      const writerPayload = {
        api_key: apiKey,
        base_url: baseUrl,
        model: writerModelToSave,
        temperature,
        enable_thinking: enableThinking,
      };

      const agentsPayload: Record<string, any> = {
        global: { ...directorPayload, agent_name: 'global' },
        architect: { ...directorPayload, agent_name: 'architect' },
        character: { ...directorPayload, agent_name: 'character' },
        volumes: { ...directorPayload, agent_name: 'volumes' },
        volume_skeleton: { ...directorPayload, agent_name: 'volume_skeleton' },
        plot: { ...directorPayload, agent_name: 'plot' },
        copilot: { ...directorPayload, agent_name: 'copilot' },
        editor: { ...directorPayload, agent_name: 'editor' },
        evaluate: { ...directorPayload, agent_name: 'evaluate' },
        writer: { ...writerPayload, agent_name: 'writer' },
      };

      const preferencesPayload = {
        theme,
        editor_font_size: fontSize,
      };

      await savePreferences(preferencesPayload);

      // 僅在有設定 Base URL 或模型名稱時才寫入 Agent 設定，防止空值覆寫正在運行的配置
      if (baseUrl.trim() || directorModelToSave) {
        await saveSettings({
          configs: agentsPayload,
          agents: agentsPayload,
          preferences: preferencesPayload,
        });
      }

      if (enableCloudSync || isWebDeploy || targetBucket || trimmedToken) {
        try {
          const syncRes = await saveCloudSyncConfig({
            storage_bucket: targetBucket,
            dataset_repo: targetBucket,
            token: trimmedToken,
          });
          if (syncRes.config) {
            setSyncStatus(syncRes.config);
          }
        } catch (syncErr: any) {
          console.error('Failed to update cloud sync config:', syncErr);
        }
      }

      setStatusMessage('✅ 設定已成功儲存！');
      setTimeout(() => {
        onClose();
      }, 500);
    } catch (err: any) {
      setStatusMessage(`儲存失敗: ${err.message}`);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="系統偏好與模型設定"
      maxWidth="lg"
      closeOnOverlayClick={false}
      footer={
        <div className="modal-footer-actions space-between">
          <span className="settings-version-tag">
            {APP_NAME} v{APP_VERSION}
          </span>
          <div className="modal-footer-buttons">
            <Button variant="ghost" onClick={onClose} disabled={isSaving}>
              關閉
            </Button>
            <Button variant="primary" onClick={handleSave} isLoading={isSaving}>
              儲存設定
            </Button>
          </div>
        </div>
      }
    >
      <div className="settings-form">
        {statusMessage && (
          <div className="form-feedback-banner">{statusMessage}</div>
        )}

        {/* 1. Theme Palette Selector */}
        <div className="settings-section">
          <h4 className="settings-section-title">色彩主題風格 (暖色紙感／拒絕刺眼高亮)</h4>
          <div className="theme-options-grid">
            <button
              type="button"
              className={`theme-option-card theme-dark ${theme === 'dark' ? 'active' : ''}`}
              onClick={() => onThemeChange('dark')}
            >
              <div className="theme-preview-box dark-preview" />
              <div className="theme-info">
                <span className="theme-name">深色模式 (Warm Dark / Espresso)</span>
                <span className="theme-desc">底色 #141210、卡片 #1e1b18、邊框 #322d28</span>
              </div>
            </button>

            <button
              type="button"
              className={`theme-option-card theme-neutral ${theme === 'neutral' ? 'active' : ''}`}
              onClick={() => onThemeChange('neutral')}
            >
              <div className="theme-preview-box neutral-preview" />
              <div className="theme-info">
                <span className="theme-name">一般模式 (Warm Balanced / Stone Paper)</span>
                <span className="theme-desc">底色 #ebe6de、卡片 #f5f1eb、邊框 #d8d0c5</span>
              </div>
            </button>

            <button
              type="button"
              className={`theme-option-card theme-light ${theme === 'light' ? 'active' : ''}`}
              onClick={() => onThemeChange('light')}
            >
              <div className="theme-preview-box light-preview" />
              <div className="theme-info">
                <span className="theme-name">淺色模式 (Warm Cream)</span>
                <span className="theme-desc">底色 #f7f4ee、卡片 #ffffff、邊框 #e5ded4</span>
              </div>
            </button>
          </div>
        </div>

        {/* 2. Middle Editor Font Size Setting */}
        <div className="settings-section">
          <div className="flex items-center justify-between">
            <h4 className="settings-section-title">中間編輯區文字大小</h4>
            <span className="text-accent font-mono text-sm font-semibold">{fontSize}px</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted">14px</span>
            <input
              type="range"
              min="14"
              max="24"
              step="1"
              value={fontSize}
              onChange={(e) => handleFontSizeChange(Number(e.target.value))}
              className="flex-1"
            />
            <span className="text-xs text-muted">24px</span>
          </div>
          <div className="preset-tags-list">
            {[14, 15, 16, 18, 20, 22].map((size) => (
              <button
                key={size}
                type="button"
                className={`preset-tag-btn ${fontSize === size ? 'active' : ''}`}
                onClick={() => handleFontSizeChange(size)}
              >
                {size}px {size === 16 ? '(預設)' : size === 18 ? '(舒適)' : size === 20 ? '(大字)' : ''}
              </button>
            ))}
          </div>
        </div>

        {/* 3. LLM API Endpoint & Key */}
        <div className="settings-section">
          <h4 className="settings-section-title">LLM API 連線配置</h4>
          <div className="form-group">
            <label className="form-label">API Base URL</label>
            <input
              type="text"
              className="form-input font-mono"
              placeholder="https://api.openai.com/v1 或相容代理伺服器網址"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label className="form-label">API Key</label>
            <input
              type="password"
              className="form-input font-mono"
              placeholder="sk-... 或 nvapi-... (本地 WebChat2Local 可留空)"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </div>
        </div>

        {/* 3. Dual Model Configuration */}
        <div className="settings-section">
          <div className="form-label-with-action">
            <h4 className="settings-section-title">模型配置 (支援導演架構師與執筆作家雙模型分離)</h4>
            <div style={{ display: 'flex', gap: '8px' }}>
              <Button
                size="xs"
                variant="secondary"
                onClick={handleTestLlm}
                isLoading={isTestingLlm}
                disabled={isTestingLlm || isFetchingModels}
              >
                測試 LLM 連線
              </Button>
              <Button
                size="xs"
                variant="ghost"
                onClick={handleFetchModels}
                isLoading={isFetchingModels}
                disabled={isTestingLlm || isFetchingModels}
              >
                動態讀取可用模型
              </Button>
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">
              導演 / 架構師模型 (世界觀構建、大綱骨架、角色設計、伏筆轉折、內容審核)
            </label>
            <input
              type="text"
              list="available-models-datalist"
              className="form-input font-mono"
              placeholder="例如: gpt-4o, claude-3-5-sonnet, gemini-1.5-pro, qwen2.5:72b"
              value={directorModel}
              onFocus={() => setActiveModelTarget('director')}
              onChange={(e) => {
                setDirectorModel(e.target.value);
                if (!separateModels) {
                  setWriterModel(e.target.value);
                }
              }}
            />
          </div>

          <div className="form-group checkbox-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={separateModels}
                onChange={(e) => {
                  setSeparateModels(e.target.checked);
                  if (!e.target.checked) {
                    setWriterModel(directorModel);
                  }
                }}
              />
              <span>為「章節執筆作家 (Chapter Writer)」指定獨立模型 (如使用寫作特化模型)</span>
            </label>
          </div>

          {separateModels && (
            <div className="form-group">
              <label className="form-label">
                章節執筆作家模型 (正文長篇敘事、人物對白、場景文風渲染)
              </label>
              <input
                type="text"
                list="available-models-datalist"
                className="form-input font-mono"
                placeholder="例如: claude-3-5-sonnet, deepseek-chat, gpt-4o"
                value={writerModel}
                onFocus={() => setActiveModelTarget('writer')}
                onChange={(e) => setWriterModel(e.target.value)}
              />
            </div>
          )}

          {/* HTML5 Datalist for native autocomplete on both inputs */}
          <datalist id="available-models-datalist">
            {availableModels.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>

          {availableModels.length > 0 && (
            <div className="model-suggestions-area">
              <div className="model-suggestions-header">
                <span className="text-muted font-xs">
                  伺服器可用模型 ({availableModels.length} 個已載入推薦下拉選單)
                </span>
                {separateModels && (
                  <div className="model-target-indicator font-xs">
                    <span className="text-muted">點擊填入目標:</span>
                    <button
                      type="button"
                      className={`btn btn-xs ${activeModelTarget === 'director' ? 'btn-primary' : 'btn-ghost'}`}
                      onClick={() => setActiveModelTarget('director')}
                    >
                      導演
                    </button>
                    <button
                      type="button"
                      className={`btn btn-xs ${activeModelTarget === 'writer' ? 'btn-primary' : 'btn-ghost'}`}
                      onClick={() => setActiveModelTarget('writer')}
                    >
                      作家
                    </button>
                  </div>
                )}
              </div>

              <div className="model-chips-list">
                {availableModels.map((m) => {
                  const isDirector = directorModel === m;
                  const isWriter = separateModels && writerModel === m;
                  return (
                    <ModelChip
                      key={m}
                      modelName={m}
                      isSelected={isDirector || isWriter}
                      onSelect={(selected) => {
                        if (!separateModels) {
                          setDirectorModel(selected);
                          setWriterModel(selected);
                        } else {
                          if (activeModelTarget === 'writer') {
                            setWriterModel(selected);
                          } else {
                            setDirectorModel(selected);
                          }
                        }
                      }}
                    />
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* 4. Generation Hyperparameters */}
        <div className="settings-section">
          <h4 className="settings-section-title">生成參數微調</h4>
          <div className="form-group">
            <label className="form-label">
              多樣性溫度 (Temperature: {temperature})
            </label>
            <input
              type="range"
              min="0"
              max="1.5"
              step="0.05"
              className="form-range"
              value={temperature}
              onChange={(e) => setTemperature(parseFloat(e.target.value))}
            />
          </div>

          <div className="form-group checkbox-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={enableThinking === 1}
                onChange={(e) => setEnableThinking(e.target.checked ? 1 : 0)}
              />
              <span>啟用深度思考推理流 (Thinking Process Stream)</span>
            </label>
          </div>
        </div>

        {/* 5. Storage & Cloud Sync */}
        <div className="settings-section cloud-sync-section">
          <div className="form-label-with-action">
            <h4 className="settings-section-title">資料庫儲存與雲端備份</h4>
            {(enableCloudSync || isWebDeploy) && (
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <Button
                  size="xs"
                  variant="ghost"
                  onClick={handleTestConnection}
                  isLoading={isTesting}
                  disabled={isTesting || isBackingUp}
                >
                  測試連線
                </Button>
                <Button
                  size="xs"
                  variant="secondary"
                  onClick={handleTriggerBackup}
                  isLoading={isBackingUp}
                  disabled={isBackingUp || isTesting}
                >
                  立即備份至雲端
                </Button>
              </div>
            )}
          </div>

          {/* Local / Server DB Path & Info */}
          <div className="local-db-info-box">
            <div className="sync-detail-item">
              <span className="detail-label">{isLocalRun ? '本機資料庫路徑:' : '伺服器資料庫路徑:'}</span>
              <span className="detail-val font-mono">
                {serverDbPath || syncStatus?.db_path || (syncLoading ? '正在獲取伺服器路徑...' : '無法取得後端資料庫路徑 (未連線)')}
              </span>
            </div>
            <div className="sync-detail-item">
              <span className="detail-label">資料庫狀態:</span>
              <span className="detail-val">
                {syncStatus ? (
                  syncStatus.db_exists ? `正常 (${syncStatus.db_size_mb} MB)` : '資料庫檔案不存在或未初始化'
                ) : (
                  syncLoading ? '連線查詢中...' : '未連線'
                )}
              </span>
            </div>
            {syncStatus?.last_backup_time && (
              <div className="sync-detail-item">
                <span className="detail-label">最後備份時間:</span>
                <span className="detail-val">
                  {syncStatus.last_backup_time} ({syncStatus.last_backup_status})
                </span>
              </div>
            )}
          </div>

          {/* Web Deploy Alert Notice */}
          {isWebDeploy && (!cloudBucket || !cloudToken) && (
            <div className="cloud-alert-banner" style={{ marginTop: '8px' }}>
              ⚠️ <strong>雲端部署環境通知</strong>：目前於 HTTPS / 雲端發布環境運行，請務必填寫下方「儲存庫名稱」與「Access Token 金鑰」，以確保作品資料能永久保存，避免容器重置遺失！
            </div>
          )}

          {/* Checkbox */}
          <div className="form-group checkbox-group" style={{ marginTop: '8px' }}>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={enableCloudSync || isWebDeploy}
                disabled={isWebDeploy}
                onChange={(e) => setEnableCloudSync(e.target.checked)}
              />
              <span>
                啟用雲端持久化備份 (Hugging Face / Git 網頁發布同步)
                {isWebDeploy ? ' (雲端環境強制開啟)' : ''}
              </span>
            </label>
          </div>

          {/* Cloud Inputs (shown when enabled or on web deploy) */}
          {(enableCloudSync || isWebDeploy) && (
            <div className="cloud-inputs-container" style={{ marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div className="form-group">
                <label className="form-label">Hugging Face 儲存庫名稱 (Storage Bucket 或 Dataset Repo)</label>
                <input
                  type="text"
                  className="form-input font-mono"
                  placeholder="例如: botsz/writenovel-storage-bucket 或 username/storage-repo"
                  value={cloudBucket}
                  onChange={(e) => setCloudBucket(e.target.value)}
                />
                <span className="text-xs text-muted" style={{ display: 'block', marginTop: '4px' }}>
                  填寫您的 Hugging Face 儲存庫名稱（用於 SQLite 資料庫持久化與雲端同步備份，非 LLM 呼叫端點）。
                </span>
              </div>

              <div className="form-group">
                <label className="form-label">雲端存取金鑰 (Hugging Face Access Token)</label>
                <input
                  type="password"
                  className="form-input font-mono"
                  placeholder="hf_..."
                  value={cloudToken}
                  onChange={(e) => setCloudToken(e.target.value)}
                />
              </div>
            </div>
          )}

          {backupMessage && (
            <div className="form-feedback-banner" style={{ marginTop: '8px' }}>{backupMessage}</div>
          )}
        </div>
      </div>
    </Modal>
  );
};
