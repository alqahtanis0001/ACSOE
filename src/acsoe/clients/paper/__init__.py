"""The paper broker — `context.clients.kraken` in paper mode.

Operator ruling 2026-09-16: the fill simulator is a client, not an engine, and it is B's.
See `README.md` in this directory for every fill rule and why each one is the pessimistic
reading.
"""

from acsoe.clients.paper.broker import FALLBACK_PAPER_LEDGER, PaperBroker, PaperBrokerError

__all__ = ["FALLBACK_PAPER_LEDGER", "PaperBroker", "PaperBrokerError"]
