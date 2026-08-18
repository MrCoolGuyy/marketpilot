import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

from marketpilot.notifications.notification_models import NotificationEvent, NotificationType
from marketpilot.notifications.telegram_notifier import TelegramNotifier
from marketpilot.notifications.telegram_formatters import format_phase5_admission
from marketpilot.config.settings import TelegramSettings
from marketpilot.cli import _cmd_telegram
from marketpilot.models.causal import (
    FinalCandidate, PricedCandidate, SignalIntent, StrategyIdentity, SignalDirection,
    ExecutableQuoteSnapshot, PricingStatus, EvidenceAssessment, AssessmentStatus,
    PreSizeEconomics, SizingDecision, SizeAwareEconomics, Interval
)
from marketpilot.models.portfolio import (
    PortfolioAdmissionDecision, PortfolioExposureSnapshot, EquitySnapshot, PortfolioAllocationToken
)

@pytest.fixture
def sample_candidate_objects():
    test_candidate = FinalCandidate(
        candidate_id="test_cand_1",
        priced_candidate=PricedCandidate(
            candidate_id="test_cand_1",
            intent=SignalIntent(
                intent_id="test_int_1",
                identity=StrategyIdentity(
                    strategy_id="TEST_STRAT",
                    strategy_version="1.0",
                    registry_version="1.0",
                    parameter_set_id="default"
                ),
                symbol="BTCUSDT",
                timeframe=Interval.M5,
                direction=SignalDirection.LONG,
                signal_timestamp=0.0,
                signal_timestamp_us=0,
                logical_stop_loss=Decimal("49000"),
                logical_take_profit=Decimal("55000"),
                provenance_snapshot_id="test_prov"
            ),
            quote=ExecutableQuoteSnapshot(
                quote_id="test_q_1",
                environment="MAINNET",
                quote_timestamp=0.0,
                symbol="BTCUSDT",
                bid=Decimal("50000"),
                ask=Decimal("50000")
            ),
            pricing_status=PricingStatus.PRICED,
            executable_entry_price=Decimal("50000")
        ),
        assessment=EvidenceAssessment(
            assessment_id="test_ass",
            status=AssessmentStatus.VALIDATED,
            approved_expected_gross_r=Decimal("1.5")
        ),
        pre_size_economics=PreSizeEconomics(
            approved_expected_gross_r=Decimal("1.5"),
            pre_size_expected_cost_r=Decimal("0.1"),
            pre_size_net_ev_r=Decimal("1.4"),
            cost_model_provenance="TEST"
        ),
        sizing=SizingDecision(
            sizing_id="test_size",
            provisional_quantity=Decimal("0.05"),
            effective_stop_price=Decimal("49000"),
            risk_policy_provenance="TEST"
        ),
        size_aware_economics=SizeAwareEconomics(
            size_aware_cost_r=Decimal("0.1"),
            final_net_ev_r=Decimal("1.4")
        ),
        is_eligible=True
    )

    test_decision = PortfolioAdmissionDecision(
        decision_id="test_dec",
        is_admitted=True,
        token=PortfolioAllocationToken(
            candidate_id="test_cand_1",
            decision_id="test_dec",
            strategy_id="TEST_STRAT",
            strategy_version="1.0",
            parameter_set_id="default",
            symbol="BTCUSDT",
            direction="LONG",
            sizing_id="test_size",
            effective_stop=Decimal("49000"),
            quantity=Decimal("0.05"),
            executable_entry=Decimal("50000"),
            candidate_risk_amount=Decimal("50.0"),
            final_net_ev=Decimal("1.4"),
            portfolio_snapshot_version="v1",
            equity_snapshot_version="v1",
            portfolio_policy_version="v1",
            reservation_identity="test_res",
            lineage_identity="test_lin",
            admission_timestamp=0.0
        )
    )

    test_exposure = PortfolioExposureSnapshot(
        exposure_version="v1",
        timestamp=0.0,
        active_position_ids=("pos_1",),
        reserved_allocation_ids=(),
        active_risk_amount=Decimal("150.0"),
        reserved_risk_amount=Decimal("0.0"),
        policy_limit_risk_amount=Decimal("1000.0"),
        policy_max_lineages=5,

    )

    test_equity = EquitySnapshot(
        snapshot_id="test_eq",
        version="1.0",
        captured_at=0.0,
        environment="PAPER",
        safe_account_fingerprint="test",
        configured_allocated_capital=Decimal("10000.0"),
        usable_account_value=Decimal("15000.0"),
        effective_risk_capital=Decimal("10000.0"),
        freshness_status="FRESH",
        provenance="TEST"
    )

    return test_candidate, test_decision, test_exposure, test_equity


@pytest.mark.asyncio
async def test_telegram_cli_test_command_does_not_send_enum_value():
    """
    Test that `uv run marketpilot telegram test --confirm` uses the
    canonical presentation formatter and NOT the literal 'PAPER_TRADE' string.
    """
    settings = MagicMock()
    settings.telegram = TelegramSettings(
        enabled=True,
        bot_token="fake:token",
        chat_id="123456"
    )

    with patch("marketpilot.cli.TelegramNotifier.notify", new_callable=AsyncMock) as mock_notify:
        await _cmd_telegram(settings, ["test", "--confirm"])

        mock_notify.assert_called_once()
        event: NotificationEvent = mock_notify.call_args[0][0]

        assert event.event_type == NotificationType.PAPER_TRADE
        assert "message" in event.message_data

        payload = event.message_data["message"]

        # Assert rich formatting elements
        assert "MARKETPILOT — TRADE CANDIDATE" in payload
        assert "NO_EVIDENCE" not in payload # It uses VALIDATED
        assert "Network Permit    : NOT ISSUED" in payload
        assert "Exchange Order    : NOT SUBMITTED" in payload
        assert payload != "PAPER_TRADE"

@pytest.mark.asyncio
async def test_telegram_notifier_transport_dumb_rendering(sample_candidate_objects):
    """
    Test that the TelegramNotifier accepts pre-rendered HTML and
    sends it to the API with parse_mode=HTML, without mutating it.
    """
    settings = TelegramSettings(
        enabled=True,
        bot_token="fake:token",
        chat_id="123456",
        send_trade=True
    )
    notifier = TelegramNotifier(settings)

    rendered_html = format_phase5_admission(*sample_candidate_objects)

    event = NotificationEvent(
        event_type=NotificationType.EXECUTION_SUCCESS,
        message_data={"message": rendered_html}
    )

    with patch.object(notifier, "_send_sync") as mock_send:
        await notifier.notify(event)

        mock_send.assert_called_once()
        sent_text = mock_send.call_args[0][0]
        assert sent_text == rendered_html

        # Verify HTML format tags are preserved
        assert "<b>ADMITTED</b>" in sent_text
        assert "<code>test_res</code>" in sent_text
        assert "<b>BTCUSDT — LONG</b>" in sent_text
