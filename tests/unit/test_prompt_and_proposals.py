# -*- coding: utf-8 -*-
import uuid
import pytest
from backend.generation.routing.schema import GenerationTaskRequest, coerce_generation_task_request
from backend.generation.handlers import resolve_handler_prompt
from backend import persistence as db

def test_prompt_coercion_and_resolution():
    payload = {
        'novel_id': 'test_novel_prompt',
        'stage': 'writer',
        'prompt': '這章的內容加入表情符號去做表示',
        'target': {'chapter_index': 1}
    }
    task = coerce_generation_task_request(payload)
    assert task.prompt == '這章的內容加入表情符號去做表示'
    assert task.user_prompt == '這章的內容加入表情符號去做表示'
    assert task.instruction == '這章的內容加入表情符號去做表示'

    resolved = resolve_handler_prompt(task, default_instruction='請根據大綱撰寫')
    assert resolved == '這章的內容加入表情符號去做表示'

def test_proposal_lifecycle():
    novel_id = f'test_prop_{uuid.uuid4().hex[:8]}'
    try:
        db.create_novel(title='測試作品', genre='奇幻', style='流暢', novel_id=novel_id)
        db.save_chapter(novel_id, 1, '這是原始第一章內容。')

        prop = db.create_proposal(
            novel_id=novel_id,
            chapter_index=1,
            proposed_text='這是修訂後的第一章內容，文筆更佳。',
            original_text='這是原始第一章內容。',
            review_comments=[{'type': 'editor_refine', 'summary': '潤飾'}]
        )

        assert prop['id'].startswith('prop_')
        assert prop['original_text'] == '這是原始第一章內容。'
        assert prop['proposed_text'] == '這是修訂後的第一章內容，文筆更佳。'

        props = db.get_proposals(novel_id, chapter_index=1)
        assert len(props) == 1
        assert props[0]['status'] == 'pending'

        db.update_proposal_status(prop['id'], 'rejected')
        updated = db.get_proposal(prop['id'])
        assert updated['status'] == 'rejected'
    finally:
        try:
            db.delete_novel(novel_id)
        except Exception:
            pass
