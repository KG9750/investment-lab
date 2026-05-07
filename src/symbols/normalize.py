from __future__ import annotations


def _cn_exchange(code: str) -> str:
    if code.startswith(("6", "9")):
        return "SH"
    return "SZ"


def normalize_symbol(raw: str, market: str, provider: str = "manual") -> str:
    value = raw.strip().upper()
    provider = provider.lower()
    market = market.upper()
    if market == "US":
        return value
    if market == "CN":
        if value.endswith((".SZ", ".SH")):
            return value
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) != 6:
            raise ValueError(f"Cannot normalize CN symbol: {raw}")
        return f"{digits}.{_cn_exchange(digits)}"
    if market == "HK":
        if value.endswith(".HK"):
            digits = value.removesuffix(".HK")
            digits = digits[-4:].zfill(4)
            return f"{digits}.HK"
        digits = "".join(ch for ch in value if ch.isdigit())
        if not digits:
            raise ValueError(f"Cannot normalize HK symbol: {raw}")
        digits = digits[-4:]
        return f"{digits.zfill(4)}.HK"
    if market in {"ETF", "INDEX"}:
        return value
    raise ValueError(f"Unsupported market: {market}")


def denormalize_symbol(unified: str, market: str, target_provider: str = "manual") -> str:
    value = unified.strip().upper()
    provider = target_provider.lower()
    market = market.upper()
    if market == "US":
        return value
    if market == "CN":
        if provider == "akshare":
            return value.split(".")[0]
        return value
    if market == "HK":
        digits = value.removesuffix(".HK").zfill(4)
        if provider == "akshare":
            return "0" + digits if len(digits) == 4 and not digits.startswith("0") else digits
        return f"{digits}.HK"
    return value
