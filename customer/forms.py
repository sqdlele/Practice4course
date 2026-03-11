from django import forms
import re
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

User = get_user_model()

FIO_NO_DIGITS = re.compile(r'\d')


class CustomerRegisterForm(UserCreationForm):
    """Регистрация обычного пользователя (клиента)."""
    phone = forms.CharField(
        label='Телефон',
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': '89991234567'}),
    )
    last_name = forms.CharField(
        label='Фамилия',
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Фамилия', 'autocomplete': 'family-name'}),
    )
    first_name = forms.CharField(
        label='Имя',
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Имя', 'autocomplete': 'given-name'}),
    )
    patronymic = forms.CharField(
        label='Отчество',
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Отчество', 'autocomplete': 'additional-name'}),
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

    def _clean_fio(self, value, field_name):
        if not value:
            return value
        if FIO_NO_DIGITS.search(value):
            raise forms.ValidationError('В поле не должно быть цифр.')
        return value.strip()

    def clean_last_name(self):
        return self._clean_fio(self.cleaned_data.get('last_name'), 'last_name')

    def clean_first_name(self):
        return self._clean_fio(self.cleaned_data.get('first_name'), 'first_name')

    def clean_patronymic(self):
        return self._clean_fio(self.cleaned_data.get('patronymic'), 'patronymic')


class CustomerProfileForm(forms.ModelForm):
    """Редактирование профиля в личном кабинете. В ФИО нельзя вводить цифры."""
    class Meta:
        model = User
        fields = ('last_name', 'first_name', 'patronymic', 'email')
        widgets = {
            'last_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Фамилия', 'autocomplete': 'family-name'}),
            'first_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Имя', 'autocomplete': 'given-name'}),
            'patronymic': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Отчество', 'autocomplete': 'additional-name'}),
            'email': forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'Email (необязательно)'}),
        }

    def _clean_fio(self, value):
        if not value:
            return value
        if FIO_NO_DIGITS.search(value):
            raise forms.ValidationError('В поле не должно быть цифр.')
        return value.strip()

    def clean_last_name(self):
        return self._clean_fio(self.cleaned_data.get('last_name', ''))

    def clean_first_name(self):
        return self._clean_fio(self.cleaned_data.get('first_name', ''))

    def clean_patronymic(self):
        return self._clean_fio(self.cleaned_data.get('patronymic', ''))


class OrderReviewForm(forms.Form):
    """Форма отзыва по выданному заказу."""
    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]
    text = forms.CharField(
        label='Текст отзыва',
        widget=forms.Textarea(attrs={'class': 'form-input', 'rows': 4, 'placeholder': 'Расскажите, как прошла работа над заказом'}),
        min_length=10,
        max_length=2000,
    )
    rating = forms.TypedChoiceField(
        label='Оценка',
        choices=RATING_CHOICES,
        coerce=int,
        widget=forms.RadioSelect(attrs={'class': 'form-radio-group'}),
        initial=5,
    )
