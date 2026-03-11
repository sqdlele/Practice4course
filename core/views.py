from datetime import timedelta
from decimal import Decimal
import re
from django.shortcuts import render, redirect
from django.db.models import Q, Prefetch
from django.contrib.auth.views import LoginView, LogoutView
from functools import wraps
from django.contrib.auth.decorators import login_required as _login_required


def login_required(view_func):
    """login_required with staff login URL."""
    return _login_required(view_func, login_url='core:login')
from django.views.generic import CreateView
from django.urls import reverse_lazy
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.shortcuts import get_object_or_404

from .models import Order, Client, Service, OrderItem, ServiceCategory
from .forms import RegisterForm, OrderCreateForm
from customer.models import ChatRoom, ChatMessage

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

    # Поиск по ID, ФИО или телефону (ФИО — без учёта регистра, телефон — по цифрам)
    query = request.GET.get('q', '').strip()
    search_results = []
    if query:
        if query.isdigit():
            search_results = Order.objects.filter(pk=int(query)).select_related('client')
        else:
            search_results = _order_search_by_client(query)

    web_orders_new = Order.objects.filter(source=Order.SOURCE_WEB, status=Order.STATUS_ACCEPTED).count()

    context = {
        'in_work': in_work,
        'ready_count': ready_count,
        'urgent_orders': urgent_orders,
        'search_query': query,
        'search_results': search_results,
        'web_orders_new_count': web_orders_new,
    }
    return render(request, 'core/home.html', context)


def _order_search_by_client(q):
    """Поиск заказов по ФИО (без учёта регистра) или телефону (по цифрам). Регистр через Python — SQLite не переводит кириллицу в lower()."""
    q_lower = q.lower()
    digits = re.sub(r'\D', '', q)
    # По телефону — в БД
    phone_q = Q(client__phone__icontains=q)
    if len(digits) >= 3:
        phone_q |= Q(client__phone__contains=digits)
    by_phone = list(
        Order.objects.filter(phone_q).select_related('client').order_by('-created_at')[:20]
    )
    seen_ids = {o.pk for o in by_phone}
    if len(by_phone) >= 20:
        return by_phone
    # По ФИО без учёта регистра — в Python (кириллица в SQLite lower() не поддерживается)
    candidates = (
        Order.objects.exclude(pk__in=seen_ids)
        .select_related('client')
        .order_by('-created_at')[:300]
    )
    for order in candidates:
        if len(by_phone) >= 20:
            break
        if q_lower in order.client.name.lower():
            by_phone.append(order)
            seen_ids.add(order.pk)
    return by_phone


@login_required
@require_GET
def api_client_search(request):
    """Живой поиск клиентов по имени или телефону (JSON). ФИО без учёта регистра — через Python (кириллица в SQLite)."""
    q = (request.GET.get('q') or '').strip()[:50]
    if len(q) < 2:
        return JsonResponse({'clients': []})
    q_lower = q.lower()
    digits = re.sub(r'\D', '', q)
    # По телефону — в БД
    phone_q = Q(phone__icontains=q)
    if len(digits) >= 3:
        phone_q |= Q(phone__contains=digits)
    by_phone = list(Client.objects.filter(phone_q).values('id', 'name', 'phone')[:15])
    seen_ids = {c['id'] for c in by_phone}
    if len(by_phone) >= 15:
        return JsonResponse({'clients': by_phone})
    # По ФИО без учёта регистра — в Python
    for client in Client.objects.exclude(pk__in=seen_ids).values('id', 'name', 'phone').order_by('id')[:400]:
        if len(by_phone) >= 15:
            break
        if q_lower in (client['name'] or '').lower():
            by_phone.append(client)
            seen_ids.add(client['id'])
    return JsonResponse({'clients': by_phone})


@login_required
@require_GET
def api_order_search(request):
    """Живой поиск заказов по ID, ФИО или телефону клиента (JSON)."""
    q = (request.GET.get('q') or '').strip()[:50]
    if not q:
        return JsonResponse({'orders': []})
    if q.isdigit():
        orders = Order.objects.filter(pk=int(q)).select_related('client')
    else:
        orders = _order_search_by_client(q)
    status_display = dict(Order.STATUS_CHOICES)
    return JsonResponse({
        'orders': [
            {
                'id': o.pk,
                'client_name': o.client.name,
                'client_phone': o.client.phone,
                'status': o.status,
                'status_display': status_display.get(o.status, o.status),
                'ready_by': o.ready_by.strftime('%d.%m.%Y') if o.ready_by else None,
            }
            for o in orders
        ]
    })


@login_required
def order_create(request):
    """Оформление нового заказа: выбор или регистрация клиента + услуги по категориям с подпунктами."""
    default_ready = timezone.localdate() + timedelta(days=3)
    form = OrderCreateForm(
        request.POST or None,
        initial={'ready_by': default_ready},
    )

    if request.method == 'POST' and form.is_valid():
        client = form.get_client()
        discount = Decimal('3') if client.completed_orders_count() >= 2 else Decimal('0')

        order = Order.objects.create(
            client=client,
            discount_percent=discount,
            ready_by=form.cleaned_data['ready_by'],
        )
        for service in form.cleaned_data['services']:
            qty = request.POST.get(f'quantity_{service.pk}', '1')
            try:
                quantity = max(1, int(qty))
            except (ValueError, TypeError):
                quantity = 1
            length = Decimal(request.POST.get(f'length_{service.pk}', '0') or '0')
            width = Decimal(request.POST.get(f'width_{service.pk}', '0') or '0')
            weight = Decimal(request.POST.get(f'weight_{service.pk}', '0') or '0')
            complexity = Decimal(request.POST.get(f'complexity_{service.pk}', '1.0') or '1.0')
            OrderItem.objects.create(
                order=order,
                service=service,
                unit_price=service.price,
                quantity=quantity,
                length=length,
                width=width,
                weight=weight,
                complexity=complexity,
            )

        from django.contrib import messages
        messages.success(request, f'Заказ #{order.pk} оформлен. Итого: {order.get_total()} ₽.')
        return redirect('core:home')

    # Группировка: категории → родительские услуги → выбираемые пункты (дети или сама услуга)
    categories = ServiceCategory.objects.prefetch_related(
        Prefetch(
            'services',
            queryset=Service.objects.filter(parent__isnull=True).prefetch_related('children').order_by('name'),
        )
    ).order_by('order', 'name')

    service_groups = []
    for cat in categories:
        groups = []
        for parent in cat.services.all():
            children = list(parent.children.all())
            items = children if children else [parent]
            groups.append({'parent': parent, 'items': items})
        if groups:
            service_groups.append({'category': cat, 'groups': groups})

    # Услуги без категории (родительские) — одна общая группа
    uncat = Service.objects.filter(category__isnull=True, parent__isnull=True).prefetch_related('children').order_by('name')
    if uncat.exists():
        uncat_groups = []
        for parent in uncat:
            children = list(parent.children.all())
            items = children if children else [parent]
            uncat_groups.append({'parent': parent, 'items': items})
        service_groups.append({'category': None, 'groups': uncat_groups})

    return render(request, 'core/order_create.html', {
        'form': form,
        'service_groups': service_groups,
    })


@login_required
def order_detail(request, pk):
    """Детальная страница заказа: просмотр, смена статуса, редактирование позиций."""
    order = get_object_or_404(
        Order.objects.select_related('client', 'delivery_option').prefetch_related('items__service'),
        pk=pk,
    )

    if request.method == 'POST':
        from django.contrib import messages
        action = request.POST.get('action')

        if action == 'change_status':
            new_status = request.POST.get('status', '')
            valid = dict(Order.STATUS_CHOICES)
            if new_status in valid:
                order.status = new_status
                order.save(update_fields=['status'])
                messages.success(request, f'Статус изменён на «{valid[new_status]}».')

        elif action == 'set_ready_by':
            from datetime import date
            try:
                d = request.POST.get('ready_by', '')
                order.ready_by = date.fromisoformat(d) if d else None
                order.save(update_fields=['ready_by'])
                messages.success(request, 'Дата готовности обновлена.')
            except (ValueError, TypeError):
                messages.error(request, 'Некорректная дата.')

        elif action == 'update_items':
            for item in order.items.all():
                price_key = f'price_{item.pk}'
                qty_key = f'qty_{item.pk}'
                if price_key in request.POST:
                    try:
                        item.unit_price = Decimal(request.POST[price_key])
                    except Exception:
                        pass
                if qty_key in request.POST:
                    try:
                        item.quantity = max(1, int(request.POST[qty_key]))
                    except Exception:
                        pass
                item.save()
            messages.success(request, 'Позиции обновлены.')

        elif action == 'delete_item':
            item_id = request.POST.get('item_id')
            order.items.filter(pk=item_id).delete()
            if not order.items.exists():
                messages.warning(request, 'Заказ пуст — все позиции удалены.')
            else:
                messages.success(request, 'Позиция удалена.')

        return redirect('core:order_detail', pk=order.pk)

    next_statuses = []
    transitions = {
        Order.STATUS_ACCEPTED: [Order.STATUS_IN_PROGRESS],
        Order.STATUS_IN_PROGRESS: [Order.STATUS_READY],
        Order.STATUS_READY: [Order.STATUS_ISSUED],
    }
    for s in transitions.get(order.status, []):
        next_statuses.append({'value': s, 'label': dict(Order.STATUS_CHOICES)[s]})

    return render(request, 'core/order_detail.html', {
        'order': order,
        'next_statuses': next_statuses,
    })


@login_required
def web_orders(request):
    """Заявки с сайта (source=web)."""
    orders = (
        Order.objects.filter(source=Order.SOURCE_WEB)
        .select_related('client')
        .prefetch_related('items__service')
        .order_by('-created_at')[:100]
    )
    new_count = Order.objects.filter(source=Order.SOURCE_WEB, status=Order.STATUS_ACCEPTED).count()
    status_display = dict(Order.STATUS_CHOICES)
    pickup_display = dict(Order.PICKUP_CHOICES)
    return render(request, 'core/web_orders.html', {
        'orders': orders,
        'new_count': new_count,
        'status_display': status_display,
        'pickup_display': pickup_display,
    })


@login_required
@require_GET
def api_web_orders_count(request):
    """Кол-во новых заявок с сайта (статус 'accepted') для бейджа."""
    count = Order.objects.filter(source=Order.SOURCE_WEB, status=Order.STATUS_ACCEPTED).count()
    return JsonResponse({'count': count})


@login_required
def finance(request):
    """Страница финансов для сотрудников: выручка за месяц, налог 13%, прогноз."""
    if not request.user.is_staff:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('Доступ только для сотрудников.')
    context = _get_finance_context(request)
    return render(request, 'core/finance.html', context)


def _get_finance_context(request):
    """Общая логика расчёта финансов — используется и в панели сотрудника, и в админке."""
    from calendar import monthrange
    from datetime import date

    today = timezone.localdate()
    year = request.GET.get('year')
    month = request.GET.get('month')
    period = request.GET.get('period', '').strip()
    if period:
        try:
            y, m = period.split('-')
            year, month = int(y), int(m)
            if month < 1 or month > 12:
                year, month = today.year, today.month
        except (ValueError, TypeError):
            year, month = today.year, today.month
    else:
        try:
            year = int(year) if year else today.year
            month = int(month) if month else today.month
            if month < 1 or month > 12:
                year, month = today.year, today.month
        except (TypeError, ValueError):
            year, month = today.year, today.month

    start = date(year, month, 1)
    _, last_day = monthrange(year, month)
    end = date(year, month, last_day)

    period_months = request.GET.get('period_months', '1').strip()
    try:
        period_months = int(period_months)
        if period_months < 1:
            period_months = 1
        elif period_months > 12:
            period_months = 12
    except (ValueError, TypeError):
        period_months = 1

    # Конец периода: start + (period_months - 1) месяцев
    end_month = month + period_months - 1
    end_year = year + (end_month - 1) // 12
    end_month = ((end_month - 1) % 12) + 1
    _, last_day_end = monthrange(end_year, end_month)
    end = date(end_year, end_month, last_day_end)

    orders_issued_in_month = list(Order.objects.filter(
        status=Order.STATUS_ISSUED,
        created_at__date__gte=start,
        created_at__date__lte=end,
    ).prefetch_related('items__service'))

    month_revenue = sum(o.get_total() for o in orders_issued_in_month)
    tax_rate = Decimal('0.13')
    month_tax = (month_revenue * tax_rate).quantize(Decimal('0.01'))
    month_net = (month_revenue - month_tax).quantize(Decimal('0.01'))
    orders_count_issued = len(orders_issued_in_month)

    # Ожидаемая выручка по незавершённым заказам (в работе)
    orders_in_work = list(Order.objects.filter(
        status__in=[Order.STATUS_ACCEPTED, Order.STATUS_IN_PROGRESS, Order.STATUS_READY],
    ).prefetch_related('items__service'))
    forecast_revenue = sum(o.get_total() for o in orders_in_work)
    forecast_tax = (forecast_revenue * tax_rate).quantize(Decimal('0.01'))
    orders_count_forecast = len(orders_in_work)

    months_choices = []
    d = today.replace(day=1)
    for _ in range(12):
        months_choices.append({
            'year': d.year,
            'month': d.month,
            'label': d.strftime('%m.%Y'),
        })
        if d.month == 1:
            d = d.replace(year=d.year - 1, month=12)
        else:
            d = d.replace(month=d.month - 1)

    month_names = [
        (1, 'Январь'), (2, 'Февраль'), (3, 'Март'), (4, 'Апрель'),
        (5, 'Май'), (6, 'Июнь'), (7, 'Июль'), (8, 'Август'),
        (9, 'Сентябрь'), (10, 'Октябрь'), (11, 'Ноябрь'), (12, 'Декабрь'),
    ]
    years_choices = list(range(today.year, today.year - 5, -1))  # текущий и 4 прошлых года

    period_choices = [
        (1, '1 месяц'),
        (2, '2 месяца'),
        (3, '3 месяца'),
        (6, '6 месяцев'),
        (12, '12 месяцев (год)'),
    ]

    month_label = date(year, month, 1).strftime('%m.%Y')
    period_end_label = date(end_year, end_month, 1).strftime('%m.%Y')
    if period_months == 1:
        period_label = month_label
    else:
        period_label = f'{month_label} – {period_end_label}'

    return {
        'year': year,
        'month': month,
        'month_label': month_label,
        'period_months': period_months,
        'period_label': period_label,
        'months_choices': months_choices,
        'month_choices': month_names,
        'years_choices': years_choices,
        'period_choices': period_choices,
        'month_revenue': month_revenue,
        'month_tax': month_tax,
        'month_net': month_net,
        'orders_count_issued': orders_count_issued,
        'tax_percent': 13,
        'forecast_revenue': forecast_revenue,
        'forecast_tax': forecast_tax,
        'orders_count_forecast': orders_count_forecast,
    }


def finance_admin(request):
    """Финансы в админке — те же данные, шаблон в стиле Django Admin."""
    if not request.user.is_staff:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('Доступ только для сотрудников.')
    context = _get_finance_context(request)
    context['title'] = 'Финансы и налоги'
    context['site_title'] = 'Чисто.Тут'
    context['site_header'] = 'Администрирование Чисто.Тут'
    return render(request, 'admin/finance.html', context)


@login_required
def staff_chat_list(request):
    """Список активных чатов для сотрудника."""
    rooms = ChatRoom.objects.select_related('user').order_by('-created_at')
    rooms_data = []
    for room in rooms:
        last_msg = room.messages.order_by('-created_at').first()
        rooms_data.append({
            'room': room,
            'last_msg': last_msg,
            'unread': room.unread_for_staff(),
        })
    return render(request, 'core/chat_list.html', {'rooms': rooms_data})


@login_required
def staff_chat(request, room_id):
    import json
    from django.http import JsonResponse
    from django.shortcuts import render, get_object_or_404

    room = get_object_or_404(ChatRoom.objects.select_related('user'), pk=room_id)

    if request.method == 'POST':
        data = json.loads(request.body)
        text = (data.get('text') or '').strip()
        if not text:
            return JsonResponse({'error': 'Пустое сообщение'}, status=400)
        
        msg = ChatMessage.objects.create(
            room=room,
            author=request.user,
            is_staff_message=True,
            text=text,
        )
        return JsonResponse({
            'id': msg.id, 
            'text': msg.text,
            'is_staff': True, 
            'time': msg.created_at.isoformat() 
        })

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        after_id = int(request.GET.get('after', 0))
        msgs = room.messages.filter(pk__gt=after_id).values(
            'id', 'text', 'is_staff_message', 'created_at',
        )
        room.messages.filter(is_staff_message=False, is_read=False).update(is_read=True)
        return JsonResponse({
            'messages': [
                {
                    'id': m['id'], 
                    'text': m['text'],
                    'is_staff': m['is_staff_message'],
                    'time': m['created_at'].isoformat(), 
                }
                for m in msgs
            ]
        })

    messages_qs = list(room.messages.order_by('-created_at')[:100])[::-1]
    room.messages.filter(is_staff_message=False, is_read=False).update(is_read=True)
    
    return render(request, 'core/chat_room.html', {
        'room': room,
        'chat_messages': messages_qs,
    })
