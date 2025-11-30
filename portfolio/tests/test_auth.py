from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User

class AuthTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='testpassword')
        self.login_url = reverse('portfolio:login')
        self.logout_url = reverse('portfolio:logout')
        self.dashboard_url = reverse('portfolio:dashboard')

    def test_login_required_for_dashboard(self):
        """Test that dashboard requires login."""
        response = self.client.get(self.dashboard_url)
        self.assertNotEqual(response.status_code, 200)
        self.assertRedirects(response, f'{self.login_url}?next={self.dashboard_url}')

    def test_login_view(self):
        """Test that login page renders correctly."""
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'portfolio/login.html')

    def test_successful_login(self):
        """Test valid login redirects to dashboard."""
        response = self.client.post(self.login_url, {
            'username': 'testuser',
            'password': 'testpassword'
        })
        self.assertRedirects(response, self.dashboard_url)
        
        # Verify user is logged in
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Welcome, testuser')

    def test_logout(self):
        """Test logout functionality."""
        self.client.login(username='testuser', password='testpassword')
        
        response = self.client.post(self.logout_url)
        self.assertRedirects(response, self.login_url)
        
        # Verify user is logged out (cannot access dashboard)
        response = self.client.get(self.dashboard_url)
        self.assertNotEqual(response.status_code, 200)
        self.assertRedirects(response, f'{self.login_url}?next={self.dashboard_url}')
