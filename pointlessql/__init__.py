"""PointlesSQL - web UI for open-source Databricks components."""

from importlib.metadata import PackageNotFoundError, version

from pointlessql.pql import PQL

try:
    __version__ = version("pointlessql")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = ["PQL", "__version__"]
