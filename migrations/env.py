# Connect Alembic to SAGE's database and model definitions.

from logging.config import fileConfig

from alembic import context
from alembic.util import CommandError

from database.connection import Base, DatabaseConfigurationError, get_database_url, get_engine
from database.models import User

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline():
    # Generate SQL without opening a database connection.
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    # Apply migrations through a live database connection.
    with get_engine().connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


try:
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()
except DatabaseConfigurationError as error:
    raise CommandError(str(error)) from None
