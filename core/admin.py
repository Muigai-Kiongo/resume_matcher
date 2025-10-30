from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils.html import format_html
import csv
import datetime
import logging

from .models import (
    User,
    Skill,
    Resume,
    Experience,
    Education,
    Job_Posting,
    Application,
    Feedback,
)

logger = logging.getLogger(__name__)


# helpers
def _csv_response(filename):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def export_selected_as_csv(modeladmin, request, queryset):
    """
    Generic CSV exporter used by specific admin actions below.
    """
    model = modeladmin.model
    opts = model._meta
    now = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    filename = f"{opts.model_name}_export_{now}.csv"
    response = _csv_response(filename)

    writer = csv.writer(response)
    # header using field verbose names
    try:
        headers = [f.verbose_name for f in opts.fields]
    except Exception:
        headers = [field.name for field in opts.fields]
    writer.writerow(headers)

    for obj in queryset:
        row = []
        for field in opts.fields:
            try:
                val = getattr(obj, field.name)
                # If the attribute is callable (rare), call it to get a string
                if callable(val):
                    try:
                        val = val()
                    except Exception:
                        val = str(val)
                row.append(str(val))
            except Exception:
                row.append(str(getattr(obj, field.name, "")))
        writer.writerow(row)
    return response


export_selected_as_csv.short_description = "Export selected items to CSV"


def print_selected_as_html(modeladmin, request, queryset):
    """
    Render a printable HTML report for the selected queryset.
    Uses template core/templates/admin/reports/report.html
    """
    opts = modeladmin.model._meta
    model_name = opts.verbose_name.title()
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    rows = []
    # build rows for known models to render useful columns
    if modeladmin.model is Application:
        headers = ["Application ID", "Applicant", "Job", "Status", "Score", "Submitted"]
        for a in queryset.select_related("user", "job", "resume"):
            rows.append({
                "Application ID": getattr(a, "application_id", ""),
                "Applicant": str(a.user),
                "Job": str(a.job),
                "Status": a.get_status_display(),
                "Score": f"{a.match_score:.2f}",
                "Submitted": a.submission_date.strftime("%Y-%m-%d %H:%M:%S") if a.submission_date else "",
                "detail": a,
            })
    elif modeladmin.model is Resume:
        headers = ["Resume ID", "User", "Uploaded", "Match Score", "Skills"]
        for r in queryset.select_related("user").prefetch_related("skills"):
            rows.append({
                "Resume ID": getattr(r, "resume_id", ""),
                "User": str(r.user),
                "Uploaded": r.uploaded_at.strftime("%Y-%m-%d %H:%M:%S") if r.uploaded_at else "",
                "Match Score": f"{r.match_score:.2f}",
                "Skills": r.get_skills_as_string(),
                "detail": r,
            })
    elif modeladmin.model is Job_Posting:
        headers = ["Job ID", "Title", "Company", "Posted By", "Active", "Created"]
        for j in queryset.select_related("posted_by").prefetch_related("requirements"):
            rows.append({
                "Job ID": getattr(j, "job_id", ""),
                "Title": j.title,
                "Company": j.company,
                "Posted By": str(j.posted_by),
                "Active": "Yes" if j.is_active else "No",
                "Created": j.created_at.strftime("%Y-%m-%d %H:%M:%S") if j.created_at else "",
                "detail": j,
            })
    else:
        headers = ["PK", "Object"]
        for obj in queryset:
            rows.append({"PK": getattr(obj, "pk", ""), "Object": str(obj), "detail": obj})

    html = render_to_string("admin/reports/report.html", {
        "model_name": model_name,
        "now": now,
        "headers": headers,
        "rows": rows,
        "user": request.user,
    })
    response = HttpResponse(content_type="text/html; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{opts.model_name}_report.html"'
    response.write(html)
    return response


print_selected_as_html.short_description = "Print selected items (HTML report)"


def print_selected_as_pdf(modeladmin, request, queryset):
    """
    Generate a PDF for the selected queryset using WeasyPrint.
    If WeasyPrint is not available, display an admin message pointing to installation steps.
    """
    try:
        from weasyprint import HTML, CSS  # type: ignore
    except Exception:
        msg = (
            "WeasyPrint is not installed or its native dependencies are missing. "
            "Install with `pip install weasyprint` and ensure system libs (cairo, pango, gdk-pixbuf) are available. "
            "Falling back to HTML report (downloadable)."
        )
        messages.warning(request, msg)
        return print_selected_as_html(modeladmin, request, queryset)

    opts = modeladmin.model._meta
    model_name = opts.verbose_name.title()
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    # Build same rows as the HTML printer (re-use logic)
    rows = []
    if modeladmin.model is Application:
        headers = ["Application ID", "Applicant", "Job", "Status", "Score", "Submitted"]
        for a in queryset.select_related("user", "job", "resume"):
            rows.append({
                "Application ID": getattr(a, "application_id", ""),
                "Applicant": str(a.user),
                "Job": str(a.job),
                "Status": a.get_status_display(),
                "Score": f"{a.match_score:.2f}",
                "Submitted": a.submission_date.strftime("%Y-%m-%d %H:%M:%S") if a.submission_date else "",
                "detail": a,
            })
    elif modeladmin.model is Resume:
        headers = ["Resume ID", "User", "Uploaded", "Match Score", "Skills"]
        for r in queryset.select_related("user").prefetch_related("skills"):
            rows.append({
                "Resume ID": getattr(r, "resume_id", ""),
                "User": str(r.user),
                "Uploaded": r.uploaded_at.strftime("%Y-%m-%d %H:%M:%S") if r.uploaded_at else "",
                "Match Score": f"{r.match_score:.2f}",
                "Skills": r.get_skills_as_string(),
                "detail": r,
            })
    elif modeladmin.model is Job_Posting:
        headers = ["Job ID", "Title", "Company", "Posted By", "Active", "Created"]
        for j in queryset.select_related("posted_by").prefetch_related("requirements"):
            rows.append({
                "Job ID": getattr(j, "job_id", ""),
                "Title": j.title,
                "Company": j.company,
                "Posted By": str(j.posted_by),
                "Active": "Yes" if j.is_active else "No",
                "Created": j.created_at.strftime("%Y-%m-%d %H:%M:%S") if j.created_at else "",
                "detail": j,
            })
    else:
        headers = ["PK", "Object"]
        for obj in queryset:
            rows.append({"PK": getattr(obj, "pk", ""), "Object": str(obj), "detail": obj})

    html = render_to_string("admin/reports/report.html", {
        "model_name": model_name,
        "now": now,
        "headers": headers,
        "rows": rows,
        "user": request.user,
    })

    try:
        pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf(stylesheets=[CSS(string='@page { size: A4; margin: 1cm }')])
    except Exception as e:
        logger.exception("WeasyPrint failed to generate PDF: %s", e)
        messages.error(request, "Failed to generate PDF. See logs for details.")
        return print_selected_as_html(modeladmin, request, queryset)

    filename = f"{opts.model_name}_report_{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')}.pdf"
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


print_selected_as_pdf.short_description = "Print selected items (PDF)"


# ReportAdminMixin: adds per-ModelAdmin report endpoints and changelist template
class ReportAdminMixin:
    change_list_template = "admin/change_list_with_reports.html"

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path("generate-report/", self.admin_site.admin_view(self.generate_report_view), name=f"{self.model._meta.model_name}_generate_report"),
            path("print-pdf/", self.admin_site.admin_view(self.print_pdf_view), name=f"{self.model._meta.model_name}_print_pdf"),
        ]
        return custom_urls + urls

    def generate_report_view(self, request):
        """
        Generate an HTML report for the full queryset visible to this admin (respecting the admin's get_queryset).
        Returns an HTML file downloadable (attachment).
        """
        qs = self.get_queryset(request).select_related().all()
        # Reuse the print_selected_as_html logic by passing entire queryset
        return print_selected_as_html(self, request, qs)

    def print_pdf_view(self, request):
        """
        Generate a PDF for the full queryset using WeasyPrint (or fallback to HTML).
        """
        qs = self.get_queryset(request).select_related().all()
        return print_selected_as_pdf(self, request, qs)


# ModelAdmins
@admin.register(User)
class UserAdmin(ReportAdminMixin, BaseUserAdmin):
    list_display = ("username", "email", "account_type", "is_staff", "is_superuser", "created_at")
    list_filter = ("account_type", "is_staff", "is_superuser")
    search_fields = ("username", "email")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("email", "profile_picture")}),
        ("Account", {"fields": ("account_type",)}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    actions = [export_selected_as_csv, print_selected_as_html, print_selected_as_pdf]


@admin.register(Skill)
class SkillAdmin(ReportAdminMixin, admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    actions = [export_selected_as_csv, print_selected_as_html]


class ExperienceInline(admin.TabularInline):
    model = Experience
    extra = 0
    fields = ("company", "title", "start_date", "end_date", "is_current", "order")
    show_change_link = False


class EducationInline(admin.TabularInline):
    model = Education
    extra = 0
    fields = ("institution", "degree", "start_year", "end_year", "order")
    show_change_link = False


@admin.register(Resume)
class ResumeAdmin(ReportAdminMixin, admin.ModelAdmin):
    list_display = ("resume_id", "user", "uploaded_at", "match_score", "skills_list", "download_link")
    list_filter = ("uploaded_at",)
    search_fields = ("user__username", "user__email", "summary")
    readonly_fields = ("uploaded_at", "updated_at", "match_score")
    inlines = [ExperienceInline, EducationInline]
    actions = [export_selected_as_csv, print_selected_as_html, print_selected_as_pdf]

    def skills_list(self, obj):
        return ", ".join([s.name for s in obj.skills.all()]) if obj.skills.exists() else "—"
    skills_list.short_description = "Skills"

    def download_link(self, obj):
        if obj.file:
            return format_html('<a href="{}" target="_blank">Download</a>', obj.file.url)
        return "No file"
    download_link.short_description = "File"


@admin.register(Job_Posting)
class JobPostingAdmin(ReportAdminMixin, admin.ModelAdmin):
    list_display = ("job_id", "title", "company", "posted_by", "is_active", "created_at")
    list_filter = ("is_active", "created_at", "posted_by")
    search_fields = ("title", "company", "posted_by__username")
    readonly_fields = ("created_at", "updated_at")
    filter_horizontal = ("requirements",)
    actions = [export_selected_as_csv, print_selected_as_html, print_selected_as_pdf]


@admin.register(Application)
class ApplicationAdmin(ReportAdminMixin, admin.ModelAdmin):
    list_display = ("application_id", "user", "job", "status", "match_score", "submission_date")
    list_filter = ("status", "submission_date", "job__company")
    search_fields = ("user__username", "job__title", "job__company")
    readonly_fields = ("submission_date", "updated_at")
    actions = [
        export_selected_as_csv,
        print_selected_as_html,
        print_selected_as_pdf,
        "mark_as_shortlisted",
        "mark_as_rejected",
        "mark_as_hired",
    ]

    def mark_as_shortlisted(self, request, queryset):
        updated = queryset.update(status="shortlisted")
        self.message_user(request, f"{updated} application(s) marked as shortlisted.")
    mark_as_shortlisted.short_description = "Mark selected applications as Shortlisted"

    def mark_as_rejected(self, request, queryset):
        updated = queryset.update(status="rejected")
        self.message_user(request, f"{updated} application(s) marked as rejected.")
    mark_as_rejected.short_description = "Mark selected applications as Rejected"

    def mark_as_hired(self, request, queryset):
        updated = queryset.update(status="hired")
        self.message_user(request, f"{updated} application(s) marked as hired.")
    mark_as_hired.short_description = "Mark selected applications as Hired"


@admin.register(Feedback)
class FeedbackAdmin(ReportAdminMixin, admin.ModelAdmin):
    list_display = ("user", "application", "rating", "created_at")
    list_filter = ("rating", "created_at")
    search_fields = ("user__username", "application__job__title")
    readonly_fields = ("created_at",)
    actions = [export_selected_as_csv, print_selected_as_html]


# Admin site branding
admin.site.site_header = "Resume Matcher Admin"
admin.site.site_title = "Resume Matcher"
admin.site.index_title = "Site Administration"