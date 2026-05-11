from .base import REPORT_EVALUATION_TOOL, Risk
from .bonus_abuse import BONUS_ABUSE
from .latency_arbitrage import LATENCY_ARBITRAGE
from .scalping import SCALPING
from .swap_arbitrage import SWAP_ARBITRAGE


# Order is the canonical iteration order. Adding a new risk type is one
# import line + one entry here. The rest of the system keys off `Risk.key`.
ALL_RISKS: tuple[Risk, ...] = (
    LATENCY_ARBITRAGE,
    SCALPING,
    SWAP_ARBITRAGE,
    BONUS_ABUSE,
)


__all__ = [
    "ALL_RISKS",
    "BONUS_ABUSE",
    "LATENCY_ARBITRAGE",
    "REPORT_EVALUATION_TOOL",
    "Risk",
    "SCALPING",
    "SWAP_ARBITRAGE",
]
