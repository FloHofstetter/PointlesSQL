"""Statement-type enum, parse-error class, and the ``PreparedSQL`` dataclass."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pointlessql.exceptions import ValidationError
from pointlessql.types import ErrorCode


class StmtType(StrEnum):
    """Classification of the top-level SQL statement.

    Drives dispatcher routing in
    :mod:`pointlessql.api.sql_dispatcher`.  Each value names the
    primitive family the dispatcher will route to (DuckDB rewriter,
    PQL primitive, or soyuz facade).
    """

    SELECT = "select"
    INSERT_FROM_SELECT = "insert_from_select"
    CREATE_TABLE_AS = "create_table_as"
    UPDATE = "update"
    DELETE = "delete"
    MERGE = "merge"
    DROP_TABLE = "drop_table"
    CREATE_SCHEMA = "create_schema"
    DROP_SCHEMA = "drop_schema"
    ALTER_TABLE = "alter_table"


class SQLParseError(ValidationError):
    """Raised when the SQL cannot be parsed or is out-of-scope.

    Subclass of :class:`ValidationError` (was :class:`ValueError`)
    so it inherits the 422 status_code and the
    :class:`PointlessSQLError` envelope path.  The dedicated
    ``sql_parse_error`` code lets dashboards filter SQL syntax
    failures separately from generic validation errors.

    Note: ``ValidationError`` itself dual-inherits :class:`ValueError`,
    so ``except ValueError`` continues to catch :class:`SQLParseError`.

    Attributes:
        error_code: Always ``ErrorCode.SQL_PARSE_ERROR``. ``status_code``
            inherits 422 from :class:`ValidationError`.
    """

    error_code: ErrorCode = ErrorCode.SQL_PARSE_ERROR


@dataclass(frozen=True)
class PreparedSQL:
    """A parsed SQL statement ready to hand to DuckDB.

    Attributes:
        refs: The distinct 3-part table names the query references,
            in first-appearance order.
        rewritten_sql: The SQL string with every 3-part reference
            collapsed to a single quoted identifier.  Safe to execute
            against a DuckDB connection that has each ref registered
            as a view at the identical dotted identifier.
    """

    refs: list[str]
    rewritten_sql: str
