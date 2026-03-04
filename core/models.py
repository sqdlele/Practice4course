from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User


class Client(models.Model):
    """Клиент химчистки."""
    name = models.CharField('ФИО', max_length=200)
    phone = models.CharField('Телефон', max_length=20, db_index=True)

    class Meta:
        verbose_name = 'клиент'
        verbose_name_plural = 'клиенты'

    def __str__(self):
        return f"{self.name} ({self.phone})"

    def completed_orders_count(self):
        """Количество выданных заказов (для скидки 3%)."""
        return self.orders.filter(status=Order.STATUS_ISSUED).count()


class Service(models.Model):
    """Услуга из прайс-листа."""
    name = models.CharField('Название', max_length=200)
    price = models.DecimalField('Цена', max_digits=10, decimal_places=2, default=0)

    class Meta:
        verbose_name = 'услуга'
        verbose_name_plural = 'услуги'

    def __str__(self):
        return f"{self.name} — {self.price} ₽"


class Order(models.Model):
    """Заказ. Статусы по ТЗ: Принято → В чистке → Готово → Выдано."""
    STATUS_ACCEPTED = 'accepted'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_READY = 'ready'
    STATUS_ISSUED = 'issued'

    STATUS_CHOICES = [
        (STATUS_ACCEPTED, 'Принято'),
        (STATUS_IN_PROGRESS, 'В чистке'),
        (STATUS_READY, 'Готово'),
        (STATUS_ISSUED, 'Выдано'),
    ]

    COMPLEXITY_CHOICES = [
        (Decimal('1.0'), '1'),
        (Decimal('1.3'), '1.3'),
        (Decimal('1.5'), '1.5'),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='orders', verbose_name='Клиент')
    status = models.CharField('Статус', max_length=20, choices=STATUS_CHOICES, default=STATUS_ACCEPTED, db_index=True)
    ready_by = models.DateField('Готовность к', null=True, blank=True)
    created_at = models.DateTimeField('Создан', auto_now_add=True)
    complexity = models.DecimalField(
        'Множитель сложности',
        max_digits=3,
        decimal_places=1,
        choices=COMPLEXITY_CHOICES,
        default=Decimal('1.0'),
    )
    discount_percent = models.DecimalField(
        'Скидка %',
        max_digits=5,
        decimal_places=2,
        default=0,
    )

    class Meta:
        verbose_name = 'заказ'
        verbose_name_plural = 'заказы'
        ordering = ['ready_by', 'created_at']

    def __str__(self):
        return f"Заказ #{self.pk} — {self.client.name}"

    def get_total(self):
        """Итог с учётом сложности и скидки."""
        total = sum(
            (item.unit_price * item.quantity * self.complexity)
            for item in self.items.all()
        )
        if self.discount_percent:
            total *= (Decimal('100') - self.discount_percent) / Decimal('100')
        return total.quantize(Decimal('0.01'))


class OrderItem(models.Model):
    """Позиция заказа (услуга + цена на момент заказа)."""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    service = models.ForeignKey(Service, on_delete=models.PROTECT, verbose_name='Услуга')
    unit_price = models.DecimalField('Цена за ед.', max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField('Кол-во', default=1)

    class Meta:
        verbose_name = 'позиция заказа'
        verbose_name_plural = 'позиции заказа'

    def __str__(self):
        return f"{self.service.name} × {self.quantity}"
