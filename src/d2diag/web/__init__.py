"""Webbdashboard för realtidsdiagnostik (HTTP + SSE, stdlib).

`sources` levererar datasnapshots (Mock för UI-dev, Td5 för bilen); `server`
serverar dashboarden och strömmar snapshots via Server-Sent Events.
"""
from .sources import (
    DataSource,
    MockDataSource,
    MockSlabsDataSource,
    SlabsDataSource,
    Td5DataSource,
)

__all__ = [
    "DataSource", "MockDataSource", "Td5DataSource",
    "SlabsDataSource", "MockSlabsDataSource",
]
