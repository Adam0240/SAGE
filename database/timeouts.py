"""Bound database socket waits as well as PostgreSQL query/lock execution."""

import psycopg
from psycopg.errors import _WaitTimeout
from sqlalchemy.exc import TimeoutError as PoolTimeout


class DatabaseWaitTimeout(psycopg.OperationalError):
    """The connection was discarded because its result could not be confirmed."""


class DeadlineConnection(psycopg.Connection):
    wait_timeout = 15.0

    def wait(self, gen, interval=0.1, timeout=None):
        # psycopg 3.3.6 exposes a timeout on its socket-wait implementation.
        # Keep an explicitly shorter deadline if a caller supplies one.
        timeout = self.wait_timeout if timeout is None else min(timeout, self.wait_timeout)
        try:
            return super().wait(gen, interval=interval, timeout=timeout)
        except _WaitTimeout as error:
            # Do not issue cancellation/rollback over the unresponsive socket.
            # Closing makes SQLAlchemy discard it; the server owns rollback of
            # an uncommitted transaction. A lost COMMIT reply is indeterminate.
            self.close()
            raise DatabaseWaitTimeout("Database response deadline exceeded.") from error


def connect_with_deadline(_dialect, _record, args, kwargs):
    return DeadlineConnection.connect(*args, **kwargs)


def is_database_timeout(error):
    original = getattr(error, "orig", None)
    return (isinstance(error, PoolTimeout) or isinstance(original, DatabaseWaitTimeout)
            or getattr(original, "sqlstate", None) in {"57014", "55P03", "25P04"})
