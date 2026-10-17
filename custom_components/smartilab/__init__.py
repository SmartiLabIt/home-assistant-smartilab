"""SmartiLab: the devices of a SmartiLab account in Home Assistant, through the SmartiLab cloud.

Signing in is the sign-in page of the site with "Allow" (OAuth 2.0 with PKCE). The devices, what
they are made of and their values come from the API v1; every change arrives at once on the live
channel. A command goes to the device through the cloud, with the rights of the account.
"""

from __future__ import annotations

from dataclasses import dataclass

from aiohttp import ClientError
import voluptuous as vol

from homeassistant.components.application_credentials import ClientCredential, async_import_client_credential
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.config_entry_oauth2_flow import (
    ImplementationUnavailableError,
    OAuth2Session,
    async_get_config_entry_implementation,
)
from homeassistant.exceptions import OAuth2TokenRequestError, OAuth2TokenRequestReauthError
from homeassistant.helpers.typing import ConfigType

from .api import SmartiLabApi, SmartiLabError
from .const import CLIENT_ID, CONF_BROWSER, CONF_SERVER, DATA_URLS, DEFAULT_SERVER, DOMAIN
from .coordinator import SmartiLabCoordinator
from .live import LiveChannel
from .model import Point
from .urls import Urls, urls_of

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.LIGHT, Platform.NUMBER, Platform.SELECT,
             Platform.SENSOR, Platform.SWITCH, Platform.TEXT]

# Only for who develops against another console: where Home Assistant reaches it (server) and where a
# browser opens it (browser). Without, smartilab.it for both.
CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.Schema({vol.Optional(CONF_SERVER): cv.url, vol.Optional(CONF_BROWSER): cv.url})},
    extra=vol.ALLOW_EXTRA,
)


@dataclass
class SmartiLabRuntime:
    """What a loaded entry holds."""

    coordinator: SmartiLabCoordinator
    live: LiveChannel
    site: str

    def coordinator_points(self, platform: str) -> list[Point]:
        return [p for dev in (self.coordinator.data or {}).values() for p in dev.points if p.platform == platform]


type SmartiLabConfigEntry = ConfigEntry[SmartiLabRuntime]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    conf = config.get(DOMAIN) or {}
    server = str(conf.get(CONF_SERVER) or DEFAULT_SERVER).rstrip("/")
    hass.data[DATA_URLS] = Urls(server=server, browser=str(conf.get(CONF_BROWSER) or server).rstrip("/"))
    await async_import_client_credential(hass, DOMAIN, ClientCredential(CLIENT_ID, "", name="SmartiLab"))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SmartiLabConfigEntry) -> bool:
    try:
        implementation = await async_get_config_entry_implementation(hass, entry)
    except ImplementationUnavailableError as err:
        raise ConfigEntryNotReady(translation_domain=DOMAIN, translation_key="not_ready") from err
    session = OAuth2Session(hass, entry, implementation)

    async def access() -> str:
        """A valid access, renewed when it is about to expire."""
        try:
            await session.async_ensure_token_valid()
        except OAuth2TokenRequestReauthError as err:
            raise ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="auth_failed") from err
        except (OAuth2TokenRequestError, ClientError) as err:
            raise SmartiLabError(0, "unreachable", str(err)) from err
        return str(session.token["access_token"])

    urls = urls_of(hass)
    api = SmartiLabApi(async_get_clientsession(hass), urls.server, access, hass.config.language)
    coordinator = SmartiLabCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    live = LiveChannel(hass, entry, coordinator, api, urls.server, urls.browser)
    entry.runtime_data = SmartiLabRuntime(coordinator=coordinator, live=live, site=urls.browser)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    live.start()
    entry.async_on_unload(live.stop)

    # A device added or removed, a firmware that declares other things: the entry is loaded again,
    # so the entities are the ones the devices have now.
    known = coordinator.structure()

    def watch() -> None:
        if coordinator.data is not None and coordinator.structure() != known:
            hass.config_entries.async_schedule_reload(entry.entry_id)

    entry.async_on_unload(coordinator.async_add_listener(watch))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SmartiLabConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
