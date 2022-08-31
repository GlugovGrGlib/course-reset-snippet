""" API v0 views. """
import json
import logging
from datetime import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.http import HttpResponseBadRequest, JsonResponse
from django.utils.translation import ugettext as _
from django.views.decorators.http import require_GET
from rest_framework.generics import ListAPIView

from common.djangoapps.student.models import CourseEnrollment
from lms.djangoapps.courseware.models import StudentModule
from lms.djangoapps.course_api.api import list_courses
from opaque_keys.edx.keys import CourseKey
from edx_rest_framework_extensions.paginators import NamespacedPageNumberPagination
from openedx.core.lib.api.view_utils import DeveloperErrorViewMixin, view_auth_classes

from custom_views.utils import get_grades, reset_student_attempts, list_all_courses

log = logging.getLogger(__name__)
USER_MODEL = get_user_model()


def get_grades_api(request):
    """
    Get grades details providing student and course IDs.
    """
    course_id_raw = request.GET.get("course_id")
    student_id_raw = request.GET.get("student_id")
    if not course_id_raw or student_id_raw:
        return HttpResponseBadRequest("course_id and student_id parameters not valid")
    grades_details = get_grades(course_id_raw, student_id_raw)
    return JsonResponse(grades_details)


def service_reset_course(request):
    user_id = request.GET.get("user_id")
    user = User.objects.get(id=user_id)
    course_id = request.GET.get("course_id").replace(" ", "+")
    course_key = CourseKey.from_string(course_id)
    if not CourseEnrollment.is_enrolled(user, course_key):
        return HttpResponseBadRequest(_("You are not enrolled in this course"))
    for exam in StudentModule.objects.filter(student=user, course_id=course_id):
        log.error(exam.module_state_key)
        try:
            reset_student_attempts(course_id, user, exam.module_state_key, None, True)
        except:
            pass

    for exam in StudentModule.objects.filter(student=user, course_id=course_key):
        try:
            state = json.loads(exam.state)
            resetcount = 0
            if state.get("resetcount"):
                resetcount = state["resetcount"]
            state["attempts"] = 0
            exam.state = (
                '{"resetcount":' + str(resetcount + 1) + "}"
            )  # json.dumps(state)
            exam.delete()
        #                exam.save()
        except:
            pass
    return JsonResponse(
        {"Email": user.email, "User ID": user.id, "course_id": course_id}
    )

