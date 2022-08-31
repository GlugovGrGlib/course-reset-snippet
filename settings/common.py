"""
Common Django settings for amat_edx_extensions project.

For more information on this file, see
https://docs.djangoproject.com/en/1.11/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.11/ref/settings/
"""


def plugin_settings(settings):
    """
    Set of plugin settings used by the Open Edx platform.
    More info: https://github.com/edx/edx-platform/blob/master/openedx/core/djangoapps/plugins/README.rst
    """
    settings.ENABLE_CUSTOM_VIEWS = True
    settings.OVERRIDE_CHANGE_ENROLLMENT = "custom_views.overrides.change_enrollment"
    settings.OVERRIDE_PROGRESS = "custom_views.overrides.progress"
