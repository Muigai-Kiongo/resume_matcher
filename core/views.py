from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden
import os
from .models import Resume, Job_Posting, Application, Feedback, Skill
from .forms import (
    ResumeForm,
    JobPostingForm,
    ApplicationForm,
    FeedbackForm,
    ExperienceFormSet,
    EducationFormSet,
)
from .utils import (
    extract_text_from_resume,
    extract_skills,
    calculate_match_score,
)

import tempfile
import os


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
        return HttpResponseForbidden(render(request, '403.html'))
    resumes = Resume.objects.filter(user=request.user)
    applications = Application.objects.filter(user=request.user).select_related('job', 'resume')
    return render(request, 'seeker/seeker_dashboard.html', {
        'resumes': resumes,
        'applications': applications,
    })


@login_required
def recruiter_dashboard(request):
    if request.user.account_type != 'recruiter':
        return HttpResponseForbidden(render(request, '403.html'))
    jobs = Job_Posting.objects.filter(posted_by=request.user)
    applications = Application.objects.filter(job__posted_by=request.user).select_related('user', 'resume', 'job')
    return render(request, 'recruiter/recruiter_dashboard.html', {
        'jobs': jobs,
        'applications': applications,
    })


# Resume CRUD Views (normalized models + inline formsets)
@login_required
def resume_list(request):
    resumes = Resume.objects.filter(user=request.user)
    return render(request, 'resume/resume_list.html', {'resumes': resumes})


@login_required
def resume_create(request):
    """
    Create Resume + Experience + Education.
    - Uses ResumeForm and inline formsets for Experience/Education.
    - Parses uploaded file (request.FILES['file']) and associates Skill objects.
    """
    if request.method == 'POST':
        form = ResumeForm(request.POST, request.FILES)
        exp_fs = ExperienceFormSet(request.POST, request.FILES, prefix='exp')
        edu_fs = EducationFormSet(request.POST, request.FILES, prefix='edu')

        if form.is_valid() and exp_fs.is_valid() and edu_fs.is_valid():
            with transaction.atomic():
                resume = form.save(commit=False)
                resume.user = request.user

                uploaded_file = request.FILES.get('file')
                parsed_text = ''
                extracted_skill_names = []

                if uploaded_file:
                    # write to temporary file to allow existing extractors to read by path if needed
                    ext = uploaded_file.name.split('.')[-1].lower()
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.' + ext) as tmp:
                        for chunk in uploaded_file.chunks():
                            tmp.write(chunk)
                        tmp_path = tmp.name
                    try:
                        parsed_text = extract_text_from_resume(tmp_path, ext) or ''
                        resume.extracted_text = parsed_text
                        if not resume.summary:
                            resume.summary = parsed_text[:500] if parsed_text else resume.summary
                        extracted_skill_names = extract_skills(parsed_text) or []
                    finally:
                        try:
                            os.remove(tmp_path)
                        except Exception:
                            pass

                resume.save()
                # Formsets require the parent object saved first
                # handle skills: create missing Skill instances and attach
                skill_objs = []
                for name in extracted_skill_names:
                    name_clean = name.strip()
                    if not name_clean:
                        continue
                    # create/get skill using case-insensitive check
                    skill_obj = None
                    try:
                        skill_obj = Skill.objects.get(name__iexact=name_clean)
                    except Skill.DoesNotExist:
                        skill_obj = Skill.objects.create(name=name_clean)
                    if skill_obj:
                        skill_objs.append(skill_obj)
                # If the user manually selected skills in the form, they will be saved via form.save_m2m()
                form.save_m2m()
                if skill_objs:
                    # add parsed skills in addition to any selected skills (avoid duplicates automatically via M2M)
                    resume.skills.add(*skill_objs)

                # Save inline formsets
                exp_fs.instance = resume
                exp_fs.save()
                edu_fs.instance = resume
                edu_fs.save()

                messages.success(request, "Resume uploaded and parsed successfully.")
                return redirect('resume_list')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = ResumeForm()
        exp_fs = ExperienceFormSet(prefix='exp')
        edu_fs = EducationFormSet(prefix='edu')

    return render(request, 'resume/resume_form.html', {
        'form': form,
        'exp_formset': exp_fs,
        'edu_formset': edu_fs,
    })



# core/views.py
from django.shortcuts import render, get_object_or_404
from django.http import Http404, HttpResponseForbidden
from django.contrib.auth.decorators import login_required

from .models import Resume, Application

@login_required
def resume_detail(request, pk):
    # try to get the resume regardless of owner first
    resume = Resume.objects.filter(pk=pk).first()
    if not resume:
        raise Http404("Resume not found.")

    # Owner always allowed
    if resume.user == request.user:
        allowed = True
    # Allow recruiters only if the resume was submitted to one of their jobs
    elif request.user.account_type == 'recruiter':
        allowed = Application.objects.filter(resume=resume, job__posted_by=request.user).exists()
    else:
        allowed = False

    if not allowed:
        # For privacy, you may prefer 404 (so it looks like not found) instead of 403
        return HttpResponseForbidden(render(request, '403.html', status=403))

    # gather experiences/education same as before
    experiences = getattr(resume, 'get_experiences', lambda: resume.experiences.all())()
    education_list = getattr(resume, 'get_education_list', lambda: resume.education_entries.all())()
    # optional: compute match_percent etc, or pass resume.match_score as needed

    return render(request, 'resume/resume_detail.html', {
        'resume': resume,
        'experiences': experiences,
        'education_list': education_list,
    })

@login_required
def resume_update(request, pk):
    resume = get_object_or_404(Resume, pk=pk, user=request.user)
    if request.method == 'POST':
        form = ResumeForm(request.POST, request.FILES, instance=resume)
        exp_fs = ExperienceFormSet(request.POST, request.FILES, instance=resume, prefix='exp')
        edu_fs = EducationFormSet(request.POST, request.FILES, instance=resume, prefix='edu')

        if form.is_valid() and exp_fs.is_valid() and edu_fs.is_valid():
            with transaction.atomic():
                resume = form.save(commit=False)

                uploaded_file = request.FILES.get('file')
                if uploaded_file:
                    ext = uploaded_file.name.split('.')[-1].lower()
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.' + ext) as tmp:
                        for chunk in uploaded_file.chunks():
                            tmp.write(chunk)
                        tmp_path = tmp.name
                    try:
                        parsed_text = extract_text_from_resume(tmp_path, ext) or ''
                        resume.extracted_text = parsed_text
                        resume.summary = parsed_text[:500] if parsed_text else resume.summary

                        extracted_skill_names = extract_skills(parsed_text) or []
                        skill_objs = []
                        for name in extracted_skill_names:
                            name_clean = name.strip()
                            if not name_clean:
                                continue
                            try:
                                skl = Skill.objects.get(name__iexact=name_clean)
                            except Skill.DoesNotExist:
                                skl = Skill.objects.create(name=name_clean)
                            skill_objs.append(skl)
                        # Save resume and its explicit skills (from form), then replace/add parsed skills
                    finally:
                        try:
                            os.remove(tmp_path)
                        except Exception:
                            pass

                resume.save()
                # save M2M from form (if user selected skills)
                form.save_m2m()

                # if we built skill_objs from parsing, merge them into resume.skills
                if uploaded_file and 'skill_objs' in locals() and skill_objs:
                    resume.skills.add(*skill_objs)

                exp_fs.save()
                edu_fs.save()

                messages.success(request, "Resume updated and parsed successfully.")
                return redirect('resume_detail', pk=resume.pk)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = ResumeForm(instance=resume)
        exp_fs = ExperienceFormSet(instance=resume, prefix='exp')
        edu_fs = EducationFormSet(instance=resume, prefix='edu')

    return render(request, 'resume/resume_form.html', {
        'form': form,
        'exp_formset': exp_fs,
        'edu_formset': edu_fs,
        'resume': resume,
    })







@login_required
def resume_delete(request, pk):
    resume = get_object_or_404(Resume, pk=pk, user=request.user)
    file_name = None
    if resume.file:
        # resume.file.name might be a path like 'resumes/somefile.pdf'
        file_name = os.path.basename(resume.file.name)
    if request.method == 'POST':
        resume.delete()
        messages.success(request, "Resume deleted.")
        return redirect('resume_list')
    return render(request, 'resume/resume_confirm_delete.html', {'resume': resume, 'file_name': file_name})

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
            # Save instance with commit=False so we can set posted_by
            job = form.save(commit=False)
            job.posted_by = request.user
            job.save()
            # Persist M2M from the form (selected existing requirements)
            form.save_m2m()
            # Attach any pending new requirements created inside form.save(commit=False)
            if hasattr(form, "attach_pending_new_requirements"):
                form.attach_pending_new_requirements(job)
            messages.success(request, "Job posted successfully.")
            return redirect('job_list')
        else:
            messages.error(request, "Please correct the errors below.")
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
            job = form.save(commit=False)
            job.save()
            form.save_m2m()
            messages.success(request, "Job updated successfully.")
            return redirect('job_detail', pk=job.pk)
        else:
            messages.error(request, "Please correct the errors below.")
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


# core/views.py (application_create)
@login_required
def application_create(request, job_id):
    job = get_object_or_404(Job_Posting, pk=job_id, is_active=True)

    # limit resume choices in the form to current user's resumes
    resumes_qs = Resume.objects.filter(user=request.user)

    if request.method == "POST":
        form = ApplicationForm(request.POST, user=request.user)
        # ensure resume field only shows user's resumes (security)
        form.fields['resume'].queryset = resumes_qs

        # IMPORTANT: set the job on the form.instance before validation
        form.instance.job = job

        if form.is_valid():
            application = form.save(commit=False)
            # enforce ownership & job association server-side
            application.user = request.user
            application.job = job

            # optional: compute match_score here if you have a helper
            try:
                resume = application.resume
                if resume:
                    resume_skill_names = [s.name for s in resume.skills.all()]
                    job_req_names = [s.name for s in job.requirements.all()]
                    # replace with your actual scoring fn
                    application.match_score = calculate_match_score(resume_skill_names, job_req_names)
            except Exception:
                pass

            application.save()
            # persist any m2m fields (if any)
            form.save_m2m()

            messages.success(request, "Application submitted.")
            return redirect('application_list')
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        # GET: present form; include job as hidden initial so template has it if needed
        form = ApplicationForm(user=request.user, initial={'job': job.pk})
        form.fields['resume'].queryset = resumes_qs

    return render(request, "applications/application_form.html", {"form": form, "job": job})


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

    # permission: applicant or the job poster may edit
    if request.user != application.user and request.user != application.job.posted_by:
        messages.error(request, "You don't have permission to edit this application.")
        return redirect('application_detail', pk=pk)

    # pass user so form limits resume choices
    if request.method == "POST":
        form = ApplicationForm(request.POST, instance=application, user=request.user)
        # set instance.job so clean() sees it (especially if job is hidden)
        form.instance.job = application.job
        if form.is_valid():
            app = form.save(commit=False)
            # ensure user/job not changed illegitimately
            app.user = application.user
            app.job = application.job
            app.save()
            form.save_m2m()
            messages.success(request, "Application updated.")
            return redirect('application_detail', pk=pk)
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = ApplicationForm(instance=application, user=request.user)
    return render(request, "applications/application_form.html", {"form": form, "job": application.job})

@login_required
def application_delete(request, pk):
    """
    Allow deletion only by:
      - the applicant (application.user), or
      - the recruiter who posted the job (application.job.posted_by)
    Only responds to POST for deletion.
    """
    application = get_object_or_404(Application, pk=pk)
    # permission check
    if request.user != application.user and request.user != application.job.posted_by:
        messages.error(request, "You do not have permission to delete this application.")
        return redirect('application_detail', pk=pk)

    if request.method == 'POST':
        application.delete()
        messages.success(request, "Application deleted.")
        # Redirect recruiter to their applications by job, applicant to their list
        if request.user == application.job.posted_by:
            return redirect('application_list')
        return redirect('application_list')

    # GET -> show confirmation page
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
            messages.error(request, "Please correct the errors below.")
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