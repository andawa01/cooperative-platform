"""
Central model registry.

Every model MUST be imported here. Alembic's autogenerate reads Base.metadata,
and only imported models are registered in it. If you forget to import a model
here, Alembic will silently miss it and propose to DROP the table next run.
"""
from app.models.user import User  # noqa: F401

__all__ = ["User"]