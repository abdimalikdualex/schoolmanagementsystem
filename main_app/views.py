import json
import requests
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.views.decorators.csrf import csrf_exempt

from .models import Attendance, Session, Subject

# Create your views here.


def login_page(request):
    if request.user.is_authenticated:
        if request.user.user_type == '1':
            return redirect(reverse("admin_home"))
        elif request.user.user_type == '2':
            return redirect(reverse("staff_home"))
        elif request.user.user_type == '3':
            return redirect(reverse("student_home"))
        elif request.user.user_type == '4':
            return redirect(reverse("parent_home"))
        elif str(request.user.user_type) == '5':
            return redirect(reverse("finance_dashboard"))
        else:
            return redirect(reverse("student_home"))
    from django.conf import settings
    response = render(request, 'main_app/login.html', {'debug': settings.DEBUG})
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


def doLogin(request, **kwargs):
    if request.method != 'POST':
        return redirect(reverse('login_page'))
    else:
        # Google recaptcha - Skip in development mode
        from django.conf import settings
        if not settings.DEBUG:
            captcha_token = request.POST.get('g-recaptcha-response')
            captcha_url = "https://www.google.com/recaptcha/api/siteverify"
            captcha_key = "6LfswtgZAAAAABX9gbLqe-d97qE2g1JP8oUYritJ"
            data = {
                'secret': captcha_key,
                'response': captcha_token
            }
            # Make request
            try:
                captcha_server = requests.post(url=captcha_url, data=data)
                response = json.loads(captcha_server.text)
                if response['success'] == False:
                    messages.error(request, 'Invalid Captcha. Try Again')
                    return redirect(reverse('login_page'))
            except:
                messages.error(request, 'Captcha could not be verified. Try Again')
                return redirect(reverse('login_page'))
        
        # Authenticate using Django's authenticate function
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        user = authenticate(request, username=email, password=password)
        
        if user is not None:
            if not user.is_active:
                messages.error(request, "Account is disabled. Contact administrator.")
                return redirect(reverse("login_page"))
            login(request, user)
            request.session.save()  # Ensure session is persisted before redirect
            user_type = str(user.user_type) if user.user_type else '3'
            if user_type == '1':
                return redirect(reverse("admin_home"))
            elif user_type == '2':
                return redirect(reverse("staff_home"))
            elif user_type == '3':
                return redirect(reverse("student_home"))
            elif user_type == '4':
                return redirect(reverse("parent_home"))
            elif user_type == '5':
                return redirect(reverse("finance_dashboard"))
            else:
                return redirect(reverse("student_home"))
        else:
            messages.error(request, "Invalid email or password")
            return redirect(reverse("login_page"))



def logout_user(request):
    if request.user != None:
        logout(request)
    return redirect("/")


@csrf_exempt
def get_attendance(request):
    subject_id = request.POST.get('subject')
    session_id = request.POST.get('session')
    try:
        subject = get_object_or_404(Subject, id=subject_id)
        session = get_object_or_404(Session, id=session_id)
        attendance = Attendance.objects.filter(subject=subject, session=session)
        attendance_list = []
        for attd in attendance:
            data = {
                    "id": attd.id,
                    "attendance_date": str(attd.date),
                    "session": attd.session.id
                    }
            attendance_list.append(data)
        return JsonResponse(attendance_list, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def showFirebaseJS(request):
    data = """
    // Give the service worker access to Firebase Messaging.
// Note that you can only use Firebase Messaging here, other Firebase libraries
// are not available in the service worker.
importScripts('https://www.gstatic.com/firebasejs/7.22.1/firebase-app.js');
importScripts('https://www.gstatic.com/firebasejs/7.22.1/firebase-messaging.js');

// Initialize the Firebase app in the service worker by passing in
// your app's Firebase config object.
// https://firebase.google.com/docs/web/setup#config-object
firebase.initializeApp({
    apiKey: "AIzaSyBarDWWHTfTMSrtc5Lj3Cdw5dEvjAkFwtM",
    authDomain: "sms-with-django.firebaseapp.com",
    databaseURL: "https://sms-with-django.firebaseio.com",
    projectId: "sms-with-django",
    storageBucket: "sms-with-django.appspot.com",
    messagingSenderId: "945324593139",
    appId: "1:945324593139:web:03fa99a8854bbd38420c86",
    measurementId: "G-2F2RXTL9GT"
});

// Retrieve an instance of Firebase Messaging so that it can handle background
// messages.
const messaging = firebase.messaging();
messaging.setBackgroundMessageHandler(function (payload) {
    const notification = JSON.parse(payload);
    const notificationOption = {
        body: notification.body,
        icon: notification.icon
    }
    return self.registration.showNotification(payload.notification.title, notificationOption);
});
    """
    return HttpResponse(data, content_type='application/javascript')
