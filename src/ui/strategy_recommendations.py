from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyRecommendation:
    key: str
    title: str
    angle: str
    markets: tuple[str, ...]
    objectives: tuple[str, ...]
    horizons: tuple[str, ...]
    risks: tuple[str, ...]
    rationale: str
    best_when: str
    risk_note: str
    data_requirement: str
    screen_config_by_market: dict[str, str]
    backtest_config_by_market: dict[str, str]
    next_step: str


STRATEGY_LIBRARY = [
    StrategyRecommendation(
        key="trend_ma",
        title="趋势跟随：均线确认",
        angle="价格趋势",
        markets=("CN", "US"),
        objectives=("趋势确认", "稳健筛选", "数据优先"),
        horizons=("中期", "长期"),
        risks=("低", "中"),
        rationale="用 MA20 > MA60、收盘价站上长均线过滤趋势已经形成的标的。",
        best_when="市场处在单边或缓慢上行阶段，目标是少交易、少解释。",
        risk_note="震荡市容易反复打脸；必须配合数据新鲜度和交易成本检查。",
        data_requirement="需要连续日线、真实 provider、无 stale 标的。",
        screen_config_by_market={
            "CN": "configs/screens/trend_cn_real_core.yaml",
            "US": "configs/screens/us_momentum.yaml",
        },
        backtest_config_by_market={
            "CN": "configs/backtests/ma_cross_cn_real_core.yaml",
        },
        next_step="先跑 data-status，确认 research_ready 覆盖，再跑筛选。",
    ),
    StrategyRecommendation(
        key="momentum_rotation",
        title="动量轮动：强者恒强",
        angle="横截面动量",
        markets=("US", "CN"),
        objectives=("资产轮动", "趋势确认"),
        horizons=("中期",),
        risks=("中", "高"),
        rationale="比较同一股票池中近 60 日动量，优先选择相对强势资产。",
        best_when="资产之间分化明显，资金持续追逐强势方向。",
        risk_note="快速反转时回撤会集中出现；信号必须延后一日执行，避免未来函数。",
        data_requirement="需要同一股票池内标的日期对齐，避免 stale 或 synthetic-only 混入。",
        screen_config_by_market={
            "US": "configs/screens/us_momentum.yaml",
            "CN": "configs/screens/trend_cn_real_core.yaml",
        },
        backtest_config_by_market={
            "US": "configs/backtests/etf_rotation_us.yaml",
        },
        next_step="适合先在 ETF 池验证，再扩展到 A 股核心池。",
    ),
    StrategyRecommendation(
        key="low_vol_defensive",
        title="防守低波动：先活下来",
        angle="风险约束",
        markets=("US", "CN", "HK"),
        objectives=("防守低波动", "稳健筛选", "数据优先"),
        horizons=("中期", "长期"),
        risks=("低",),
        rationale="优先过滤低波动、低回撤、流动性稳定的标的，再叠加趋势或动量。",
        best_when="市场方向不清楚，目标是降低组合波动而不是追最高收益。",
        risk_note="可能长期落后强势成长行情；不要把低波动误读成无风险。",
        data_requirement="需要稳定成交量、足够长的历史窗口和异常价格检查。",
        screen_config_by_market={
            "US": "configs/screens/us_momentum.yaml",
        },
        backtest_config_by_market={},
        next_step="先用现有波动率因子做筛选，后续再补专门的低波策略配置。",
    ),
    StrategyRecommendation(
        key="liquidity_quality",
        title="流动性优先：减少脏成交",
        angle="可交易性",
        markets=("CN", "HK", "US"),
        objectives=("稳健筛选", "数据优先"),
        horizons=("短期", "中期"),
        risks=("低", "中"),
        rationale="先排除成交额不足、停牌疑似、缺日期、价格异常的标的，再讨论收益。",
        best_when="股票池扩大后，数据质量和可交易性比模型复杂度更重要。",
        risk_note="会过滤掉部分小盘弹性机会；但能减少不可成交回测幻觉。",
        data_requirement="需要 data-quality 无 blocking，且 research_ready 覆盖达到策略要求。",
        screen_config_by_market={
            "CN": "configs/screens/trend_cn_real_core.yaml",
        },
        backtest_config_by_market={},
        next_step="先看 data-status 中 missing、stale、synthetic-only、mixed provider。",
    ),
    StrategyRecommendation(
        key="mean_reversion",
        title="均值回归：超跌修复观察",
        angle="反转/修复",
        markets=("CN", "US"),
        objectives=("探索备选",),
        horizons=("短期",),
        risks=("高",),
        rationale="关注 RSI 偏低、短期跌幅较大但长期趋势未破坏的标的。",
        best_when="市场宽幅震荡，强趋势策略频繁被洗出。",
        risk_note="阶段一还没有专门配置；容易接飞刀，必须先做严格止损和样本外验证。",
        data_requirement="需要 RSI、回撤、ATR 和成交额因子，并明确延后一日成交。",
        screen_config_by_market={},
        backtest_config_by_market={},
        next_step="作为后续研究方向记录，暂不默认执行。",
    ),
]


def recommend_strategies(
    *,
    market: str,
    objective: str,
    horizon: str,
    risk: str,
    limit: int = 5,
) -> list[dict]:
    scored = []
    for item in STRATEGY_LIBRARY:
        score = 0
        score += 4 if market in item.markets else 0
        score += 3 if objective in item.objectives else 0
        score += 2 if horizon in item.horizons else 0
        score += 2 if risk in item.risks else 0
        if item.screen_config_by_market.get(market):
            score += 1
        if item.backtest_config_by_market.get(market):
            score += 1
        scored.append((score, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [_to_row(item, score, market) for score, item in scored[:limit]]


def _to_row(item: StrategyRecommendation, score: int, market: str) -> dict:
    screen_config = item.screen_config_by_market.get(market)
    backtest_config = item.backtest_config_by_market.get(market)
    return {
        "score": score,
        "key": item.key,
        "title": item.title,
        "angle": item.angle,
        "rationale": item.rationale,
        "best_when": item.best_when,
        "risk_note": item.risk_note,
        "data_requirement": item.data_requirement,
        "screen_config": screen_config,
        "backtest_config": backtest_config,
        "screen_command": (
            f"python -m src.cli screen --config {screen_config} --output json"
            if screen_config
            else None
        ),
        "backtest_command": (
            f"python -m src.cli backtest --config {backtest_config} --output json"
            if backtest_config
            else None
        ),
        "next_step": item.next_step,
    }
