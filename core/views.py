from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .models import Resume, Job_Posting, Application, Feedback
from .forms import ResumeForm, JobPostingForm, ApplicationForm, FeedbackForm
from .utils import (
    extract_text_from_resume,
    extract_skills,
    extract_experience,
    extract_education,
    calculate_match_score,
)

@login_required
def role_redirect(request):
    if request.user.account_type == 'seeker':
        return redirect('seeker_dashboard')
    elif request.user.account_type == 'recruiter':
        return redirect('recruiter_dashboard')
    else:
        return redirect('login')

@login_required
def seeker_dashboard(request):
    if request.user.account_type != 'seeker':
        return render(request, '403.html', status=403)
    resumes = Resume.objects.filter(user=request.user)
    applications = Application.objects.filter(user=request.user).select_related('job', 'resume')
    return render(request, 'seeker/seeker_dashboard.html', {
        'resumes': resumes,
        'applications': applications,
    })

@login_required
def recruiter_dashboard(request):
    if request.user.account_type != 'recruiter':
        return render(request, '403.html', status=403)
    jobs = Job_Posting.objects.filter(posted_by=request.user)
    applications = Application.objects.filter(job__posted_by=request.user).select_related('user', 'resume', 'job')
    return render(request, 'recruiter/recruiter_dashboard.html', {
        'jobs': jobs,
        'applications': applications,
    })

# Resume CRUD Views
@login_required
def resume_list(request):
    resumes = Resume.objects.filter(user=request.user)
    return render(request, 'resume/resume_list.html', {'resumes': resumes})

@login_required
def resume_create(request):
    if request.method == 'POST':
        form = ResumeForm(request.POST, request.FILES)
        if form.is_valid():
            resume = form.save(commit=False)
            resume.user = request.user

            # Parse uploaded resume for details
            file = request.FILES.get('file_path')
            if file:
                ext = file.name.split('.')[-1].lower()
                # Save file temporarily for parsing
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix='.' + ext) as temp_file:
                    for chunk in file.chunks():
                        temp_file.write(chunk)
                    temp_path = temp_file.name

                text = extract_text_from_resume(temp_path, ext)
                resume.extracted_text = text
                resume.skills = extract_skills(text)
                resume.experience = extract_experience(text)
                resume.education = extract_education(text)
                resume.summary = text[:500] if text else None  # Simple summary: first 500 chars

            resume.save()
            messages.success(request, "Resume uploaded and parsed successfully.")
            return redirect('resume_list')
    else:
        form = ResumeForm()
    return render(request, 'resume/resume_form.html', {'form': form})

@login_required
def resume_detail(request, pk):
    resume = get_object_or_404(Resume, pk=pk, user=request.user)
    return render(request, 'resume/resume_detail.html', {'resume': resume})

@login_required
def resume_update(request, pk):
    resume = get_object_or_404(Resume, pk=pk, user=request.user)
    if request.method == 'POST':
        form = ResumeForm(request.POST, request.FILES, instance=resume)
        if form.is_valid():
            resume = form.save(commit=False)

            # Re-parse if a new file uploaded
            file = request.FILES.get('file_path')
            if file:
                ext = file.name.split('.')[-1].lower()
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix='.' + ext) as temp_file:
                    for chunk in file.chunks():
                        temp_file.write(chunk)
                    temp_path = temp_file.name

                text = extract_text_from_resume(temp_path, ext)
                resume.extracted_text = text
                resume.skills = extract_skills(text)
                resume.experience = extract_experience(text)
                resume.education = extract_education(text)
                resume.summary = text[:500] if text else None

            resume.save()
            messages.success(request, "Resume updated and parsed successfully.")
            return redirect('resume_detail', pk=resume.pk)
    else:
        form = ResumeForm(instance=resume)
    return render(request, 'resume/resume_form.html', {'form': form})

@login_required
def resume_delete(request, pk):
    resume = get_object_or_404(Resume, pk=pk, user=request.user)
    if request.method == 'POST':
        resume.delete()
        messages.success(request, "Resume deleted.")
        return redirect('resume_list')
    return render(request, 'resume/resume_confirm_delete.html', {'resume': resume})

# Job Posting CRUD Views (Recruiter only)
@login_required
def job_list(request):
    jobs = Job_Posting.objects.all()
    return render(request, 'jobs/job_list.html', {'jobs': jobs})

@login_required
def job_create(request):
    if request.user.account_type != 'recruiter':
        messages.error(request, "Only recruiters can create jobs.")
        return redirect('job_list')
    if request.method == 'POST':
        form = JobPostingForm(request.POST)
        if form.is_valid():
            job = form.save(commit=False)
            job.posted_by = request.user
            job.save()
            messages.success(request, "Job posted successfully.")
            return redirect('job_list')
    else:
        form = JobPostingForm()
    return render(request, 'jobs/job_form.html', {'form': form})

@login_required
def job_detail(request, pk):
    job = get_object_or_404(Job_Posting, pk=pk)
    return render(request, 'jobs/job_detail.html', {'job': job})

@login_required
def job_update(request, pk):
    job = get_object_or_404(Job_Posting, pk=pk, posted_by=request.user)
    if request.method == 'POST':
        form = JobPostingForm(request.POST, instance=job)
        if form.is_valid():
            form.save()
            messages.success(request, "Job updated successfully.")
            return redirect('job_detail', pk=job.pk)
    else:
        form = JobPostingForm(instance=job)
    return render(request, 'jobs/job_form.html', {'form': form})

@login_required
def job_delete(request, pk):
    job = get_object_or_404(Job_Posting, pk=pk, posted_by=request.user)
    if request.method == 'POST':
        job.delete()
        messages.success(request, "Job deleted.")
        return redirect('job_list')
    return render(request, 'jobs/job_confirm_delete.html', {'job': job})

# Application CRUD Views
@login_required
def application_list(request):
    if request.user.account_type == 'recruiter':
        applications = Application.objects.filter(job__posted_by=request.user)
    else:
        applications = Application.objects.filter(user=request.user)
    return render(request, 'applications/application_list.html', {'applications': applications})

@login_required
def application_create(request, job_id):
    job = get_object_or_404(Job_Posting, pk=job_id)
    resumes = Resume.objects.filter(user=request.user)
    if request.method == 'POST':
        form = ApplicationForm(request.POST)
        form.fields['resume'].queryset = resumes
        if form.is_valid():
            application = form.save(commit=False)
            application.user = request.user
            application.job = job
            # Calculate match score based on resume and job requirements
            if application.resume and job.requirements:
                application.match_score = calculate_match_score(application.resume.skills, job.requirements)
            application.save()
            messages.success(request, "Application submitted successfully.")
            return redirect('application_list')
    else:
        form = ApplicationForm()
        form.fields['resume'].queryset = resumes
    return render(request, 'applications/application_form.html', {'form': form, 'job': job})

@login_required
def application_detail(request, pk):
    application = get_object_or_404(Application, pk=pk)
    if request.user != application.user and request.user != application.job.posted_by:
        messages.error(request, "You do not have permission to view this application.")
        return redirect('application_list')
    return render(request, 'applications/application_detail.html', {'application': application})

@login_required
def application_update(request, pk):
    application = get_object_or_404(Application, pk=pk)
    if request.user != application.user and request.user != application.job.posted_by:
        messages.error(request, "You do not have permission to update this application.")
        return redirect('application_list')
    if request.method == 'POST':
        form = ApplicationForm(request.POST, instance=application)
        if form.is_valid():
            application = form.save(commit=False)
            # Recalculate match score if resume updated
            if application.resume and application.job.requirements:
                application.match_score = calculate_match_score(application.resume.skills, application.job.requirements)
            application.save()
            messages.success(request, "Application updated successfully.")
            return redirect('application_detail', pk=application.pk)
    else:
        form = ApplicationForm(instance=application)
    return render(request, 'applications/application_form.html', {'form': form, 'application': application})

@login_required
def application_delete(request, pk):
    application = get_object_or_404(Application, pk=pk, user=request.user)
    if request.method == 'POST':
        application.delete()
        messages.success(request, "Application deleted.")
        return redirect('application_list')
    return render(request, 'applications/application_confirm_delete.html', {'application': application})

# Feedback Views
@login_required
def feedback_create(request, application_id):
    application = get_object_or_404(Application, pk=application_id, user=request.user)
    if request.method == 'POST':
        form = FeedbackForm(request.POST)
        if form.is_valid():
            feedback = form.save(commit=False)
            feedback.user = request.user
            feedback.application = application
            feedback.save()
            messages.success(request, "Feedback submitted.")
            return redirect('application_detail', pk=application_id)
    else:
        form = FeedbackForm()
    return render(request, 'feedback/feedback_form.html', {'form': form, 'application': application})

@login_required
def feedback_list(request):
    feedbacks = Feedback.objects.filter(user=request.user)
    return render(request, 'feedback/feedback_list.html', {'feedbacks': feedbacks})

@login_required
def feedback_detail(request, pk):
    feedback = get_object_or_404(Feedback, pk=pk, user=request.user)
    return render(request, 'feedback/feedback_detail.html', {'feedback': feedback})

@login_required
def feedback_delete(request, pk):
    feedback = get_object_or_404(Feedback, pk=pk, user=request.user)
    if request.method == 'POST':
        feedback.delete()
        messages.success(request, "Feedback deleted.")
        return redirect('feedback_list')
    return render(request, 'feedback/feedback_confirm_delete.html', {'feedback': feedback})