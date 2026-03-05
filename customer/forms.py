from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

User = get_user_model()


class CustomerRegisterForm(UserCreationForm):
    """Регистрация обычного пользователя (клиента)."""
    phone = forms.CharField(
        label='Телефон',
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': '89991234567'}),
    )
    last_name = forms.CharField(
        label='Фамилия',
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Фамилия'}),
    )
    first_name = forms.CharField(
        label='Имя',
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Имя'}),
    )
    patronymic = forms.CharField(
        label='Отчество',
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Отчество'}),
    )
    password1 = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Пароль'}),
    )
    password2 = forms.CharField(
        label='Повтор пароля',
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Повторите пароль'}),
    )

    class Meta:
        model = User
        fields = ('phone', 'last_name', 'first_name', 'patronymic', 'password1', 'password2')


class CustomerProfileForm(forms.ModelForm):
    """Редактирование профиля в личном кабинете."""
    class Meta:
        model = User
        fields = ('last_name', 'first_name', 'patronymic', 'email')
        widgets = {
            'last_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Фамилия'}),
            'first_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Имя'}),
            'patronymic': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Отчество'}),
            'email': forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'Email (необязательно)'}),
        }
