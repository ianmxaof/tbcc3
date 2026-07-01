"""secretary_settings: FE verbosity, LLM overrides, public FAQ toggle

Revision ID: 079_secretary_fe_llm_settings
Revises: 078_content_performance_growth
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "079_secretary_fe_llm_settings"
down_revision: Union[str, None] = "078_content_performance_growth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("secretary_settings", sa.Column("fe_verbosity", sa.String(length=16), nullable=True))
    op.add_column("secretary_settings", sa.Column("public_faq_enabled", sa.Boolean(), nullable=True))
    op.add_column("secretary_settings", sa.Column("llm_provider", sa.String(length=32), nullable=True))
    op.add_column("secretary_settings", sa.Column("llm_api_key", sa.Text(), nullable=True))
    op.add_column("secretary_settings", sa.Column("llm_model", sa.String(length=128), nullable=True))
    op.add_column("secretary_settings", sa.Column("llm_base_url", sa.String(length=256), nullable=True))


def downgrade() -> None:
    op.drop_column("secretary_settings", "llm_base_url")
    op.drop_column("secretary_settings", "llm_model")
    op.drop_column("secretary_settings", "llm_api_key")
    op.drop_column("secretary_settings", "llm_provider")
    op.drop_column("secretary_settings", "public_faq_enabled")
    op.drop_column("secretary_settings", "fe_verbosity")
