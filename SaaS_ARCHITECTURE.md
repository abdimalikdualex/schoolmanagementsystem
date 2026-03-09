# MVP SaaS Architecture – Multi-School (Multi-Tenant) System

This document describes the architecture of the School Management System as an MVP SaaS platform where **each school's data stays isolated and safe**, and **system updates from Git only change code, never delete or mix data**.

---

## 1. Core Concept: Multi-Tenant School Architecture

**Rule:** Every record in the system belongs to a school.

All major models include a school reference (direct `school` ForeignKey or via a related model):

```
School (Tenant) → Users, Students, Staff, Results, Fees, etc.
```

---

## 2. School Model (Tenant)

```python
class School(models.Model):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True)  # e.g. SCH001
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    status = models.CharField(...)  # pending, approved, rejected, suspended
    is_active = models.BooleanField(default=True)
    # ...

    @property
    def is_approved(self):
        """True when school can access the system."""
        return self.status == 'approved'
```

- **status**: `pending` → `approved` (by Platform Owner) → school can use the system
- **is_approved**: Convenience property for `status == 'approved'`

---

## 3. User Linked to School

```python
class CustomUser(AbstractUser):
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True)
    user_type = models.CharField(...)  # HOD, Staff, Student, Parent, Finance Officer
```

| User Type | School | Access |
|-----------|--------|--------|
| Super Admin | `null` | Platform owner, manages all schools |
| HOD (Admin) | School A | School A only |
| Teacher | School A | School A only |
| Student | School A | School A only |
| Parent | School A | School A only |
| Finance Officer | School A | School A only |

Users cannot access other schools' data.

---

## 4. Models with School Link

All major models are scoped by school:

| Model | School Link | Notes |
|-------|-------------|-------|
| CustomUser | `school` FK | Direct |
| Session | `school` FK | Academic year/term |
| AcademicTerm | `school` FK | Term dates |
| GradeLevel | `school` FK | CBC/8-4-4 levels |
| Stream | `school` FK | Class streams |
| SchoolClass (Course) | `school` FK | Classes |
| Subject | via `course.school` | Course → School |
| Student | via `admin.school` | CustomUser → School |
| Staff | via `admin.school` | CustomUser → School |
| Parent | via `admin.school` | CustomUser → School |
| FeeType, FeeGroup | `school` FK | Fee structure |
| FeePayment | via `student.admin.school` | Student → School |
| ExamType, GradingScale | `school` FK | Exam config |
| SchoolSettings | `school` FK | Per-school settings |
| Notification | `school` FK | In-app notifications |
| SMSQueue, SMSLog | via `created_by.school` | User → School |

---

## 5. School Isolation Middleware

```python
class SchoolContextMiddleware:
    """Set request.school for multi-tenant data isolation."""
    def process_request(self, request):
        request.school = None
        if request.user.is_authenticated and hasattr(request.user, 'school'):
            school = getattr(request.user, 'school', None)
            if school is None:
                return None  # Super Admin
            if school.status != 'approved':
                logout(request)
                return redirect('login_page')
            request.school = school
        return None
```

- Super Admin: `request.school = None` (sees all schools)
- School users: `request.school = user.school` (only their school)
- Non-approved schools: logged out and redirected

---

## 6. Safe Data Access in Views

**Wrong:**
```python
students = Student.objects.all()
```

**Correct:**
```python
school = getattr(request, 'school', None)
students = Student.objects.filter(admin__school=school) if school else Student.objects.all()
```

- With `school`: filter by school
- With `school=None` (Super Admin): allow `.all()` for platform-wide views

---

## 7. SaaS School Registration Flow

### Step 1 – School Registers

1. School fills registration form
2. System creates:
   - `School` (status=`pending`)
   - `CustomUser` (HOD, `school` set)
   - `SchoolSettings` (defaults)

### Step 2 – Platform Owner Approves School

1. Super Admin opens Schools dashboard
2. Approves school: `school.status = 'approved'`
3. School can log in and use the system

### Step 3 – School Uses System

School admin can:

- Add teachers, students
- Record attendance
- Enter results
- Manage fees
- Send SMS

All records are linked to the school via `school_id` or `admin__school`.

---

## 8. Safe System Updates

When updating from Git:

```bash
git pull
pip install -r requirements.txt
python manage.py backup_db
python manage.py migrate
python manage.py collectstatic --noinput
```

**Result:**

- Database remains
- Schools remain
- Students, teachers, results remain
- New features and schema changes are applied

**Never run in production:**

- `python manage.py flush`
- `python manage.py reset_db`

---

## 9. Database Layout (Shared DB, Row-Level Isolation)

| School | Students | Teachers | Results |
|--------|----------|----------|---------|
| School A | 450 | 25 | 10,000 |
| School B | 300 | 18 | 7,000 |
| School C | 120 | 10 | 2,500 |

Same database, separated by `school_id` (or equivalent) on each table.

---

## 10. Deployment Architecture (MVP SaaS)

```
                Internet
                    │
                    ▼
            Django Application
                    │
                    ▼
         PostgreSQL / SQLite
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
     School A    School B    School C
```

- One codebase
- One database
- Data isolated by `school_id`

---

## 11. Protection Rules

1. **No flush/reset** in production
2. **Backup before migrate** (`python manage.py backup_db`)
3. **Filter by school** in all school-scoped views
4. **Middleware** sets `request.school` for every request
5. **Approval** required before school can access the system

---

## 12. MVP Feature Checklist

| Feature | Status |
|---------|--------|
| School registration | ✅ |
| Admin approval | ✅ |
| School-isolated users | ✅ |
| Student management | ✅ |
| Results system | ✅ |
| PDF report cards | ✅ |
| Notifications | ✅ |
| SMS alerts | ✅ |
| Safe updates | ✅ |
| Database backup before migrate | ✅ |

---

## 13. Future SaaS Scaling (After MVP)

- Subdomain per school: `schoolA.yoursystem.com`
- Separate database per school
- Billing / subscriptions
- API integrations

---

## 14. File Reference

| File | Purpose |
|------|---------|
| `main_app/models.py` | School, CustomUser, and school-scoped models |
| `main_app/middleware.py` | SchoolContextMiddleware |
| `main_app/super_admin_views.py` | School approval and platform management |
| `main_app/hod_views.py` | School admin views (filtered by school) |
| `DEPLOYMENT.md` | Safe update and deployment process |
| `main_app/management/commands/backup_db.py` | Database backup before migrations |
