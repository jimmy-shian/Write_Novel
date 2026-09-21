import React from 'react';
import { GeometryNodeDto, GeometryEdgeDto } from '../../types/geometry';
import { Badge } from '../common/Badge';
import { Button } from '../common/Button';
import { IconCompass, IconGitBranch, IconFileText, IconShield } from '../common/Icons';

interface GeometryNodeDetailProps {
  node: GeometryNodeDto | null;
  edges: {
    incoming: GeometryEdgeDto[];
    outgoing: GeometryEdgeDto[];
  };
  onPreviewContext: (node: GeometryNodeDto) => void;
  onNavigateToChapter?: (chapterIndex: number) => void;
  onClose?: () => void;
}

export const GeometryNodeDetail: React.FC<GeometryNodeDetailProps> = ({
  node,
  edges,
  onPreviewContext,
  onNavigateToChapter,
  onClose,
}) => {
  if (!node) {
    return (
      <aside className="geometry-inspector-pane">
        <div className="geometry-inspector-content">
          <div className="pane-sub-header flex items-center justify-between">
            <span>幾何節點檢查器</span>
            {onClose && (
              <button
                type="button"
                className="geometry-inspector-close"
                onClick={onClose}
                title="收合右側檢查器"
                aria-label="收合檢查器"
              >
                ✕
              </button>
            )}
          </div>
          <p className="text-xs text-[var(--text-muted)] leading-relaxed">
            請在左側拓撲畫布點擊任意幾何節點，即可在此檢視其結構義務、前置承接、跨線關聯與文學語義。
          </p>
        </div>
      </aside>
    );
  }

  const roleObligationDescriptions: Record<string, string> = {
    OPEN_THREAD: '【線程開啟/伏筆埋設】：建立核心衝突動機，拋出未解之謎或長程懸念。',
    DEVELOP: '【情節推進/博弈深化】：在既有軌道上擴張衝突烈度，增加難度或揭示次要阻礙。',
    BRANCH: '【分支演化/次要危機】：由主線派生出新支線或遭遇意外變故，擴展故事維度。',
    REVISIT: '【重訪/深化回溯】：重新檢視前期鋪設之懸念或場景，揭示此前被忽略的線索。',
    ESCALATE: '【矛盾激化/籌碼加碼】：重大危機逼近臨界點，主角陷入不可逆的代價抉擇。',
    CONVERGE: '【多線匯聚/合流】：多條線程在此產生劇烈交會與碰撞，不同勢力直接衝突。',
    CHARACTER_SHIFT: '【心境轉向/信念打破】：角色經歷價值觀重構、重大代價抉擇或破除假信念。',
    RELATIONSHIP_CHANGE: '【關係質變】：人際羈絆發生本質變化（結盟、反目、背叛、情感確立）。',
    PAYOFF: '【伏筆回收/高潮兌現】：強烈釋放前文累積的懸念能量，兌現承諾。',
    TRANSITION: '【過場/沉澱】：在高潮後提供情緒釋放與空間位移，整備下一波衝突。',
    CLOSE: '【收束/收尾】：完滿收束當前弧線或副線，確認得失，平息餘波。',
    ECHO: '【主題呼應】：遠程呼應此前之象徵或對話，強化文學意境與命運感。',
  };

  const obligationText = roleObligationDescriptions[node.structural_role] || '維持該章節之結構平衡。';

  return (
    <aside className="geometry-inspector-pane">
      <div className="geometry-inspector-content">
        <div className="pane-sub-header flex items-center justify-between">
          <span>幾何節點檢查器</span>
          <span className="flex items-center gap-2">
            <span className="font-mono text-accent font-bold">{node.node_id}</span>
            {onClose && (
              <button
                type="button"
                className="geometry-inspector-close"
                onClick={onClose}
                title="收合右側檢查器"
                aria-label="收合檢查器"
              >
                ✕
              </button>
            )}
          </span>
        </div>

        {/* 1. 結構定位 */}
        <div className="geometry-inspector-section">
          <span className="geometry-inspector-label">結構定位 (Structural Role)</span>
          <div>
            <Badge variant="accent" size="sm">{node.structural_role}</Badge>
          </div>
          <p className="text-xs text-[var(--text-secondary)] mt-1">
            {obligationText}
          </p>
        </div>

        {/* 2. 章節與座標 */}
        <div className="geometry-inspector-section">
          <span className="geometry-inspector-label">章節範圍與層級</span>
          <div className="text-xs space-y-1">
            <div>所屬章節：<strong>第 {node.chapter_start} - {node.chapter_end} 章</strong></div>
            <div>線程歸屬：<strong>{node.primary_thread || '全域主線'}</strong></div>
            <div>層級座標：第 {node.volume_index} 卷 · 第 {node.arc_index} 弧 · 序列 {node.sequence_index}</div>
            <div>重要度權重：{node.importance || 1.0}</div>
          </div>
        </div>

        {/* 3. 前置因果 (Incoming Edges) */}
        <div className="geometry-inspector-section">
          <span className="geometry-inspector-label">
            前置承接鏈路 ({edges.incoming.length})
          </span>
          {edges.incoming.length === 0 ? (
            <div className="text-xs text-[var(--text-muted)] italic">（無前置幾何邊）</div>
          ) : (
            <div className="geometry-edge-list">
              {edges.incoming.map((e) => (
                <div key={e.edge_id} className="geometry-edge-item">
                  <div className="flex items-center gap-1.5">
                    <IconGitBranch size={12} className="text-accent" />
                    <span className="font-mono font-bold">{e.source}</span>
                    <span>→ {e.edge_type}</span>
                  </div>
                  <Badge variant="neutral" size="sm">跨 {e.distance} 章</Badge>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 4. 後續結構義務 (Outgoing Obligations) */}
        <div className="geometry-inspector-section">
          <span className="geometry-inspector-label">
            後續結構義務 ({edges.outgoing.length})
          </span>
          {edges.outgoing.length === 0 ? (
            <div className="text-xs text-[var(--text-muted)] italic">（本節點無後續鋪墊邊）</div>
          ) : (
            <div className="geometry-edge-list">
              {edges.outgoing.map((e) => (
                <div key={e.edge_id} className="geometry-edge-item">
                  <div className="flex items-center gap-1.5">
                    <IconCompass size={12} className="text-warning" />
                    <span>{e.edge_type} →</span>
                    <span className="font-mono font-bold">{e.target}</span>
                  </div>
                  <Badge variant="neutral" size="sm">跨 {e.distance} 章</Badge>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 5. 文學語義預覽 (防劇透) */}
        <div className="geometry-inspector-section">
          <span className="geometry-inspector-label">文學語義 (Semantic)</span>
          {node.semantic ? (
            <pre className="p-2 rounded bg-[var(--surface-subtle)] border border-[var(--border-subtle)] text-[11px] overflow-x-auto text-[var(--text-secondary)]">
              {typeof node.semantic === 'string'
                ? node.semantic
                : JSON.stringify(node.semantic, null, 2)}
            </pre>
          ) : (
            <div className="p-2 rounded bg-[var(--surface-subtle)] border border-[var(--border-subtle)] text-xs text-[var(--text-muted)] italic">
              semantic = NULL (空拓撲，等待 LLM 分層注入文學語義)
            </div>
          )}
        </div>

        {/* 6. Context Package 預覽按鈕 */}
        <Button
          variant="primary"
          size="sm"
          onClick={() => onPreviewContext(node)}
          icon={<IconShield size={14} />}
        >
          預覽結構義務 (Context Package)
        </Button>

        {onNavigateToChapter && (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => onNavigateToChapter(node.chapter_start)}
            icon={<IconFileText size={14} />}
          >
            跳轉至第 {node.chapter_start} 章寫作
          </Button>
        )}

        {/* 7. 拓撲修復 (vNext 預留) */}
        <div className="geometry-vnext-box mt-2">
          <div className="flex items-center justify-between mb-1">
            <span className="font-semibold text-xs text-[var(--text-primary)]">拓撲自動修復 (Repair)</span>
            <Badge variant="neutral" size="sm">vNext 後續版本</Badge>
          </div>
          <p className="text-[11px] text-[var(--text-muted)]">
            門禁演算法支持 SPLIT / EXPAND / INSERT / COMPRESS 四大結構拓撲重構操作。
          </p>
        </div>
      </div>
    </aside>
  );
};
