"""
mailtm_otp.py

A reusable Python class for creating temporary email addresses via the
Mail.tm API (https://api.mail.tm), waiting for incoming mail, and
extracting an OTP / verification code from the message.

Install dependency:
    pip install requests

Basic usage:
    from mailtm_otp import MailTmClient

    client = MailTmClient()
    email, password = client.create_account()
    print("Temp email:", email)

    # ... trigger an OTP email to `email` from whatever service you're testing ...

    otp = client.wait_for_otp(timeout=120)
    print("OTP:", otp)
"""

from __future__ import annotations

import random
import re
import string
import time
from dataclasses import dataclass
from typing import Any

import requests


BASE_URL = "https://api.mail.tm"


class MailTmError(Exception):
    """Raised for any Mail.tm API related failure."""


@dataclass
class MailMessage:
    id: str
    subject: str
    sender: str
    intro: str
    text: str
    html: str
    received_at: str


class MailTmClient:
    """
    A thin wrapper around the Mail.tm API that handles:
      - picking an active domain
      - creating a random disposable account
      - authenticating and holding a bearer token
      - polling the inbox for new messages
      - extracting an OTP code from a message via regex

    All methods raise MailTmError on unrecoverable API failures.
    """

    def __init__(self, base_url: str = BASE_URL, session: requests.Session | None = None):
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.email: str | None = None
        self.password: str | None = None
        self.token: str | None = None
        self.account_id: str | None = None

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _request(self, method: str, path: str, auth: bool = False, **kwargs) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {})
        if auth:
            if not self.token:
                raise MailTmError("No auth token set. Call create_account() or login() first.")
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            resp = self.session.request(method, url, headers=headers, timeout=30, **kwargs)
        except requests.RequestException as e:
            raise MailTmError(f"Network error calling {method} {url}: {e}") from e

        if resp.status_code >= 400:
            raise MailTmError(f"{method} {url} failed [{resp.status_code}]: {resp.text}")

        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    @staticmethod
    def _random_string(length: int = 10) -> str:
        chars = string.ascii_lowercase + string.digits
        return "".join(random.choice(chars) for _ in range(length))

    # ------------------------------------------------------------------ #
    # Account creation / auth
    # ------------------------------------------------------------------ #

    def get_active_domain(self) -> str:
        """Fetch a currently active Mail.tm domain."""
        data = self._request("GET", "/domains?page=1")
        domains = data.get("hydra:member") or data.get("member") or []
        active = [d for d in domains if d.get("isActive")]
        if not active:
            raise MailTmError("No active Mail.tm domains available right now.")
        return active[0]["domain"]

    def create_account(
        self,
        local_part: str | None = None,
        password: str | None = None,
    ) -> tuple[str, str]:
        """
        Create a new random disposable account and log in immediately.

        Returns (email, password).
        """
        domain = self.get_active_domain()
        local_part = local_part or self._random_string(12)
        password = password or self._random_string(16)
        email = f"{local_part}@{domain}"

        self._request(
            "POST",
            "/accounts",
            json={"address": email, "password": password},
        )

        self.email = email
        self.password = password
        self.login(email, password)
        return email, password

    def login(self, email: str, password: str) -> str | None:
        """Authenticate and store the bearer token. Returns the token."""
        data = self._request(
            "POST",
            "/token",
            json={"address": email, "password": password},
        )
        self.token = data["token"]
        self.email = email
        self.password = password

        me = self._request("GET", "/me", auth=True)
        self.account_id = me.get("id")
        return self.token

    # ------------------------------------------------------------------ #
    # Inbox handling
    # ------------------------------------------------------------------ #

    def list_messages(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/messages?page=1", auth=True)
        return data.get("hydra:member") or data.get("member") or []

    def get_message(self, message_id: str) -> MailMessage:
        data = self._request("GET", f"/messages/{message_id}", auth=True)
        sender = data.get("from", {}).get("address", "")
        return MailMessage(
            id=data.get("id", message_id),
            subject=data.get("subject", ""),
            sender=sender,
            intro=data.get("intro", ""),
            text=data.get("text", "") or "",
            html="".join(data.get("html", []) or []),
            received_at=data.get("createdAt", ""),
        )

    def wait_for_message(
        self,
        timeout: int = 120,
        poll_interval: float = 3.0,
        subject_contains: str | None = None,
        from_contains: str | None = None,
        seen_ids: set[str] | None = None,
    ) -> MailMessage:
        """
        Poll the inbox until a new message arrives (optionally matching
        subject/sender filters), or raise MailTmError on timeout.

        `seen_ids` lets you ignore messages that already existed before
        you started waiting (useful if the mailbox isn't brand new).
        """
        seen_ids = seen_ids or set()
        deadline = time.time() + timeout

        while time.time() < deadline:
            for msg in self.list_messages():
                if msg["id"] in seen_ids:
                    continue
                if subject_contains and subject_contains.lower() not in msg.get("subject", "").lower():
                    continue
                if from_contains and from_contains.lower() not in msg.get("from", {}).get("address", "").lower():
                    continue
                return self.get_message(msg["id"])
            time.sleep(poll_interval)

        raise MailTmError(f"Timed out after {timeout}s waiting for a matching message.")

    # ------------------------------------------------------------------ #
    # OTP extraction
    # ------------------------------------------------------------------ #

    @staticmethod
    def extract_otp(message: MailMessage, pattern: str = r"\b\d{4,8}\b") -> str | None:
        """
        Extract an OTP-like code from a message. Checks subject, intro,
        and plain-text body, in that order.

        Default pattern matches a standalone 4-8 digit number. Override
        `pattern` for services with alphanumeric or differently-shaped
        codes, e.g. r"\\b[A-Z0-9]{6}\\b".
        """
        haystacks = [message.subject, message.intro, message.text]
        for text in haystacks:
            if not text:
                continue
            match = re.search(pattern, text)
            if match:
                return match.group(0)
        return None

    def wait_for_otp(
        self,
        timeout: int = 120,
        poll_interval: float = 3.0,
        subject_contains: str | None = None,
        from_contains: str | None = None,
        otp_pattern: str = r"\b\d{4,8}\b",
        seen_ids: set[str] | None = None,
    ) -> str:
        """
        Convenience method: wait for a matching message, then extract
        the OTP from it. Raises MailTmError if no message arrives or
        no OTP-shaped code is found in it.
        """
        message = self.wait_for_message(
            timeout=timeout,
            poll_interval=poll_interval,
            subject_contains=subject_contains,
            from_contains=from_contains,
            seen_ids=seen_ids,
        )
        otp = self.extract_otp(message, pattern=otp_pattern)
        if not otp:
            raise MailTmError(
                f"Message received (subject={message.subject!r}) but no OTP matched pattern {otp_pattern!r}."
            )
        return otp
