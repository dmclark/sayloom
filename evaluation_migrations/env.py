"""Alembic environment for the separate cleanup evaluation database."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from local_text.evaluation_models import EvaluationBase

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = EvaluationBase.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
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
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql("PRAGMA secure_delete=ON")
        connection.exec_driver_sql("PRAGMA temp_store=MEMORY")
        connection.exec_driver_sql("PRAGMA journal_mode=DELETE")
        connection.exec_driver_sql("PRAGMA journal_size_limit=0")
        connection.commit()
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
