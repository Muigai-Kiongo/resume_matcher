from django.urls import path
from . import views



urlpatterns = [
    path('', views.role_redirect, name='role_redirect'),
    path('dashboard/seeker/', views.seeker_dashboard, name='seeker_dashboard'),
    path('dashboard/recruiter/', views.recruiter_dashboard, name='recruiter_dashboard'),

    # Resume URLs
    path('resumes/', views.resume_list, name='resume_list'),
    path('resumes/create/', views.resume_create, name='resume_create'),
    path('resumes/<int:pk>/', views.resume_detail, name='resume_detail'),
    path('resumes/<int:pk>/update/', views.resume_update, name='resume_update'),
    path('resumes/<int:pk>/delete/', views.resume_delete, name='resume_delete'),

    # Job Posting URLs
    path('jobs/', views.job_list, name='job_list'),
    path('jobs/create/', views.job_create, name='job_create'),
    path('jobs/<int:pk>/', views.job_detail, name='job_detail'),
    path('jobs/<int:pk>/update/', views.job_update, name='job_update'),
    path('jobs/<int:pk>/delete/', views.job_delete, name='job_delete'),

    # Application URLs
    path('applications/', views.application_list, name='application_list'),
    path('applications/create/<int:job_id>/', views.application_create, name='application_create'),
    path('applications/<int:pk>/', views.application_detail, name='application_detail'),
    path('applications/<int:pk>/update/', views.application_update, name='application_update'),
    path('applications/<int:pk>/delete/', views.application_delete, name='application_delete'),

    # Feedback URLs
    path('feedback/', views.feedback_list, name='feedback_list'),
    path('feedback/create/<int:application_id>/', views.feedback_create, name='feedback_create'),
    path('feedback/<int:pk>/', views.feedback_detail, name='feedback_detail'),
    path('feedback/<int:pk>/delete/', views.feedback_delete, name='feedback_delete'),

    # Messaging / Conversations (mapped inline — no separate namespace)
    path('messages/', views.conversations_list, name='conversations_list'),
    path('messages/create/', views.conversation_create, name='conversation_create'),
    path('messages/start/<int:user_id>/', views.start_conversation_with_user, name='start_conversation_with_user'),
    path('messages/<int:conversation_id>/', views.conversation_detail, name='conversation_detail'),
    path('messages/<int:conversation_id>/send/', views.message_create, name='message_create'),
    path('messages/message/<int:message_id>/read/', views.mark_message_read, name='mark_message_read'),
]