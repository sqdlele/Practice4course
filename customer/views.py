import json
import re
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
from core.models import Service, ServiceCategory, HeroBanner, Review, Client, Order, OrderItem, AboutPage, AboutFeature, AboutStep, DeliveryOption


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
    """Страница «О нас»: контент из БД и вычисляемые показатели."""
    about_page = AboutPage.get_single()
    features = list(AboutFeature.objects.all())
    steps = list(AboutStep.objects.all())

    orders_issued = Order.objects.filter(status=Order.STATUS_ISSUED).count()
    clients_count = Client.objects.filter(orders__status=Order.STATUS_ISSUED).distinct().count()
    total_reviews = Review.objects.count()
    positive_reviews = Review.objects.filter(rating__gte=4).count()
    positive_reviews_pct = round(positive_reviews / total_reviews * 100) if total_reviews else 0

    if not features:
        delivery_from = (about_page.free_delivery_from or 2000)
        features = [
            {'title': 'Быстрые руки', 'description': 'Все заказы готовы ровно в срок!!! '},
            {'title': 'Бережная обработка', 'description': 'Подбираем метод чистки индивидуально для каждого типа ткани'},
            {'title': 'Экологичность', 'description': 'Используем составы без ужасной химии — безопасно для здоровья, 100%.'},
            {'title': 'Доставка', 'description': f'Забираем и привозим вещи прямо к двери. Бесплатная доставка от {delivery_from:.0f} ₽.'},
            {'title': 'Прозрачные цены', 'description': 'Фиксированный прайс без обмана. Стоимость известна до начала работ.'},
            {'title': 'Программа лояльности', 'description': 'Клиентам обратившимся в сервис 3 раза скидка!'},
        ]
    if not steps:
        steps = [
            {'step_number': 1, 'title': 'Приём вещей', 'description': 'Привезите вещи к нам или оформите доставку. Мастер осмотрит и зафиксирует состояние.'},
            {'step_number': 2, 'title': 'Диагностика', 'description': 'Определяем тип ткани, выявляем пятна и подбираем оптимальный метод обработки.'},
            {'step_number': 3, 'title': 'Чистка', 'description': 'Профессиональная обработка на современном оборудовании с контролем на каждом этапе.'},
            {'step_number': 4, 'title': 'Выдача', 'description': 'Финальный контроль, упаковка и выдача. Если есть замечания — переделаем бесплатно.'},
        ]

    return render(request, 'customer/about.html', {
        'about': about_page,
        'about_features': features,
        'about_steps': steps,
        'reviews': Review.objects.all()[:6],
        'stats': {
            'years': about_page.years_experience,
            'orders': orders_issued,
            'clients': clients_count,
            'reviews_pct': positive_reviews_pct,
        },
        'cta_phone_href': re.sub(r'\D', '', about_page.cta_phone or '88001234567'),
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
    from django.contrib import messages
    client = Client.objects.filter(phone=user.phone).first()
    if not client and not user.is_staff:
        client, _ = Client.objects.get_or_create(
            phone=user.phone,
            defaults={'name': user.get_full_name() or user.phone},
        )
    orders = Order.objects.filter(client=client).select_related('client', 'delivery_option').prefetch_related('items').order_by('-created_at')[:50] if client else []

    if request.method == 'POST':
        form = CustomerProfileForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Профиль сохранён.')
            return redirect('customer:account')
    else:
        form = CustomerProfileForm(instance=user)

    return render(request, 'customer/account.html', {
        'client': client,
        'orders': orders,
        'profile_form': form,
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


@require_GET
def api_delivery_options(request):
    """
    Список способов получения с рассчитанной стоимостью.
    GET-параметры: cart_total (сумма корзины), cart_kg (общий вес в кг, опционально).
    """
    from decimal import Decimal
    try:
        cart_total = Decimal(request.GET.get('cart_total', '0'))
    except Exception:
        cart_total = Decimal('0')
    try:
        cart_kg = Decimal(request.GET.get('cart_kg', '0'))
    except Exception:
        cart_kg = Decimal('0')

    options = []
    for opt in DeliveryOption.objects.all():
        cost = opt.compute_cost(cart_total, cart_kg)
        options.append({
            'id': opt.pk,
            'slug': opt.slug,
            'name': opt.name,
            'cost': str(cost),
        })
    return JsonResponse({'delivery_options': options})


@require_POST
@login_required
def api_create_order(request):
    """Создать заявку из корзины клиента. В теле: items, delivery_option_slug (опционально)."""
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

    # Способ получения и стоимость доставки
    delivery_slug = (data.get('delivery_option_slug') or '').strip() or 'pickup'
    delivery_option = DeliveryOption.objects.filter(slug=delivery_slug).first()
    if delivery_option:
        order.delivery_option = delivery_option
        subtotal = order.get_subtotal()
        total_kg = sum(
            (oi.weight or Decimal('0')) * oi.quantity
            for oi in order.items.all()
        )
        order.delivery_cost = delivery_option.compute_cost(subtotal, total_kg)
        order.save(update_fields=['delivery_option', 'delivery_cost'])

    return JsonResponse({
        'order_id': order.pk,
        'total': str(order.get_total()),
        'delivery_cost': str(order.delivery_cost or 0),
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
    msgs = list(room.messages.filter(pk__gt=after_id).values(
        'id', 'text', 'is_staff_message', 'created_at',
    ))
    # При первом заходе (after=0) и пустой переписке — приветственное сообщение
    if after_id == 0 and not msgs:
        from django.utils import timezone
        welcome = {
            'id': 0,
            'text': 'Здравствуйте! По всем вопросам вы можете написать в этот чат — мы ответим в ближайшее рабочее время.',
            'is_staff': True,
            'time': timezone.now().strftime('%H:%M'),
        }
        return JsonResponse({'messages': [welcome]})
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
