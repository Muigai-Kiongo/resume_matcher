from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils.text import slugify
from django.core.exceptions import ValidationError
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


class User(AbstractUser):
    """
    Custom User Model (unchanged except normalized fields)
    """
    USER_TYPES = (
        ('seeker', 'Job Seeker'),
        ('recruiter', 'Recruiter'),
        ('admin', 'Admin'),
    )

    account_type = models.CharField(max_length=10, choices=USER_TYPES, default='seeker')
    email = models.EmailField(unique=True)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return f"{self.username} ({self.account_type})"


class Skill(models.Model):
    """
    Normalized skill model so users can add/select skills via forms and admin.
    """
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)

    class Meta:
        db_table = 'skills'
        ordering = ['name']
        verbose_name = 'Skill'
        verbose_name_plural = 'Skills'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Resume(models.Model):
    """
    Resume: normalized structure. Skills are M2M to Skill.
    Experience and Education are separate related models for user-friendly input.
    """
    resume_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='resumes')
    file = models.FileField(upload_to='resumes/', blank=True, null=True)
    extracted_text = models.TextField(blank=True, null=True)
    skills = models.ManyToManyField(Skill, blank=True, related_name='resumes')
    summary = models.TextField(blank=True, null=True)
    match_score = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'resumes'
        verbose_name = 'Resume'
        verbose_name_plural = 'Resumes'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"Resume for {self.user.username} (ID: {self.resume_id})"

    def get_skills_as_string(self):
        return ', '.join(skill.name for skill in self.skills.all()) if self.skills.exists() else 'No skills extracted'

    def get_experiences(self):
        return self.experiences.order_by('-start_date')

    def get_education_list(self):
        return self.education_entries.order_by('-end_year')


class Experience(models.Model):
    """
    Normalized experience entry for a resume.
    User-friendly input: company, title, start/end, description.
    """
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name='experiences')
    company = models.CharField(max_length=200)
    title = models.CharField(max_length=200)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    is_current = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0, help_text="Lower values display first")

    class Meta:
        db_table = 'resume_experiences'
        ordering = ['order', '-start_date']
        verbose_name = 'Experience'
        verbose_name_plural = 'Experiences'

    def __str__(self):
        return f"{self.title} @ {self.company}"


class Education(models.Model):
    """
    Normalized education entry for a resume.
    """
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name='education_entries')
    institution = models.CharField(max_length=255)
    degree = models.CharField(max_length=255, blank=True)
    field_of_study = models.CharField(max_length=255, blank=True)
    start_year = models.PositiveSmallIntegerField(blank=True, null=True)
    end_year = models.PositiveSmallIntegerField(blank=True, null=True)
    grade = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'resume_education'
        ordering = ['order', '-end_year']
        verbose_name = 'Education'
        verbose_name_plural = 'Education'

    def __str__(self):
        title = self.degree or self.institution
        return f"{title} ({self.institution})"


class Job_Posting(models.Model):
    """
    Job Posting Model: requirements now use normalized Skill M2M for structured input
    and an optional free-text requirements field for nuance.

    Added duration_min_months and duration_max_months to represent expected duration range.
    Added application_deadline to control when applications close.
    """
    job_id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=200)
    company = models.CharField(max_length=200)
    location = models.CharField(max_length=100, blank=True)
    description = models.TextField()
    requirements = models.ManyToManyField(Skill, blank=True, related_name='job_postings')
    requirements_text = models.TextField(blank=True, null=True, help_text="Optional free-text requirements")
    salary_range = models.CharField(max_length=50, blank=True, help_text="e.g., 'KES 50,000 - 100,000'")
    posted_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='posted_jobs',
        limit_choices_to={'account_type': 'recruiter'}
    )

    # Duration fields (in months)
    duration_min_months = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(0), MaxValueValidator(120)],
        help_text="Minimum expected duration in months (0 = open/indefinite)"
    )
    duration_max_months = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(0), MaxValueValidator(120)],
        help_text="Maximum expected duration in months (leave blank for open-ended)"
    )

    # Application deadline (optional). If set, applications should be blocked after this time.
    application_deadline = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Optional deadline (date & time). After this time applications will be closed."
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'job_postings'
        verbose_name = 'Job Posting'
        verbose_name_plural = 'Job Postings'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} at {self.company}"

    def get_requirements_as_string(self):
        skills_part = ', '.join(skill.name for skill in self.requirements.all()) if self.requirements.exists() else ''
        if self.requirements_text:
            return (skills_part + ', ' + self.requirements_text) if skills_part else self.requirements_text
        return skills_part or 'No requirements specified'

    def clean(self):
        """
        Ensure duration_min_months <= duration_max_months when both provided.
        Ensure application_deadline, if provided, is not set in the past (sensible default).
        """
        super().clean()
        min_m = self.duration_min_months
        max_m = self.duration_max_months
        if min_m is not None and max_m is not None and min_m > max_m:
            raise ValidationError({
                'duration_max_months': "Maximum duration (months) must be greater than or equal to minimum duration."
            })

        if self.application_deadline is not None:
            # Prevent accidentally saving a past deadline (adjust if you prefer allowing past deadlines)
            if self.application_deadline < timezone.now():
                raise ValidationError({
                    'application_deadline': "Application deadline must be in the future."
                })

    def duration_display(self):
        if self.duration_min_months is None and self.duration_max_months is None:
            return "—"
        if self.duration_min_months is None:
            return f"Up to {self.duration_max_months} mo"
        if self.duration_max_months is None:
            return f"{self.duration_min_months}+ mo"
        return f"{self.duration_min_months}–{self.duration_max_months} mo"


class Application(models.Model):
    """
    Application Model: remains similar but resume link is preserved.
    """
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('shortlisted', 'Shortlisted'),
        ('rejected', 'Rejected'),
        ('hired', 'Hired'),
    )

    application_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='applications')
    job = models.ForeignKey(Job_Posting, on_delete=models.CASCADE, related_name='applications')
    resume = models.ForeignKey(
        Resume, on_delete=models.SET_NULL, null=True, blank=True, related_name='applications'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    match_score = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="AI-generated match score (0-1)"
    )
    ai_feedback = models.TextField(blank=True, null=True)
    submission_date = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'applications'
        constraints = [
            models.UniqueConstraint(fields=['user', 'job'], name='unique_user_job_application')
        ]
        verbose_name = 'Application'
        verbose_name_plural = 'Applications'
        ordering = ['-submission_date']

    def __str__(self):
        return f"Application by {self.user.username} for {self.job.title} (Score: {self.match_score:.2f})"


class Feedback(models.Model):
    """
    Feedback Model (unchanged)
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='feedback')
    application = models.ForeignKey(
        Application, on_delete=models.CASCADE,
        related_name='feedback_entries', null=True, blank=True
    )
    rating = models.IntegerField(choices=[(i, i) for i in range(1, 6)], help_text="1-5 stars")
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'feedback'
        verbose_name = 'Feedback'
        verbose_name_plural = 'Feedback'

    def __str__(self):
        return f"Feedback from {self.user.username} (Rating: {self.rating})"


# -----------------------
# Messaging / Chat models
# -----------------------
class Conversation(models.Model):
    """
    Conversation groups participants (recruiters and seekers) and holds metadata.
    - participants: M2M to User (two or more participants; typically one seeker + one recruiter)
    - last_message: optional FK to last Message for quick access
    """
    conversation_id = models.AutoField(primary_key=True)
    participants = models.ManyToManyField(User, related_name='conversations')
    subject = models.CharField(max_length=255, blank=True, null=True, help_text="Optional subject or context")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_message = models.ForeignKey('Message', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    class Meta:
        db_table = 'conversations'
        verbose_name = 'Conversation'
        verbose_name_plural = 'Conversations'
        ordering = ['-updated_at']

    def __str__(self):
        # avoid heavy DB work in __str__ in large production deployments if many participants
        participants = self.participants.all()[:5]
        parts = ", ".join([p.username for p in participants])
        return f"Conversation ({parts})"

    def add_participant(self, user):
        self.participants.add(user)
        self.touch()

    def remove_participant(self, user):
        self.participants.remove(user)
        self.touch()

    def unread_count_for(self, user):
        """
        Count messages in this conversation that the given user has not read and that were not sent by the user.
        """
        return self.messages.exclude(read_by=user).exclude(sender=user).count()

    def touch(self):
        self.updated_at = timezone.now()
        self.save(update_fields=['updated_at'])


class Message(models.Model):
    """
    Message inside a Conversation.
    - read_by: M2M to User tracks which participants have read the message.
    """
    message_id = models.AutoField(primary_key=True)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    content = models.TextField(blank=True)
    attachment = models.FileField(upload_to='messages/attachments/', blank=True, null=True)
    read_by = models.ManyToManyField(User, blank=True, related_name='read_messages')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'messages'
        verbose_name = 'Message'
        verbose_name_plural = 'Messages'
        ordering = ['created_at']

    def __str__(self):
        preview = (self.content or "")[:60]
        return f"Message by {self.sender.username}: {preview!s}"

    def mark_read(self, user):
        """
        Mark this message as read by a user.
        """
        if user and user.pk:
            self.read_by.add(user)
            return True
        return False

    def is_read_by(self, user):
        return self.read_by.filter(pk=user.pk).exists()

    def save(self, *args, **kwargs):
        """
        Override save to update Conversation.last_message and updated_at values.
        """
        super().save(*args, **kwargs)
        try:
            conv = self.conversation
            conv.last_message = self
            conv.updated_at = timezone.now()
            conv.save(update_fields=['last_message', 'updated_at'])
        except Exception:
            logger.exception("Failed to update conversation after saving message", exc_info=True)