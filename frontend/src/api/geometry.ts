import { request } from './client';
import {
  GeometryGraphResponse,
  GeometryStats,
  GeometryParams,
  GeometryRepairPayload,
  NodeContextPackage,
} from '../types/geometry';

export * from '../types/geometry';

export const geometryApi = {
  /**
   * 取得敘事幾何骨架圖（支援章節範圍切片）
   */
  getGeometry: (novelId: string, chapterStart?: number, chapterEnd?: number) => {
    const params = new URLSearchParams();
    if (chapterStart !== undefined) params.set('chapter_start', String(chapterStart));
    if (chapterEnd !== undefined) params.set('chapter_end', String(chapterEnd));
    const qs = params.toString() ? `?${params.toString()}` : '';
    return request<GeometryGraphResponse>(`/api/novels/${novelId}/geometry${qs}`);
  },

  /**
   * 取得幾何圖整體統計與填充進度
   */
  getStats: (novelId: string) => {
    return request<GeometryStats>(`/api/novels/${novelId}/geometry/stats`);
  },

  /**
   * 重新生成敘事幾何骨架
   */
  generate: (novelId: string, payload: Partial<GeometryParams>) => {
    return request<{ status: string; message: string; stats: GeometryStats }>(
      `/api/novels/${novelId}/geometry/generate`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    );
  },

  /**
   * 觸發拓撲修復操作 (SPLIT / EXPAND / INSERT / COMPRESS)
   */
  repair: (novelId: string, payload: GeometryRepairPayload) => {
    return request<{ success: boolean; message?: string; [key: string]: any }>(
      `/api/novels/${novelId}/geometry/repair`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    );
  },

  /**
   * 局部更新單一節點文學語義
   */
  updateNodeSemantic: (novelId: string, nodeId: string, semantic: Record<string, any>) => {
    return request<{ status: string; node_id: string; updated_semantic: any }>(
      `/api/novels/${novelId}/geometry/nodes/${nodeId}/semantic`,
      {
        method: 'PATCH',
        body: JSON.stringify(semantic),
      }
    );
  },

  /**
   * 取得節點專屬上下文約束與敘事義務包裹 (Layer 3 & Layer 4)
   */
  getNodeContext: (novelId: string, nodeId: string) => {
    return request<NodeContextPackage>(`/api/novels/${novelId}/geometry/nodes/${nodeId}/context`);
  },
};
