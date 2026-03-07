from decimal import Decimal
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import RegexValidator
from django.conf import settings


phone_validator = RegexValidator(
    regex=r'^[78]\d{10}$',
    message='Телефон в формате 89991234567 или 79991234567 (11 цифр).',
)


class UserManager(BaseUserManager):
    def create_user(self, phone, password=None, **extra):
        if not phone:
            raise ValueError('Телефон обязателен')
        user = self.model(phone=phone, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra):
        extra.setdefault('is_staff', True)
        extra.setdefault('is_superuser', True)
        extra.setdefault('is_active', True)
        return self.create_user(phone, password, **extra)


class User(AbstractUser):
    """Пользователь с телефоном вместо логина и отчеством."""
    username = None
    phone = models.CharField(
        'Телефон',
        max_length=11,
        unique=True,
        validators=[phone_validator],
        help_text='Формат: 89991234567 или 79991234567',
    )
    patronymic = models.CharField('Отчество', max_length=150)

    objects = UserManager()

    USERNAME_FIELD = 'phone'
    REQUIRED_FIELDS = ['first_name']

    class Meta:
        verbose_name = 'пользователь'
        verbose_name_plural = 'пользователи'

    def __str__(self):
        return self.get_full_name() or self.phone

    def get_full_name(self):
        parts = [self.last_name, self.first_name, self.patronymic]
        return ' '.join(p for p in parts if p)


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


class ServiceCategory(models.Model):
    """Категория услуг: Одежда, Дом и т.п."""
    name = models.CharField('Название', max_length=100)
    slug = models.SlugField('Slug', unique=True)
    image = models.ImageField('Изображение', upload_to='categories/', blank=True, null=True)
    description = models.TextField('Описание', blank=True, default='')
    order = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        verbose_name = 'категория услуг'
        verbose_name_plural = 'категории услуг'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class Service(models.Model):
    
    """Услуга из прайс-листа."""
    UNIT_PIECE = 'piece'
    UNIT_KG = 'kg'
    UNIT_M2 = 'm2'

    UNIT_CHOICES = [
        (UNIT_PIECE, 'За штуку'),
        (UNIT_KG, 'За кг'),
        (UNIT_M2, 'За м²'),
    ]

    category = models.ForeignKey(
        ServiceCategory, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='services', verbose_name='Категория',
    )
    svg_code = models.TextField(
        'Код SVG иконки', 
        blank=True, 
        null=True, 
        help_text='Если нет фото, вставьте сюда <svg>...</svg>. Если оба поля пусты, иконки не будет.'
    )
    parent = models.ForeignKey(
        'self', on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='children', verbose_name='Родительская услуга',
        help_text='Если задана — это вариант/подуслуга',
    )
    name = models.CharField('Название', max_length=200)
    price = models.DecimalField('Цена', max_digits=10, decimal_places=2, default=0)
    image = models.ImageField('Изображение', upload_to='services/', blank=True, null=True)
    cleaning_time = models.CharField('Срок чистки', max_length=50, default='3 дня', help_text='Например: 3 дня, 7-10 дней, от 5 дней')
    price_unit = models.CharField('Единица расчёта', max_length=10, choices=UNIT_CHOICES, default=UNIT_PIECE)
    has_dimensions = models.BooleanField('Нужны длина и ширина (м²)', default=False, help_text='Для штор, ковров и т.п.')
    has_weight = models.BooleanField('Нужен вес (кг)', default=False, help_text='Для постельного белья и т.п.')
    is_popular = models.BooleanField('Популярная (на главной)', default=False)

    class Meta:
        verbose_name = 'услуга'
        verbose_name_plural = 'услуги'

    def __str__(self):
        return f"{self.name} — {self.price} ₽"

    def price_label(self):
        if self.price_unit == self.UNIT_KG:
            return f"{self.price:,.0f} ₽/кг".replace(',', ' ')
        if self.price_unit == self.UNIT_M2:
            return f"{self.price:,.0f} ₽/м²".replace(',', ' ')
        return f"{self.price:,.0f} ₽".replace(',', ' ')


class HeroBanner(models.Model):
    """Баннер-слайдер на главной."""
    image = models.ImageField('Изображение', upload_to='banners/')
    title = models.CharField('Заголовок', max_length=200, blank=True, default='')
    subtitle = models.CharField('Подзаголовок', max_length=300, blank=True, default='')
    order = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        verbose_name = 'баннер'
        verbose_name_plural = 'баннеры'
        ordering = ['order']

    def __str__(self):
        return self.title or f"Баннер #{self.pk}"


class Review(models.Model):
    """Отзыв клиента для главной страницы."""
    author_name = models.CharField('Имя автора', max_length=150)
    text = models.TextField('Текст отзыва')
    rating = models.PositiveSmallIntegerField('Оценка', default=5)
    created_at = models.DateTimeField('Дата', auto_now_add=True)

    class Meta:
        verbose_name = 'отзыв'
        verbose_name_plural = 'отзывы'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.author_name} — {self.rating}★"


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

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='orders', verbose_name='Клиент')
    status = models.CharField('Статус', max_length=20, choices=STATUS_CHOICES, default=STATUS_ACCEPTED, db_index=True)
    ready_by = models.DateField('Готовность к', null=True, blank=True)
    created_at = models.DateTimeField('Создан', auto_now_add=True)
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
        """Итог с учётом сложности (per-item), объёма/веса и скидки."""
        total = sum(item.get_line_total() for item in self.items.all())
        if self.discount_percent:
            total *= (Decimal('100') - self.discount_percent) / Decimal('100')
        return total.quantize(Decimal('0.01'))


class OrderItem(models.Model):
    """Позиция заказа (услуга + цена на момент заказа)."""
    COMPLEXITY_CHOICES = [
        (Decimal('1.0'), '1'),
        (Decimal('1.3'), '1.3'),
        (Decimal('1.5'), '1.5'),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    service = models.ForeignKey(Service, on_delete=models.PROTECT, verbose_name='Услуга')
    unit_price = models.DecimalField('Цена за ед.', max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField('Кол-во', default=1)
    width = models.DecimalField('Ширина (м)', max_digits=6, decimal_places=2, default=0)
    length = models.DecimalField('Длина (м)', max_digits=6, decimal_places=2, default=0)
    weight = models.DecimalField('Вес (кг)', max_digits=6, decimal_places=2, default=0)
    complexity = models.DecimalField(
        'Сложность', max_digits=3, decimal_places=1,
        choices=COMPLEXITY_CHOICES, default=Decimal('1.0'),
    )

    class Meta:
        verbose_name = 'позиция заказа'
        verbose_name_plural = 'позиции заказа'

    def __str__(self):
        return f"{self.service.name} × {self.quantity}"

    def get_multiplier(self):
        """Множитель объёма: м² или кг."""
        if self.width and self.length:
            return self.width * self.length
        if self.weight:
            return self.weight
        return Decimal('1')

    def get_line_total(self):
        return (self.unit_price * self.quantity * self.get_multiplier() * self.complexity).quantize(Decimal('0.01'))
