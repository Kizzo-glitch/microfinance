"""
Fedha-Grow — payment gateway client
===================================
Talks to the Fedha-Grow payment gateway (a separate service) over its v1 API.

Configured in settings.PAYMENT_GATEWAY from environment variables:
    PAYMENT_GATEWAY_URL   e.g. http://127.0.0.1:8001  or the Railway URL
    PAYMENT_GATEWAY_KEY   the API key from `manage.py create_api_client`

Design rules (same as the rest of the integrations layer):
  * Not configured => GatewayNotConfigured. Never a fake success.
  * Lender credentials pass THROUGH to the gateway and are never stored here.
  * Every failure carries a stable `code` the UI can explain.
"""
import logging

import requests
from django.conf import settings
from django.utils.module_loading import import_string

log = logging.getLogger(__name__)


class GatewayError(Exception):
    def __init__(self, message, code="gateway_error", status=None):
        super().__init__(message)
        self.code = code
        self.status = status


class GatewayNotConfigured(GatewayError):
    def __init__(self):
        super().__init__("Instant collection isn't connected yet.", code="not_configured")


def _config() -> dict:
    return getattr(settings, "PAYMENT_GATEWAY", {}) or {}


def gateway_provider(fedha_provider: str):
    """Fedha-Grow provider code -> gateway provider name, or None if unsupported."""
    return (_config().get("providers") or {}).get(fedha_provider)


def supported_providers() -> set:
    return set((_config().get("providers") or {}).keys())


def get_gateway_client():
    cfg = _config()
    if cfg.get("client_class"):            # tests swap in FakeGatewayClient
        return import_string(cfg["client_class"])()
    if not cfg.get("base_url") or not cfg.get("api_key"):
        raise GatewayNotConfigured()
    return GatewayClient(cfg["base_url"], cfg["api_key"], timeout=cfg.get("timeout", 20))


class GatewayClient:
    def __init__(self, base_url, api_key, timeout=20, session=None):
        self.base = base_url.rstrip("/") + "/api/v1"
        self.api_key = api_key
        self.timeout = timeout
        self.session = session or requests.Session()

    def _request(self, method, path, body=None) -> dict:
        try:
            resp = self.session.request(
                method, f"{self.base}/{path}", json=body, timeout=self.timeout,
                headers={"Authorization": f"Bearer {self.api_key}"})
        except requests.RequestException as exc:
            log.warning("Payment gateway unreachable: %s", exc)
            raise GatewayError("The payment gateway couldn't be reached. Please try again.",
                               code="gateway_unreachable") from exc
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if resp.status_code >= 400:
            err = data.get("error") or {}
            raise GatewayError(err.get("message") or f"Gateway error ({resp.status_code}).",
                               code=err.get("code") or "gateway_error", status=resp.status_code)
        return data

    # ---- merchants ------------------------------------------------------
    def register_merchant(self, *, party_ref, provider, mode, merchant_code, display_name="",
                          credentials=None) -> dict:
        return self._request("POST", "merchants/", {
            "party_ref": party_ref, "provider": provider, "mode": mode,
            "merchant_code": merchant_code, "display_name": display_name,
            "credentials": credentials or {},
        })

    def get_merchant(self, merchant_id) -> dict:
        return self._request("GET", f"merchants/{merchant_id}/")

    def start_verification(self, merchant_id, msisdn) -> dict:
        return self._request("POST", f"merchants/{merchant_id}/verify/", {"msisdn": msisdn})

    def confirm_verification(self, merchant_id, otp) -> dict:
        return self._request("POST", f"merchants/{merchant_id}/verify/confirm/", {"otp": otp})

    def disable_merchant(self, merchant_id) -> dict:
        return self._request("POST", f"merchants/{merchant_id}/disable/")

    # ---- collections (borrower pays lender) -----------------------------
    def start_collection(self, *, source_ref, payer_ref, payee_ref, payer_account, amount,
                         reference, idempotency_key, provider, narration="") -> dict:
        return self._request("POST", "collections/", {
            "source_ref": source_ref, "payer_ref": payer_ref, "payee_ref": payee_ref,
            "payer_account": payer_account, "amount": str(amount), "reference": reference,
            "idempotency_key": idempotency_key, "provider": provider, "narration": narration,
        })

    def get_collection(self, collection_id) -> dict:
        return self._request("GET", f"collections/{collection_id}/")

    def submit_collection_otp(self, collection_id, otp) -> dict:
        return self._request("POST", f"collections/{collection_id}/otp/", {"otp": otp})


class FakeGatewayClient:
    """In-memory stand-in for tests. The OTP is always FAKE_OTP; client secret
    "bad" is rejected at verification, like wrong credentials would be."""

    FAKE_OTP = "1234"
    merchants: dict = {}
    collections: dict = {}
    calls: list = []
    fail_next_start = None        # set to a GatewayError to simulate a refusal/outage

    @classmethod
    def reset(cls):
        cls.merchants, cls.collections, cls.calls = {}, {}, []
        cls.fail_next_start = None

    def _view(self, m):
        data = {k: v for k, v in m.items() if k != "credentials"}
        return dict(data)

    def register_merchant(self, *, party_ref, provider, mode, merchant_code, display_name="",
                          credentials=None):
        self.calls.append(("register", party_ref, provider, mode, merchant_code))
        if mode == "direct" and not (credentials or {}).get("client_secret"):
            raise GatewayError("Direct mode needs credentials: client_secret.",
                               code="invalid_request", status=400)
        existing = next((m for m in self.merchants.values()
                         if m["party_ref"] == party_ref and m["provider"] == provider), None)
        mid = existing["id"] if existing else len(self.merchants) + 1
        self.merchants[mid] = {"id": mid, "party_ref": party_ref, "provider": provider,
                               "mode": mode, "merchant_code": merchant_code,
                               "credentials": credentials or {}, "status": "pending_verification",
                               "last_error": "", "verification": None}
        return self._view(self.merchants[mid])

    def get_merchant(self, merchant_id):
        return self._view(self.merchants[merchant_id])

    def start_verification(self, merchant_id, msisdn):
        self.calls.append(("verify", merchant_id, msisdn))
        m = self.merchants[merchant_id]
        if m["mode"] == "sub_merchant":
            m["status"], m["last_error"] = "failed", "Provider does not support sub-merchants yet."
            raise GatewayError(m["last_error"], code="not_supported_by_provider", status=400)
        if m["credentials"].get("client_secret") == "bad":
            m["status"], m["last_error"] = "failed", "Merchant credentials rejected"
            m["verification"] = {"status": "failed", "required_action": None,
                                 "amount": "1.00", "expires_at": None}
            return self._view(m)
        m["verification"] = {"status": "awaiting_action", "required_action": "otp",
                             "amount": "1.00", "expires_at": "2030-01-01T00:00:00+00:00"}
        return {**self._view(m), "test_otp": self.FAKE_OTP}

    def confirm_verification(self, merchant_id, otp):
        self.calls.append(("confirm", merchant_id, otp))
        m = self.merchants[merchant_id]
        ok = otp == self.FAKE_OTP
        m["status"] = "verified" if ok else "failed"
        m["last_error"] = "" if ok else "OTP does not match"
        m["verification"] = {"status": "succeeded" if ok else "failed", "required_action": None,
                             "amount": "1.00", "expires_at": None}
        return self._view(m)

    def disable_merchant(self, merchant_id):
        self.calls.append(("disable", merchant_id))
        m = self.merchants[merchant_id]
        m["status"], m["credentials"] = "disabled", {}
        return self._view(m)

    # ---- collections ------------------------------------------------------
    def start_collection(self, *, source_ref, payer_ref, payee_ref, payer_account, amount,
                         reference, idempotency_key, provider, narration=""):
        self.calls.append(("collect", payee_ref, payer_account, str(amount), idempotency_key))
        if FakeGatewayClient.fail_next_start is not None:
            exc, FakeGatewayClient.fail_next_start = FakeGatewayClient.fail_next_start, None
            raise exc
        for c in self.collections.values():           # idempotent, like the real gateway
            if c["idempotency_key"] == idempotency_key:
                return {**c, "test_otp": self.FAKE_OTP}
        merchant = next((m for m in self.merchants.values()
                         if m["party_ref"] == payee_ref and m["status"] == "verified"), None)
        if merchant is None:
            raise GatewayError("Merchant has not been verified", code="merchant_not_verified",
                               status=400)
        cid = f"00000000-0000-0000-0000-{len(self.collections) + 1:012d}"
        self.collections[cid] = {
            "id": cid, "status": "awaiting_action", "required_action": "otp",
            "amount": f"{amount}", "reference": reference, "idempotency_key": idempotency_key,
            "provider_transaction_id": "", "error_code": "", "error_message": "",
            "expires_at": "2030-01-01T00:00:00+00:00", "settles_to": merchant["merchant_code"]}
        return {**self.collections[cid], "test_otp": self.FAKE_OTP}

    def get_collection(self, collection_id):
        self.calls.append(("get_collection", collection_id))
        return dict(self.collections[collection_id])

    def submit_collection_otp(self, collection_id, otp):
        self.calls.append(("otp", collection_id, otp))
        c = self.collections[collection_id]
        if c["status"] != "awaiting_action":
            return dict(c)
        if otp == self.FAKE_OTP:
            c.update(status="succeeded", required_action=None,
                     provider_transaction_id=f"SIM-{collection_id[-6:]}")
        else:
            c.update(status="failed", required_action=None, error_code="INVALID_OTP",
                     error_message="OTP does not match")
        return dict(c)
