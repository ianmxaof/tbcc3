"""listening_relay_settings: relay_random_network_channel

Revision ID: 099_listening_relay_random_network
Revises: 098_funnel_dm_consents
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "099_relay_random_net"
down_revision: Union[str, None] = "098_funnel_dm_consents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "listening_relay_settings" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("listening_relay_settings")}
    if "relay_random_network_channel" not in cols:
        op.add_column(
            "listening_relay_settings",
            sa.Column(
                "relay_random_network_channel",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "listening_relay_settings" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("listening_relay_settings")}
    if "relay_random_network_channel" in cols:
        op.drop_column("listening_relay_settings", "relay_random_network_channel")
