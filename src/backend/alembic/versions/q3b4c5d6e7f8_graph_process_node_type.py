"""add process node type to graph constraint (OH-3.9)

Revision ID: q3b4c5d6e7f8
Revises: p2a3b4c5d6e7
Create Date: 2026-10-07
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "q3b4c5d6e7f8"
down_revision = "p2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE soc_graph_nodes
        DROP CONSTRAINT IF EXISTS ck_graph_node_type;
    """)
    op.execute("""
        ALTER TABLE soc_graph_nodes ADD CONSTRAINT ck_graph_node_type
        CHECK (node_type IN (
            'asset','port','vulnerability','account','ip',
            'business_system','person','segment','alert_group','process'
        ));
    """)


def downgrade() -> None:
    op.execute("DELETE FROM soc_graph_edges WHERE rel_type = 'creates'")
    op.execute("DELETE FROM soc_graph_nodes WHERE node_type = 'process'")
    op.execute("""
        ALTER TABLE soc_graph_nodes
        DROP CONSTRAINT IF EXISTS ck_graph_node_type;
    """)
    op.execute("""
        ALTER TABLE soc_graph_nodes ADD CONSTRAINT ck_graph_node_type
        CHECK (node_type IN (
            'asset','port','vulnerability','account','ip',
            'business_system','person','segment','alert_group'
        ));
    """)
