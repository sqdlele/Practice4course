"""Контекст для шаблонов клиентской части."""
from core.models import Client


def customer_discount(request):
    """Добавляет has_discount_3: скидка 3% активна (2+ выданных заказа)."""
    has_discount_3 = False
    if request.user.is_authenticated and not getattr(request.user, 'is_staff', False):
        client = Client.objects.filter(phone=request.user.phone).first()
        if client and client.completed_orders_count() >= 2:
            has_discount_3 = True
    return {'has_discount_3': has_discount_3}
