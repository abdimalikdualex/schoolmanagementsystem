from django.shortcuts import get_object_or_404, render, redirect
from django.views import View
from django.contrib import messages
from .models import Subject, Staff, Student, StudentResult
from .forms import EditResultForm
from django.urls import reverse


class EditResultView(View):
    def get(self, request, *args, **kwargs):
        from .result_entry_permissions import can_teacher_enter_legacy_results
        if not request.user.is_superuser and request.user.user_type != '1':
            if not can_teacher_enter_legacy_results(request):
                return render(request, "staff_template/result_entry_closed.html", {
                    'page_title': "Result Entry Closed",
                    'message': "Result upload is currently closed. Please contact the administrator."
                }, status=403)
        resultForm = EditResultForm()
        # Allow staff to edit only their subjects; superuser can edit all
        try:
            staff = Staff.objects.get(admin=request.user)
            resultForm.fields['subject'].queryset = Subject.objects.filter(staff=staff)
        except Staff.DoesNotExist:
            if request.user.is_superuser:
                resultForm.fields['subject'].queryset = Subject.objects.all()
            else:
                return render(request, "staff_template/edit_student_result.html", {
                    'form': resultForm,
                    'page_title': "Edit Student's Result"
                })
        context = {
            'form': resultForm,
            'page_title': "Edit Student's Result"
        }
        return render(request, "staff_template/edit_student_result.html", context)

    def post(self, request, *args, **kwargs):
        from .result_entry_permissions import can_teacher_enter_legacy_results
        if not request.user.is_superuser and request.user.user_type != '1':
            if not can_teacher_enter_legacy_results(request):
                return render(request, "staff_template/result_entry_closed.html", {
                    'page_title': "Result Entry Closed",
                    'message': "Result upload is currently closed. Please contact the administrator."
                }, status=403)
        form = EditResultForm(request.POST)
        context = {'form': form, 'page_title': "Edit Student's Result"}
        if form.is_valid():
            try:
                student = form.cleaned_data.get('student')
                subject = form.cleaned_data.get('subject')
                test = form.cleaned_data.get('test')
                exam = form.cleaned_data.get('exam')
                # Ensure non-superuser staff only update their own subject results
                if not request.user.is_superuser:
                    staff = get_object_or_404(Staff, admin=request.user)
                    if subject.staff != staff:
                        messages.warning(request, "You don't have permission to update this subject's result")
                        return render(request, "staff_template/edit_student_result.html", context)
                # Validating and updating
                result = StudentResult.objects.get(student=student, subject=subject)
                result.exam = exam
                result.test = test
                result.save()
                messages.success(request, "Result Updated")
                return redirect(reverse('edit_student_result'))
            except StudentResult.DoesNotExist:
                messages.warning(request, "Result does not exist — please add it first")
            except Exception as e:
                messages.warning(request, "Result Could Not Be Updated")
        else:
            messages.warning(request, "Result Could Not Be Updated")
        return render(request, "staff_template/edit_student_result.html", context)
