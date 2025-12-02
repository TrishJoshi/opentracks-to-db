"""add spatial indexes

Revision ID: de84ed66e4b3
Revises: 76a50bff962c
Create Date: 2025-11-10 21:21:39.047028

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import geoalchemy2


# revision identifiers, used by Alembic.
revision: str = 'de84ed66e4b3'
down_revision: Union[str, Sequence[str], None] = '76a50bff962c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Manually added spatial indexes
    op.create_index(
        'idx_opentracks_tracks_geom_track',
        'opentracks_tracks',
        ['geom_track'],
        unique=False,
        postgresql_using='gist'
    )
    op.create_index(
        'idx_opentracks_track_points_geom_point',
        'opentracks_track_points',
        ['geom_point'],
        unique=False,
        postgresql_using='gist'
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Manually added drop index commands for rollback
    op.drop_index('idx_opentracks_track_points_geom_point', table_name='opentracks_track_points', postgresql_using='gist')
    op.drop_index('idx_opentracks_tracks_geom_track', table_name='opentracks_tracks', postgresql_using='gist')
