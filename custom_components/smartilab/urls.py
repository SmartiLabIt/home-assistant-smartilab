"""Where the SmartiLab cloud is: smartilab.it, or a development console set in configuration.yaml."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.core import HomeAssistant

from .const import DATA_URLS, DEFAULT_SERVER


@dataclass(frozen=True)
class Urls:
    """``server``: as Home Assistant reaches it (API, token). ``browser``: as a browser opens it (sign-in page)."""

    server: str
    browser: str


def urls_of(hass: HomeAssistant) -> Urls:
    return hass.data.get(DATA_URLS) or Urls(DEFAULT_SERVER, DEFAULT_SERVER)
