"""add retrying document processing status

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""

from typing import Sequence, Union

from alembic import op


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE processingstatus ADD VALUE IF NOT EXISTS 'RETRYING'")


def downgrade() -> None:
    op.execute(
        "UPDATE documents SET processing_status = 'FAILED' WHERE processing_status = 'RETRYING'"
    )
    op.execute("ALTER TYPE processingstatus RENAME TO processingstatus_with_retrying")
    op.execute("CREATE TYPE processingstatus AS ENUM ('PENDING', 'PROCESSING', 'DONE', 'FAILED')")
    op.execute(
        "ALTER TABLE documents ALTER COLUMN processing_status TYPE processingstatus "
        "USING processing_status::text::processingstatus"
    )
    op.execute("DROP TYPE processingstatus_with_retrying")
