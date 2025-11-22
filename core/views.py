from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden, Http404, JsonResponse, HttpResponseBadRequest
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags
from django.urls import reverse
import logging
import os
import tempfile
from django.utils import timezone
from django.core.paginator import Paginator

from .models import Resume, Job_Posting, Application, Feedback, Skill, Conversation, Message, User
from .forms import (
    ResumeForm,
    JobPostingForm,
    ApplicationForm,
    FeedbackForm,
    ExperienceFormSet,
    EducationFormSet,
    ConversationForm,
    MessageForm
)
from .utils import (
    extract_text_from_resume,
    extract_skills,
    calculate_match_score,
)

logger = logging.getLogger(__name__)


@login_required
def role_redirect(request):
    """
    Redirect users after login according to their role, with explicit admin handling.

    Priority:
      1. superuser / staff  -> admin dashboard (prefer 'admin_dashboard' if present, fall back to Django admin)
      2. recruiter          -> recruiter_dashboard
      3. seeker             -> seeker_dashboard
      4. fallback           -> send to profile edit if available, otherwise to login

    Notes:
    - Keeps a helpful message when account_type is missing / profile incomplete.
    - Don't remove this view's @login_required decorator — it's intended as the post-login redirect.
    """
    user = request.user

    # Admins / staff should go to an admin area.
    if user.is_superuser or user.is_staff:
        # Prefer a custom named admin-dashboard view if your project has one,
        # otherwise fall back to Django's built-in admin index.
        try:
            return redirect('admin:index')  # optional custom admin dashboard view
        except Exception:
            return redirect('admin:index')  # Django admin

    account_type = getattr(user, "account_type", None)

    if account_type == 'recruiter':
        return redirect('recruiter_dashboard')
    if account_type == 'seeker':
        return redirect('seeker_dashboard')

    # Fallback: user has no account_type set or is unusual.
    messages.info(request, "Please complete your account profile to continue.")
    # Try to send them to a profile-editing view if you have one, otherwise to login.
    try:
        return redirect('profile_edit')
    except Exception:
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
                    application.match_score = calculate_match_score(resume_skill_names, job_req_names)
            except Exception:
                logger.exception("Error computing match score", exc_info=True)

            application.save()
            # persist any m2m fields (if any)
            form.save_m2m()

            # Build absolute URLs for emails
            try:
                application_url = request.build_absolute_uri(reverse('application_detail', args=[application.pk]))
            except Exception:
                application_url = ""
            try:
                resume_url = request.build_absolute_uri(reverse('resume_detail', args=[application.resume.pk])) if application.resume else ""
            except Exception:
                resume_url = ""

            # Notify the recruiter (job.posted_by) if they have an email
            if job.posted_by and getattr(job.posted_by, "email", None):
                try:
                    ctx = {
                        "job": job,
                        "application": application,
                        "resume": application.resume,
                        "application_url": application_url,
                        "resume_url": resume_url,
                    }
                    subject = f"New application for {job.title} at {job.company}"
                    html_body = render_to_string("emails/new_application_notification.html", ctx)
                    text_body = render_to_string("emails/new_application_notification.txt", ctx)
                    msg = EmailMultiAlternatives(subject, strip_tags(html_body), None, [job.posted_by.email])
                    msg.attach_alternative(html_body, "text/html")
                    msg.send(fail_silently=False)
                except Exception as e:
                    logger.exception("Failed to send new application email to recruiter: %s", e)

            # Confirmation email to applicant
            if request.user and getattr(request.user, "email", None):
                try:
                    ctx = {
                        "job": job,
                        "application": application,
                        "application_url": application_url,
                    }
                    subject = f"Application submitted: {job.title} at {job.company}"
                    html_body = render_to_string("emails/application_submitted.html", ctx)
                    text_body = render_to_string("emails/application_submitted.txt", ctx)
                    msg = EmailMultiAlternatives(subject, strip_tags(html_body), None, [request.user.email])
                    msg.attach_alternative(html_body, "text/html")
                    msg.send(fail_silently=False)
                except Exception as e:
                    logger.exception("Failed to send confirmation email to applicant: %s", e)

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

    prev_status = application.status

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

            # If status changed and edited by the job poster, notify applicant
            if prev_status != app.status and request.user == application.job.posted_by:
                if app.user and getattr(app.user, "email", None):
                    try:
                        application_url = request.build_absolute_uri(reverse('application_detail', args=[app.pk]))
                        ctx = {"application": app, "application_url": application_url}
                        subject = f"Update: your application for {app.job.title}"
                        html_body = render_to_string("emails/application_status_changed.html", ctx)
                        text_body = render_to_string("emails/application_status_changed.txt", ctx)
                        msg = EmailMultiAlternatives(subject, strip_tags(html_body), None, [app.user.email])
                        msg.attach_alternative(html_body, "text/html")
                        msg.send(fail_silently=False)
                    except Exception as e:
                        logger.exception("Failed to send status-change email: %s", e)

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
    return render(request, 'feedback/feedback_confirm_delete.html', {'feedback': feedback}
    )


@login_required
def conversations_list(request):
    """
    Show conversations that include the current user.
    Paginated to 25 per page.
    """
    qs = Conversation.objects.filter(participants=request.user).select_related("last_message").prefetch_related("participants").order_by("-updated_at")
    paginator = Paginator(qs, 25)
    page_number = request.GET.get("page") or 1
    page = paginator.get_page(page_number)
    return render(request, "messages/conversation_list.html", {"page": page, "conversations": page.object_list})


@login_required
@transaction.atomic
def conversation_create(request):
    """
    Create a new conversation. If a conversation with the same exact participants and subject should be reused,
    consider implementing a dedupe check. For now this always creates a new Conversation.
    """
    if request.method == "POST":
        form = ConversationForm(request.POST)
        if form.is_valid():
            conv = form.save(commit=False)
            conv.save()
            # Add participants (ConversationForm validates at least 2 participants)
            participants = form.cleaned_data["participants"]
            conv.participants.add(*participants)
            # Ensure the creator is included
            if request.user not in participants:
                conv.participants.add(request.user)
            conv.save()
            # Redirect to non-namespaced route
            return redirect("conversation_detail", conversation_id=conv.conversation_id)
    else:
        # Prefill participants with current user for convenience (but form requires 2+)
        form = ConversationForm(initial={"participants": [request.user.pk]})
    return render(request, "messages/conversation_form.html", {"form": form})


@login_required
def conversation_detail(request, conversation_id):
    """
    Display one conversation with its messages and a form to post new messages.
    Marks unread messages as read for the current user when the page is loaded.
    """
    conv = get_object_or_404(Conversation, conversation_id=conversation_id)
    if not conv.participants.filter(pk=request.user.pk).exists():
        return HttpResponseForbidden("You are not a participant in this conversation.")

    # Messages ordered oldest -> newest for display
    messages_qs = conv.messages.select_related("sender").order_by("created_at")

    # Mark unread messages (sender != current user) as read by this user
    unread_messages = messages_qs.exclude(read_by=request.user).exclude(sender=request.user)
    if unread_messages.exists():
        for m in unread_messages:
            m.read_by.add(request.user)

    # Provide a message form for posting
    msg_form = MessageForm()

    # paging recent messages for long conversations (show latest 100 by default)
    paginator = Paginator(messages_qs, 200)
    page_num = request.GET.get("page") or paginator.num_pages
    page = paginator.get_page(page_num)

    return render(request, "messages/conversation_detail.html", {
        "conversation": conv,
        "messages": page.object_list,
        "page": page,
        "form": msg_form,
    })


@login_required
@transaction.atomic
def message_create(request, conversation_id):
    """
    POST handler to create a message in a conversation.
    Accepts 'content' and optional file 'attachment'.
    Redirects back to the conversation detail.
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    conv = get_object_or_404(Conversation, conversation_id=conversation_id)
    if not conv.participants.filter(pk=request.user.pk).exists():
        return HttpResponseForbidden("You are not a participant in this conversation.")

    form = MessageForm(request.POST, request.FILES)
    if form.is_valid():
        msg = form.save(commit=False)
        msg.conversation = conv
        msg.sender = request.user
        msg.save()
        # message.save() will update conversation.last_message (per model.save override)
        # Mark message as read by sender
        try:
            msg.read_by.add(request.user)
        except Exception:
            # ignore read_by failures for now
            pass
        # Redirect to non-namespaced route
        return redirect("conversation_detail", conversation_id=conv.conversation_id)
    else:
        # On invalid form, re-render the conversation detail with errors
        messages_qs = conv.messages.select_related("sender").order_by("created_at")
        return render(request, "messages/conversation_detail.html", {
            "conversation": conv,
            "messages": messages_qs,
            "form": form,
        })


@login_required
def mark_message_read(request, message_id):
    """
    Mark a single message as read by the current user. Returns JSON.
    """
    msg = get_object_or_404(Message, message_id=message_id)
    conv = msg.conversation
    if not conv.participants.filter(pk=request.user.pk).exists():
        return JsonResponse({"error": "forbidden"}, status=403)
    msg.read_by.add(request.user)
    return JsonResponse({"ok": True, "message_id": msg.message_id, "read_by_count": msg.read_by.count()})


@login_required
def start_conversation_with_user(request, user_id, subject=None):
    """
    Convenience view to start a one-to-one conversation with a specific user.
    If a conversation between the two users with the same subject already exists you may choose to reuse it.
    This implementation always creates a new conversation for simplicity.
    """
    other = get_object_or_404(User, pk=user_id)
    if other == request.user:
        return HttpResponseBadRequest("Cannot start a conversation with yourself.")

    if request.method == "POST":
        form = ConversationForm(request.POST)
        if form.is_valid():
            conv = form.save(commit=False)
            conv.save()
            conv.participants.add(request.user, other)
            # Redirect to non-namespaced route
            return redirect("conversation_detail", conversation_id=conv.conversation_id)
    else:
        initial = {"participants": [request.user.pk, other.pk]}
        if subject:
            initial["subject"] = subject
        form = ConversationForm(initial=initial)
    return render(request, "messages/conversation_form.html", {"form": form, "other": other})