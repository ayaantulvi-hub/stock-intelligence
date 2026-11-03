from alembic import context
from sqlalchemy import create_engine

from stockintel.config import get_settings
from stockintel.db import metadata

engine = create_engine(get_settings().database_url)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()
