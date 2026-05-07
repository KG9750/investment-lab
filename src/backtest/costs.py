from __future__ import annotations


def total_one_way_cost(costs: dict) -> float:
    return float(costs.get("commission", 0)) + float(costs.get("slippage", 0))


def sell_cost(costs: dict) -> float:
    return total_one_way_cost(costs) + float(costs.get("stamp_tax_sell", 0))
