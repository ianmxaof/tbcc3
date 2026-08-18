"""secretary_user_contexts.psych_markers — financial intent / trust / urgency scan

Revision ID: 115_secretary_psych_markers
Revises: 114_gatekeeper_lane_labels
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "115_secretary_psych_markers"
down_revision: Union[str, None] = "114_gatekeeper_lane_labels"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("secretary_user_contexts")}
    if "psych_markers" not in cols:
        op.add_column(
            "secretary_user_contexts",
            sa.Column("psych_markers", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("secretary_user_contexts")}
    if "psych_markers" in cols:
        op.drop_column("secretary_user_contexts", "psych_markers")
