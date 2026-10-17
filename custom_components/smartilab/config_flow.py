"""Adding SmartiLab: the sign-in page of the site with "Allow", then the account is in Home Assistant."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.components.application_credentials import ClientCredential, async_import_client_credential
from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlowResult
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SmartiLabApi, SmartiLabError
from .const import CLIENT_ID, DOMAIN, LOGGER
from .urls import urls_of


class OAuth2FlowHandler(config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN):
    """Signs in with SmartiLab."""

    DOMAIN = DOMAIN
    VERSION = 1

    @property
    def logger(self) -> logging.Logger:
        return LOGGER

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        # The program of the cloud is built in: nobody types an identifier.
        await async_import_client_credential(self.hass, DOMAIN, ClientCredential(CLIENT_ID, "", name="SmartiLab"))
        return await super().async_step_user(user_input)

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Signed in: whose account it is. One entry per account."""
        token = str(data["token"]["access_token"])

        async def access() -> str:
            return token

        api = SmartiLabApi(async_get_clientsession(self.hass), urls_of(self.hass).server, access, self.hass.config.language)
        try:
            me = await api.me()
        except SmartiLabError as err:
            LOGGER.warning("SmartiLab: the account could not be read: %s", err)
            return self.async_abort(reason="cannot_connect")
        account = str(me.get("email") or me.get("name") or "").strip().lower()
        if account == "":
            return self.async_abort(reason="cannot_connect")
        await self.async_set_unique_id(account)
        if self.source == SOURCE_REAUTH:
            self._abort_if_unique_id_mismatch(reason="wrong_account")
            return self.async_update_reload_and_abort(self._get_reauth_entry(), data=data)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=str(me.get("name") or me.get("email") or "SmartiLab"), data=data)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await self.async_step_user()
