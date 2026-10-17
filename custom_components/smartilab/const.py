"""Constants of the SmartiLab integration."""

from __future__ import annotations

import logging
from typing import Final

DOMAIN: Final = "smartilab"
LOGGER = logging.getLogger(__package__)

# The SmartiLab cloud. The same address serves the sign-in page (in the browser) and the API
# (from Home Assistant). A development console can split them: see CONF_SERVER in __init__.py.
DEFAULT_SERVER: Final = "https://smartilab.it"
API_PATH: Final = "/sc/api/v1"
AUTHORIZE_PATH: Final = "/sc/api/oauth/authorize"
TOKEN_PATH: Final = "/sc/api/oauth/token"
REVOKE_PATH: Final = "/sc/api/oauth/revoke"

# The program "Home Assistant" of the SmartiLab cloud: a public client, protected by PKCE.
CLIENT_ID: Final = "smartilab-home-assistant"
SCOPES: Final = "account devices:read devices:control"

# Configuration in configuration.yaml, only for who develops against another console.
CONF_SERVER: Final = "server"
CONF_BROWSER: Final = "browser"
DATA_URLS: Final = f"{DOMAIN}_urls"

MANUFACTURER: Final = "SmartiLab"

# How often the whole state is read again: often while the live channel is down, rarely while it
# brings every change by itself.
POLL_WITHOUT_LIVE: Final = 60
POLL_WITH_LIVE: Final = 900
