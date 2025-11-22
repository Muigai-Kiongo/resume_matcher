from typing import List, Optional

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.forms import inlineformset_factory
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import (
    User,
    Resume,
    Job_Posting,
    Application,
    Feedback,
    Skill,
    Experience,
    Education,
    Conversation,
    Message,
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
        """
        # Save resume instance first (so it has a PK)
        resume = super().save(commit=commit)

        # Create and attach new skills from new_skills field
        raw = self.cleaned_data.get("new_skills", "")
        new_names = self._split_and_clean(raw)
        new_skill_objs = []
        for name in new_names:
            # prefer case-insensitive lookup first
            skill = Skill.objects.filter(name__iexact=name).first()
            if not skill:
                skill = Skill.objects.create(name=name)
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
    - duration_min_months / duration_max_months: integer months range (0..120)
    - application_deadline: optional datetime-local input; once deadline reached the protected fields
      are disabled in the form and server-side validation prevents modification.
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
            "title",
            "company",
            "location",
            "description",
            "requirements",
            "new_requirements",
            "requirements_text",
            "salary_range",
            "duration_min_months",
            "duration_max_months",
            "application_deadline",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
            "requirements_text": forms.Textarea(attrs={"rows": 3, "placeholder": "Optional free-text requirements"}),
            "salary_range": forms.TextInput(attrs={"placeholder": "KES 50,000 - 100,000"}),
            "duration_min_months": forms.NumberInput(attrs={"min": 0, "max": 120, "class": "duration-number"}),
            "duration_max_months": forms.NumberInput(attrs={"min": 0, "max": 120, "class": "duration-number"}),
            # HTML5 datetime-local input (browser-local)
            "application_deadline": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    # Fields we protect from edits after the deadline
    _protected_fields_after_deadline = [
        "title",
        "company",
        "location",
        "description",
        "requirements",
        "new_requirements",
        "requirements_text",
        "salary_range",
        "duration_min_months",
        "duration_max_months",
    ]

    def __init__(self, *args, **kwargs):
        """
        - Format initial application_deadline value for datetime-local input.
        - If instance has a passed deadline, disable protected fields in the form widgets so users cannot edit them.
        """
        super().__init__(*args, **kwargs)

        # Pre-fill formatted initial for datetime-local widget if instance has a deadline
        inst = getattr(self, "instance", None)
        if inst and getattr(inst, "application_deadline", None):
            try:
                # Convert to current timezone then format
                dt_local = inst.application_deadline.astimezone(timezone.get_current_timezone()).strftime("%Y-%m-%dT%H:%M")
            except Exception:
                dt_local = inst.application_deadline.strftime("%Y-%m-%dT%H:%M")
            self.initial.setdefault("application_deadline", dt_local)

        # Determine whether the instance deadline has already passed
        self._deadline_passed = False
        if inst and inst.pk and inst.application_deadline:
            if timezone.now() >= inst.application_deadline:
                self._deadline_passed = True

        # If deadline has passed, disable protected inputs (UI-level protection)
        if self._deadline_passed:
            for fname in self._protected_fields_after_deadline:
                if fname in self.fields:
                    field = self.fields[fname]
                    # mark as disabled so browsers render them readonly
                    field.disabled = True
                    # add explanatory help text (preserve any existing help_text)
                    prev = getattr(field, "help_text", "") or ""
                    extra = " (locked — application deadline reached)"
                    field.help_text = (prev + extra).strip()

            # Also disable new_requirements if present (it's not a model field in cleaned_data if instance exists)
            if "new_requirements" in self.fields:
                self.fields["new_requirements"].disabled = True
                prev = getattr(self.fields["new_requirements"], "help_text", "") or ""
                self.fields["new_requirements"].help_text = (prev + " (locked — application deadline reached)").strip()

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

    def clean(self):
        """
        - Validate duration min/max semantics.
        - If the instance's deadline has passed, prevent modification to protected fields even if a POST is crafted.
        """
        cleaned = super().clean()

        # duration range validation
        min_m = cleaned.get("duration_min_months")
        max_m = cleaned.get("duration_max_months")
        if min_m is not None and max_m is not None and min_m > max_m:
            raise ValidationError("Minimum duration must be less than or equal to maximum duration.")

        # If editing an existing job whose deadline has passed, disallow changes to protected fields.
        inst = getattr(self, "instance", None)
        if inst and inst.pk and inst.application_deadline and timezone.now() >= inst.application_deadline:
            changed = []
            for fname in self._protected_fields_after_deadline:
                if fname not in self.fields:
                    continue
                new_val = cleaned.get(fname, None)
                old_val = getattr(inst, fname, None)
                # Special handling for M2M 'requirements' which will be a QuerySet/list in cleaned data
                if fname == "requirements":
                    # convert to set of pks for comparison
                    new_pks = set([o.pk for o in new_val]) if new_val is not None else set()
                    old_pks = set(inst.requirements.values_list("pk", flat=True))
                    if new_pks != old_pks:
                        changed.append(fname)
                else:
                    # For textual/numeric fields, compare directly (treat None/"" carefully)
                    # Normalize dates/datetimes if any (none in protected list)
                    if new_val is None and old_val in (None, ""):
                        continue
                    if new_val != old_val:
                        changed.append(fname)

            # new_requirements is a free-text field: if provided and different, flag it
            if "new_requirements" in self.fields:
                new_req_raw = (self.data.get("new_requirements") or "").strip()
                if new_req_raw:
                    # if user attempted to add new requirements after deadline, disallow
                    changed.append("new_requirements")

            if changed:
                raise ValidationError(
                    "Cannot modify the following fields after the application deadline has passed: "
                    + ", ".join(changed)
                )

        return cleaned

    def save(self, commit=True):
        """
        Save the Job_Posting instance and attach any new requirements created.
        If the form was instantiated with commit=False on a deadline-passed instance, we still prevent modifications
        because clean() already enforces it.
        """
        job = super().save(commit=commit)

        # create Skill objects for new_requirements (or find existing)
        raw = self.cleaned_data.get("new_requirements", "")
        new_names = self._split_and_clean(raw)
        new_skill_objs = []
        for name in new_names:
            skill = Skill.objects.filter(name__iexact=name).first()
            if not skill:
                skill = Skill.objects.create(name=name)
            new_skill_objs.append(skill)

        # If job already persisted, attach now. Otherwise keep pending.
        if commit and new_skill_objs:
            job.requirements.add(*new_skill_objs)
        else:
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


class ApplicationForm(forms.ModelForm):
    """
    ApplicationForm:
    - job hidden (view sets it)
    - resume queryset limited by role
    - seekers cannot set status
    """

    def __init__(self, *args, user: Optional[object] = None, **kwargs):
        super().__init__(*args, **kwargs)

        # Hide job widget and make it optional — view will set it
        self.fields["job"].widget = forms.HiddenInput()
        self.fields["job"].required = False

        # Store user for use in clean/save
        self._request_user = user

        # Configure resume queryset depending on role and instance:
        if user is not None and getattr(user, "account_type", None) == "seeker":
            self.fields["resume"].queryset = Resume.objects.filter(user=user)
        else:
            # recruiter / admin
            if getattr(self.instance, "pk", None) and getattr(self.instance, "resume", None):
                # limit to the attached resume and disable so recruiter can't change it
                self.fields["resume"].queryset = Resume.objects.filter(pk=self.instance.resume.pk)
                self.fields["resume"].disabled = True
            else:
                # creation by recruiter/admin — allow selection of any resume
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
        if not cleaned.get("job") and not getattr(self.instance, "job", None):
            raise forms.ValidationError("Missing job: the server must set the job for this application.")
        return cleaned

    def save(self, commit=True):
        app = super().save(commit=False)
        user = getattr(self, "_request_user", None)

        if not app.pk:
            app.status = "pending"
        else:
            if user is not None and getattr(user, "account_type", None) == "seeker":
                app.status = self.instance.status

        if commit:
            app.save()
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


# ---------------------------
# Messaging / Chat form types
# ---------------------------
class ConversationForm(forms.ModelForm):
    """
    Create or edit a Conversation.
    - participants: choose two or more users (typically one seeker + one recruiter)
    - subject: optional context
    """
    participants = forms.ModelMultipleChoiceField(
        queryset=User.objects.all(),
        widget=forms.SelectMultiple(attrs={"size": 6}),
        help_text="Choose participants for this conversation (at least 2)."
    )

    class Meta:
        model = Conversation
        fields = ["participants", "subject", "is_active"]
        widgets = {
            "subject": forms.TextInput(attrs={"placeholder": "Optional subject/context"}),
        }

    def clean_participants(self):
        participants = self.cleaned_data.get("participants")
        if not participants or participants.count() < 2:
            raise ValidationError("A conversation requires at least two participants.")
        return participants


class MessageForm(forms.ModelForm):
    """
    Message form for posting messages in a conversation.
    """
    content = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Write a message..."}),
    )
    attachment = forms.FileField(required=False)

    class Meta:
        model = Message
        fields = ["content", "attachment"]

    def clean(self):
        cleaned = super().clean()
        content = cleaned.get("content", "")
        attachment = cleaned.get("attachment")
        if not content and not attachment:
            raise ValidationError("Message must contain text or an attachment.")
        return cleaned