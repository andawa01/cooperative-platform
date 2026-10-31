"""
Central model registry.

Every model MUST be imported here. Alembic's autogenerate reads Base.metadata,
and only imported models are registered in it. If you forget to import a model
here, Alembic will silently miss it and propose to DROP the table next run.
"""

from app.models.delivery import Delivery
from app.models.farmer import Farmer, FarmerStatus
from app.models.notification import (
    Notification,
    NotificationChannel,
    NotificationTemplate,
)
from app.models.payment import (
    Payment,
    PaymentAllocation,
    PaymentMethod,
    PaymentStatus,
)
from app.models.produce import ProduceLine, Rate
from app.models.user import User

__all__ = [
    "User",
    "Farmer",
    "FarmerStatus",
    "ProduceLine",
    "Rate",
    "Delivery",
    "Payment",
    "PaymentMethod",
    "PaymentStatus",
    "PaymentAllocation",
    "Notification",
    "NotificationChannel",
    "NotificationTemplate",
]
