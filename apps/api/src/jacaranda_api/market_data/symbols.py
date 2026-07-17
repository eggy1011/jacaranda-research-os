from __future__ import annotations

import re

from jacaranda_api.market_data.errors import SymbolNormalizationError
from jacaranda_api.market_data.models import Exchange, Market, NormalizedSymbol

_CN_SYMBOL = re.compile(r"^(?P<code>[0-9]{6})\.(?P<suffix>SS|SH|SZ)$")
_US_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")


def normalize_symbol(raw_symbol: str) -> NormalizedSymbol:
    original = raw_symbol
    symbol = raw_symbol.strip().upper()
    cn_match = _CN_SYMBOL.fullmatch(symbol)
    if cn_match:
        code = cn_match.group("code")
        suffix = cn_match.group("suffix")
        if suffix in {"SS", "SH"}:
            return NormalizedSymbol(
                original=original,
                canonical=f"{code}.SS",
                provider_symbol=code,
                market=Market.CN_A,
                exchange=Exchange.SSE,
            )
        return NormalizedSymbol(
            original=original,
            canonical=f"{code}.SZ",
            provider_symbol=code,
            market=Market.CN_A,
            exchange=Exchange.SZSE,
        )

    if _US_SYMBOL.fullmatch(symbol) and not symbol.isdigit():
        return NormalizedSymbol(
            original=original,
            canonical=symbol,
            provider_symbol=symbol,
            market=Market.US,
            exchange=None,
        )

    raise SymbolNormalizationError
