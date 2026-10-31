"""
Simulated SMS gateway.

This module is the seam between ShambaTrack and a real SMS provider
(Africa's Talking, Twilio). The interface is deliberately tiny:

    send(recipient: str, content: str) -> GatewayResult

- In MVP: a simulated sender that fails ~sms_simulated_failure_rate of the
  time and otherwise returns success after a short sleep.
- In production: swap the implementation for an HTTP call to the provider.
  The rest of the code does not change.

The brief explicitly says real gateway integration is out of scope. What
matters is that the *boundary* is honest — everything above this module
behaves as if a real gateway were behind it.
"""

import logging
import random
import time
from dataclasses import dataclass

from app.core.config import settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GatewayResult:
    success: bool
    provider_message_id: str | None
    error: str | None


# Dedicated RNG so tests can seed it independently of other randomness.
_rng = random.Random()


def send(recipient: str, content: str) -> GatewayResult:
    """
    Simulate sending an SMS.

    Simulated latency and failure rate make the queue and retry behaviour
    observable during development and in the demo.

    A real implementation would:
      - POST to the provider with an API key from settings
      - Parse the provider's response for a message id
      - Return success/failure + error message
      - Time out after a few seconds
    """
    # Simulated network latency.
    time.sleep(0.05)

    if _rng.random() < settings.sms_simulated_failure_rate:
        return GatewayResult(
            success=False,
            provider_message_id=None,
            error="simulated gateway failure",
        )

    return GatewayResult(
        success=True,
        provider_message_id=f"sim-{int(time.time() * 1000)}",
        error=None,
    )
