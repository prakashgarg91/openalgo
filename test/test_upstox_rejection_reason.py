"""A rejected Upstox order shows Upstox's own reason, so a trader is not left guessing."""

from broker.upstox.mapping.order_data import transform_order_data


def _order(status, **extra):
    return {
        "tradingsymbol": "NIFTY09NOV2623850PE",
        "exchange": "NFO",
        "transaction_type": "BUY",
        "quantity": 65,
        "price": 158.75,
        "order_type": "LIMIT",
        "product": "NRML",
        "order_id": "261104000116600",
        "status": status,
        "order_timestamp": "2026-11-04 10:18:16",
        **extra,
    }


def test_a_rejected_order_carries_the_reason_upstox_gave():
    out = transform_order_data([_order("rejected", status_message="RMS:Margin Exceeds, Required:18000")])
    assert out[0]["order_status"] == "rejected"
    assert out[0]["rejection_reason"] == "RMS:Margin Exceeds, Required:18000"


def test_the_raw_message_is_used_when_the_plain_one_is_missing():
    out = transform_order_data([_order("rejected", status_message_raw="Price out of range")])
    assert out[0]["rejection_reason"] == "Price out of range"


def test_other_orders_keep_exactly_the_old_shape():
    out = transform_order_data([_order("complete", status_message="ignored")])
    assert "rejection_reason" not in out[0]
    out = transform_order_data([_order("rejected")])
    assert "rejection_reason" not in out[0]
