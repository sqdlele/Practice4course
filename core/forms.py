from django import forms
from decimal import Decimal
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

from .models import Service, Order, OrderItem, Client

User = get_user_model()


class RegisterForm(UserCreationForm):
    """Регистрация сотрудника."""
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


class OrderCreateForm(forms.Form):
    """Оформление заказа: выбор клиента или быстрая регистрация + услуги."""
    client_id = forms.IntegerField(required=False, widget=forms.HiddenInput())
    new_client_name = forms.CharField(
        label='ФИО нового клиента',
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'ФИО'}),
    )
    new_client_phone = forms.CharField(
        label='Телефон нового клиента',
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': '89991234567'}),
    )
    services = forms.ModelMultipleChoiceField(
        label='Услуги',
        queryset=Service.objects.all(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'service-checkbox'}),
        required=True,
    )
    ready_by = forms.DateField(
        label='Готовность к',
        required=True,
        input_formats=['%d/%m/%Y', '%d.%m.%Y', '%Y-%m-%d'],
        widget=forms.DateInput(
            format='%d/%m/%Y',
            attrs={'class': 'form-input', 'placeholder': 'день/месяц/год'},
        ),
    )

    def clean(self):
        data = super().clean()
        client_id = data.get('client_id')
        new_name = (data.get('new_client_name') or '').strip()
        new_phone = (data.get('new_client_phone') or '').strip()

        if client_id:
            if not Client.objects.filter(pk=client_id).exists():
                raise forms.ValidationError('Выбранный клиент не найден.')
            return data

        if not new_name or not new_phone:
            raise forms.ValidationError(
                'Укажите существующего клиента (поиск выше) или заполните ФИО и телефон для нового.'
            )
        return data

    def get_client(self):
        """Возвращает клиента: либо по client_id, либо создаёт нового."""
        client_id = self.cleaned_data.get('client_id')
        if client_id:
            return Client.objects.get(pk=client_id)
        return Client.objects.create(
            name=self.cleaned_data['new_client_name'].strip(),
            phone=self.cleaned_data['new_client_phone'].strip(),
        )
