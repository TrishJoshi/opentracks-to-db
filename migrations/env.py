from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# --- ADDED BLOCK START ---
import os
import sys
# 1. Add the parent directory to path so we can find our app's files
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# 2. Import the Base (registry) and the models (to register them)
from database import Base
import models
# --- ADDED BLOCK END ---

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# --- INCLUDE_OBJECT HOOK ---
def include_object(object, name, type_, reflected, compare_to):
    # This function filters out PostGIS tables so Alembic doesn't try to drop them
    if type_ == "table" and name in ['spatial_ref_sys', 'geometry_columns', 'geography_columns', 'raster_columns', 'raster_overviews']:
        print(f"DEBUG: Alembic is ignoring table '{name}'")
        return False
    return True
# ---------------------------

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,  # <--- CRITICAL: Must be here
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,  # <--- CRITICAL: Must be here for autogenerate
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
