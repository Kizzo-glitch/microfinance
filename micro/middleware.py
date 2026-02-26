from django.shortcuts import redirect
from django.urls import reverse



class PasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. Check if user is logged in
        if request.user.is_authenticated and request.user.is_regulator:
            # 2. Check if they are forced to change password
            # 3. Don't redirect if they are already on the change-password or logout page
            exempt_urls = [reverse('password_change'), reverse('logout')]
            
            if request.user.must_change_password and request.path not in exempt_urls:
                return redirect('password_change')

        return self.get_response(request)