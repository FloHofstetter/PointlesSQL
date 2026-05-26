# SQL parsing

Two modules cover SQL handling on the PQL side:

- `pointlessql.pql.sql_parser` — parse + validate a
  user-submitted SQL string into a `PreparedSQL` envelope.
  Includes AST classification (`StmtType`, `classify`,
  `parse_and_classify`, `parse_batch`) and AST-inspection helpers
  (`extract_source_refs`, `extract_write_target`,
  `extract_table_refs`, `extract_column_lineage`).
- `pointlessql.pql.sql_merge_translator` — `sqlglot` MERGE AST →
  `PQL.merge` translator. Used by the SQL dispatcher so a
  user-submitted `MERGE INTO …` statement runs through the
  same audit-trail-emitting `PQL.merge` call as a Python caller.

## `pointlessql.pql.sql_parser`

::: pointlessql.pql.sql_parser
    options:
      show_root_heading: false
      filters:
        - "!^_"

## `pointlessql.pql.sql_merge_translator`

::: pointlessql.pql.sql_merge_translator
    options:
      show_root_heading: false
      filters:
        - "!^_"
