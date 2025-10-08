from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator


class User(AbstractUser):
    """
    Custom User Model
    """
    USER_TYPES = (
        ('seeker', 'Job Seeker'),
        ('recruiter', 'Recruiter'),
        ('admin', 'Admin'),
    )

    account_type = models.CharField(max_length=10, choices=USER_TYPES, default='seeker')
    email = models.EmailField(unique=True)  # make email unique
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return f"{self.username} ({self.account_type})"


class Resume(models.Model):
    """
    Resume Model: Stores parsed resume data for a user.
    """
    resume_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='resumes')
    file_path = models.FileField(upload_to='resumes/', blank=True, null=True)
    extracted_text = models.TextField(blank=True, null=True)
    skills = models.JSONField(default=list, blank=True)  # e.g. ["Python", "Machine Learning"]
    experience = models.JSONField(default=dict, blank=True)  # e.g. {"company": "...", "role": "..."}
    education = models.TextField(blank=True, null=True)
    summary = models.TextField(blank=True, null=True)
    match_score = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'resumes'
        constraints = [
            models.UniqueConstraint(fields=['user', 'uploaded_at'], name='unique_user_resume_upload')
        ]
        verbose_name = 'Resume'
        verbose_name_plural = 'Resumes'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"Resume for {self.user.username} (ID: {self.resume_id})"

    def get_skills_as_string(self):
        return ', '.join(self.skills) if self.skills else 'No skills extracted'


class Job_Posting(models.Model):
    """
    Job Posting Model
    """
    job_id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=200)
    company = models.CharField(max_length=200)
    location = models.CharField(max_length=100, blank=True)
    description = models.TextField()
    requirements = models.JSONField(default=list, blank=True)
    salary_range = models.CharField(max_length=50, blank=True, help_text="e.g., 'KES 50,000 - 100,000'")
    posted_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='posted_jobs',
        limit_choices_to={'account_type': 'recruiter'}
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
        return ', '.join(self.requirements) if self.requirements else 'No requirements specified'


class Application(models.Model):
    """
    Application Model: User applications to jobs
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
    ai_feedback = models.TextField(blank=True, null=True)  # renamed from "feedback"
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
    Feedback Model: Stores user feedback on AI suggestions
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
