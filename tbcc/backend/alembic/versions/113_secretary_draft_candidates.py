"""secretary_pending_drafts.candidates_json — Pilot natural/clear/close set

Revision ID: 113_secretary_draft_candidates
Revises: 112_secretary_pending_drafts
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "113_secretary_draft_candidates"
down_revision: Union[str, None] = "112_secretary_pending_drafts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "secretary_pending_drafts" not in set(insp.get_table_names()):
        return
    cols = {c["name"] for c in insp.get_columns("secretary_pending_drafts")}
    if "candidates_json" in cols:
        return
    op.add_column("secretary_pending_drafts", sa.Column("candidates_json", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "secretary_pending_drafts" not in set(insp.get_table_names()):
        return
    cols = {c["name"] for c in insp.get_columns("secretary_pending_drafts")}
    if "candidates_json" not in cols:
        return
    op.drop_column("secretary_pending_drafts", "candidates_json")
