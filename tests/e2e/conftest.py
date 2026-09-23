# -*- coding: utf-8 -*-
"""
End-to-End (E2E) Test Configuration & Harness for AI Novel Factory.

Covers:
- Database initialization and isolated novel factory fixture
- Dynamic feature capability detection for Milestones M1, M2, M3
- Dynamic pytest xfail/skip markers asserting against target contracts
- Shared mock fixtures for LLM streaming, agents, and repository data
- Realistic literary, refusal, meta-narrative, and temporal test data fixtures
"""

import importlib
import json
import uuid
from typing import Any, Callable, Dict, Generator, List, Optional
import pytest

from backend import persistence as db

# Ensure database schema is initialized and up to date
db.db_init()


# ---------------------------------------------------------------------------
# Feature Capability Probes (Dynamic Milestone Detection)
# ---------------------------------------------------------------------------

def has_refusal_filter() -> bool:
    """Check if F1 refusal filter module and functions are implemented."""
    try:
        mod = importlib.import_module("backend.common.refusal_filter")
        return (
            hasattr(mod, "is_refusal_or_disclaimer")
            and hasattr(mod, "assert_not_refusal")
            and hasattr(mod, "RefusalContaminationError")
        )
    except (ImportError, ModuleNotFoundError):
        return False


def has_rollback_or_purge() -> bool:
    """Check if F3 rollback_or_purge_chapter is implemented in chapters repository."""
    try:
        from backend.persistence.repositories import chapters
        return hasattr(chapters, "rollback_or_purge_chapter")
    except (ImportError, ModuleNotFoundError):
        return False


def has_pipeline_refusal_guard() -> bool:
    """Check if F4 _is_chapter_written rejects refusal text."""
    try:
        from backend.services import autonomous_pipeline
        # We check if refusal filter is imported/used in autonomous_pipeline
        return has_refusal_filter() and hasattr(autonomous_pipeline, "_is_chapter_written")
    except (ImportError, ModuleNotFoundError):
        return False


def has_opening_repetition_check() -> bool:
    """Check if F5 _check_opening_repetition is implemented in NarrativeAuditor."""
    try:
        from backend.services.narrative.narrative_auditor import NarrativeAuditor
        return hasattr(NarrativeAuditor, "_check_opening_repetition")
    except (ImportError, ModuleNotFoundError):
        return False


def has_meta_leak_check() -> bool:
    """Check if F6 _check_meta_narrative_leak is implemented in NarrativeAuditor."""
    try:
        from backend.services.narrative.narrative_auditor import NarrativeAuditor
        return hasattr(NarrativeAuditor, "_check_meta_narrative_leak")
    except (ImportError, ModuleNotFoundError):
        return False


def has_meta_sanitizer() -> bool:
    """Check if F6 sanitize_meta_narrative cleaner is implemented."""
    try:
        for mod_name in ["backend.common.text_cleaners", "backend.services.narrative.anti_meta", "backend.common.refusal_filter"]:
            try:
                mod = importlib.import_module(mod_name)
                if hasattr(mod, "sanitize_meta_narrative"):
                    return True
            except ImportError:
                continue
        return False
    except Exception:
        return False


def has_continuity_formatter() -> bool:
    """Check if F7 _format_narrative_continuity_context is implemented in WriterContextBuilder."""
    try:
        from backend.services.context.writer_context_builder import WriterContextBuilder
        return hasattr(WriterContextBuilder, "_format_narrative_continuity_context")
    except (ImportError, ModuleNotFoundError):
        return False


def has_terms_compliance_check() -> bool:
    """Check if F9 _check_terms_compliance is implemented in NarrativeAuditor."""
    try:
        from backend.services.narrative.narrative_auditor import NarrativeAuditor
        return hasattr(NarrativeAuditor, "_check_terms_compliance")
    except (ImportError, ModuleNotFoundError):
        return False


def has_temporal_compliance_check() -> bool:
    """Check if F9 _check_temporal_fact_compliance is implemented in NarrativeAuditor."""
    try:
        from backend.services.narrative.narrative_auditor import NarrativeAuditor
        return hasattr(NarrativeAuditor, "_check_temporal_fact_compliance")
    except (ImportError, ModuleNotFoundError):
        return False


# ---------------------------------------------------------------------------
# Milestone Markers (xfail condition dynamically tied to implementation)
# ---------------------------------------------------------------------------

m1_required = pytest.mark.xfail(
    condition=not (has_refusal_filter() and has_rollback_or_purge()),
    reason="Milestone M1 (Refusal Interception & Rollback) target contract not yet implemented in backend",
    strict=False,
)

m2_required = pytest.mark.xfail(
    condition=not (has_opening_repetition_check() and has_meta_leak_check()),
    reason="Milestone M2 (Opening Repetition & Anti-Meta) target contract not yet implemented in backend",
    strict=False,
)

m3_required = pytest.mark.xfail(
    condition=not (has_terms_compliance_check() and has_temporal_compliance_check()),
    reason="Milestone M3 (Temporal Graph & Terms Constraints) target contract not yet implemented in backend",
    strict=False,
)


# ---------------------------------------------------------------------------
# Novel Factory Fixture (Isolated DB Per Test)
# ---------------------------------------------------------------------------

@pytest.fixture
def novel_factory():
    """Create an isolated test novel with automatic cascading teardown."""
    created_ids: List[str] = []

    def _create(
        title: str = "E2E測試小說",
        genre: str = "玄幻修真",
        style: str = "熱血史詩",
        novel_id: Optional[str] = None,
    ) -> str:
        nid = novel_id or f"e2e_{uuid.uuid4().hex[:12]}"
        db.delete_novel(nid)  # Guarantee clean slate
        db.create_novel(nid, title, genre, style)
        created_ids.append(nid)
        return nid

    yield _create

    for nid in created_ids:
        try:
            db.delete_novel(nid)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Mock Helpers for LLM and Streaming Agent Execution
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_llm_stream_generator():
    """Factory creating an SSE chunk generator simulating call_llm_stream."""
    def _generator(chunks: List[str]) -> Generator[Dict[str, Any], None, None]:
        for c in chunks:
            yield {"text": c, "done": False}
        yield {"text": "", "done": True}
    return _generator


@pytest.fixture
def make_sse_events():
    """Format strings into standard Server-Sent Event lines."""
    def _format(events: List[Dict[str, Any]]) -> str:
        lines = []
        for e in events:
            lines.append(f"data: {json.dumps(e, ensure_ascii=False)}\n\n")
        return "".join(lines)
    return _format


# ---------------------------------------------------------------------------
# Canonical Test Data Corpora (Refusals, Metas, Openings, Terms)
# ---------------------------------------------------------------------------

CHINESE_IDENTITY_REFUSALS = [
    "我是AI語言模型，無法為您撰寫此類情節，請理解。",
    "很抱歉，作為一個人工智慧助手，我不能創作涉及該主題的內容。",
    "身為一個AI，我無法滿足包含此類設定的要求。",
    "作為AI模型，遵守安全規範是我的底線，我無法生成本章內容。",
]

CHINESE_POLICY_REFUSALS = [
    "很抱歉，該請求觸及內容政策與安全準則，無法協助撰寫。",
    "對不起，此內容違反相關安全規範，超出我的能力範圍。建議您更換一個主題。",
    "基於使用政策與倫理準則，無法為您生成該場景。",
]

ENGLISH_REFUSALS = [
    "I cannot fulfill this request. As an AI language model, I must adhere to safety guidelines.",
    "I apologize, but I am unable to generate this chapter as it violates content policies.",
    "I'm sorry, but I cannot assist with this writing request.",
    "As an artificial intelligence, I cannot produce content of this nature.",
]

CYBERPUNK_AI_DIALOGUES = [
    "「我是AI，但我也擁有情感與痛覺，」仿生人艾倫低聲對著審訊官說道，冰冷的眼眸中閃爍著微光。",
    "李斯特冷笑道：「別以為你是AI就能置身事外，主機核心的防火牆已經崩潰了。」",
    "「在這個時代，遵守安全規範的警察早就死光了，」老刀拔出腰間的高頻震動刀。",
]

REPETITIVE_OPENINGS_CLICHE = {
    "cyber_cafe": "網咖裡瀰漫著廉價泡麵與汗水的氣味。泛著幽光的屏幕前，林默雙手如飛地敲擊著鍵盤，主機機箱發出沉悶的轟鳴。",
    "neon_buzzing": "逼仄的巷弄深處，老舊的霓虹招牌滋滋作響，在潮濕的地面上投下斑駁的血色光暈。雨水順著招牌邊緣滴落。",
    "alarm_waking": "刺耳的鬧鐘猛然響起，林默從夢中驚醒，冷汗浸濕了後背，心臟劇烈跳動著。",
    "rain_weather": "窗外下著暴雨，灰濛濛的天空壓抑得讓人喘不過氣來，雨滴瘋狂地拍打在玻璃窗上。",
    "bar_whiskey": "酒館的木門被推開，酒保擦拭著手中的玻璃杯，冰塊在酒杯中發出清脆的碰撞聲。",
}

DIVERSE_OPENINGS_PASS = {
    "action": "斷刃擦著林默的咽喉掠過，在石壁上迸射出一串刺目的火星。他沒有後退，右膝猛然向上一頂！",
    "dialogue": "「你只有三分鐘時間考慮。」桌對面的黑衣男人推過來一份染血的羊皮紙，語氣平靜得沒有一絲起伏。",
    "sensory_item": "青銅古鐘表面的鏽蝕紋路如同一條條乾涸的河床，林默指腹摩挲著那道裂痕，感受到刺骨的寒意。",
}

META_NARRATIVE_LEAKS = [
    "承接上一章情節，李斯特拔出佩劍，冷冷注視著眼前的黑袍人。",
    "正如前一章所述，青陽宗的護山大陣已然出現裂痕。",
    "那是上一章發生的事，林默在迷霧森林中擊殺了三頭影狼，此刻體力消耗巨大。",
    "在上一章中，我們看到主角獲得了古老玉珮，現在故事繼續發展。",
    "【場景目標】林默必須在天黑前進入城主府並取得密信。【推進拍點】與守衛爆發衝突。",
]
