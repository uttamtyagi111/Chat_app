from django.urls import path
from authentication import views
from django.conf import settings
from django.conf.urls.static import static
from authentication.views import LoginAPIView, SignupAPIView, ResetPasswordRequestAPIView


urlpatterns = [
path('login/', LoginAPIView.as_view(), name='login'),
path('Signup/', SignupAPIView.as_view(), name='signup'),    
path('reset-password/', ResetPasswordRequestAPIView.as_view(), name='reset-password'),

]