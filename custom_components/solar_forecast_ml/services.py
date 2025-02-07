import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, SupportsResponse
import homeassistant.helpers.config_validation as cv

from . import service_handlers_solar, service_handlers_consumption

# Import model functions from model.py
from .const import DOMAIN  # Define DOMAIN in const.py

_LOGGER = logging.getLogger(__name__)


def register_services(hass: HomeAssistant):
    hass.services.async_register(
        DOMAIN,
        "solar_train_from_history",
        service_handlers_solar.handle_train_from_history_service,
        schema=vol.Schema(
            {
                vol.Optional("days_back", default=60): cv.positive_int,
                vol.Optional("hours_offset", default=1): cv.positive_int,
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        "solar_train_from_csv",
        service_handlers_solar.handle_train_from_csv_service,
        schema=vol.Schema(
            {vol.Required("csv_file", default="pv_power.csv"): cv.string}
        ),
    )

    hass.services.async_register(
        DOMAIN,
        "solar_predict",
        service_handlers_solar.handle_predict_service,
        schema=vol.Schema(
            {
                vol.Required("from"): cv.datetime,
                vol.Required("to"): cv.datetime,
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )

    hass.services.async_register(
        DOMAIN,
        "consumption_train_from_history",
        service_handlers_consumption.handle_train_from_history_service,
        schema=vol.Schema(
            {
                vol.Optional("days_back", default=60): cv.positive_int,
                vol.Optional("hours_offset", default=1): cv.positive_int,
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        "consumption_train_from_csv",
        service_handlers_consumption.handle_train_from_csv_service,
        schema=vol.Schema(
            {vol.Required("csv_file", default="pv_power.csv"): cv.string}
        ),
    )

    hass.services.async_register(
        DOMAIN,
        "consumption_predict",
        service_handlers_consumption.handle_predict_service,
        schema=vol.Schema(
            {
                vol.Required("from"): cv.datetime,
                vol.Required("to"): cv.datetime,
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )
