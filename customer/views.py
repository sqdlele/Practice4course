import json
from django.db import models
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.decorators import login_required
from django.views.generic import CreateView
from django.urls import reverse_lazy
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from .models import ChatRoom, ChatMessage
from .forms import CustomerRegisterForm, CustomerProfileForm
from core.models import Service, ServiceCategory, HeroBanner, Review, Client, Order, OrderItem


class CustomerLoginView(LoginView):
    template_name = 'customer/login.html'
    redirect_authenticated_user = True


class CustomerLogoutView(LogoutView):
    next_page = '/'


class CustomerRegisterView(CreateView):
    form_class = CustomerRegisterForm
    template_name = 'customer/register.html'
    success_url = reverse_lazy('customer:home')

    def form_valid(self, form):
        user = form.save(commit=False)
        user.is_staff = False
        user.save()
        login(self.request, user)
        return redirect(self.success_url)


def customer_home(request):
    """Главная: слайдер, популярные услуги, категории, карта, отзывы."""
    popular = Service.objects.filter(is_popular=True, parent__isnull=True)[:6]
    if not popular.exists():
        popular = Service.objects.filter(parent__isnull=True).order_by('?')[:6]
    categories = ServiceCategory.objects.prefetch_related(
        models.Prefetch('services', queryset=Service.objects.filter(parent__isnull=True))
    ).all()
    return render(request, 'customer/home.html', {
        'banners': HeroBanner.objects.all(),
        'services': popular,
        'categories': categories,
        'reviews': Review.objects.all()[:20],
    })


def about(request):
    """Страница «О нас»."""
    return render(request, 'customer/about.html', {
        'reviews': Review.objects.all()[:6],
    })


def catalog(request):
    """Каталог: список категорий с превью услуг."""
    categories = ServiceCategory.objects.prefetch_related('services').all()
    return render(request, 'customer/catalog.html', {
        'categories': categories,
    })


def category_detail(request, slug):
    """Услуги конкретной категории (только top-level)."""
    cat = get_object_or_404(ServiceCategory, slug=slug)
    services = cat.services.filter(parent__isnull=True)
    return render(request, 'customer/category.html', {
        'category': cat,
        'services': services,
    })


def service_detail(request, slug, pk):
    """Страница конкретной услуги с вариантами/ценами."""
    cat = get_object_or_404(ServiceCategory, slug=slug)
    service = get_object_or_404(Service, pk=pk, category=cat, parent__isnull=True)
    children = service.children.all()
    return render(request, 'customer/service_detail.html', {
        'category': cat,
        'service': service,
        'children': children,
    })


def cart_page(request):
    """Страница корзины (рендер; данные из localStorage)."""
    return render(request, 'customer/cart.html')


@login_required
def account(request):
    """Личный кабинет: профиль и список заказов."""
    user = request.user
    client = Client.objects.filter(phone=user.phone).first()
    if not client and not user.is_staff:
        client, _ = Client.objects.get_or_create(
            phone=user.phone,
            defaults={'name': user.get_full_name() or user.phone},
        )
    orders = Order.objects.filter(client=client).select_related('client').prefetch_related('items').order_by('-created_at')[:50] if client else []
    return render(request, 'customer/account.html', {
        'client': client,
        'orders': orders,
    })


@login_required
def account_edit(request):
    """Редактирование профиля."""
    if request.method == 'POST':
        form = CustomerProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            from django.contrib import messages
            messages.success(request, 'Профиль сохранён.')
            return redirect('customer:account')
    else:
        form = CustomerProfileForm(instance=request.user)
    return render(request, 'customer/account_edit.html', {'form': form})


@require_GET
def api_services(request):
    """JSON-список услуг для JS-корзины."""
    qs = Service.objects.select_related('category', 'parent').all()
    data = []
    for s in qs:
        data.append({
            'id': s.pk,
            'name': s.name,
            'price': str(s.price),
            'price_label': s.price_label(),
            'price_unit': s.price_unit,
            'cleaning_time': s.cleaning_time,
            'has_dimensions': s.has_dimensions,
            'has_weight': s.has_weight,
            'image': s.image.url if s.image else '',
            'category': s.category.name if s.category else '',
            'parent_id': s.parent_id,
        })
    return JsonResponse({'services': data})


@require_POST
@login_required
def api_create_order(request):
    """Создать заявку из корзины клиента."""
    from decimal import Decimal
    data = json.loads(request.body)
    items = data.get('items', [])
    if not items:
        return JsonResponse({'error': 'Корзина пуста'}, status=400)

    user = request.user
    client, _ = Client.objects.get_or_create(
        phone=user.phone,
        defaults={'name': user.get_full_name() or user.phone},
    )

    discount = Decimal('3') if client.completed_orders_count() >= 2 else Decimal('0')
    order = Order.objects.create(client=client, discount_percent=discount)

    for item in items:
        try:
            svc = Service.objects.get(pk=item['service_id'])
        except Service.DoesNotExist:
            continue
        OrderItem.objects.create(
            order=order,
            service=svc,
            unit_price=svc.price,
            quantity=max(1, int(item.get('qty', 1))),
            width=Decimal(str(item.get('width', 0))),
            length=Decimal(str(item.get('length', 0))),
            weight=Decimal(str(item.get('weight', 0))),
        )

    return JsonResponse({
        'order_id': order.pk,
        'total': str(order.get_total()),
    })


# --- Chat API ---

def _get_or_create_room(user):
    room, _ = ChatRoom.objects.get_or_create(user=user)
    return room


@login_required
@require_GET
def chat_messages(request):
    """Получить сообщения чата текущего пользователя (JSON)."""
    room = _get_or_create_room(request.user)
    after_id = int(request.GET.get('after', 0))
    msgs = room.messages.filter(pk__gt=after_id).values(
        'id', 'text', 'is_staff_message', 'created_at',
    )
    # Отметить прочитанными сообщения от поддержки
    room.messages.filter(is_staff_message=True, is_read=False).update(is_read=True)
    return JsonResponse({
        'messages': [
            {
                'id': m['id'],
                'text': m['text'],
                'is_staff': m['is_staff_message'],
                'time': m['created_at'].strftime('%H:%M'),
            }
            for m in msgs
        ]
    })


@login_required
@require_POST
def chat_send(request):
    """Отправить сообщение в чат от пользователя."""
    room = _get_or_create_room(request.user)
    data = json.loads(request.body)
    text = (data.get('text') or '').strip()
    if not text:
        return JsonResponse({'error': 'Пустое сообщение'}, status=400)
    msg = ChatMessage.objects.create(
        room=room,
        author=request.user,
        is_staff_message=False,
        text=text,
    )
    return JsonResponse({
        'id': msg.id,
        'text': msg.text,
        'is_staff': False,
        'time': msg.created_at.strftime('%H:%M'),
    })
