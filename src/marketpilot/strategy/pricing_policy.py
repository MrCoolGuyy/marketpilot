"""
MarketPilot Strategy - Pricing Policy.

Evaluates an abstract SignalIntent against a real ExecutableQuoteSnapshot
to determine realistic entry price and availability.
"""

from decimal import Decimal
import uuid
from marketpilot.models.causal import SignalIntent, ExecutableQuoteSnapshot, PricedCandidate, PricingStatus, SignalDirection

class PricingPolicy:
    """Deterministically prices a SignalIntent against a given quote."""
    
    def price_intent(self, intent: SignalIntent, quote: ExecutableQuoteSnapshot) -> PricedCandidate:
        """
        Prices a SignalIntent against an ExecutableQuoteSnapshot.
        
        Args:
            intent: The abstract trade intent.
            quote: The strictly causal executable quote.
            
        Returns:
            A PricedCandidate yielding either PRICED or UNPRICEABLE.
        """
        if quote.quote_timestamp < intent.signal_timestamp:
            return PricedCandidate(
                candidate_id=str(uuid.uuid4()),
                intent=intent,
                quote=quote,
                pricing_status=PricingStatus.UNPRICEABLE,
                executable_entry_price=Decimal("0"),
                rejection_reason=f"Quote timestamp ({quote.quote_timestamp}) precedes signal ({intent.signal_timestamp})"
            )
            
        if intent.direction == SignalDirection.LONG:
            # Entering LONG requires buying at the ASK
            entry_price = quote.ask
        elif intent.direction == SignalDirection.SHORT:
            # Entering SHORT requires selling at the BID
            entry_price = quote.bid
        else:
            return PricedCandidate(
                candidate_id=str(uuid.uuid4()),
                intent=intent,
                quote=quote,
                pricing_status=PricingStatus.UNPRICEABLE,
                executable_entry_price=Decimal("0"),
                rejection_reason="Cannot price a HOLD intent"
            )
            
        if entry_price <= 0:
            return PricedCandidate(
                candidate_id=str(uuid.uuid4()),
                intent=intent,
                quote=quote,
                pricing_status=PricingStatus.UNPRICEABLE,
                executable_entry_price=Decimal("0"),
                rejection_reason="Invalid or zero quote price"
            )
            
        return PricedCandidate(
            candidate_id=str(uuid.uuid4()),
            intent=intent,
            quote=quote,
            pricing_status=PricingStatus.PRICED,
            executable_entry_price=entry_price,
            rejection_reason=None
        )
