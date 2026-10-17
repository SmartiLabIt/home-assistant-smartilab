"""Signing in with SmartiLab: OAuth 2.0 with PKCE, no secret (the program is public)."""

from __future__ import annotations

from typing import Any, override

from homeassistant.helpers import config_entry_oauth2_flow

from .const import SCOPES


class SmartiLabImplementation(config_entry_oauth2_flow.LocalOAuth2ImplementationWithPkce):
    """The sign-in page of the SmartiLab site, with "Allow"."""

    @property
    @override
    def name(self) -> str:
        return "SmartiLab"

    @property
    @override
    def extra_authorize_data(self) -> dict[str, Any]:
        # What Home Assistant may do: read the devices and command them, never more than the account can.
        # The name of this home goes with it: in the Accesses of the console the access reads
        # "Home Assistant · <name>", and two of them can be told apart.
        data: dict[str, Any] = {"scope": SCOPES}
        if self.hass.config.location_name:
            data["device_name"] = self.hass.config.location_name[:60]
        data.update(super().extra_authorize_data)
        return data
