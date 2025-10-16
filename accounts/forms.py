from django import forms
from django.contrib.auth.forms import UserCreationForm
from core.models import User

class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True)
    account_type = forms.ChoiceField(choices=User.USER_TYPES)
    profile_picture = forms.ImageField(required=False)

    class Meta:
        model = User
        fields = (
            "username",
            "email",
            "account_type",
            "profile_picture",
            "password1",
            "password2",
        )