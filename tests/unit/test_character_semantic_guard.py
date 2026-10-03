# -*- coding: utf-8 -*-
"""驗證 character_semantic 空結果不再靜默成功"""
import json

def collect(gen):
    events = []
    for chunk in gen:
        assert chunk.startswith("data:"), chunk
        payload = chunk[5:].strip()
        if payload == "[DONE]":
            events.append({"type": "done"})
        else:
            events.append(json.loads(payload))
    return events

def test_empty_llm_yields_error(monkeypatch, novel_factory):
    from backend.agents.character_semantic import runner as cs_runner
    from backend import persistence as db
    # 建立最小幾何圖：直接用現有 novel_factory 建小說並手動塞幾何？改用 mock graph
    nid = novel_factory(title="空結果測試", genre="玄幻", style="史詩")

    class FakeThread:
        def __init__(self, tid):
            self.thread_id = tid
            self.thread_type = "CHARACTER_ARC"
            self.node_sequence = ["G1"]
            self.metadata = {}
            self.semantic = {"thread_name": "t"}
    class FakeNode:
        def __init__(self, nid_):
            self.node_id = nid_
            self.structural_role = "CHARACTER_SHIFT"
            self.chapter_window = (1, 2)
            self.primary_thread = "TC1"
            self.semantic = None
    class FakeGraph:
        threads = {"TC1": FakeThread("TC1")}
        nodes = {"G1": FakeNode("G1")}

    monkeypatch.setattr(db, "load_geometry_graph", lambda _nid: FakeGraph())
    monkeypatch.setattr(db, "get_novel", lambda _nid: {"title": "測書"})
    monkeypatch.setattr(db, "get_latest_characters", lambda _nid: {"parsed_data": {"characters": [{"name": "主角"}]}})
    monkeypatch.setattr(cs_runner, "build_character_semantic_messages", lambda **kw: [])
    # LLM 回空
    monkeypatch.setattr(cs_runner, "call_llm_json", lambda agent, msgs: {})
    # 若有寫入則報錯
    def _fail_write(*a, **k):
        raise AssertionError("空結果不應寫入DB")
    monkeypatch.setattr(db, "update_thread_semantic", _fail_write)
    monkeypatch.setattr(db, "update_node_semantic", _fail_write)

    events = collect(cs_runner.run_character_semantic(nid))
    kinds = [e.get("type") for e in events]
    assert "error" in kinds, f"空 LLM 必須產生 error 事件，實際 {kinds}"
    assert not any(e.get("type") == "content" for e in events), "空結果不得回報 content 成功"

def test_hallucinated_ids_filtered(monkeypatch, novel_factory):
    from backend.agents.character_semantic import runner as cs_runner
    from backend import persistence as db
    nid = novel_factory(title="幻覺ID測試", genre="玄幻", style="史詩")

    class FakeThread:
        def __init__(self, tid):
            self.thread_id = tid
            self.thread_type = "CHARACTER_ARC"
            self.node_sequence = ["G1"]
            self.metadata = {}
            self.semantic = {"thread_name": "t"}
    class FakeNode:
        def __init__(self, nid_):
            self.node_id = nid_
            self.structural_role = "CHARACTER_SHIFT"
            self.chapter_window = (1, 2)
            self.primary_thread = "TC1"
            self.semantic = None
    class FakeGraph:
        threads = {"TC1": FakeThread("TC1")}
        nodes = {"G1": FakeNode("G1")}
    monkeypatch.setattr(db, "load_geometry_graph", lambda _nid: FakeGraph())
    monkeypatch.setattr(db, "get_novel", lambda _nid: {"title": "測書"})
    monkeypatch.setattr(db, "get_latest_characters", lambda _nid: {"parsed_data": {"characters": [{"name": "主角"}]}})
    monkeypatch.setattr(cs_runner, "build_character_semantic_messages", lambda **kw: [])
    monkeypatch.setattr(cs_runner, "call_llm_json", lambda agent, msgs: {
        "thread_bindings": {"FAKE_T": {"primary_character": "誰"}},  # 幻覺
        "node_shifts": {"G1": {"focus_character": "主角", "internal_shift": "轉變", "dramatic_choice": "抉擇"}},
    })
    written = {}
    monkeypatch.setattr(db, "update_thread_semantic", lambda nid_, tid, sem: written.update({("t", tid): sem}))
    monkeypatch.setattr(db, "update_node_semantic", lambda nid_, nnid, sem: written.update({("n", nnid): sem}))

    events = collect(cs_runner.run_character_semantic(nid))
    kinds = [e.get("type") for e in events]
    assert "error" not in kinds, f"有 1 個有效節點時不應 error，實際 {events}"
    assert ("t", "FAKE_T") not in written, "幻覺線程ID不得寫入DB"
    assert ("n", "G1") in written, "有效節點必須寫入"
    # content 計數必須是持久化數（1 節點、0 線程），不得虛報
    contents = [e for e in events if e.get("type") == "content"]
    assert contents, "應有 content 成功事件"
    payload = json.loads(contents[0]["delta"])
    assert payload["threads_bound"] == 0 and payload["nodes_shifted"] == 1, payload
