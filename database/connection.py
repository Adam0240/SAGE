# Database connection and shared model base.

from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import URL, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


# Read the .env file located beside this Python file.
settings = dotenv_values(Path(__file__).resolve().parent.parent / ".env")

# Build the connection using the credentials you already configured.
database_url = URL.create(
    drivername="postgresql+psycopg",
    username=settings["POSTGRES_USER"],
    password=settings["POSTGRES_PASSWORD"],
    host="127.0.0.1",
    port=5432,
    database=settings["POSTGRES_DB"],
)

engine = create_engine(
    database_url,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 3},
)

# Sessions will be used by repositories to work with database records.
SessionLocal = sessionmaker(bind=engine)


# All database model classes inherit from this base.
class Base(DeclarativeBase):
    pass