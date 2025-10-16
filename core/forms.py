from django import forms
from .models import User, Resume, Job_Posting, Application, Feedback
from django.contrib.auth.forms import UserCreationForm

class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = (
            "username", "email", "account_type", "profile_picture", "password1", "password2"
        )

class ResumeForm(forms.ModelForm):
    class Meta:
        model = Resume
        fields = [
            "file_path", "extracted_text", "skills", "experience", "education", "summary"
        ]
        widgets = {
            "skills": forms.Textarea(attrs={"placeholder": "Comma-separated skills"}),
            "experience": forms.Textarea(attrs={"placeholder": "Describe experience"}),
            "education": forms.Textarea(attrs={"placeholder": "Education details"}),
            "summary": forms.Textarea(attrs={"placeholder": "Summary"}),
        }

class JobPostingForm(forms.ModelForm):
    class Meta:
        model = Job_Posting
        fields = [
            "title", "company", "location", "description", "requirements", "salary_range", "is_active"
        ]
        widgets = {
            "requirements": forms.Textarea(attrs={"placeholder": "Comma-separated requirements"}),
            "description": forms.Textarea(attrs={"placeholder": "Job description"}),
            "salary_range": forms.TextInput(attrs={"placeholder": "KES 50,000 - 100,000"}),
        }

class ApplicationForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = [
            "job", "resume", "status"
        ]
        widgets = {
            "status": forms.Select(),
        }

class FeedbackForm(forms.ModelForm):
    class Meta:
        model = Feedback
        fields = [
            "rating", "comments"
        ]
        widgets = {
            "comments": forms.Textarea(attrs={"placeholder": "Add comments here"}),
        }