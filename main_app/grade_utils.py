"""
Grade calculation utilities for the Advanced Results System.
Uses school's GradingScale when configured, otherwise falls back to KNEC/KCSE or simple MVP scale.
"""
from .knec_utils import get_knec_grade, get_mean_grade_from_points

# Simple MVP grading scale (user-requested): 80-100 A, 70-79 B, 60-69 C, 50-59 D, <50 E
SIMPLE_MVP_GRADING = [
    (80, 100, ('A', 12, 'Excellent')),
    (70, 79, ('B', 10, 'Very Good')),
    (60, 69, ('C', 8, 'Good')),
    (50, 59, ('D', 6, 'Fair')),
    (0, 49, ('E', 4, 'Needs Improvement')),
]


def get_grade_for_marks(marks, school=None):
    """
    Get grade, points, and remarks for marks (0-100).
    Uses school's GradingScale when configured, else KNEC (KCSE), else simple MVP scale.
    Returns (grade, points, remarks) or (None, 0, '') for invalid marks.
    """
    if marks is None:
        return (None, 0, '')
    try:
        m = float(marks)
    except (TypeError, ValueError):
        return (None, 0, '')

    # 1. Try school's GradingScale first
    if school:
        from .models import GradingScale
        scale_qs = GradingScale.objects.filter(
            school=school,
            min_marks__lte=m,
            max_marks__gte=m,
            is_active=True
        ).order_by('-min_marks')
        scale = scale_qs.first()
        if scale:
            return (scale.grade, float(scale.points), scale.remarks or '')

    # 2. Fall back to KNEC (KCSE) - detailed 12-grade scale
    grade, points, remarks = get_knec_grade(m)
    if grade:
        return (grade, points, remarks)

    # 3. Fall back to simple MVP scale
    for min_m, max_m, (grade, points, remarks) in SIMPLE_MVP_GRADING:
        if min_m <= m <= max_m:
            return (grade, points, remarks)

    return (None, 0, '')


def get_mean_grade_from_points_school(mean_points, school=None):
    """
    Convert mean points to grade for overall mean grade on report card.
    Uses school's GradingScale when available (find grade by points), else KNEC.
    """
    if mean_points is None or mean_points <= 0:
        return 'E'

    # Try school's GradingScale - find grade whose points are closest
    if school:
        from .models import GradingScale
        scale = GradingScale.objects.filter(
            school=school,
            points__lte=mean_points,
            is_active=True
        ).order_by('-points').first()
        if scale:
            return scale.grade

    return get_mean_grade_from_points(mean_points)
