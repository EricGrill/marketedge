# marketedge/src/formulas.py
"""Quant formula engine for Kalshi weather prediction markets."""

from dataclasses import dataclass
from typing import Optional, Tuple, List
from datetime import datetime

from src.config import trading_config, weather_config


@dataclass
class EdgeAnalysis:
    """Result of edge calculation."""

    model_probability: float
    market_probability: float
    raw_edge: float
    fee_adjusted_edge: float
    fee_adjusted_breakeven: float
    is_tradeable: bool
    expected_value: float


@dataclass
class KellyResult:
    """Kelly criterion sizing result."""

    full_kelly_fraction: float
    fractional_kelly_fraction: float
    recommended_fraction: float
    max_position_size: float
    recommended_bet_dollars: float
    confidence_adjusted: bool


@dataclass
class IYResult:
    """Annualized yield analysis."""

    entry_price: float
    payout: float
    days_to_resolution: float
    annualized_yield: float
    is_above_threshold: bool


@dataclass
class LASResult:
    """Liquidity-adjusted spread analysis."""

    bid: float
    ask: float
    mid: float
    spread: float
    las_ratio: float
    is_liquid: bool
    recommended_size_reduction: float


@dataclass
class RiskMetrics:
    """Portfolio risk metrics."""

    risk_of_ruin: float
    max_drawdown_estimate: float
    sharpe_estimate: float
    var_95: float  # Value at Risk
    correlation_exposure: float


REGION_BY_CITY = {
    "NYC": "northeast",
    "BOS": "northeast",
    "PHL": "northeast",
    "CHI": "midwest",
    "DEN": "mountain",
    "SEA": "west",
    "LAX": "west",
    "SFO": "west",
    "MIA": "southeast",
    "ATL": "southeast",
    "AUS": "south",
    "HOU": "south",
    "PHX": "southwest",
}


class QuantEngine:
    """Core quant calculations for Kalshi weather trading."""

    def __init__(self, config=trading_config):
        self.config = config

    # ========== 1. EDGE DETECTION ==========

    def calculate_edge(
        self, model_probability: float, market_price: float, side: str = "yes"
    ) -> EdgeAnalysis:
        """
        Calculate edge with Kalshi's 3% settlement fee adjustment.

        Args:
            model_probability: Your model's estimated probability (0-1)
            market_price: Current market price in cents (0-100)
            side: 'yes' or 'no'
        """
        market_prob = market_price / 100.0

        if side == "no":
            market_prob = 1.0 - market_prob
            model_probability = 1.0 - model_probability

        raw_edge = model_probability - market_prob

        # Fee-adjusted breakeven: p_model / (1 + 0.03 * p_model)
        fee_adj_breakeven = model_probability / (
            1 + self.config.settlement_fee_pct * model_probability
        )
        fee_adj_edge = model_probability - max(market_prob, fee_adj_breakeven)

        # Expected value per dollar bet
        if side == "yes":
            ev = model_probability * (1 - market_price / 100) * (
                1 - self.config.settlement_fee_pct
            ) - ((1 - model_probability) * market_price / 100)
        else:
            ev = model_probability * (market_price / 100) * (
                1 - self.config.settlement_fee_pct
            ) - ((1 - model_probability) * (1 - market_price / 100))

        is_tradeable = fee_adj_edge > self.config.min_edge_pct and ev > 0

        return EdgeAnalysis(
            model_probability=model_probability,
            market_probability=market_prob,
            raw_edge=raw_edge,
            fee_adjusted_edge=fee_adj_edge,
            fee_adjusted_breakeven=fee_adj_breakeven,
            is_tradeable=is_tradeable,
            expected_value=ev,
        )

    # ========== 2. KELLY CRITERION ==========

    def kelly_sizing(
        self,
        edge_analysis: EdgeAnalysis,
        bankroll: float,
        confidence: float = 1.0,
        las_result: Optional[LASResult] = None,
    ) -> KellyResult:
        """
        Calculate position size using fractional Kelly with confidence adjustment.

        Args:
            edge_analysis: EdgeAnalysis object
            bankroll: Current bankroll in dollars
            confidence: Model confidence 0-1 (from ensemble spread)
            las_result: Liquidity analysis for size reduction
        """
        p = edge_analysis.model_probability
        market_prob = edge_analysis.market_probability

        # Kelly formula: f* = (p*(b+1) - 1) / b
        # where b = (1/market_prob) - 1
        if market_prob <= 0.01:
            b = 99.0
        else:
            b = (1.0 / market_prob) - 1.0

        if b <= 0:
            full_kelly = 0.0
        else:
            full_kelly = (p * (b + 1) - 1) / b

        # Fractional Kelly
        frac_kelly = full_kelly * self.config.kelly_fraction

        # Confidence adjustment
        confidence_adj = frac_kelly * confidence

        # LAS size reduction
        size_reduction = 1.0
        if las_result:
            size_reduction = 1.0 - las_result.recommended_size_reduction

        recommended_fraction = confidence_adj * size_reduction

        # Cap at max position size
        max_position = bankroll * self.config.max_position_pct
        recommended_dollars = min(bankroll * recommended_fraction, max_position)

        return KellyResult(
            full_kelly_fraction=full_kelly,
            fractional_kelly_fraction=frac_kelly,
            recommended_fraction=recommended_fraction,
            max_position_size=max_position,
            recommended_bet_dollars=recommended_dollars,
            confidence_adjusted=(confidence < 1.0),
        )

    # ========== 3. ANNUALIZED YIELD ==========

    def calculate_iy(
        self,
        entry_price: float,
        resolution_date: datetime,
        current_date: Optional[datetime] = None,
    ) -> IYResult:
        """
        Calculate annualized yield for screening opportunities.

        IY = (1 / price)^(365 / days) - 1
        """
        if current_date is None:
            current_date = datetime.utcnow()

        days_to_res = (resolution_date - current_date).days
        if days_to_res <= 0:
            days_to_res = 0.1  # Avoid division by zero

        price = entry_price / 100.0
        if price <= 0:
            price = 0.01

        annualized_yield = (1.0 / price) ** (365.0 / days_to_res) - 1.0

        return IYResult(
            entry_price=entry_price,
            payout=1.0,
            days_to_resolution=days_to_res,
            annualized_yield=annualized_yield,
            is_above_threshold=annualized_yield > self.config.min_iy_annualized,
        )

    # ========== 4. LIQUIDITY-ADJUSTED SPREAD ==========

    def calculate_las(self, bid: float, ask: float) -> LASResult:
        """
        Calculate liquidity-adjusted spread.

        LAS = (Ask - Bid) / Mid Price
        """
        mid = (bid + ask) / 2.0
        if mid <= 0:
            mid = 0.01

        spread = ask - bid
        las_ratio = spread / mid

        # Size reduction recommendations
        if las_ratio < 0.05:
            reduction = 0.0
            is_liquid = True
        elif las_ratio < 0.10:
            reduction = 0.25
            is_liquid = True
        elif las_ratio < 0.15:
            reduction = 0.50
            is_liquid = False
        else:
            reduction = 1.0  # Skip entirely
            is_liquid = False

        return LASResult(
            bid=bid,
            ask=ask,
            mid=mid,
            spread=spread,
            las_ratio=las_ratio,
            is_liquid=is_liquid,
            recommended_size_reduction=reduction,
        )

    # ========== 5. OVERROUND (Multi-Outcome) ==========

    def calculate_overround(self, market_prices: List[float]) -> float:
        """
        Calculate overround for multi-outcome weather events.

        Overround = sum(market_probs) - 1
        Positive = vig built in
        Negative = potential arbitrage
        """
        probs = [p / 100.0 for p in market_prices]
        return sum(probs) - 1.0

    # ========== 6. BAYESIAN UPDATE ==========

    def bayesian_update(
        self,
        prior_prob: float,
        likelihood_new_forecast: float,
        evidence_strength: float = 1.0,
    ) -> float:
        """
        Update probability with new forecast data.

        p_posterior ∝ p_prior * likelihood(evidence)
        """
        # Weighted update based on evidence strength (0-1)
        posterior = (prior_prob * likelihood_new_forecast * evidence_strength) / (
            (prior_prob * likelihood_new_forecast * evidence_strength)
            + ((1 - prior_prob) * (1 - likelihood_new_forecast) * evidence_strength)
        )

        # Smoothing to avoid extreme swings
        smoothed = 0.7 * posterior + 0.3 * prior_prob
        return max(0.01, min(0.99, smoothed))

    # ========== 7. WEATHER MODEL BLEND ==========

    def blend_weather_probabilities(
        self,
        ecmwf: float,
        gefs: float,
        analog: float,
        microclimate: float,
        nws_delta: float,
        ensemble_spread: float = 0.1,
    ) -> Tuple[float, float]:
        """
        Blend multiple weather model outputs into single probability + confidence.

        Returns:
            (blended_probability, confidence_score)
        """
        w = weather_config

        # Weighted blend
        blended = (
            ecmwf * w.ecmwf_weight
            + gefs * w.gefs_weight
            + analog * w.analog_weight
            + microclimate * w.microclimate_weight
            + nws_delta * w.nws_delta_weight
        )

        # Confidence based on ensemble spread
        # Low spread = high confidence, high spread = low confidence
        confidence = max(0.1, min(1.0, 1.0 - (ensemble_spread / 0.5)))

        return max(0.01, min(0.99, blended)), confidence

    # ========== 8. RISK OF RUIN ==========

    def calculate_ror(
        self, edge: float, bet_size_fraction: float, bankroll: float
    ) -> float:
        """
        Calculate risk of ruin.

        RoR = ((1 - edge) / (1 + edge))^(bankroll / bet_size)
        """
        if edge <= 0:
            return 1.0
        if bet_size_fraction <= 0 or bankroll <= 0:
            return 1.0

        base = (1.0 - edge) / (1.0 + edge)
        exponent = bankroll / (bankroll * bet_size_fraction)

        return base**exponent

    # ========== 9. PORTFOLIO CORRELATION EXPOSURE ==========

    def correlation_exposure(
        self,
        positions: List[dict],  # {ticker, size, region, event_type}
        new_position: dict,
    ) -> float:
        """
        Calculate correlation-weighted exposure for a new position.
        """
        total_correlated = 0.0

        for pos in positions:
            # Same region = high correlation
            # Same event type = medium correlation
            # Different everything = low correlation
            if pos.get("region") == new_position.get("region"):
                corr = 0.8
            elif pos.get("event_type") == new_position.get("event_type"):
                corr = 0.4
            else:
                corr = 0.1

            total_correlated += pos.get("size", 0) * corr

        new_exposure = new_position.get("size", 0)
        total_exposure = sum(p.get("size", 0) for p in positions) + new_exposure

        if total_exposure <= 0:
            return 0.0

        return (total_correlated + new_exposure) / total_exposure

    def summarize_correlated_risk(self, positions: List[dict], bankroll: float) -> dict:
        """Return dashboard-ready correlated exposure and scenario risk."""
        normalized = [_normalize_risk_position(pos) for pos in positions]
        normalized = [pos for pos in normalized if pos["exposure"] > 0]
        total_exposure = sum(pos["exposure"] for pos in normalized)

        groups = {
            "correlation_group": self._summarize_exposure_groups(
                normalized, "correlation_group", bankroll
            ),
            "city": self._summarize_exposure_groups(normalized, "city", bankroll),
            "region": self._summarize_exposure_groups(normalized, "region", bankroll),
            "event_type": self._summarize_exposure_groups(
                normalized, "event_type", bankroll
            ),
            "resolution_date": self._summarize_exposure_groups(
                normalized, "resolution_date", bankroll
            ),
        }

        overexposed_clusters = [
            group
            for group_list in groups.values()
            for group in group_list
            if group["overexposed"]
        ]

        return {
            "position_count": len(normalized),
            "total_exposure": round(total_exposure, 2),
            "exposure_pct_of_bankroll": _pct(total_exposure, bankroll),
            "worst_case_pnl": round(-total_exposure, 2),
            "likely_case_pnl": round(sum(pos["expected_pnl"] for pos in normalized), 2),
            "groups": groups,
            "overexposed_clusters": overexposed_clusters,
            "hedge_candidates": _find_hedge_candidates(normalized),
        }

    def _summarize_exposure_groups(
        self, positions: List[dict], category: str, bankroll: float
    ) -> List[dict]:
        grouped: dict[str, List[dict]] = {}
        for position in positions:
            grouped.setdefault(position[category], []).append(position)

        summaries = []
        for key, items in grouped.items():
            exposure = sum(item["exposure"] for item in items)
            likely_case_pnl = sum(item["expected_pnl"] for item in items)
            exposure_pct = _pct(exposure, bankroll)
            overexposed = exposure_pct > self.config.max_correlated_pct
            reason_codes = [f"grouped_by_{category}"]
            if overexposed:
                reason_codes.append("over_correlated_exposure_limit")
            if len(items) > 1:
                reason_codes.append("multiple_positions")
            summaries.append(
                {
                    "category": category,
                    "key": key,
                    "position_count": len(items),
                    "tickers": sorted(item["ticker"] for item in items),
                    "exposure": round(exposure, 2),
                    "exposure_pct_of_bankroll": exposure_pct,
                    "worst_case_pnl": round(-exposure, 2),
                    "likely_case_pnl": round(likely_case_pnl, 2),
                    "overexposed": overexposed,
                    "reason_codes": reason_codes,
                }
            )

        return sorted(
            summaries,
            key=lambda summary: (summary["exposure"], summary["position_count"]),
            reverse=True,
        )

    # ========== 10. COMPLETE OPPORTUNITY SCREEN ==========

    def screen_opportunity(
        self,
        model_prob: float,
        market_bid: float,
        market_ask: float,
        resolution_date: datetime,
        bankroll: float,
        ensemble_spread: float = 0.1,
        side: str = "yes",
    ) -> dict:
        """
        Full pipeline: screen a weather opportunity across all metrics.
        """
        entry_price = market_ask if side == "yes" else (100 - market_bid)

        # 1. Edge
        edge = self.calculate_edge(model_prob, entry_price, side)

        # 2. LAS
        las = self.calculate_las(market_bid, market_ask)

        # 3. IY
        iy = self.calculate_iy(entry_price, resolution_date)

        # 4. Kelly
        # Estimate confidence from ensemble spread
        confidence = max(0.1, min(1.0, 1.0 - (ensemble_spread / 0.5)))
        kelly = self.kelly_sizing(edge, bankroll, confidence, las)

        # 5. Risk
        ror = self.calculate_ror(
            edge.fee_adjusted_edge, kelly.recommended_fraction, bankroll
        )

        # 6. Pass/Fail
        passes = all(
            [
                edge.is_tradeable,
                iy.is_above_threshold,
                las.is_liquid,
                ror < self.config.max_ror_monthly,
                kelly.recommended_bet_dollars > 0,
            ]
        )

        return {
            "edge": edge,
            "las": las,
            "iy": iy,
            "kelly": kelly,
            "ror": ror,
            "passes_screen": passes,
            "recommended_action": "ENTER" if passes else "PASS",
            "entry_price": entry_price,
            "side": side,
        }


def _normalize_risk_position(position: dict) -> dict:
    ticker = str(position.get("ticker") or "UNKNOWN").upper()
    side = str(position.get("side") or "yes").lower()
    quantity = int(position.get("quantity") or 0)
    entry_price = float(position.get("entry_price") or 0)
    exposure = max(0.0, quantity * entry_price / 100.0)
    model_probability = _bounded_probability(position.get("model_probability"), 0.5)
    win_probability = model_probability if side == "yes" else 1.0 - model_probability
    expected_pnl = (win_probability * (1.0 - entry_price / 100.0)) - (
        (1.0 - win_probability) * entry_price / 100.0
    )
    city = _normalize_key(position.get("city") or position.get("location"), "unknown")
    event_type = _normalize_key(
        position.get("event_type") or position.get("weather_event_type"), "unknown"
    )
    resolution_date = _resolution_date_key(position.get("resolution_date"))
    region = _normalize_key(position.get("region"), "")
    if not region:
        region = REGION_BY_CITY.get(city.upper(), "unknown")
    correlation_group = _normalize_key(
        position.get("correlation_group") or position.get("correlated_group"),
        f"{city}:{event_type}:{resolution_date}",
    )

    return {
        "ticker": ticker,
        "side": side,
        "quantity": quantity,
        "entry_price": entry_price,
        "exposure": exposure,
        "expected_pnl": expected_pnl * quantity,
        "city": city,
        "region": region,
        "event_type": event_type,
        "resolution_date": resolution_date,
        "correlation_group": correlation_group,
    }


def _find_hedge_candidates(positions: List[dict]) -> List[dict]:
    candidates = []
    for index, left in enumerate(positions):
        for right_index in range(index + 1, len(positions)):
            right = positions[right_index]
            if left["side"] == right["side"]:
                continue
            if not _shares_risk_bucket(left, right):
                continue
            hedged_exposure = min(left["exposure"], right["exposure"])
            if hedged_exposure <= 0:
                continue
            candidates.append(
                {
                    "long_ticker": left["ticker"],
                    "short_ticker": right["ticker"],
                    "shared_group": (
                        left["correlation_group"]
                        if left["correlation_group"] == right["correlation_group"]
                        else f"{left['city']}:{left['event_type']}:{left['resolution_date']}"
                    ),
                    "hedged_exposure": round(hedged_exposure, 2),
                    "reason_codes": ["inverse_position", "shared_risk_bucket"],
                }
            )
    return sorted(candidates, key=lambda item: item["hedged_exposure"], reverse=True)


def _shares_risk_bucket(left: dict, right: dict) -> bool:
    return left["correlation_group"] == right["correlation_group"] or (
        left["city"] == right["city"]
        and left["event_type"] == right["event_type"]
        and left["resolution_date"] == right["resolution_date"]
    )


def _bounded_probability(value, default: float) -> float:
    try:
        probability = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.01, min(0.99, probability))


def _normalize_key(value, default: str) -> str:
    text = str(value or "").strip().lower()
    return text or default


def _resolution_date_key(value) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    text = str(value or "").strip()
    if not text:
        return "unknown"
    return text[:10]


def _pct(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)
