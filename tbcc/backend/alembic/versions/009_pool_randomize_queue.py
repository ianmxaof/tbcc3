"""Add randomize_queue to content_pools."""
from alembic import op
import sqlalchemy as sa

revision = "009_pool_randomize"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("content_pools") as batch:
        batch.add_column(sa.Column("randomize_queue", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table("content_pools") as batch:
        batch.drop_column("randomize_queue")
