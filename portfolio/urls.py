from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = 'portfolio'

urlpatterns = [
    path('', views.index, name='dashboard'),
    path('login/', auth_views.LoginView.as_view(template_name='portfolio/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
]
