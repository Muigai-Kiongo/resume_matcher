from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.forms import inlineformset_factory
from typing import List
from django import forms
from typing import Optional


from .models import (
    User,
    Resume,
    Job_Posting,
    Application,
    Feedback,
    Skill,
    Experience,
    Education,
)


class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)

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

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"].lower()
        if commit:
            user.save()
        return user


class ResumeForm(forms.ModelForm):
    """
    Resume form:
    - skills: ModelMultipleChoiceField for selecting existing skills.
    - new_skills: optional comma-separated input to create/attach skills that don't yet exist.
    - save() will ensure created skills are attached to the resume.
    """
    skills = forms.ModelMultipleChoiceField(
        queryset=Skill.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-multiselect", "size": 6}),
        help_text="Select existing skills. Use 'Add new skills' to create new ones."
    )

    new_skills = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Add new skills, comma-separated"}),
        help_text="Comma-separated skill names to create+attach (optional)."
    )

    class Meta:
        model = Resume
        fields = [
            "file", "extracted_text", "skills", "new_skills", "summary"
        ]
        widgets = {
            "file": forms.ClearableFileInput(attrs={"accept": ".pdf,.doc,.docx"}),
            "extracted_text": forms.Textarea(attrs={"rows": 6, "placeholder": "Optional extracted text / notes"}),
            "summary": forms.Textarea(attrs={"rows": 4, "placeholder": "Short summary or objective (optional)"}),
        }

    def _split_and_clean(self, raw: str) -> List[str]:
        if not raw:
            return []
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        # Deduplicate preserving order (case-insensitive)
        seen = set()
        out = []
        for p in parts:
            key = p.lower()
            if key not in seen:
                seen.add(key)
                out.append(p)
        return out

    def save(self, commit=True):
        """
        Save resume, then create any new skills and attach them.
        Note: If the view calls form.save_m2m(), that will persist M2M from the 'skills' field.
        We still create and attach new skills here to ensure they're available.
        """
        # Save resume instance first (so it has a PK)
        resume = super().save(commit=commit)

        # Create and attach new skills from new_skills field
        raw = self.cleaned_data.get("new_skills", "")
        new_names = self._split_and_clean(raw)
        new_skill_objs = []
        for name in new_names:
            # use case-insensitive get_or_create
            skill, created = Skill.objects.get_or_create(name__iexact=name, defaults={"name": name})
            # The above may create duplicates on some DBs; prefer to fetch by iexact if exists
            if not skill.name or skill.name.lower() != name.lower():
                try:
                    skill = Skill.objects.get(name__iexact=name)
                except Skill.DoesNotExist:
                    # skill remains as created
                    pass
            new_skill_objs.append(skill)

        if new_skill_objs:
            resume.skills.add(*new_skill_objs)

        return resume


class ExperienceForm(forms.ModelForm):
    class Meta:
        model = Experience
        exclude = ("resume",)
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 3}),
            "order": forms.NumberInput(attrs={"min": 0}),
        }


class EducationForm(forms.ModelForm):
    class Meta:
        model = Education
        exclude = ("resume",)
        widgets = {
            "start_year": forms.NumberInput(attrs={"min": 1900, "max": 2100}),
            "end_year": forms.NumberInput(attrs={"min": 1900, "max": 2100}),
            "description": forms.Textarea(attrs={"rows": 3}),
            "order": forms.NumberInput(attrs={"min": 0}),
        }


# Inline formsets for Experience and Education
ExperienceFormSet = inlineformset_factory(
    parent_model=Resume,
    model=Experience,
    form=ExperienceForm,
    extra=1,
    can_delete=True,
    fk_name="resume",
)

EducationFormSet = inlineformset_factory(
    parent_model=Resume,
    model=Education,
    form=EducationForm,
    extra=1,
    can_delete=True,
    fk_name="resume",
)


class JobPostingForm(forms.ModelForm):
    """
    Job form:
    - requirements: structured M2M to Skill (select existing).
    - new_requirements: free comma-separated text to create/attach new skills quickly.
    - requirements_text: free text for nuances (already in model).
    """
    requirements = forms.ModelMultipleChoiceField(
        queryset=Skill.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-multiselect", "size": 6}),
        help_text="Select relevant skills for this role."
    )

    new_requirements = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Add new requirements, comma-separated"}),
        help_text="Comma-separated skill names to create and attach (optional)."
    )

    class Meta:
        model = Job_Posting
        fields = [
            "title", "company", "location", "description", "requirements", "new_requirements", "requirements_text", "salary_range", "is_active"
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
            "requirements_text": forms.Textarea(attrs={"rows": 3, "placeholder": "Optional free-text requirements"}),
            "salary_range": forms.TextInput(attrs={"placeholder": "KES 50,000 - 100,000"}),
        }

    def _split_and_clean(self, raw: str) -> List[str]:
        if not raw:
            return []
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        seen = set()
        out = []
        for p in parts:
            key = p.lower()
            if key not in seen:
                seen.add(key)
                out.append(p)
        return out

    def save(self, commit=True):
        """
        Save the Job_Posting instance. Create Skill objects for new_requirements but defer
        attaching them to the job if commit=False. If commit=True attach immediately.
        """
        job = super().save(commit=commit)

        # create Skill objects for new_requirements (or find existing)
        raw = self.cleaned_data.get("new_requirements", "")
        new_names = self._split_and_clean(raw)
        new_skill_objs = []
        for name in new_names:
            try:
                skill = Skill.objects.get(name__iexact=name)
            except Skill.DoesNotExist:
                skill = Skill.objects.create(name=name)
            new_skill_objs.append(skill)

        # If job already persisted, attach now. Otherwise keep pending.
        if commit and new_skill_objs:
            job.requirements.add(*new_skill_objs)
        else:
            # keep pending list on the form for the view to attach later
            self._pending_new_requirements = new_skill_objs

        return job

    def attach_pending_new_requirements(self, job_instance):
        """
        Attach any pending requirement skills created while save(commit=False) was used.
        Call this AFTER job_instance.save() and form.save_m2m() in the view.
        """
        pending = getattr(self, "_pending_new_requirements", None)
        if pending:
            job_instance.requirements.add(*pending)

# (excerpt) ApplicationForm in core/forms.py



class ApplicationForm(forms.ModelForm):
    """
    ApplicationForm enhancements:
    - default status to 'pending' for new applications
    - make the 'job' field hidden and not required (view sets it)
    - hide the status field for seekers (they shouldn't set status); recruiters can see/edit it
    - avoid forcing recruiters to select a resume: when a recruiter edits an existing application
      the resume field is limited to the attached resume and disabled so the recruiter can update
      status without needing to own/select the applicant's resume.
    """

    def __init__(self, *args, user: Optional[object] = None, **kwargs):
        super().__init__(*args, **kwargs)

        # Hide job widget and make it optional — view will set it
        self.fields["job"].widget = forms.HiddenInput()
        self.fields["job"].required = False

        # Store user for use in clean/save
        self._request_user = user

        # Configure resume queryset depending on role and instance:
        # - Seekers: only their own resumes (they can choose)
        # - Recruiters editing an existing application: show exactly the attached resume and disable the field
        # - Otherwise (admin or recruiter creating an application): show all resumes so validation can pass
        if user is not None and getattr(user, "account_type", None) == "seeker":
            self.fields["resume"].queryset = Resume.objects.filter(user=user)
        else:
            # recruiter / admin
            if getattr(self.instance, "pk", None) and getattr(self.instance, "resume", None):
                # limit to the attached resume and disable so recruiter can't change it
                self.fields["resume"].queryset = Resume.objects.filter(pk=self.instance.resume.pk)
                self.fields["resume"].disabled = True
            else:
                # creation by recruiter/admin — allow selection of any resume (or change to desired behavior)
                self.fields["resume"].queryset = Resume.objects.all()

        # Default new applications to 'pending' status
        if not getattr(self.instance, "pk", None):
            self.fields["status"].initial = "pending"

        # Hide status control for seekers; recruiters/admin see the status select
        if user is not None and getattr(user, "account_type", None) == "seeker":
            self.fields["status"].widget = forms.HiddenInput()

    class Meta:
        model = Application
        fields = ["job", "resume", "status"]
        widgets = {
            "status": forms.Select(),
        }

    def clean(self):
        cleaned = super().clean()

        # Ensure the view or the form instance supplies a job before saving.
        # For typical flows the view sets form.instance.job before validation OR initial contains job.
        if not cleaned.get("job") and not getattr(self.instance, "job", None):
            raise forms.ValidationError("Missing job: the server must set the job for this application.")

        return cleaned

    def save(self, commit=True):
        """
        Enforce status rules:
        - New applications always become 'pending' regardless of submitted value.
        - Seekers cannot change status when editing (we preserve the instance.status).
        - Recruiters may change status when editing.
        """
        app = super().save(commit=False)
        user = getattr(self, "_request_user", None)

        if not app.pk:
            # New application: ensure default pending
            app.status = "pending"
        else:
            # Editing existing application:
            if user is not None and getattr(user, "account_type", None) == "seeker":
                # preserve existing status; seekers are not allowed to change it
                app.status = self.instance.status
            # recruiters/admin may change status via the form

        if commit:
            app.save()
            # save m2m (if any)
            self.save_m2m()
        return app


class FeedbackForm(forms.ModelForm):
    class Meta:
        model = Feedback
        fields = [
            "rating", "comments"
        ]
        widgets = {
            "comments": forms.Textarea(attrs={"rows": 4, "placeholder": "Add constructive comments"}),
        }


# Optional: add media for JS/CSS if you plan to wire a nicer multi-select (Select2 etc.)
# Example (uncomment and adapt if you include select2 assets):
#
# class Media:
#     css = {
#         'all': ('https://cdnjs.cloudflare.com/ajax/libs/select2/4.0.13/css/select2.min.css',)
#     }
#     js = (
#         'https://cdnjs.cloudflare.com/ajax/libs/jquery/3.6.0/jquery.min.js',
#         'https://cdnjs.cloudflare.com/ajax/libs/select2/4.0.13/js/select2.min.js',
#     )
#
# Then initialize Select2 in the template for the multi-select fields.