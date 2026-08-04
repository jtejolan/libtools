import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context

# Make the app package importable the same way the app itself expects
# (PYTHONPATH=app), so `from database import ...` and the model modules
# below resolve identically to how main.py imports them.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from database import Base, engine  # noqa: E402
from accounts import models as accounts_models  # noqa: E402,F401
from bookclub import models as bookclub_models  # noqa: E402,F401
from lendery import models as lendery_models  # noqa: E402,F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import every package's models above so Base.metadata is fully populated
# before autogenerate compares it against the live database.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    context.configure(
        url=engine.url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Reuses the app's own engine (built in database.py from DATABASE_URL,
    with the same sqlite/postgres URL normalization the app relies on)
    instead of building a second one from alembic.ini.
    """
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
