"""The program of the SmartiLab cloud for Home Assistant: nothing to type, it is built in."""

from __future__ import annotations

from homeassistant.components.application_credentials import AuthorizationServer, ClientCredential
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow

from .const import AUTHORIZE_PATH, TOKEN_PATH
from .oauth import SmartiLabImplementation
from .urls import urls_of


async def async_get_authorization_server(hass: HomeAssistant) -> AuthorizationServer:
    urls = urls_of(hass)
    return AuthorizationServer(authorize_url=urls.browser + AUTHORIZE_PATH, token_url=urls.server + TOKEN_PATH)


async def async_get_auth_implementation(
    hass: HomeAssistant, auth_domain: str, credential: ClientCredential
) -> config_entry_oauth2_flow.AbstractOAuth2Implementation:
    urls = urls_of(hass)
    # The sign-in page opens in the browser; the token is asked by Home Assistant itself.
    return SmartiLabImplementation(hass, auth_domain, credential.client_id, urls.browser + AUTHORIZE_PATH, urls.server + TOKEN_PATH)
