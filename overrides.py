"""Overrides for Open edX functions."""
import logging
from datetime import datetime

from common.djangoapps.edxmako.shortcuts import render_to_response
from common.djangoapps.util.db import outer_atomic
from django.conf import settings
from django.contrib.auth.models import (
    User,
)  # lint-amnesty, pylint: disable=imported-auth-user
from django.db.models import prefetch_related_objects, F
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
)
from django.utils.translation import ugettext as _

from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey
from xmodule.modulestore.django import modulestore

from amat_analytics.models import EmployeeResetCount


log = logging.getLogger("amat_extensions.overrides")


def change_enrollment(prev_func, request, check_access=True):
    from common.djangoapps.student.models import CourseEnrollment
    from lms.djangoapps.courseware.models import StudentModule
    from custom_views.views import reset_student_attempts

    # Get the user
    user = request.user

    # Ensure the user is authenticated
    if not user.is_authenticated:
        return HttpResponseForbidden()

    # Ensure we received a course_id
    action = request.POST.get("enrollment_action")
    if "course_id" not in request.POST:
        return HttpResponseBadRequest(_("Course id not specified"))

    try:
        course_id = CourseKey.from_string(request.POST.get("course_id"))
    except InvalidKeyError:
        log.warning(
            "User %s tried to %s with invalid course id: %s",
            user.username,
            action,
            request.POST.get("course_id"),
        )
        return HttpResponseBadRequest(_("Invalid course id"))

    if action == "reset":
        log.info("In Reset")
        if not CourseEnrollment.is_enrolled(user, course_id):
            return HttpResponseBadRequest(_("You are not enrolled in this course"))

        enrollment = CourseEnrollment.objects.filter(course_id=course_id, user=user).first()
        if enrollment:
            reset_count, created = EmployeeResetCount.objects.get_or_create(course_enrollment=enrollment)
            if created:
                reset_count.first_reset_date = datetime.now()

            reset_count.last_reset_date = datetime.now()
            reset_count.reset_count = F('reset_count') + 1
            reset_count.save()

        for exam in StudentModule.objects.filter(student=user, course_id=course_id):
            try:
                reset_student_attempts(
                    course_id, user, exam.module_state_key, None, True
                )
            except:
                pass
            exam.delete()
        return HttpResponse("/dashboard")
    return prev_func(request, check_access=check_access)


def progress(prev_func, request, course_key, student_id):
    """
    Override of the unwrapped version of "progress".
    User progress. We show the grade bar and every problem score.
    Course staff are allowed to see the progress of students in their class.
    """
    from lms.djangoapps.ccx.custom_exception import CCXLocatorValidationException
    from lms.djangoapps.courseware.access import has_access, has_ccx_coach_role
    from lms.djangoapps.courseware.courses import get_course_with_access, get_studio_url
    from lms.djangoapps.courseware.masquerade import setup_masquerade
    from lms.djangoapps.courseware.permissions import (
        MASQUERADE_AS_STUDENT,
    )  # lint-amnesty, pylint: disable=unused-import
    from common.djangoapps.student.models import CourseEnrollment
    from lms.djangoapps.grades.api import CourseGradeFactory
    from lms.djangoapps.courseware.views.views import (
        credit_course_requirements,
        get_cert_data,
    )
    from lms.djangoapps.experiments.utils import get_experiment_user_metadata_context
    from openedx.features.course_duration_limits.access import (
        generate_course_expired_fragment,
    )
    from custom_views.utils import calculate_grade_stats

    if student_id is not None:
        try:
            student_id = int(student_id)
        # Check for ValueError if 'student_id' cannot be converted to integer.
        except ValueError:
            raise Http404  # lint-amnesty, pylint: disable=raise-missing-from

    course = get_course_with_access(request.user, "load", course_key)

    staff_access = bool(has_access(request.user, "staff", course))
    can_masquerade = request.user.has_perm(MASQUERADE_AS_STUDENT, course)

    masquerade = None
    if student_id is None or student_id == request.user.id:
        # This will be a no-op for non-staff users, returning request.user
        masquerade, student = setup_masquerade(
            request, course_key, can_masquerade, reset_masquerade_data=True
        )
    else:
        try:
            coach_access = has_ccx_coach_role(request.user, course_key)
        except CCXLocatorValidationException:
            coach_access = False

        has_access_on_students_profiles = staff_access or coach_access
        # Requesting access to a different student's profile
        if not has_access_on_students_profiles:
            raise Http404
        try:
            student = User.objects.get(id=student_id)
        except User.DoesNotExist:
            raise Http404  # lint-amnesty, pylint: disable=raise-missing-from

    # NOTE: To make sure impersonation by instructor works, use
    # student instead of request.user in the rest of the function.

    # The pre-fetching of groups is done to make auth checks not require an
    # additional DB lookup (this kills the Progress page in particular).
    prefetch_related_objects([student], "groups")
    if request.user.id != student.id:
        # refetch the course as the assumed student
        course = get_course_with_access(
            student, "load", course_key, check_if_enrolled=True
        )

    # NOTE: To make sure impersonation by instructor works, use
    # student instead of request.user in the rest of the function.

    course_grade = CourseGradeFactory().read(student, course)
    courseware_summary = list(course_grade.chapter_grades.values())

    studio_url = get_studio_url(course, "settings/grading")
    # checking certificate generation configuration
    enrollment_mode, _ = CourseEnrollment.enrollment_mode_for_user(student, course_key)

    course_expiration_fragment = generate_course_expired_fragment(student, course)

    get_credit_enabled = True
    try:
        get_credit_enabled = course.get_credit_enabled
    except AttributeError:
        log.warning(f"No get_credit_enabled attribute in a course {course_key}")

    is_user_masquerade = False
    is_anonymous_student_masquerade = False
    if masquerade:
        is_user_masquerade = masquerade.user_name is not None and masquerade.user_name != request.user.username
        is_anonymous_student_masquerade = masquerade.user_name is None and masquerade.role != 'staff'

    context = {
        "course": course,
        "courseware_summary": courseware_summary,
        "studio_url": studio_url,
        "grade_summary": course_grade.summary,
        "can_masquerade": can_masquerade,
        "staff_access": staff_access,
        "masquerade": masquerade,
        "supports_preview_menu": True,
        "student": student,
        "credit_course_requirements": credit_course_requirements(course_key, student),
        "course_expiration_fragment": course_expiration_fragment,
        "certificate_data": get_cert_data(
            student, course, enrollment_mode, course_grade
        ),
        "get_credit_enabled": get_credit_enabled,
        "is_user_masquerade": is_user_masquerade,
        "is_anonymous_student_masquerade": is_anonymous_student_masquerade,
    }

    context.update(
        get_experiment_user_metadata_context(
            course,
            student,
        )
    )

    answered = 0
    reset = None
    if request.user.id != student.id:
        # refetch the course as the assumed student
        course = get_course_with_access(
            student, "load", course_key, check_if_enrolled=True
        )

    course_grade = CourseGradeFactory().read(student, course)
    courseware_summary = list(course_grade.chapter_grades.values())

    answered, reset, count = calculate_grade_stats(request.user.id, course.id, courseware_summary)
    progress_context = {
        "answered": answered,
        "count": count,
        "reset": reset,
        "passed": course_grade.passed,
    }

    context.update(progress_context)

    with outer_atomic():
        response = render_to_response("courseware/progress.html", context)

    return response

