# Configuration package
# Exports settings singleton for application-wide configuration access.

from app.config.settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]
