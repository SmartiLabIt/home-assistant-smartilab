"""Adding SmartiLab: the sign-in page of the site with "Allow", then the account is in Home Assistant."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.components.application_credentials import ClientCredential, async_import_client_credential
from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlowResult
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SmartiLabApi, SmartiLabError, give_back
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
        """Signed in: whose account it is. One entry per account. An access that is not kept goes back to
        the cloud at once, so the Accesses of the console list only the ones Home Assistant uses."""
        token = str(data["token"]["access_token"])
        session = async_get_clientsession(self.hass)
        server = urls_of(self.hass).server

        async def access() -> str:
            return token

        api = SmartiLabApi(session, server, access, self.hass.config.language)
        try:
            me = await api.me()
        except SmartiLabError as err:
            LOGGER.warning("SmartiLab: the account could not be read: %s", err)
            await give_back(session, server, data.get("token"))
            return self.async_abort(reason="cannot_connect")
        account = str(me.get("email") or me.get("name") or "").strip().lower()
        if account == "":
            await give_back(session, server, data.get("token"))
            return self.async_abort(reason="cannot_connect")
        await self.async_set_unique_id(account)
        if self.source == SOURCE_REAUTH:
            entry = self._get_reauth_entry()
            if entry.unique_id != account:
                await give_back(session, server, data.get("token"))
                return self.async_abort(reason="wrong_account")
            # The new access takes the place of the old one, which goes back.
            await give_back(session, server, entry.data.get("token"))
            return self.async_update_reload_and_abort(entry, data=data)
        if any(e.unique_id == account for e in self._async_current_entries(include_ignore=False)):
            await give_back(session, server, data.get("token"))
            return self.async_abort(reason="already_configured")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=str(me.get("name") or me.get("email") or "SmartiLab"), data=data)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await self.async_step_user()
