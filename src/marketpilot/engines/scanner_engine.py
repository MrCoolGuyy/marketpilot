"""
MarketPilot Engines � Scanner Engine.

Deterministically ranks instruments based on Market Quality.
Pure analysis component: No DB, No Execution, No API calls.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Sequence

from marketpilot.config.settings import ScannerSettings
from marketpilot.models.scanner import InstrumentSnapshot, ScannerResult, TrendAge, EngineMetadata


class ScannerEngine:
    """Evaluates and ranks instruments based on market data snapshots."""

    def __init__(self, settings: ScannerSettings):
        self._settings = settings

    def _normalize_min_max(self, values: list[Decimal], invert: bool = False) -> list[Decimal]:
        """Normalize a list of Decimals to 0-100 scale using min-max."""
        if not values:
            return []
        min_val = min(values)
        max_val = max(values)
        diff = max_val - min_val

        normalized = []
        for val in values:
            if diff == Decimal("0"):
                normalized.append(Decimal("50")) # All values identical
            else:
                score = ((val - min_val) / diff) * Decimal("100")
                if invert:
                    score = Decimal("100") - score
                normalized.append(score)
        return normalized

    def _categorize_trend_age(self, candles: int) -> TrendAge:
        """Categorize trend age based on 1H candle count."""
        if candles <= 5:
            return TrendAge.NEW
        elif candles <= 24:
            return TrendAge.EARLY
        elif candles <= 72:
            return TrendAge.MATURE
        else:
            return TrendAge.LATE

    def evaluate(self, snapshots: Sequence[InstrumentSnapshot]) -> ScannerResult:
        """Evaluate a batch of snapshots and return a ranked ScannerResult."""
        start_time = time.time()
        
        if not snapshots:
            return ScannerResult(
                top_candidates=[], 
                market_health=Decimal("0"), 
                timestamp=time.time(),
                metadata=EngineMetadata(processing_time_ms=0.0)
            )

        # Separate valid vs invalid (failed absolute thresholds)
        valid_snapshots = []
        rejected_snapshots = []

        min_liq = Decimal(str(self._settings.minimum_liquidity))
        min_vol = Decimal(str(self._settings.minimum_volume))
        min_atr = Decimal(str(self._settings.minimum_atr_percent))
        max_spread = Decimal(str(self._settings.maximum_spread_bps))

        for snap in snapshots:
            if (snap.liquidity_turnover_24h < min_liq or
                snap.volume_24h < min_vol or
                snap.atr_percent < min_atr or
                snap.spread_bps > max_spread):
                rejected_snapshots.append(snap)
            else:
                valid_snapshots.append(snap)

        evaluated_snapshots = []
        
        # Calculate Market Health based on % of valid symbols
        market_health = Decimal("0")
        if snapshots:
            market_health = (Decimal(str(len(valid_snapshots))) / Decimal(str(len(snapshots)))) * Decimal("100")

        if not valid_snapshots:
            # Reconstruct rejected ones with 0 score
            for snap in rejected_snapshots:
                breakdown = {"Rejection": "Failed absolute thresholds"}
                evaluated_snapshots.append(
                    InstrumentSnapshot(
                        **snap.model_dump(exclude={"market_quality", "trend_age", "score_breakdown"}),
                        market_quality=Decimal("0"),
                        trend_age=self._categorize_trend_age(snap.trend_age_candles),
                        score_breakdown=breakdown
                    )
                )
            
            processing_time_ms = (time.time() - start_time) * 1000
            return ScannerResult(
                top_candidates=[],
                market_health=market_health.quantize(Decimal("0.01")),
                timestamp=time.time(),
                metadata=EngineMetadata(
                    processing_time_ms=processing_time_ms,
                    warnings=["No instruments passed absolute thresholds."]
                )
            )

        # Extract vectors for normalization on VALID snapshots only
        liquidity_vec = [s.liquidity_turnover_24h for s in valid_snapshots]
        spread_vec = [s.spread_bps for s in valid_snapshots]
        atr_vec = [s.atr_percent for s in valid_snapshots]
        momentum_vec = [abs(s.momentum_24h) for s in valid_snapshots] # Absolute momentum
        trend_str_vec = [s.trend_strength for s in valid_snapshots]
        funding_vec = [abs(s.funding_rate) if s.funding_rate is not None else Decimal("0") for s in valid_snapshots]
        oi_vec = [s.open_interest if s.open_interest is not None else Decimal("0") for s in valid_snapshots]
        age_vec = [Decimal(s.trend_age_candles) for s in valid_snapshots]

        # Normalize (0-100)
        norm_liq = self._normalize_min_max(liquidity_vec, invert=False)
        norm_spread = self._normalize_min_max(spread_vec, invert=True) # Lower spread is better
        norm_atr = self._normalize_min_max(atr_vec, invert=False)
        norm_mom = self._normalize_min_max(momentum_vec, invert=False)
        norm_tstr = self._normalize_min_max(trend_str_vec, invert=False)
        norm_fund = self._normalize_min_max(funding_vec, invert=False)
        norm_oi = self._normalize_min_max(oi_vec, invert=False)
        norm_age = self._normalize_min_max(age_vec, invert=True) # Younger trend is better

        for i, snap in enumerate(valid_snapshots):
            # Calculate weighted score (Penalty based on deviation from median/50 could be done, 
            # but standard is to map standard weights)
            # The prompt requested penalty display: "Spread +15, Funding -4"
            # To do that, we center the normalized score at 50, so <50 is negative penalty, >50 is positive bonus.
            # Base score = 50. Then we add/subtract based on weights.
            
            # Re-centering scores from -50 to +50
            centered_liq = norm_liq[i] - Decimal("50")
            centered_spread = norm_spread[i] - Decimal("50")
            centered_atr = norm_atr[i] - Decimal("50")
            centered_mom = norm_mom[i] - Decimal("50")
            centered_tstr = norm_tstr[i] - Decimal("50")
            centered_fund = norm_fund[i] - Decimal("50")
            centered_oi = norm_oi[i] - Decimal("50")
            centered_age = norm_age[i] - Decimal("50")
            
            score_liq = centered_liq * Decimal(str(self._settings.weight_liquidity))
            score_spread = centered_spread * Decimal(str(self._settings.weight_spread))
            score_atr = centered_atr * Decimal(str(self._settings.weight_atr))
            score_mom = centered_mom * Decimal(str(self._settings.weight_momentum))
            score_tstr = centered_tstr * Decimal(str(self._settings.weight_trend_strength))
            score_fund = centered_fund * Decimal(str(self._settings.weight_funding))
            score_oi = centered_oi * Decimal(str(self._settings.weight_open_interest))
            score_age = centered_age * Decimal(str(self._settings.weight_trend_age))

            # Total score = 50 (base) + all deviations
            total_score = (
                Decimal("50") + score_liq + score_spread + score_atr + score_mom + 
                score_tstr + score_fund + score_oi + score_age
            )
            
            # Bound it 0-100
            total_score = max(Decimal("0"), min(Decimal("100"), total_score))

            # Build human-readable breakdown with +/-
            def fmt_pts(val: Decimal) -> str:
                return f"+{val:.2f}" if val >= 0 else f"{val:.2f}"

            breakdown = {
                "Liquidity": fmt_pts(score_liq),
                "Spread": fmt_pts(score_spread),
                "ATR/Vol": fmt_pts(score_atr),
                "Momentum": fmt_pts(score_mom),
                "Trend Strength": fmt_pts(score_tstr),
                "Funding": fmt_pts(score_fund),
                "Open Interest": fmt_pts(score_oi),
                "Trend Age": fmt_pts(score_age),
                "Total Adjustment": fmt_pts(total_score - Decimal("50"))
            }

            # Create new snapshot with score
            evaluated_snapshots.append(
                InstrumentSnapshot(
                    **snap.model_dump(exclude={"market_quality", "trend_age", "score_breakdown"}),
                    market_quality=total_score.quantize(Decimal("0.01")),
                    trend_age=self._categorize_trend_age(snap.trend_age_candles),
                    score_breakdown=breakdown
                )
            )

        # Re-add rejected with 0 score
        for snap in rejected_snapshots:
            breakdown = {"Rejection": "Failed absolute thresholds"}
            evaluated_snapshots.append(
                InstrumentSnapshot(
                    **snap.model_dump(exclude={"market_quality", "trend_age", "score_breakdown"}),
                    market_quality=Decimal("0"),
                    trend_age=self._categorize_trend_age(snap.trend_age_candles),
                    score_breakdown=breakdown
                )
            )

        # Sort descending by score
        evaluated_snapshots.sort(key=lambda s: s.market_quality or Decimal("0"), reverse=True)
        
        # Filter top candidates (exclude rejected ones from top_candidates)
        valid_sorted = [s for s in evaluated_snapshots if "Rejection" not in s.score_breakdown]

        processing_time_ms = (time.time() - start_time) * 1000

        return ScannerResult(
            top_candidates=valid_sorted[:self._settings.max_results],
            market_health=market_health.quantize(Decimal("0.01")),
            timestamp=time.time(),
            metadata=EngineMetadata(processing_time_ms=processing_time_ms)
        )
