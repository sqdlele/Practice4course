import json
import os
import re
from decimal import Decimal
from io import BytesIO
from django.db import models
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.decorators import login_required
from django.views.generic import CreateView
from django.urls import reverse, reverse_lazy
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_GET, require_POST
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from .models import ChatRoom, ChatMessage
from .forms import CustomerRegisterForm, CustomerProfileForm, OrderReviewForm
from core.models import Service, ServiceCategory, HeroBanner, Review, Client, Order, OrderItem, AboutPage, AboutFeature, AboutStep, DeliveryOption


_FONT_REGISTERED = False
_FONT_NAME = 'Helvetica'
_FONT_BOLD = 'Helvetica-Bold'


def _ensure_cyrillic_font():
    global _FONT_REGISTERED, _FONT_NAME, _FONT_BOLD
    if _FONT_REGISTERED:
        return _FONT_NAME, _FONT_BOLD
    candidates = [
        ('c:/windows/fonts/arial.ttf', 'c:/windows/fonts/arialbd.ttf'),
        ('/Library/Fonts/Arial.ttf', '/Library/Fonts/Arial Bold.ttf'),
        ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
         '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
        ('/usr/share/fonts/truetype/freefont/FreeSans.ttf',
         '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf'),
    ]
    for regular, bold in candidates:
        if os.path.isfile(regular):
            try:
                pdfmetrics.registerFont(TTFont('CyrFont', regular))
                _FONT_NAME = 'CyrFont'
                if os.path.isfile(bold):
                    pdfmetrics.registerFont(TTFont('CyrFontBold', bold))
                    _FONT_BOLD = 'CyrFontBold'
                break
            except Exception:
                pass
    _FONT_REGISTERED = True
    return _FONT_NAME, _FONT_BOLD


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
        next_url = self.request.GET.get('next') or self.request.POST.get('next') or self.success_url
        return redirect(next_url)


def customer_home(request):
    # слайдер, популярные услуги, категории, карта, отзывы
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
    categories = ServiceCategory.objects.prefetch_related(
        'services__children'
    ).all()
    # Строим плоский список всех услуг для шаблона (parent=None — корневые)
    all_services = []
    for cat in categories:
        for svc in cat.services.filter(parent__isnull=True):
            if svc.children.exists():
                for child in svc.children.all():
                    all_services.append({
                        'id': child.pk,
                        'name': f'{svc.name} — {child.name}',
                        'short_name': child.name,
                        'parent_name': svc.name,
                        'price_label': child.price_label,
                        'cat_id': cat.pk,
                        'cat_name': cat.name,
                        'cat_slug': cat.slug,
                        'svc_pk': svc.pk,
                    })
            else:
                all_services.append({
                    'id': svc.pk,
                    'name': svc.name,
                    'short_name': svc.name,
                    'parent_name': '',
                    'price_label': svc.price_label,
                    'cat_id': cat.pk,
                    'cat_name': cat.name,
                    'cat_slug': cat.slug,
                    'svc_pk': svc.pk,
                })
    return render(request, 'customer/catalog.html', {
        'categories': categories,
        'all_services': all_services,
    })


def category_detail(request, slug):
    # Услуги конкретной категории 
    cat = get_object_or_404(ServiceCategory, slug=slug)
    services = cat.services.filter(parent__isnull=True)
    return render(request, 'customer/category.html', {
        'category': cat,
        'services': services,
    })


def service_detail(request, slug, pk):
    # Страница конкретной услуги с вариантами/ценами
    cat = get_object_or_404(ServiceCategory, slug=slug)
    service = get_object_or_404(Service, pk=pk, category=cat, parent__isnull=True)
    children = service.children.all()
    return render(request, 'customer/service_detail.html', {
        'category': cat,
        'service': service,
        'children': children,
    })


def cart_page(request):
    # Страница корзины (рендерит данные из localStorage).
    return render(request, 'customer/cart.html')


def _client_for_user(user):
    return Client.objects.filter(phone=user.phone).first()


def _order_for_user(user, pk):
    client = _client_for_user(user)
    if not client:
        return None
    return get_object_or_404(
        Order.objects.select_related('client', 'delivery_option').prefetch_related('items__service'),
        pk=pk,
        client=client,
    )


@login_required
def account(request):
    # профиль и список заказов
    user = request.user
    from django.contrib import messages
    client = Client.objects.filter(phone=user.phone).first()
    if not client and not user.is_staff:
        client, _ = Client.objects.get_or_create(
            phone=user.phone,
            defaults={'name': user.get_full_name() or user.phone},
        )
    orders = Order.objects.filter(client=client).select_related('client', 'delivery_option').prefetch_related('items__service').order_by('-created_at')[:50] if client else []
    order_ids_with_review = set(Review.objects.filter(order__client=client).values_list('order_id', flat=True)) if client else set()

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
        'order_ids_with_review': order_ids_with_review,
        'profile_form': form,
    })


@login_required
def account_edit(request):
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
    # JSON-список услуг для JS-корзины.
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
    # Список способов получения с рассчитанной стоимостью.
        
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
    # Создать заявку из корзины клиента. В теле: items, pickup_method.
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

    pickup = data.get('pickup_method', Order.PICKUP_SELF)
    if pickup not in (Order.PICKUP_COURIER, Order.PICKUP_SELF):
        pickup = Order.PICKUP_SELF

    courier_addr = ''
    if pickup == Order.PICKUP_COURIER:
        courier_addr = (data.get('courier_address') or '').strip()[:500]
        if not courier_addr:
            return JsonResponse({'error': 'Укажите адрес для курьера'}, status=400)

    order = Order.objects.create(
        client=client,
        discount_percent=discount,
        pickup_method=pickup,
        courier_address=courier_addr,
        pickup_cost=Decimal('400.00') if pickup == Order.PICKUP_COURIER else Decimal('0'),
        source=Order.SOURCE_WEB,
    )

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

    if not order.items.exists():
        order.delete()
        return JsonResponse({'error': 'Не удалось добавить позиции — проверьте корзину'}, status=400)

    return JsonResponse({
        'order_id': order.pk,
        'payment_url': reverse('customer:order_payment', kwargs={'pk': order.pk}),
        'complete_url': reverse('customer:order_complete', kwargs={'pk': order.pk}),
        'subtotal': str(order.get_subtotal()),
        'pickup_cost': str(order.pickup_cost),
        'prepayment_amount': str(order.get_prepayment_due()),
        'total': str(order.get_total()),
    })


@login_required
def order_payment(request, pk):
    # Страница выбора способа оплаты для только что оформленного заказа
    order = _order_for_user(request.user, pk)
    if order is None:
        return HttpResponse('Клиент не найден', status=404)
    if order.payment_method and request.method == 'GET':
        return redirect('customer:order_complete', pk=order.pk)

    if request.method == 'POST':
        payment_method = (request.POST.get('payment_method') or '').strip()
        valid_methods = {code for code, _ in Order.PAYMENT_CHOICES}
        if payment_method not in valid_methods:
            return render(request, 'customer/order_payment.html', {
                'order': order,
                'payment_choices': Order.PAYMENT_CHOICES,
                'error': 'Выберите способ оплаты.',
                'prepayment_amount': order.get_prepayment_due(),
                'remaining_amount': order.get_total() - order.get_prepayment_due(),
            })
        order.payment_method = payment_method
        order.prepayment_amount = order.get_prepayment_due()
        order.save(update_fields=['payment_method', 'prepayment_amount'])
        return redirect('customer:order_complete', pk=order.pk)

    return render(request, 'customer/order_payment.html', {
        'order': order,
        'payment_choices': Order.PAYMENT_CHOICES,
        'prepayment_amount': order.get_prepayment_due(),
        'remaining_amount': order.get_total() - order.get_prepayment_due(),
    })


@login_required
def order_complete(request, pk):
    # Финальная страница после выбора способа оплаты
    order = _order_for_user(request.user, pk)
    if order is None:
        return HttpResponse('Клиент не найден', status=404)
    if not order.payment_method:
        return redirect('customer:order_payment', pk=order.pk)
    return render(request, 'customer/order_complete.html', {
        'order': order,
        'prepayment_amount': order.prepayment_amount or order.get_prepayment_due(),
        'remaining_amount': order.get_remaining_due(),
    })


@login_required
def order_review(request, pk):
    # oставить отзыв по выданному заказу """
    from django.contrib import messages
    order = _order_for_user(request.user, pk)
    if order is None:
        return HttpResponse('Клиент не найден', status=404)
    if order.status != Order.STATUS_ISSUED:
        messages.warning(request, 'Отзыв можно оставить только по заказу со статусом «Выдано».')
        return redirect('customer:account')
    if Review.objects.filter(order=order).exists():
        messages.info(request, 'Вы уже оставили отзыв по этому заказу.')
        return redirect('customer:account')

    form = OrderReviewForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        author_name = request.user.get_full_name() or request.user.phone or 'Клиент'
        Review.objects.create(
            order=order,
            author_name=author_name.strip() or 'Клиент',
            text=form.cleaned_data['text'].strip(),
            rating=form.cleaned_data['rating'],
        )
        messages.success(request, 'Спасибо! Ваш отзыв опубликован.')
        return redirect('customer:account')

    return render(request, 'customer/order_review.html', {
        'order': order,
        'form': form,
    })


@require_POST
@login_required
def api_request_return_delivery(request, pk):
    # Запросить доставку готового заказа 
    client = _client_for_user(request.user)
    if not client:
        return JsonResponse({'error': 'Клиент не найден'}, status=404)
    order = get_object_or_404(Order, pk=pk, client=client)
    if order.status != Order.STATUS_READY:
        return JsonResponse({'error': 'Заказ ещё не готов'}, status=400)
    if order.return_delivery_requested:
        return JsonResponse({'error': 'Доставка уже запрошена'}, status=400)

    delivery_opt = DeliveryOption.objects.filter(slug='delivery').first()
    if not delivery_opt:
        return JsonResponse({'error': 'Доставка недоступна'}, status=400)

    subtotal = order.get_subtotal()
    total_kg = sum(
        (oi.weight or Decimal('0')) * oi.quantity for oi in order.items.all()
    )
    order.delivery_option = delivery_opt
    order.delivery_cost = delivery_opt.compute_cost(subtotal, total_kg)
    order.return_delivery_requested = True
    order.save(update_fields=['delivery_option', 'delivery_cost', 'return_delivery_requested'])

    return JsonResponse({
        'ok': True,
        'delivery_cost': str(order.delivery_cost),
        'total': str(order.get_total()),
    })


@login_required
def order_receipt_pdf(request, pk):
    # Генерация pdf
    client = _client_for_user(request.user)
    if not client:
        return HttpResponse('Клиент не найден', status=404)
    order = get_object_or_404(Order, pk=pk, client=client)

    font, font_bold = _ensure_cyrillic_font()
    buf = BytesIO()
    w, h = A4
    c = canvas.Canvas(buf, pagesize=A4)

    margin = 25 * mm
    y = h - margin

    def text(x, yy, txt, size=10, bold=False):
        c.setFont(font_bold if bold else font, size)
        c.drawString(x, yy, str(txt))

    def text_right(x, yy, txt, size=10, bold=False):
        c.setFont(font_bold if bold else font, size)
        c.drawRightString(x, yy, str(txt))

    right_edge = w - margin

    
    text(margin, y, 'КВИТАНЦИЯ ХИМЧИСТКИ', 16, bold=True)
    y -= 8 * mm
    text(margin, y, '«Чисто.Тут» — профессиональная химчистка', 10)
    text_right(right_edge, y, f'Квитанция № {order.pk}', 10, bold=True)
    y -= 5 * mm
    text(margin, y, 'г. Ижевск  |  тел. 8 (800) 123-45-67', 9)
    y -= 4 * mm

    c.setStrokeColor(colors.HexColor('#0d9488'))
    c.setLineWidth(1.5)
    c.line(margin, y, right_edge, y)
    y -= 7 * mm

    # Информация о заказе
    text(margin, y, 'Дата оформления:', 9)
    from django.utils.timezone import localtime
    text(margin + 40 * mm, y, localtime(order.created_at).strftime('%d.%m.%Y %H:%M'), 9, bold=True)
    if order.ready_by:
        text(right_edge - 70 * mm, y, 'Дата готовности:', 9)
        text(right_edge - 35 * mm, y, order.ready_by.strftime('%d.%m.%Y'), 9, bold=True)
    y -= 5 * mm

    text(margin, y, 'Клиент:', 9)
    text(margin + 35 * mm, y, order.client.name, 9, bold=True)
    y -= 5 * mm
    text(margin, y, 'Телефон:', 9)
    text(margin + 35 * mm, y, order.client.phone, 9, bold=True)
    y -= 5 * mm
    text(margin, y, 'Сдача вещей:', 9)
    text(margin + 35 * mm, y, order.get_pickup_method_display(), 9, bold=True)
    y -= 5 * mm
    if order.courier_address:
        text(margin, y, 'Адрес курьера:', 9)
        text(margin + 35 * mm, y, order.courier_address[:70], 9, bold=True)
        y -= 5 * mm
    if order.payment_method:
        text(margin, y, 'Оплата:', 9)
        text(margin + 35 * mm, y, order.get_payment_method_display(), 9, bold=True)
        y -= 5 * mm
    text(margin, y, 'Статус:', 9)
    text(margin + 35 * mm, y, order.get_status_display(), 9, bold=True)
    y -= 7 * mm

    c.setStrokeColor(colors.HexColor('#e2e8f0'))
    c.setLineWidth(0.5)
    c.line(margin, y, right_edge, y)
    y -= 6 * mm

    # Заголовок таблицы
    col_x = [margin, margin + 8*mm, margin + 75*mm, margin + 95*mm,
             margin + 115*mm, margin + 135*mm]
    text(col_x[0], y, '№', 8, bold=True)
    text(col_x[1], y, 'Наименование', 8, bold=True)
    text(col_x[2], y, 'Кол-во', 8, bold=True)
    text(col_x[3], y, 'Параметры', 8, bold=True)
    text(col_x[4], y, 'Цена', 8, bold=True)
    text_right(right_edge, y, 'Сумма', 8, bold=True)
    y -= 3 * mm
    c.line(margin, y, right_edge, y)
    y -= 5 * mm

    items = order.items.select_related('service').all()
    for idx, item in enumerate(items, 1):
        if y < margin + 30 * mm:
            c.showPage()
            y = h - margin

        text(col_x[0], y, str(idx), 8)
        name = item.service.name
        if len(name) > 38:
            name = name[:36] + '...'
        text(col_x[1], y, name, 8)
        text(col_x[2], y, str(item.quantity), 8)

        params = ''
        if item.width and item.length:
            params = f'{item.width}×{item.length} м'
        elif item.weight:
            params = f'{item.weight} кг'
        if item.complexity != Decimal('1.0'):
            params += f'  сл.{item.complexity}'
        text(col_x[3], y, params, 8)

        text(col_x[4], y, f'{item.unit_price} ₽', 8)
        line_total = item.get_line_total(order.discount_percent)
        text_right(right_edge, y, f'{line_total} ₽', 8)
        y -= 4.5 * mm

    y -= 2 * mm
    c.line(margin, y, right_edge, y)
    y -= 6 * mm

    # Итоги
    subtotal = order.get_subtotal()
    if order.discount_percent > 0:
        raw = sum(i.get_line_total(Decimal('0')) for i in items)
        text(right_edge - 80 * mm, y, 'Сумма без скидки:', 9)
        text_right(right_edge, y, f'{Decimal(raw).quantize(Decimal("0.01"))} ₽', 9)
        y -= 5 * mm
        text(right_edge - 80 * mm, y, f'Скидка ({order.discount_percent}%):', 9, bold=True)
        discount_val = Decimal(raw).quantize(Decimal("0.01")) - subtotal
        text_right(right_edge, y, f'−{discount_val} ₽', 9, bold=True)
        y -= 5 * mm

    text(right_edge - 80 * mm, y, 'Подытог:', 9)
    text_right(right_edge, y, f'{subtotal} ₽', 9)
    y -= 5 * mm

    if order.pickup_cost and order.pickup_cost > 0:
        text(right_edge - 80 * mm, y, 'Прием вещей курьером:', 9)
        text_right(right_edge, y, f'{order.pickup_cost} ₽', 9)
        y -= 5 * mm

    if order.delivery_cost and order.delivery_cost > 0:
        text(right_edge - 80 * mm, y, 'Доставка:', 9)
        text_right(right_edge, y, f'{order.delivery_cost} ₽', 9)
        y -= 5 * mm

    total = order.get_total()
    y -= 2 * mm
    c.setStrokeColor(colors.HexColor('#0d9488'))
    c.setLineWidth(1)
    c.line(right_edge - 80 * mm, y, right_edge, y)
    y -= 6 * mm
    text(right_edge - 80 * mm, y, 'ИТОГО:', 12, bold=True)
    text_right(right_edge, y, f'{total} ₽', 12, bold=True)
    y -= 10 * mm

    prepayment = order.prepayment_amount or order.get_prepayment_due()
    remaining = order.get_remaining_due()
    text(right_edge - 80 * mm, y, 'Первый взнос:', 9)
    text_right(right_edge, y, f'{prepayment} ₽', 9)
    y -= 5 * mm
    text(right_edge - 80 * mm, y, 'Остаток при получении:', 9)
    text_right(right_edge, y, f'{remaining} ₽', 9)
    y -= 10 * mm

    # Footer notes
    c.setStrokeColor(colors.HexColor('#e2e8f0'))
    c.setLineWidth(0.5)
    c.line(margin, y, right_edge, y)
    y -= 6 * mm
    notes = [
        'Условия приёма:',
        '* Претензии по качеству принимаются в течение 24 часов после выдачи.',
        '* Проверяйте вещи перед выдачей. Компания не несёт ответственности за содержимое карманов.',
        '* Срок хранения готового заказа — 30 дней.',
        '* Окончательная стоимость может быть скорректирована при приёмке вещей.',
    ]
    for line in notes:
        bold = line.endswith(':')
        text(margin, y, line, 7.5, bold=bold)
        y -= 4 * mm

    c.save()
    buf.seek(0)
    resp = HttpResponse(buf.read(), content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="receipt_{order.pk}.pdf"'
    return resp


# Чат

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
    if after_id == 0 and not msgs:
        from django.utils import timezone
        welcome = {
            'id': 0,
            'text': 'Здравствуйте! По всем вопросам вы можете написать в этот чат — мы ответим в ближайшее рабочее время.',
            'is_staff': True,
            'time': timezone.now().strftime('%H:%M'),
        }
        return JsonResponse({'messages': [welcome]})

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
