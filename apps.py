"""
App configuration for amat_edx_extensions.
"""

from __future__ import unicode_literals

from django.apps import AppConfig
from openedx.core.djangoapps.plugins.constants import (
    PluginSettings,
    PluginURLs,
    ProjectType,
    SettingsType,
)

EXTENSIONS_APP_NAME = "custom_views"


class AMATCustomViewsConfig(AppConfig):
    """
    AMAT Open edX Plugin configuration.
    """

    name = EXTENSIONS_APP_NAME
    verbose_name = "AMAT Custom Views"

    # Class attribute that configures and enables this app as a Plugin App.
    plugin_app = {
        PluginURLs.CONFIG: {
            ProjectType.LMS: {
                PluginURLs.NAMESPACE: EXTENSIONS_APP_NAME,
                PluginURLs.APP_NAME: EXTENSIONS_APP_NAME,
                PluginURLs.REGEX: r"^",
                PluginURLs.RELATIVE_PATH: "urls",
            },
            ProjectType.CMS: {
                PluginURLs.NAMESPACE: EXTENSIONS_APP_NAME,
                PluginURLs.APP_NAME: EXTENSIONS_APP_NAME,
                PluginURLs.REGEX: r"^",
                PluginURLs.RELATIVE_PATH: "urls",
            },
        },
        PluginSettings.CONFIG: {
            ProjectType.LMS: {
                SettingsType.COMMON: {
                    PluginSettings.RELATIVE_PATH: "settings.common",
                },
                SettingsType.DEVSTACK: {
                    PluginSettings.RELATIVE_PATH: "settings.common",
                },
                SettingsType.TEST: {
                    PluginSettings.RELATIVE_PATH: "settings.test",
                },
                SettingsType.PRODUCTION: {
                    PluginSettings.RELATIVE_PATH: "settings.production",
                },
            },
            ProjectType.CMS: {
                SettingsType.COMMON: {
                    PluginSettings.RELATIVE_PATH: "settings.common",
                },
                SettingsType.DEVSTACK: {
                    PluginSettings.RELATIVE_PATH: "settings.common",
                },
                SettingsType.TEST: {
                    PluginSettings.RELATIVE_PATH: "settings.test",
                },
                SettingsType.PRODUCTION: {
                    PluginSettings.RELATIVE_PATH: "settings.production",
                },
            },
        },
    }
