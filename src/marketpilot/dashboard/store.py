"""
MarketPilot Dashboard - Projections and Read Store.
"""

from typing import Optional
from marketpilot.dashboard.models import MarketIntelligenceReadModel, EvidenceTraceabilityReadModel
from marketpilot.models.causal import ClosedInstrumentSnapshot, FinalCandidate

class DashboardProjection:
    """Projects canonical domain models into strictly read-only dashboard models."""
    
    @staticmethod
    def project_market_intelligence(snapshot: ClosedInstrumentSnapshot) -> MarketIntelligenceReadModel:
        return MarketIntelligenceReadModel(
            snapshot_id=snapshot.snapshot_id,
            snapshot_version=snapshot.snapshot_version,
            symbol=snapshot.symbol,
            timeframe=snapshot.interval.value,
            market_data_environment=snapshot.environment.value,
            candle_open_timestamp=snapshot.candle_open_time,
            candle_close_timestamp=snapshot.candle_close_time,
            snapshot_creation_timestamp=snapshot.creation_timestamp,
            open=str(snapshot.facts.open),
            high=str(snapshot.facts.high),
            low=str(snapshot.facts.low),
            close=str(snapshot.facts.close),
            volume=str(snapshot.facts.volume),
            turnover=str(snapshot.facts.turnover),
            spread_bps=str(snapshot.facts.spread_bps),
            atr_percent=str(snapshot.facts.atr_percent),
            momentum_24h=str(snapshot.facts.momentum_24h),
            trend_strength=str(snapshot.facts.trend_strength),
            trend_age_candles=snapshot.facts.trend_age_candles,
            funding_rate=str(snapshot.facts.funding_rate) if snapshot.facts.funding_rate is not None else None,
            open_interest=str(snapshot.facts.open_interest) if snapshot.facts.open_interest is not None else None,
            market_quality_score=str(snapshot.facts.market_quality_score) if snapshot.facts.market_quality_score is not None else None
        )
        
    @staticmethod
    def project_rejection(obs) -> EvidenceTraceabilityReadModel:
        # obs is CandidateRejectedObserved
        ident = obs.identity
        return EvidenceTraceabilityReadModel(
            # FACT
            snapshot_id=obs.snapshot_id,
            symbol=obs.symbol,
            signal_timestamp=obs.signal_timestamp,
            quote_id=obs.quote_id,
            quote_timestamp=obs.quote_timestamp,
            
            # STRATEGY OUTPUT
            strategy_id=ident.strategy_id,
            strategy_version=ident.strategy_version,
            parameter_set_id=ident.parameter_set_id,
            direction=obs.direction.value,
            logical_stop_loss=None,
            logical_take_profit=None,
            
            # CORE VALIDATION / ECONOMICS
            pricing_status=obs.pricing_status.value if hasattr(obs, "pricing_status") else "UNPRICEABLE",
            executable_entry_price=str(obs.executable_entry_price) if getattr(obs, "executable_entry_price", None) else None,
            
            evidence_status=obs.evidence_status.value if hasattr(obs, "evidence_status") else "INAPPLICABLE",
            approved_expected_gross_r=None,
            
            pre_size_expected_cost_r="0.0",
            pre_size_net_ev_r="0.0",
            
            sizing_id="",
            provisional_quantity="0.0",
            
            size_aware_cost_r="0.0",
            final_net_ev_r="0.0",
            
            is_eligible=False,
            rejection_reason=obs.rejection_reason,
            deterministic_rank=None,
            deterministic_decision_key=f"{obs.symbol}:{ident.strategy_id}:{ident.strategy_version}:{ident.parameter_set_id}:{obs.direction.value}"
        )
        
    @staticmethod
    def project_candidate(candidate: FinalCandidate, rank: Optional[int] = None) -> EvidenceTraceabilityReadModel:
        intent = candidate.priced_candidate.intent
        quote = candidate.priced_candidate.quote
        
        return EvidenceTraceabilityReadModel(
            # FACT
            snapshot_id=intent.provenance_snapshot_id,
            symbol=intent.symbol,
            signal_timestamp=intent.signal_timestamp,
            quote_id=quote.quote_id if quote else None,
            quote_timestamp=quote.quote_timestamp if quote else None,
            
            # STRATEGY OUTPUT
            strategy_id=intent.identity.strategy_id,
            strategy_version=intent.identity.strategy_version,
            parameter_set_id=intent.identity.parameter_set_id,
            direction=intent.direction.value,
            logical_stop_loss=str(intent.logical_stop_loss) if intent.logical_stop_loss else None,
            logical_take_profit=str(intent.logical_take_profit) if intent.logical_take_profit else None,
            
            # CORE VALIDATION / ECONOMICS
            pricing_status=candidate.priced_candidate.pricing_status.value,
            executable_entry_price=str(candidate.priced_candidate.executable_entry_price) if candidate.priced_candidate.executable_entry_price else None,
            
            evidence_status=candidate.assessment.status.value,
            approved_expected_gross_r=str(candidate.assessment.approved_expected_gross_r) if candidate.assessment.approved_expected_gross_r is not None else None,
            
            pre_size_expected_cost_r=str(candidate.pre_size_economics.pre_size_expected_cost_r),
            pre_size_net_ev_r=str(candidate.pre_size_economics.pre_size_net_ev_r),
            
            sizing_id=candidate.sizing.sizing_id,
            provisional_quantity=str(candidate.sizing.provisional_quantity),
            
            size_aware_cost_r=str(candidate.size_aware_economics.size_aware_cost_r),
            final_net_ev_r=str(candidate.size_aware_economics.final_net_ev_r),
            
            is_eligible=candidate.is_eligible,
            rejection_reason=candidate.rejection_reason,
            deterministic_rank=rank,
            deterministic_decision_key=candidate.deterministic_decision_key
        )


class DashboardReadStore:
    """
    Store for serving dashboard read requests.
    Wraps a durable FileProjectionRepository to ensure cross-process reads.
    If no repository is provided, falls back to in-memory (useful for tests).
    """
    
    def __init__(self, repository=None):
        from marketpilot.dashboard.projections import FileProjectionRepository
        self._repository = repository or FileProjectionRepository()
        
        # Keep memory state for purely local writes if needed, but primarily rely on repository
        self._intelligence_store: dict[str, MarketIntelligenceReadModel] = {}
        self._evidence_store: dict[str, EvidenceTraceabilityReadModel] = {}
        self._last_metadata: Optional[dict] = None
        
    def publish_market_observation(self, intelligence: list[MarketIntelligenceReadModel]):
        """Publish observations locally for Dashboard UI only. NEVER touches daemon projections."""
        new_intelligence = self._intelligence_store.copy()
        for model in intelligence:
            new_intelligence[model.symbol] = model
        self._intelligence_store = new_intelligence
        
    def get_market_intelligence(self, symbol: str) -> Optional[MarketIntelligenceReadModel]:
        # Always prefer durable repo
        res = self._repository.get_market_intelligence(symbol)
        if res:
            return res
        return self._intelligence_store.get(symbol)
        
    def save_evidence_traceability(self, model: EvidenceTraceabilityReadModel):
        """Deprecated. Should not be used. Included for compatibility if needed."""
        pass
            
    def get_evidence_traceability(self, decision_key: str) -> Optional[EvidenceTraceabilityReadModel]:
        res = self._repository.get_evidence_traceability(decision_key)
        if res:
            return res
        return self._evidence_store.get(decision_key)
        
    def get_all_evidence(self) -> list[EvidenceTraceabilityReadModel]:
        res = self._repository.get_all_evidence()
        if res:
            return res
        return list(self._evidence_store.values())
        
    def get_projection_metadata(self) -> Optional[dict]:
        """Fetch the raw metadata envelope to check staleness."""
        env = self._repository._read_safe_envelope(self._repository.evidence_file)
        if env and "metadata" in env:
            return env["metadata"]
        return None

    def get_lifecycle(self) -> Optional[dict]:
        """Fetch the daemon lifecycle projection."""
        return self._repository.get_lifecycle()

