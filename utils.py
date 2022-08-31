import json
import logging
from datetime import datetime

from lms.djangoapps.branding import get_visible_courses
import pytz
from opaque_keys.edx.keys import CourseKey
from common.djangoapps.student.models import anonymous_id_for_user
from common.djangoapps.track.event_transaction_utils import (
    create_new_event_transaction_id,
    get_event_transaction_id,
    set_event_transaction_type,
)
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from eventtracking import tracker
from lms.djangoapps.course_api.api import get_effective_user
from lms.djangoapps.courseware import courses
from lms.djangoapps.courseware.models import StudentModule
from lms.djangoapps.grades.api import CourseGradeFactory
from lms.djangoapps.grades.constants import ScoreDatabaseTableEnum
from lms.djangoapps.grades.signals.handlers import (
    disconnect_submissions_signal_receiver,
)
from lms.djangoapps.grades.signals.signals import PROBLEM_RAW_SCORE_CHANGED
from lms.djangoapps.instructor.enrollment import _reset_module_attempts
from submissions import api as sub_api
from submissions.models import score_set
from xmodule.modulestore.django import modulestore
from xmodule.modulestore.exceptions import ItemNotFoundError


log = logging.getLogger(__name__)
USER_MODEL = get_user_model()


def answered_count(student_id, course_id):
    problems = StudentModule.objects.filter(
        student=student_id, course_id=course_id, module_type="problem"
    ) | StudentModule.objects.filter(
        student=student_id, course_id=course_id, module_type="drag-and-drop-v2"
    )
    if problems:
        answered = 0
        for s in problems:
            log.info(json.loads(s.state))
            if json.loads(s.state).get("correct_map"):
                answered += 1
            elif json.loads(s.state).get("item_state"):
                answered += 1
            elif json.loads(s.state).get("attempts"):
                answered += 1
        is_reset = json.loads(problems[0].state).get("resetcount")
        return answered, is_reset


def reset_student_attempts(
    course_id, student, module_state_key, requesting_user, delete_module=False
):
    user_id = anonymous_id_for_user(student, course_id)
    requesting_user = User.objects.get(username="staff")
    requesting_user_id = anonymous_id_for_user(requesting_user, course_id)
    submission_cleared = False
    try:
        # A block may have children. Clear state on children first.
        block = modulestore().get_item(module_state_key)
        if block.has_children:
            for child in block.children:
                try:
                    reset_student_attempts(
                        course_id,
                        student,
                        child,
                        requesting_user,
                        delete_module=delete_module,
                    )
                except StudentModule.DoesNotExist:
                    # If a particular child doesn't have any state, no big deal, as long as the parent does.
                    pass
        if delete_module:
            # Some blocks (openassessment) use StudentModule data as a key for internal submission data.
            # Inform these blocks of the reset and allow them to handle their data.
            clear_student_state = getattr(block, "clear_student_state", None)
            if callable(clear_student_state):
                with disconnect_submissions_signal_receiver(score_set):
                    clear_student_state(
                        user_id=user_id,
                        course_id=str(course_id),
                        item_id=str(module_state_key),
                        requesting_user_id=requesting_user_id,
                    )
                submission_cleared = True
    except ItemNotFoundError:
        block = None
        log.warning(
            "Could not find %s in modulestore when attempting to reset attempts.",
            module_state_key,
        )
    if delete_module and not submission_cleared:
        sub_api.reset_score(
            user_id,
            course_id.to_deprecated_string(),
            module_state_key.to_deprecated_string(),
        )

    module_to_reset = StudentModule.objects.get(
        student_id=student.id, course_id=course_id, module_state_key=module_state_key
    )
    if delete_module:
        module_to_reset.delete()
        create_new_event_transaction_id()
        grade_update_root_type = "edx.grades.problem.state_deleted"
        set_event_transaction_type(grade_update_root_type)
        tracker.emit(
            str(grade_update_root_type),
            {
                "user_id": str(student.id),
                "course_id": str(course_id),
                "problem_id": str(module_state_key),
                "instructor_id": str(requesting_user.id),
                "event_transaction_id": str(get_event_transaction_id()),
                "event_transaction_type": str(grade_update_root_type),
            },
        )
        if not submission_cleared:
            _fire_score_changed_for_block(
                course_id,
                student,
                block,
                module_state_key,
            )
    else:
        _reset_module_attempts(module_to_reset)


def _fire_score_changed_for_block(
    course_id,
    student,
    block,
    module_state_key,
):
    """
    Fires a PROBLEM_RAW_SCORE_CHANGED event for the given module.
    The earned points are always zero. We must retrieve the possible points
    from the XModule, as noted below. The effective time is now().
    """
    if block and block.has_score:
        max_score = block.max_score()
        if max_score is not None:
            PROBLEM_RAW_SCORE_CHANGED.send(
                sender=None,
                raw_earned=0,
                raw_possible=max_score,
                weight=getattr(block, "weight", None),
                user_id=student.id,
                course_id=str(course_id),
                usage_id=str(module_state_key),
                score_deleted=True,
                only_if_higher=False,
                modified=datetime.datetime.now().replace(tzinfo=pytz.UTC),
                score_db_table=ScoreDatabaseTableEnum.courseware_student_module,
            )


def get_grades(course_id, student_id):
    student = USER_MODEL.objects.get(id=int(student_id))
    if isinstance(course_id, str):
        course_id = course_id.replace(" ", "+")
        course_id = CourseKey.from_string(course_id)
    course = courses.get_course_by_id(course_id)
    course_grade = CourseGradeFactory().read(student, course)
    courseware_summary = list(course_grade.chapter_grades.values())
    answered, reset, count = calculate_grade_stats(student.id, course.id, courseware_summary)
    return {
            "username": student.username,
            "passed": course_grade.passed,
            "percent": course_grade.percent,
            "letter_grade": course_grade.letter_grade,
            "courseware_summary": str(courseware_summary),
            "reset": reset,
        }


def calculate_grade_stats(student_id: str, course_id: str, courseware_summary: list = []) -> tuple:
    """
    Calculate if the course can be reset.
    """
    answered = 0
    reset = False
    if StudentModule.objects.filter(
        student=student_id, course_id=course_id, module_type="problem"
    ):
        answered, reset = answered_count(student_id, course_id)
    count = 0
    image_explorer_count = 0
    for sections in courseware_summary:
        for section in sections.get("sections", []):
            for item in section.problem_scores:
                if item.block_type == 'image-explorer':
                    image_explorer_count += 1

            count += sum([len(list(section.problem_scores))])
    count = count - image_explorer_count
    return answered, reset, count


def get_all_courses(user, org=None, filter_=None):
    """
    Returns a list of courses available, sorted by course.number optionally filtered by org code.
    """
    courses = get_visible_courses(org=org, filter_=filter_)
    return courses


def list_all_courses(request, username, org=None, filter_=None):
    """
    Utility to get all visible courses.
    """
    user = get_effective_user(request.user, username)
    return get_all_courses(user, org=org, filter_=filter_)

