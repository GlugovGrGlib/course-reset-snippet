# from lms.urls import urlpatterns

from django.conf.urls import url

from .views import (
    capture_credit_requested,
    credit_requested_details,
    get_grades_api,
    service_reset_course,
)

app_name = "custom_view"

urlpatterns = [
    url(
        r"^credit_requested$", capture_credit_requested, name="capture_credit_requested"
    ),
    url(
        r"^last_credit_request$",
        credit_requested_details,
        name="credit_requested_details",
    ),
    url(
        r"^services_reset_course/$",
        service_reset_course,
        name="capture_credit_requested",
    ),
    url(r"^get_grades_api", get_grades_api, name="get_grades_api"),
]
