"""
Fedha-Grow — SMSPortal gateway
==============================
The concrete SMS provider. This is your existing send_sms_smsportal function,
relocated and cleaned, wrapped as an adapter so it plugs into the integrations
registry (category "sms") — where, because it's really configured, it registers
as CONNECTED rather than pending.

Fixes applied during the move:
  - Sender ID now comes from its own SMS_SENDER_ID setting, not CLIENT_ID
    (CLIENT_ID is the API key; using it as the sender was a bug).
  - Dead `else` branch after raise_for_status() removed (unreachable).
The HTTP behaviour, number-cleaning, and error handling are otherwise unchanged.
"""

import logging
import requests
from requests.auth import HTTPBasicAuth
from django.conf import settings

logger = logging.getLogger(__name__)


class SmsPortalGateway:
    provider_name = "smsportal"

    def __init__(self, api_key=None, api_secret=None, sender_id=None, **kwargs):
        # Config comes from settings.INTEGRATIONS['sms']['config'], with a
        # fallback to top-level settings so existing deployments keep working.
        self.api_key = api_key or getattr(settings, "CLIENT_ID", None)
        self.api_secret = api_secret or getattr(settings, "SMS_API_SECRET", None)
        self.sender_id = sender_id or getattr(settings, "SMS_SENDER_ID", None)
        self.endpoint = "https://rest.smsportal.com/bulkmessages"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_secret)

    @staticmethod
    def _clean_number(number: str) -> str:
        number = (number or "").strip()
        if number.startswith("+"):
            number = number[1:]
        if number.startswith("00"):
            number = number[2:]
        return number

    def send(self, destination_number: str, message_content: str) -> dict:
        if not self.is_configured:
            logger.error("SMSPortal API Key or Secret is not configured.")
            return {"success": False, "error": "SMS service not configured."}

        destination_number = self._clean_number(destination_number)

        payload = {
            "messages": [
                {"content": message_content, "destination": destination_number}
            ]
        }
        if self.sender_id:
            payload["messages"][0]["source"] = self.sender_id

        try:
            response = requests.post(
                self.endpoint,
                auth=HTTPBasicAuth(self.api_key, self.api_secret),
                json=payload,
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
            logger.info(f"SMS sent to {destination_number}: {data}")
            return {"success": True, "data": data}

        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error sending SMS to {destination_number}: {http_err} - {response.text}")
            return {"success": False, "error": f"HTTP Error: {http_err}"}
        except requests.exceptions.ConnectionError as conn_err:
            logger.error(f"Connection error sending SMS to {destination_number}: {conn_err}")
            return {"success": False, "error": "Connection error contacting SMS provider."}
        except requests.exceptions.Timeout as timeout_err:
            logger.error(f"Timeout sending SMS to {destination_number}: {timeout_err}")
            return {"success": False, "error": "SMS provider timed out."}
        except requests.exceptions.RequestException as req_err:
            logger.error(f"Request error sending SMS to {destination_number}: {req_err}")
            return {"success": False, "error": f"Request error: {req_err}"}
        except Exception as e:  # noqa: BLE001
            logger.error(f"Unexpected error sending SMS to {destination_number}: {e}")
            return {"success": False, "error": f"Unexpected error: {e}"}