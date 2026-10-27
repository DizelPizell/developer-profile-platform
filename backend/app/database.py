from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.settings import settings

# Every connection runs in UTC, whatever the server's default. Timestamps are
# TIMESTAMP WITHOUT TIME ZONE: the application writes naive UTC, and the
# server defaults use now(), which follows the session time zone.
CONNECT_ARGS = {"options": "-c timezone=UTC"}

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    hide_parameters=True,
    connect_args=CONNECT_ARGS,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass
