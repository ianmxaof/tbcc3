"""secretary_settings.system_prompt column

Revision ID: 080_secretary_system_prompt
Revises: 079_secretary_fe_llm_settings
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "080_secretary_system_prompt"
down_revision: Union[str, None] = "079_secretary_fe_llm_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("secretary_settings", sa.Column("system_prompt", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("secretary_settings", "system_prompt")
