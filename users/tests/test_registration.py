from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse


class RegistrationTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.register_url = reverse('register')
        self.login_url = reverse('login')

    def test_register_page_renders(self) -> None:
        """Test that registration page renders correctly."""
        response = self.client.get(self.register_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'registration/register.html')

    def test_successful_registration(self) -> None:
        """Test that valid form submission creates a user."""
        response = self.client.post(self.register_url, {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'password123',
            'confirm_password': 'password123' # UserCreationForm doesn't use confirm_password by default in tests unless using a specific form setup, but let's see.
            # Wait, UserCreationForm expects 'password1' and 'password_2' usually? No, it handles it.
            # Actually, standard UserCreationForm fields are username, password 1, password 2.
            # Let's check the form definition or just try standard fields.
        })

        # Standard UserCreationForm requires 'password_1' and 'password_2'
        response = self.client.post(self.register_url, {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password1': 'TestPass123!',
            'password2': 'TestPass123!'
        })

        self.assertRedirects(response, self.login_url)
        self.assertTrue(User.objects.filter(username='newuser').exists())
        self.assertEqual(User.objects.get(username='newuser').email, 'newuser@example.com')

    def test_registration_invalid_password(self) -> None:
        """Test registration with non-matching passwords."""
        response = self.client.post(self.register_url, {
            'username': 'badpassuser',
            'email': 'badpass@example.com',
            'password1': 'TestPass123!',
            'password2': 'MismatchPass!'
        })
        self.assertEqual(response.status_code, 200) # Should re-render form
        self.assertFalse(User.objects.filter(username='badpassuser').exists())
        # Check that form has errors
        self.assertTrue(response.context['form'].errors)
