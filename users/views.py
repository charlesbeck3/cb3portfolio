from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from .forms import UserRegisterForm


def register(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            form.save()
            username = form.cleaned_data.get("username")
            messages.success(request, f"Account created for {username}! You can now log in")
            return redirect("login")
    else:
        form = UserRegisterForm()
    return render(request, "registration/register.html", {"form": form})
