#######################################################################
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
#######################################################################

class Base(DeclarativeBase):
    '''
    Description:
        SQLAlchemy declarative base class for all ORM models.

    Flow:
        None

    Args:
        None

    Returns:
        None

    Raises:
        None

    '''

    pass

class Database:
    '''
    Description:
        Manages the SQLAlchemy engine and provides session context managers
        with automatic commit and rollback.

    Flow:
        None

    Args:
        db_url (str): SQLAlchemy-compatible database connection URL.

    Returns:
        None

    Raises:
        None

    '''

    def __init__(self, db_url: str) -> None:
        '''
        Description:
            Initialises the SQLAlchemy engine and session factory.

        Flow:
            1. Create engine from db_url.
            2. Create a sessionmaker bound to the engine.

        Args:
            db_url (str): SQLAlchemy-compatible database connection URL.

        Returns:
            None

        Raises:
            sqlalchemy.exc.ArgumentError: If db_url is malformed.

        '''

        self._engine = create_engine(db_url, fast_executemany=True)
        self._factory = sessionmaker(bind=self._engine)

    def create_tables(self) -> None:
        '''
        Description:
            Creates all database tables defined by ORM models if they
            do not already exist.

        Flow:
            1. Run CREATE TABLE IF NOT EXISTS for all mapped models.

        Args:
            None

        Returns:
            None

        Raises:
            sqlalchemy.exc.OperationalError: If the database is unreachable.

        '''

        Base.metadata.create_all(bind=self._engine)

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        '''
        Description:
            Context manager that yields a SQLAlchemy session with automatic
            commit on success and rollback on failure.

        Flow:
            1. Open a new session.
            2. Yield it to the caller.
            3. Commit if no exception was raised.
            4. Rollback if an exception occurred.
            5. Close the session in all cases.

        Args:
            None

        Returns:
            Generator[Session, None, None]: Active database session.

        Raises:
            Exception: Re-raises any exception after rollback.

        '''

        s = self._factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()
