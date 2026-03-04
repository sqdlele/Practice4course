from django.shortcuts import render, redirect
from django.db.models import Q
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.decorators import login_required
from django.views.generic import CreateView
from django.urls import reverse_lazy
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .models import Order, Client, Service, OrderItem
from .forms import RegisterForm, OrderCreateForm


from django.contrib.auth.forms import AuthenticationForm


class CustomAuthForm(AuthenticationForm):
    """Вход с русским сообщением для неподтверждённых пользователей."""
    error_messages = {
        **AuthenticationForm.error_messages,
        'inactive': 'Учётная запись ещё не подтверждена администратором.',
    }


class CustomLoginView(LoginView):
    template_name = 'core/login.html'
    redirect_authenticated_user = True
    authentication_form = CustomAuthForm


class CustomLogoutView(LogoutView):
    next_page = 'core:login'


class RegisterView(CreateView):
    form_class = RegisterForm
    template_name = 'core/register.html'
    success_url = reverse_lazy('core:login')

    def form_valid(self, form):
        user = form.save(commit=False)
        user.is_active = False  # Вход только после подтверждения админом
        user.save()
        from django.contrib import messages
        messages.success(
            self.request,
            'Регистрация успешна. Вход будет доступен после подтверждения администратором.'
        )
        return redirect(self.success_url)


@login_required
def home(request):
    """Главный экран: счётчики, горящие заказы, поиск."""
    today = timezone.localdate()

    # Счётчики: В работе = Принято + В чистке; Готово к выдаче = Готово
    in_work = Order.objects.filter(
        status__in=[Order.STATUS_ACCEPTED, Order.STATUS_IN_PROGRESS]
    ).count()
    ready_count = Order.objects.filter(status=Order.STATUS_READY).count()

    # Горящие заказы: готовность сегодня или просрочены, не выданы
    urgent_orders = Order.objects.filter(
        status__in=[Order.STATUS_ACCEPTED, Order.STATUS_IN_PROGRESS, Order.STATUS_READY],
        ready_by__lte=today,
    ).select_related('client').order_by('ready_by', 'created_at')[:20]

    # Поиск по ID или телефону
    query = request.GET.get('q', '').strip()
    search_results = []
    if query:
        if query.isdigit():
            search_results = Order.objects.filter(pk=int(query)).select_related('client')
        else:
            search_results = Order.objects.filter(
                client__phone__icontains=query
            ).select_related('client').order_by('-created_at')[:20]

    context = {
        'in_work': in_work,
        'ready_count': ready_count,
        'urgent_orders': urgent_orders,
        'search_query': query,
        'search_results': search_results,
    }
    return render(request, 'core/home.html', context)


@login_required
@require_GET
def api_client_search(request):
    """Живой поиск клиентов по имени или телефону (JSON)."""
    q = (request.GET.get('q') or '').strip()[:50]
    if len(q) < 2:
        return JsonResponse({'clients': []})
    clients = Client.objects.filter(
        Q(name__icontains=q) | Q(phone__icontains=q)
    ).values('id', 'name', 'phone')[:15]
    return JsonResponse({'clients': list(clients)})


@login_required
def order_create(request):
    """Оформление нового заказа: выбор или регистрация клиента + услуги."""
    from decimal import Decimal

    default_ready = timezone.localdate() + timezone.timedelta(days=3)
    form = OrderCreateForm(
        request.POST or None,
        initial={'ready_by': default_ready},
    )

    if request.method == 'POST' and form.is_valid():
        client = form.get_client()
        discount = Decimal('3') if client.completed_orders_count() >= 2 else Decimal('0')

        order = Order.objects.create(
            client=client,
            complexity=form.cleaned_data['complexity'],
            discount_percent=discount,
            ready_by=form.cleaned_data['ready_by'],
        )
        for service in form.cleaned_data['services']:
            OrderItem.objects.create(
                order=order,
                service=service,
                unit_price=service.price,
                quantity=1,
            )

        from django.contrib import messages
        messages.success(request, f'Заказ #{order.pk} оформлен. Итого: {order.get_total()} ₽.')
        return redirect('core:home')

    return render(request, 'core/order_create.html', {
        'form': form,
        'services': Service.objects.all(),
    })
