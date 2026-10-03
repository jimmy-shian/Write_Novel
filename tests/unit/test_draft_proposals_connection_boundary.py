import sqlite3

from backend.persistence.repositories.draft_proposals import (
    create_proposal,
    delete_proposal,
    update_proposal_content,
    update_proposal_status,
)
from backend.persistence.schema import db_init


def test_draft_proposal_writes_accept_injected_provider():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db_init(connection=conn)

    provider = lambda: conn
    proposal = create_proposal(
        "injected-proposal-novel",
        1,
        "修改後內容",
        connection_provider=provider,
    )

    assert update_proposal_status(
        proposal["id"], "accepted", connection_provider=provider
    )
    assert update_proposal_content(
        proposal["id"], "再次修改", [{"comment": "ok"}], connection_provider=provider
    )
    row = conn.execute(
        "SELECT status, proposed_text, review_comments_json FROM draft_proposals WHERE id = ?",
        (proposal["id"],),
    ).fetchone()
    assert tuple(row) == ("accepted", "再次修改", '[{"comment": "ok"}]')
    assert delete_proposal(proposal["id"], connection=conn)
    conn.close()
