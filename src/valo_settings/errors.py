"""User-facing errors. Every error carries a plain-English `user_message`."""

from __future__ import annotations


class ValoError(Exception):
    default_message = "Something went wrong."

    def __init__(self, user_message: str | None = None):
        self.user_message = user_message or self.default_message
        super().__init__(self.user_message)


class ClientNotRunning(ValoError):
    default_message = "Open the Riot Client and sign in."


class ClientNotReady(ValoError):
    default_message = "Riot Client isn't signed in yet — try again in a few seconds."


class ClientUnreachable(ValoError):
    default_message = "Couldn't talk to the Riot Client. Make sure it's open and signed in."


class AuthExpired(ValoError):
    default_message = "The Riot Client session changed. Click Refresh and try again."


class InvalidSettings(ValoError):
    default_message = "The Riot Client returned empty or unreadable settings."


class BackupFailed(ValoError):
    default_message = "Couldn't save a backup of the current settings, so nothing was changed."


class ProfileError(ValoError):
    default_message = "Profile error."


def raise_for_status(resp) -> None:
    """Map an HTTP response from the local Riot Client to a ValoError."""
    code = resp.status_code
    if 200 <= code < 300:
        return
    if code in (401, 403):
        raise AuthExpired()
    if code >= 500:
        raise ClientUnreachable()
    raise ClientNotReady()
