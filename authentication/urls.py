from django.urls import path
from . import views
from .views import health_check

urlpatterns = [
    path("health/", health_check, name="health_check"),
    path('register-superadmin/', views.register_superadmin, name='request_password_reset'),
    path('login/', views.login, name='request_password_reset'),
    path('logout/', views.logout, name='request_password_reset'),
    # path('create-agent/', views.create_agent, name='request_password_reset'),
    path('password-reset/request/', views.request_password_reset, name='request_password_reset'),
    path('password-reset/verify/', views.verify_reset_code, name='verify_reset_code'),
    path('password-reset/confirm/', views.reset_password, name='reset_password'),
]
