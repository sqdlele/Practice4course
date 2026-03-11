"""
Callback для главной страницы админки Unfold: график заказов с фильтром по периоду.
"""
import json
from collections import defaultdict
from calendar import monthrange
from datetime import timedelta, datetime, time, date

from django.utils import timezone
from django.db.models import Count
from django.db.models.functions import TruncDay, TruncMonth
from django.contrib.auth import get_user_model

from core.models import Order

User = get_user_model()


PERIODS = [
    ('day', 'День', 24),      # последние 24 часа по часам
    ('week', 'Неделя', 7),    # последние 7 дней по дням
    ('month', 'Месяц', 30),   # последние 30 дней по дням
    ('year', 'Год', 12),      # последние 12 месяцев по месяцам
]


def dashboard_callback(request, context):
    period_key = request.GET.get('period', 'month')
    if period_key not in [p[0] for p in PERIODS]:
        period_key = 'month'

    now = timezone.now()
    chart_labels = []
    chart_counts = []

    if period_key == 'day':
        # Полные сутки сегодня: 00:00 — 23:00 (локальное время)
        local_now = timezone.localtime(now)
        today = local_now.date()
        day_start = timezone.make_aware(datetime.combine(today, time.min))
        day_end = day_start + timedelta(days=1)
        orders_today = Order.objects.filter(
            created_at__gte=day_start,
            created_at__lt=day_end,
        ).values_list('created_at', flat=True)
        by_hour = defaultdict(int)
        for dt in orders_today:
            h = timezone.localtime(dt).hour
            by_hour[h] += 1
        chart_labels = [f'{h:02d}:00' for h in range(24)]
        chart_counts = [by_hour[h] for h in range(24)]

    elif period_key == 'week':
        # Текущая календарная неделя: понедельник — воскресенье (локальное время)
        local_now = timezone.localtime(now)
        today = local_now.date()
        monday = today - timedelta(days=today.weekday())  # 0=пн, 6=вс
        week_start = timezone.make_aware(datetime.combine(monday, time.min))
        week_end = week_start + timedelta(days=7)
        qs = (
            Order.objects.filter(
                created_at__gte=week_start,
                created_at__lt=week_end,
            )
            .annotate(day=TruncDay('created_at'))
            .values('day')
            .annotate(count=Count('id'))
            .order_by('day')
        )
        by_key = {}
        for item in qs:
            if item['day']:
                d_local = timezone.localtime(item['day']).date()
                by_key[d_local] = item['count']
        chart_labels = []
        chart_counts = []
        for i in range(7):
            d = monday + timedelta(days=i)
            chart_labels.append(d.strftime('%d.%m'))
            chart_counts.append(by_key.get(d, 0))

    elif period_key == 'month':
        # Текущий календарный месяц: с 1-го по последний день (локальное время)
        local_now = timezone.localtime(now)
        year, month = local_now.year, local_now.month
        first_day = date(year, month, 1)
        last_day_num = monthrange(year, month)[1]
        day_start_dt = timezone.make_aware(datetime.combine(first_day, time.min))
        day_end_dt = timezone.make_aware(
            datetime.combine(date(year, month, last_day_num), time.min)
        ) + timedelta(days=1)
        qs = (
            Order.objects.filter(
                created_at__gte=day_start_dt,
                created_at__lt=day_end_dt,
            )
            .annotate(day=TruncDay('created_at'))
            .values('day')
            .annotate(count=Count('id'))
            .order_by('day')
        )
        by_key = {}
        for item in qs:
            if item['day']:
                d_local = timezone.localtime(item['day']).date()
                by_key[d_local] = item['count']
        chart_labels = []
        chart_counts = []
        for day_num in range(1, last_day_num + 1):
            d = date(year, month, day_num)
            chart_labels.append(d.strftime('%d.%m'))
            chart_counts.append(by_key.get(d, 0))

    else:  # year
        # Текущий календарный год: январь — декабрь (локальное время)
        local_now = timezone.localtime(now)
        year = local_now.year
        months_start = [date(year, m, 1) for m in range(1, 13)]
        year_start = timezone.make_aware(datetime(year, 1, 1))
        year_end = timezone.make_aware(datetime(year, 12, 31, 23, 59, 59, 999999)) + timedelta(seconds=1)
        qs = (
            Order.objects.filter(
                created_at__gte=year_start,
                created_at__lt=year_end,
            )
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(count=Count('id'))
            .order_by('month')
        )
        by_key = {}
        for item in qs:
            if item['month']:
                d_local = timezone.localtime(item['month']).date()
                key = d_local.replace(day=1)
                by_key[key] = item['count']
        chart_labels = []
        chart_counts = []
        for d in months_start:
            chart_labels.append(d.strftime('%m.%Y'))
            chart_counts.append(by_key.get(d, 0))

    chart_data = {
        'labels': chart_labels,
        'datasets': [
            {
                'label': 'Заказы',
                'data': chart_counts,
                'backgroundColor': 'var(--color-primary-500)',
                'borderColor': 'var(--color-primary-600)',
            }
        ],
    }

    admin_index = request.path
    period_filters = [
        {
            'link': f'{admin_index}?period={key}',
            'title': title,
            'active': period_key == key,
        }
        for key, title, _ in PERIODS
    ]

    context['orders_chart_data'] = json.dumps(chart_data, ensure_ascii=False)
    context['orders_period_filters'] = period_filters
    context['orders_period'] = period_key

    # Новые клиенты (пользователи), зарегистрированные сегодня
    local_now = timezone.localtime(now)
    today = local_now.date()
    day_start = timezone.make_aware(datetime.combine(today, time.min))
    day_end = day_start + timedelta(days=1)
    context['new_users_today'] = User.objects.filter(
        date_joined__gte=day_start,
        date_joined__lt=day_end,
    ).count()

    return context
