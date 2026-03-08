from django import forms
from django.forms.widgets import DateInput, TextInput

from .models import *


class FormSettings(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(FormSettings, self).__init__(*args, **kwargs)
        # Here make some changes such as:
        for field in self.visible_fields():
            field.field.widget.attrs['class'] = 'form-control'


class CustomUserForm(FormSettings):
    email = forms.EmailField(required=True)
    gender = forms.ChoiceField(choices=[('M', 'Male'), ('F', 'Female')])
    first_name = forms.CharField(required=True)
    last_name = forms.CharField(required=True)
    phone_number = forms.CharField(max_length=15, required=False, help_text="Format: 254712345678 or 0712345678")
    address = forms.CharField(widget=forms.Textarea)
    password = forms.CharField(widget=forms.PasswordInput)
    widget = {
        'password': forms.PasswordInput(),
    }
    profile_pic = forms.ImageField(required=False)

    def __init__(self, *args, **kwargs):
        super(CustomUserForm, self).__init__(*args, **kwargs)

        if kwargs.get('instance'):
            instance = kwargs.get('instance').admin.__dict__
            self.fields['password'].required = False
            for field in CustomUserForm.Meta.fields:
                self.fields[field].initial = instance.get(field)
            if self.instance.pk is not None:
                self.fields['password'].widget.attrs['placeholder'] = "Fill this only if you wish to update password"

    def clean_email(self, *args, **kwargs):
        formEmail = self.cleaned_data['email'].lower()
        if self.instance.pk is None:  # Insert
            if CustomUser.objects.filter(email=formEmail).exists():
                raise forms.ValidationError(
                    "The given email is already registered")
        else:  # Update
            dbEmail = self.Meta.model.objects.get(
                id=self.instance.pk).admin.email.lower()
            if dbEmail != formEmail:  # There has been changes
                if CustomUser.objects.filter(email=formEmail).exists():
                    raise forms.ValidationError("The given email is already registered")

        return formEmail

    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'email', 'gender', 'phone_number', 'password','profile_pic', 'address' ]


class StudentForm(CustomUserForm):
    """MVP: Student admission - class/session optional (assigned at enrollment)"""
    date_of_birth = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    admission_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))

    def __init__(self, *args, **kwargs):
        school = kwargs.pop('school', None)
        super(StudentForm, self).__init__(*args, **kwargs)
        if 'course' in self.fields:
            self.fields['course'].label = 'Class'
            self.fields['course'].required = False
            if school:
                self.fields['course'].queryset = Course.objects.filter(school=school, is_active=True)
        if 'session' in self.fields:
            self.fields['session'].required = False
            if school:
                self.fields['session'].queryset = Session.objects.filter(school=school)

    class Meta(CustomUserForm.Meta):
        model = Student
        fields = CustomUserForm.Meta.fields + \
            ['course', 'session', 'date_of_birth', 'admission_date']


class AddStudentForm(forms.Form):
    """Add student - same format as Add Staff with manual admission number."""
    admission_number = forms.CharField(
        max_length=30,
        required=True,
        label='Admission Number',
        help_text='Enter unique admission number (e.g., 2026-001)'
    )
    first_name = forms.CharField(required=True)
    last_name = forms.CharField(required=True)
    email = forms.EmailField(required=True)
    gender = forms.ChoiceField(choices=[('M', 'Male'), ('F', 'Female')], required=True)
    phone_number = forms.CharField(max_length=15, required=False, help_text="Format: 254712345678 or 0712345678")
    password = forms.CharField(widget=forms.PasswordInput, required=True)
    profile_pic = forms.ImageField(required=False)
    address = forms.CharField(widget=forms.Textarea, required=True)
    course = forms.ModelChoiceField(
        queryset=Course.objects.none(),  # Set in __init__ from school
        required=True,
        label='Class',
        empty_label='--------'
    )
    guardian_name = forms.CharField(max_length=200, required=True, label="Guardian's Name")
    guardian_email = forms.EmailField(required=False, label="Guardian's Email")
    guardian_phone = forms.CharField(max_length=20, required=True, label="Guardian's Phone Number")

    def __init__(self, *args, **kwargs):
        school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        self._school = school
        if school:
            self.fields['course'].queryset = Course.objects.filter(school=school, is_active=True)
        else:
            self.fields['course'].queryset = Course.objects.none()
        for field in self.visible_fields():
            field.field.widget.attrs['class'] = 'form-control'

    def clean_email(self):
        email = self.cleaned_data.get('email', '').lower()
        if CustomUser.objects.filter(email=email).exists():
            raise forms.ValidationError("The given email is already registered")
        return email

    def clean_admission_number(self):
        admission_number = self.cleaned_data.get('admission_number', '').strip()
        if not admission_number:
            raise forms.ValidationError("Admission number is required.")
        qs = Student.objects.filter(admission_number__iexact=admission_number)
        if hasattr(self, '_school') and self._school:
            qs = qs.filter(admin__school=self._school)
        if qs.exists():
            raise forms.ValidationError("This admission number already exists.")
        return admission_number


class AdminForm(CustomUserForm):
    def __init__(self, *args, **kwargs):
        super(AdminForm, self).__init__(*args, **kwargs)

    class Meta(CustomUserForm.Meta):
        model = Admin
        fields = CustomUserForm.Meta.fields


class StaffForm(CustomUserForm):
    def __init__(self, *args, **kwargs):
        school = kwargs.pop('school', None)
        super(StaffForm, self).__init__(*args, **kwargs)
        self.fields['course'].label = 'Class'
        if school:
            self.fields['course'].queryset = Course.objects.filter(school=school, is_active=True)
        else:
            self.fields['course'].queryset = Course.objects.none()

    class Meta(CustomUserForm.Meta):
        model = Staff
        fields = CustomUserForm.Meta.fields + \
            ['course']


class FinanceOfficerForm(forms.Form):
    """Add Finance Officer - email, password, profile, no course."""
    first_name = forms.CharField(required=True)
    last_name = forms.CharField(required=True)
    email = forms.EmailField(required=True)
    gender = forms.ChoiceField(choices=[('M', 'Male'), ('F', 'Female')], required=True)
    phone_number = forms.CharField(max_length=15, required=False)
    address = forms.CharField(widget=forms.Textarea, required=True)
    password = forms.CharField(widget=forms.PasswordInput, required=True)
    profile_pic = forms.ImageField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.visible_fields():
            field.field.widget.attrs['class'] = 'form-control'

    def clean_email(self):
        email = self.cleaned_data.get('email', '').lower()
        if CustomUser.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is already registered")
        return email


class GradeLevelForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(GradeLevelForm, self).__init__(*args, **kwargs)

    class Meta:
        model = GradeLevel
        fields = ['code', 'name', 'stage', 'order_index', 'description', 'is_active']


class StreamForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(StreamForm, self).__init__(*args, **kwargs)

    class Meta:
        model = Stream
        fields = ['name', 'code']


class CourseForm(FormSettings):
    def __init__(self, *args, **kwargs):
        school = kwargs.pop('school', None)
        super(CourseForm, self).__init__(*args, **kwargs)
        self.fields['grade_level'].required = True
        self.fields['stream'].required = True
        self.fields['grade_level'].label = 'Grade Level'
        self.fields['stream'].label = 'Stream'
        if school:
            self.fields['grade_level'].queryset = GradeLevel.objects.filter(school=school, is_active=True)
            self.fields['stream'].queryset = Stream.objects.filter(school=school)
            self.fields['academic_year'].queryset = Session.objects.filter(school=school)
            self.fields['class_teacher'].queryset = Staff.objects.filter(admin__school=school)
        else:
            self.fields['grade_level'].queryset = GradeLevel.objects.none()
            self.fields['stream'].queryset = Stream.objects.none()
            self.fields['academic_year'].queryset = Session.objects.none()
            self.fields['class_teacher'].queryset = Staff.objects.none()

    class Meta:
        fields = ['name', 'grade_level', 'stream', 'academic_year', 'class_teacher', 'capacity', 'is_active']
        model = Course


class StudentClassEnrollmentForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(StudentClassEnrollmentForm, self).__init__(*args, **kwargs)
        if 'term' in self.fields:
            self.fields['term'].required = False  # Auto-set from active term

    class Meta:
        model = StudentClassEnrollment
        fields = ['student', 'school_class', 'academic_year', 'term', 'status', 'notes']


class BulkEnrollmentForm(forms.Form):
    """Form for bulk student enrollment"""
    students = forms.ModelMultipleChoiceField(
        queryset=Student.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=True
    )
    school_class = forms.ModelChoiceField(
        queryset=Course.objects.filter(is_active=True),
        required=True,
        label="Target Class"
    )
    academic_year = forms.ModelChoiceField(
        queryset=Session.objects.all(),
        required=True
    )

    def __init__(self, *args, **kwargs):
        super(BulkEnrollmentForm, self).__init__(*args, **kwargs)
        for field in self.visible_fields():
            if not isinstance(field.field.widget, forms.CheckboxSelectMultiple):
                field.field.widget.attrs['class'] = 'form-control'


class BulkPromotionForm(forms.Form):
    """Form for bulk student promotion"""
    from_class = forms.ModelChoiceField(
        queryset=Course.objects.filter(is_active=True),
        required=True,
        label="From Class"
    )
    to_class = forms.ModelChoiceField(
        queryset=Course.objects.filter(is_active=True),
        required=True,
        label="To Class"
    )
    from_academic_year = forms.ModelChoiceField(
        queryset=Session.objects.all(),
        required=True,
        label="From Academic Year"
    )
    to_academic_year = forms.ModelChoiceField(
        queryset=Session.objects.all(),
        required=True,
        label="To Academic Year"
    )
    students = forms.ModelMultipleChoiceField(
        queryset=Student.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Leave empty to promote all active students in the class"
    )

    def __init__(self, *args, **kwargs):
        super(BulkPromotionForm, self).__init__(*args, **kwargs)
        for field in self.visible_fields():
            if not isinstance(field.field.widget, forms.CheckboxSelectMultiple):
                field.field.widget.attrs['class'] = 'form-control'


class SubjectForm(FormSettings):

    def __init__(self, *args, **kwargs):
        school = kwargs.pop('school', None)
        super(SubjectForm, self).__init__(*args, **kwargs)
        self.fields['course'].label = 'Class'
        if school:
            self.fields['course'].queryset = Course.objects.filter(school=school, is_active=True)
            self.fields['staff'].queryset = Staff.objects.filter(admin__school=school)
        else:
            self.fields['course'].queryset = Course.objects.none()
            self.fields['staff'].queryset = Staff.objects.none()

    class Meta:
        model = Subject
        fields = ['name', 'staff', 'course']


class AcademicTermForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(AcademicTermForm, self).__init__(*args, **kwargs)
        self.fields['academic_year'].widget.attrs.update({
            'min': 2020, 'max': 2035, 'placeholder': 'e.g., 2025'
        })

    class Meta:
        model = AcademicTerm
        fields = ['academic_year', 'term_name', 'start_date', 'end_date', 'status']
        widgets = {
            'start_date': DateInput(attrs={'type': 'date'}),
            'end_date': DateInput(attrs={'type': 'date'}),
        }


class SessionForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(SessionForm, self).__init__(*args, **kwargs)
        self.fields['academic_year'].widget.attrs.update({
            'min': 2020, 'max': 2030, 'placeholder': 'e.g., 2026'
        })

    class Meta:
        model = Session
        fields = ['academic_year', 'term']


class LeaveReportStaffForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(LeaveReportStaffForm, self).__init__(*args, **kwargs)

    class Meta:
        model = LeaveReportStaff
        fields = ['date', 'message']
        widgets = {
            'date': DateInput(attrs={'type': 'date'}),
        }


class FeedbackStaffForm(FormSettings):

    def __init__(self, *args, **kwargs):
        super(FeedbackStaffForm, self).__init__(*args, **kwargs)

    class Meta:
        model = FeedbackStaff
        fields = ['feedback']


class LeaveReportStudentForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(LeaveReportStudentForm, self).__init__(*args, **kwargs)

    class Meta:
        model = LeaveReportStudent
        fields = ['date', 'message']
        widgets = {
            'date': DateInput(attrs={'type': 'date'}),
        }


class FeedbackStudentForm(FormSettings):

    def __init__(self, *args, **kwargs):
        super(FeedbackStudentForm, self).__init__(*args, **kwargs)

    class Meta:
        model = FeedbackStudent
        fields = ['feedback']


class StudentEditForm(CustomUserForm):
    def __init__(self, *args, **kwargs):
        super(StudentEditForm, self).__init__(*args, **kwargs)

    class Meta(CustomUserForm.Meta):
        model = Student
        fields = CustomUserForm.Meta.fields 


class StaffEditForm(CustomUserForm):
    def __init__(self, *args, **kwargs):
        super(StaffEditForm, self).__init__(*args, **kwargs)

    class Meta(CustomUserForm.Meta):
        model = Staff
        fields = CustomUserForm.Meta.fields


class EditResultForm(FormSettings):
    session_list = Session.objects.all()
    session_year = forms.ModelChoiceField(
        label="Session Year", queryset=session_list, required=True)

    def __init__(self, *args, **kwargs):
        super(EditResultForm, self).__init__(*args, **kwargs)

    class Meta:
        model = StudentResult
        fields = ['session_year', 'subject', 'student', 'test', 'exam']


class ParentForm(CustomUserForm):
    def __init__(self, *args, **kwargs):
        super(ParentForm, self).__init__(*args, **kwargs)

    class Meta(CustomUserForm.Meta):
        model = Parent
        fields = CustomUserForm.Meta.fields


class SectionForm(FormSettings):
    """Backward compatible - maps to StreamForm"""
    def __init__(self, *args, **kwargs):
        super(SectionForm, self).__init__(*args, **kwargs)

    class Meta:
        model = Stream
        fields = ['name', 'code']


class TimetableForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(TimetableForm, self).__init__(*args, **kwargs)

    class Meta:
        model = Timetable
        fields = ['course', 'subject', 'staff', 'day', 'start_time', 'end_time', 'room', 'session']
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }


class HomeworkForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(HomeworkForm, self).__init__(*args, **kwargs)

    class Meta:
        model = Homework
        fields = ['subject', 'course', 'title', 'description', 'due_date', 'attachment', 'max_marks', 'session']
        widgets = {
            'due_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'description': forms.Textarea(attrs={'rows': 4}),
        }


class HomeworkSubmissionForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(HomeworkSubmissionForm, self).__init__(*args, **kwargs)

    class Meta:
        model = HomeworkSubmission
        fields = ['submission_file', 'submission_text']
        widgets = {
            'submission_text': forms.Textarea(attrs={'rows': 4}),
        }


class AnnouncementForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(AnnouncementForm, self).__init__(*args, **kwargs)

    class Meta:
        model = Announcement
        fields = ['title', 'content', 'target_audience', 'target_course', 'attachment', 'expiry_date']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 5}),
            'expiry_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }


class MessageForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(MessageForm, self).__init__(*args, **kwargs)

    class Meta:
        model = Message
        fields = ['recipient', 'subject', 'content']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 5}),
        }


# ============================================
# SMS FORMS
# ============================================

class SMSTemplateForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(SMSTemplateForm, self).__init__(*args, **kwargs)

    class Meta:
        model = SMSTemplate
        fields = ['name', 'template_type', 'content', 'is_active']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Use placeholders: {student_name}, {parent_name}, {class_name}, {amount}, {date}, {school_name}'}),
        }


class BulkSMSForm(forms.Form):
    """Form for composing and sending bulk SMS"""
    RECIPIENT_CHOICES = [
        ('all_students', 'All Students'),
        ('all_parents', 'All Parents'),
        ('class_students', 'Students in Specific Class'),
        ('class_parents', 'Parents of Students in Class'),
        ('grade_students', 'Students in Grade Level'),
        ('grade_parents', 'Parents of Students in Grade'),
        ('custom', 'Custom Phone Numbers'),
    ]
    
    recipient_type = forms.ChoiceField(choices=RECIPIENT_CHOICES, required=True)
    course = forms.ModelChoiceField(
        queryset=Course.objects.filter(is_active=True),
        required=False,
        label="Select Class"
    )
    grade_level = forms.ModelChoiceField(
        queryset=GradeLevel.objects.filter(is_active=True),
        required=False,
        label="Select Grade Level"
    )
    template = forms.ModelChoiceField(
        queryset=SMSTemplate.objects.filter(is_active=True),
        required=False,
        label="Use Template"
    )
    message = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        required=True,
        help_text="Max 160 characters for single SMS. Use placeholders: {student_name}, {parent_name}, {class_name}, {school_name}"
    )
    custom_numbers = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Enter phone numbers, one per line'}),
        required=False,
        help_text="One phone number per line"
    )
    schedule_time = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        required=False,
        label="Schedule for Later (Optional)"
    )
    
    def __init__(self, *args, **kwargs):
        super(BulkSMSForm, self).__init__(*args, **kwargs)
        for field in self.visible_fields():
            field.field.widget.attrs['class'] = 'form-control'


# ============================================
# FEE FORMS
# ============================================

class FeeTypeForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(FeeTypeForm, self).__init__(*args, **kwargs)

    class Meta:
        model = FeeType
        fields = ['name', 'code', 'description', 'is_mandatory', 'is_recurring', 'is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class FeeGroupForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(FeeGroupForm, self).__init__(*args, **kwargs)

    class Meta:
        model = FeeGroup
        fields = ['name', 'description', 'is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
        }


class FeeGroupItemForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(FeeGroupItemForm, self).__init__(*args, **kwargs)

    class Meta:
        model = FeeGroupItem
        fields = ['fee_group', 'fee_type', 'amount']


class FeeStructureForm(FormSettings):
    def __init__(self, *args, **kwargs):
        school = kwargs.pop('school', None)
        super(FeeStructureForm, self).__init__(*args, **kwargs)
        if school:
            self.fields['fee_group'].queryset = FeeGroup.objects.filter(school=school)
            self.fields['session'].queryset = Session.objects.filter(school=school)
            self.fields['grade_level'].queryset = GradeLevel.objects.filter(school=school)
            self.fields['course'].queryset = Course.objects.filter(school=school)

    class Meta:
        model = FeeStructure
        fields = ['fee_group', 'grade_level', 'course', 'session', 'term', 'payment_schedule', 'due_date', 'is_active']
        widgets = {
            'due_date': DateInput(attrs={'type': 'date'}),
        }


class FeePaymentForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(FeePaymentForm, self).__init__(*args, **kwargs)

    class Meta:
        model = FeePayment
        fields = ['student', 'session', 'fee_type', 'amount', 'payment_mode', 'transaction_type', 'transaction_ref', 'payment_date', 'paid_by', 'description']
        widgets = {
            'payment_date': DateInput(attrs={'type': 'datetime-local'}),
            'description': forms.Textarea(attrs={'rows': 2}),
        }


class QuickPaymentForm(forms.Form):
    """Quick payment form for fee collection"""
    student = forms.ModelChoiceField(
        queryset=Student.objects.all(),
        required=True
    )
    amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=True,
        min_value=0.01
    )
    payment_mode = forms.ChoiceField(
        choices=FeePayment.PAYMENT_MODE_CHOICES,
        required=True
    )
    transaction_ref = forms.CharField(
        max_length=100,
        required=False,
        label="Transaction Reference"
    )
    notes = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 2}),
        required=False
    )
    
    def __init__(self, *args, **kwargs):
        super(QuickPaymentForm, self).__init__(*args, **kwargs)
        for field in self.visible_fields():
            field.field.widget.attrs['class'] = 'form-control'


# ============================================
# EXAM FORMS
# ============================================

class ExamTypeForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(ExamTypeForm, self).__init__(*args, **kwargs)

    class Meta:
        model = ExamType
        fields = ['name', 'code', 'weight', 'max_marks', 'is_active']


class ExamScheduleForm(FormSettings):
    def __init__(self, *args, **kwargs):
        school = kwargs.pop('school', None)
        super(ExamScheduleForm, self).__init__(*args, **kwargs)
        if school:
            if 'exam_type' in self.fields:
                self.fields['exam_type'].queryset = ExamType.objects.filter(school=school, is_active=True)
            if 'session' in self.fields:
                self.fields['session'].queryset = Session.objects.filter(school=school)

    class Meta:
        model = ExamSchedule
        fields = ['exam_type', 'session', 'term', 'name', 'start_date', 'end_date', 'is_published', 'is_active']
        widgets = {
            'start_date': DateInput(attrs={'type': 'date'}),
            'end_date': DateInput(attrs={'type': 'date'}),
        }


class GradingScaleForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(GradingScaleForm, self).__init__(*args, **kwargs)

    class Meta:
        model = GradingScale
        fields = ['name', 'min_marks', 'max_marks', 'grade', 'points', 'remarks', 'is_active']


class ExamResultForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(ExamResultForm, self).__init__(*args, **kwargs)

    class Meta:
        model = ExamResult
        fields = ['student', 'subject', 'exam_schedule', 'marks', 'teacher_comment']


class BulkResultEntryForm(forms.Form):
    """Form for bulk result entry"""
    exam_schedule = forms.ModelChoiceField(
        queryset=ExamSchedule.objects.filter(is_active=True),
        required=True
    )
    subject = forms.ModelChoiceField(
        queryset=Subject.objects.all(),
        required=True
    )
    course = forms.ModelChoiceField(
        queryset=Course.objects.filter(is_active=True),
        required=True,
        label="Class"
    )
    
    def __init__(self, *args, **kwargs):
        super(BulkResultEntryForm, self).__init__(*args, **kwargs)
        for field in self.visible_fields():
            field.field.widget.attrs['class'] = 'form-control'


# ============================================
# ATTENDANCE FORMS
# ============================================

class ClassAttendanceForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(ClassAttendanceForm, self).__init__(*args, **kwargs)

    class Meta:
        model = ClassAttendance
        fields = ['school_class', 'date', 'session']
        widgets = {
            'date': DateInput(attrs={'type': 'date'}),
        }


class ClassAttendanceRecordForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(ClassAttendanceRecordForm, self).__init__(*args, **kwargs)

    class Meta:
        model = ClassAttendanceRecord
        fields = ['student', 'status', 'arrival_time', 'remarks']
        widgets = {
            'arrival_time': forms.TimeInput(attrs={'type': 'time'}),
        }


class TakeClassAttendanceForm(forms.Form):
    """Form for taking daily class attendance"""
    school_class = forms.ModelChoiceField(
        queryset=Course.objects.filter(is_active=True),
        required=True,
        label="Class"
    )
    date = forms.DateField(
        widget=DateInput(attrs={'type': 'date'}),
        required=True
    )
    notify_parents = forms.BooleanField(
        required=False,
        initial=True,
        label="Send SMS to parents of absent students"
    )
    
    def __init__(self, *args, **kwargs):
        super(TakeClassAttendanceForm, self).__init__(*args, **kwargs)
        for field in self.visible_fields():
            if not isinstance(field.field.widget, forms.CheckboxInput):
                field.field.widget.attrs['class'] = 'form-control'


# ============================================
# SCHOOL SETTINGS FORM
# ============================================

class SchoolSettingsForm(FormSettings):
    def __init__(self, *args, **kwargs):
        super(SchoolSettingsForm, self).__init__(*args, **kwargs)

    class Meta:
        model = SchoolSettings
        fields = [
            'school_name', 'school_motto', 'school_address', 'school_phone', 
            'school_email', 'school_logo', 'principal_name', 'principal_signature',
            'receipt_prefix', 'sms_sender_id', 'enable_sms_notifications',
            'enable_attendance_sms', 'enable_fee_reminder_sms', 'fee_reminder_days_before'
        ]
        widgets = {
            'school_address': forms.Textarea(attrs={'rows': 3}),
        }
