"""
Kenyan KCSE Grading System utilities.
Used for report card grade calculation per KCSE standards.
Marks (%) -> Grade, Points, Comment (auto-generated)
"""

# KCSE Grading Scale: (min_marks, max_marks) -> (grade, points, comment)
# Comments: A/A-=Excellent, B+/B=Very Good, B-/C+=Good, C/C-=Fair, D+/D=Needs Improvement, D-/E=Fail
KCSE_GRADING = [
    (80, 100, ('A', 12, 'Excellent')),
    (75, 79, ('A-', 11, 'Excellent')),
    (70, 74, ('B+', 10, 'Very Good')),
    (65, 69, ('B', 9, 'Very Good')),
    (60, 64, ('B-', 8, 'Good')),
    (55, 59, ('C+', 7, 'Good')),
    (50, 54, ('C', 6, 'Fair')),
    (45, 49, ('C-', 5, 'Fair')),
    (40, 44, ('D+', 4, 'Needs Improvement')),
    (35, 39, ('D', 3, 'Needs Improvement')),
    (30, 34, ('D-', 2, 'Fail')),
    (0, 29, ('E', 1, 'Fail')),
]
# Alias for backward compatibility
KNEC_GRADING = KCSE_GRADING


def get_knec_grade(marks):
    """
    Get KNEC grade, points, and remarks for a given mark (0-100).
    Returns (grade, points, remarks) or (None, 0, '') for invalid marks.
    """
    if marks is None:
        return (None, 0, '')
    try:
        m = float(marks)
    except (TypeError, ValueError):
        return (None, 0, '')
    for min_m, max_m, (grade, points, remarks) in KCSE_GRADING:
        if min_m <= m <= max_m:
            return (grade, points, remarks)
    return (None, 0, '')


def get_mean_grade_from_points(mean_points):
    """
    Convert mean points (average of subject points) to KNEC grade.
    Used for overall mean grade on report card.
    """
    if mean_points is None or mean_points <= 0:
        return 'E'
    # Find grade whose points are closest to mean_points (round up for benefit)
    best_grade = 'E'
    for min_m, max_m, (grade, points, _) in KCSE_GRADING:
        if mean_points >= points - 0.5:
            best_grade = grade
    return best_grade
