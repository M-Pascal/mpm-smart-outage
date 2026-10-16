"""Phone validation and the WhatsApp Cloud API channel (HTTP mocked; nothing reaches Meta)."""
import logging

import httpx

from app.channels.base import OutboundMessage
from app.channels.mock import MockChannel
from app.channels.whatsapp_cloud import WhatsAppCloudChannel
from app.config import Config
from app.phone import is_valid, mask, normalize

TOKEN = "EAAG-secret-token-should-never-leak"
CONFIG = Config(whatsapp_mode="cloud", whatsapp_live_send_enabled=True, whatsapp_access_token=TOKEN,
                whatsapp_phone_number_id="1234567890", whatsapp_api_version="v26.0")
MSG = OutboundMessage(to="+250788123456", template="maintenance_reminder", language="en",
                      parameters=["PowerChat Energy", "Sector A", "1 hour"], body="text", reference="7-3")


def channel(handler) -> WhatsAppCloudChannel:
    return WhatsAppCloudChannel(CONFIG, client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_phone_normalisation():
    assert normalize("+250 788 123 456") == "+250788123456"
    assert normalize("0788123456", "250") == "+250788123456"
    assert normalize("00250788123456") == "+250788123456"
    assert normalize("250788123456", "250") == "+250788123456"
    assert normalize("0788123456") is None  # local number without a default country code
    assert normalize("12345", "250") is None and normalize("", "250") is None
    assert is_valid("+250788123456") and not is_valid("0788123456")
    assert mask("+250788123456") == "+250•••456"


def test_template_payload_and_success():
    seen = {}

    def handler(request: httpx.Request):
        seen["url"], seen["auth"], seen["json"] = str(request.url), request.headers["authorization"], request.read()
        return httpx.Response(200, json={"messaging_product": "whatsapp", "messages": [{"id": "wamid.ABC"}]})

    result = channel(handler).send(MSG)
    assert result.outcome == "accepted" and result.provider_message_id == "wamid.ABC"
    assert seen["url"] == "https://graph.facebook.com/v26.0/1234567890/messages"
    assert seen["auth"] == f"Bearer {TOKEN}"
    payload = WhatsAppCloudChannel.build_payload(MSG)
    assert payload["to"] == "250788123456" and payload["type"] == "template"
    assert payload["template"] == {"name": "maintenance_reminder", "language": {"code": "en"}, "components": [
        {"type": "body", "parameters": [{"type": "text", "text": "PowerChat Energy"},
                                        {"type": "text", "text": "Sector A"}, {"type": "text", "text": "1 hour"}]}]}


def test_rate_limit_is_retryable_and_uses_retry_after():
    result = channel(lambda r: httpx.Response(429, headers={"Retry-After": "12"}, json={
        "error": {"code": 130429, "message": "Rate limit hit"}})).send(MSG)
    assert result.outcome == "retryable_error" and result.error_code == "130429" and result.retry_after_seconds == 12


def test_undeliverable_and_template_errors_are_permanent():
    for code in (131026, 132001, 190, 131048):
        result = channel(lambda r, c=code: httpx.Response(400, json={"error": {"code": c, "message": "x"}})).send(MSG)
        assert result.outcome == "permanent_error", code


def test_server_error_is_retryable():
    assert channel(lambda r: httpx.Response(503, json={})).send(MSG).outcome == "retryable_error"


def test_connect_error_retryable_but_read_timeout_is_unknown():
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    def hang(request):
        raise httpx.ReadTimeout("timed out", request=request)

    assert channel(refuse).send(MSG).outcome == "retryable_error"
    unknown = channel(hang).send(MSG)
    assert unknown.outcome == "unknown" and unknown.error_code == "outcome_unknown"


def test_token_and_full_phone_never_logged(caplog):
    caplog.set_level(logging.DEBUG)
    channel(lambda r: httpx.Response(200, json={"messages": [{"id": "wamid.X"}]})).send(MSG)
    channel(lambda r: httpx.Response(400, json={"error": {"code": 131026, "message": "x"}})).send(MSG)
    text = caplog.text
    assert TOKEN not in text and "+250788123456" not in text and "250788123456" not in text


def test_mock_channel_is_deterministic_and_never_live():
    mock = MockChannel("whatsapp", failure_rate=0.5)
    first = [mock.send(OutboundMessage("+250788000001", "t", "en", [], "b", f"r{i}")) for i in range(40)]
    second = [mock.send(OutboundMessage("+250788000001", "t", "en", [], "b", f"r{i}")) for i in range(40)]
    assert [r.outcome for r in first] == [r.outcome for r in second]
    assert {"accepted", "retryable_error", "permanent_error"} <= {r.outcome for r in first}
    assert mock.simulated is True


def test_dotenv_parsing_strips_inline_comments():
    from pathlib import Path

    from app.config import parse_dotenv
    values = parse_dotenv(Path(__file__).resolve().parent.parent.joinpath(".env.example").read_text(encoding="utf-8")
                          + '\nQUOTED="a #b"\n')
    assert values["SEED_ON_STARTUP"] == "true" and values["WHATSAPP_ALLOWED_RECIPIENTS"] == ""
    assert values["WHATSAPP_API_VERSION"] == "v26.0" and values["QUOTED"] == "a #b"
