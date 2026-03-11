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
    """Отзыв клиента для главной страницы. Может быть привязан к заказу (после статуса «Выдано»)."""
    author_name = models.CharField('Имя автора', max_length=150)
    text = models.TextField('Текст отзыва')
    rating = models.PositiveSmallIntegerField('Оценка', default=5)
    created_at = models.DateTimeField('Дата', auto_now_add=True)
    order = models.OneToOneField(
        'Order',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='review',
        verbose_name='Заказ',
        help_text='Если отзыв оставлен из личного кабинета по выданному заказу.',
    )

    class Meta:
        verbose_name = 'отзыв'
        verbose_name_plural = 'отзывы'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.author_name} — {self.rating}★"


class AboutPage(models.Model):
    """Контент страницы «О нас» (одна запись)."""
    hero_badge = models.CharField('Бейдж в герое', max_length=100, default='С 2020 года', blank=True)
    hero_title = models.CharField('Заголовок героя', max_length=200, default='Мы — Чисто.Тут', blank=True)
    hero_subtitle = models.TextField(
        'Подзаголовок героя',
        default='Профессиональная химчистка в Ижевске. Возвращаем вещам первозданный вид с заботой и вниманием к каждой детали.',
        blank=True,
    )
    years_experience = models.PositiveIntegerField('Лет опыта (в цифрах)', default=5)
    story_title = models.CharField('Заголовок блока «История»', max_length=200, default='Наша история', blank=True)
    story_para1 = models.TextField(
        'История, абзац 1',
        default='«Чисто.Тут» начиналась как небольшая мастерская с одним сотрудником и мечтой — сделать химчистку доступной, честной и по-настоящему качественной. Сегодня мы обслуживаем тысячи клиентов по всему Ижевску.',
        blank=True,
    )
    story_para2 = models.TextField(
        'История, абзац 2',
        default='Мы используем только профессиональное оборудование ведущих европейских производителей и экологичные составы, которые бережно очищают ткань, сохраняя её цвет, текстуру и форму.',
        blank=True,
    )
    story_para3 = models.TextField(
        'История, абзац 3',
        default='Каждый заказ проходит тройной контроль качества — от приёмки до выдачи. Мы не отдаём вещь, пока не будем на 100% уверены в результате.',
        blank=True,
    )
    story_rating_text = models.CharField('Текст «Рейтинг» в карточке', max_length=100, default='Рейтинг 4.9', blank=True)
    story_guarantee_text = models.CharField('Текст «Гарантия» в карточке', max_length=200, default='Гарантия на все работы', blank=True)
    cta_title = models.CharField('Заголовок CTA', max_length=200, default='Доверьте нам свои вещи', blank=True)
    cta_text = models.CharField('Текст CTA', max_length=300, default='Первый заказ — со скидкой. Попробуйте качество, которое говорит само за себя.', blank=True)
    cta_phone = models.CharField('Телефон в CTA', max_length=50, default='8 (800) 123-45-67', blank=True)
    free_delivery_from = models.DecimalField(
        'Бесплатная доставка от (₽)',
        max_digits=10,
        decimal_places=0,
        default=2000,
        null=True,
        blank=True,
        help_text='Подставляется в текст преимуществ',
    )

    class Meta:
        verbose_name = 'страница «О нас»'
        verbose_name_plural = 'страница «О нас»'

    def __str__(self):
        return 'О нас'

    @classmethod
    def get_single(cls):
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create()
        return obj


class AboutFeature(models.Model):
    """Пункт блока «Почему выбирают нас»."""
    title = models.CharField('Заголовок', max_length=150)
    description = models.TextField('Описание', blank=True)
    order = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        verbose_name = 'преимущество (О нас)'
        verbose_name_plural = 'преимущества (О нас)'
        ordering = ['order', 'pk']

    def __str__(self):
        return self.title


class AboutStep(models.Model):
    """Шаг блока «Как мы работаем»."""
    step_number = models.PositiveIntegerField('Номер шага', default=1)
    title = models.CharField('Заголовок', max_length=150)
    description = models.TextField('Описание', blank=True)
    order = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        verbose_name = 'шаг процесса (О нас)'
        verbose_name_plural = 'шаги процесса (О нас)'
        ordering = ['order', 'pk']

    def __str__(self):
        return f'{self.step_number}. {self.title}'


class DeliveryOption(models.Model):
    """Способ получения заказа: самовывоз или доставка."""
    name = models.CharField('Название', max_length=100)
    slug = models.SlugField('Slug', max_length=20, unique=True, help_text='pickup или delivery')
    base_price = models.DecimalField(
        'Базовая стоимость (₽)',
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
        help_text='Для доставки — от 300 ₽',
    )
    free_if_order_total_above = models.DecimalField(
        'Бесплатно при заказе от (₽)',
        max_digits=10,
        decimal_places=0,
        null=True,
        blank=True,
        help_text='Если сумма заказа выше — доставка бесплатно. Пусто для самовывоза.',
    )
    free_kg = models.DecimalField(
        'Бесплатно вес до (кг)',
        max_digits=6,
        decimal_places=2,
        default=Decimal('5'),
        help_text='Доплата за вес считается после этого порога.',
    )
    extra_per_kg = models.DecimalField(
        'Доплата за каждый кг сверх порога (₽)',
        max_digits=6,
        decimal_places=2,
        default=Decimal('20'),
    )
    order = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        verbose_name = 'способ получения'
        verbose_name_plural = 'способы получения'
        ordering = ['order', 'pk']

    def __str__(self):
        return self.name

    def compute_cost(self, order_total, total_kg=None):
        """
        Стоимость доставки: базовая цена (или 0 при заказе от N ₽)
        + доплата за вес сверх free_kg по extra_per_kg за кг.
        """
        if self.slug == 'pickup':
            return Decimal('0')
        total_kg = total_kg or Decimal('0')
        if self.free_if_order_total_above and order_total >= self.free_if_order_total_above:
            base = Decimal('0')
        else:
            base = self.base_price
        over_kg = max(Decimal('0'), total_kg - self.free_kg)
        extra = (over_kg * self.extra_per_kg).quantize(Decimal('0.01'))
        return (base + extra).quantize(Decimal('0.01'))


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

    PICKUP_COURIER = 'courier_pickup'
    PICKUP_SELF = 'self_bring'
    PICKUP_CHOICES = [
        (PICKUP_COURIER, 'Курьером'),
        (PICKUP_SELF, 'Отнесу сам'),
    ]
    PAYMENT_CASH = 'cash'
    PAYMENT_CARD_ON_HAND = 'card_on_hand'
    PAYMENT_CHOICES = [
        (PAYMENT_CASH, 'Наличными курьеру или в пункте приёма'),
        (PAYMENT_CARD_ON_HAND, 'Банковской картой курьеру или в пункте приёма'),
    ]

    SOURCE_WEB = 'web'
    SOURCE_STAFF = 'staff'
    SOURCE_CHOICES = [
        (SOURCE_WEB, 'Сайт'),
        (SOURCE_STAFF, 'Сотрудник'),
    ]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='orders', verbose_name='Клиент')
    status = models.CharField('Статус', max_length=20, choices=STATUS_CHOICES, default=STATUS_ACCEPTED, db_index=True)
    source = models.CharField('Источник', max_length=10, choices=SOURCE_CHOICES, default=SOURCE_STAFF, db_index=True)
    ready_by = models.DateField('Готовность к', null=True, blank=True)
    created_at = models.DateTimeField('Создан', auto_now_add=True)
    discount_percent = models.DecimalField(
        'Скидка %',
        max_digits=5,
        decimal_places=2,
        default=0,
    )
    pickup_method = models.CharField(
        'Способ сдачи вещей',
        max_length=20,
        choices=PICKUP_CHOICES,
        default=PICKUP_SELF,
    )
    courier_address = models.CharField(
        'Адрес для курьера',
        max_length=500,
        blank=True,
        default='',
    )
    pickup_cost = models.DecimalField(
        'Стоимость Приема вещей курьером (₽)',
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
    )
    delivery_option = models.ForeignKey(
        'DeliveryOption',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='orders',
        verbose_name='Способ получения готового заказа',
    )
    delivery_cost = models.DecimalField(
        'Стоимость доставки (₽)',
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
    )
    return_delivery_requested = models.BooleanField(
        'Запрос доставки готового заказа',
        default=False,
    )
    payment_method = models.CharField(
        'Способ оплаты',
        max_length=30,
        choices=PAYMENT_CHOICES,
        blank=True,
        default='',
    )
    prepayment_amount = models.DecimalField(
        'Первый взнос (₽)',
        max_digits=10,
        decimal_places=2,
        default=Decimal('0'),
    )

    class Meta:
        verbose_name = 'заказ'
        verbose_name_plural = 'заказы'
        ordering = ['ready_by', 'created_at']

    def __str__(self):
        return f"Заказ #{self.pk} — {self.client.name}"

    def get_total(self):
        """Итог: сумма по позициям с учётом скидки + Прием вещей + доставка."""
        total = sum(item.get_line_total(self.discount_percent) for item in self.items.all())
        total = Decimal(total).quantize(Decimal('0.01'))
        pickup = self.pickup_cost or Decimal('0')
        delivery = self.delivery_cost or Decimal('0')
        return (total + pickup + delivery).quantize(Decimal('0.01'))

    def get_subtotal(self):
        """Сумма по позициям без Приема и доставки."""
        total = sum(item.get_line_total(self.discount_percent) for item in self.items.all())
        return Decimal(total).quantize(Decimal('0.01'))

    def get_prepayment_due(self):
        """Первый взнос: половина стоимости услуг без логистики."""
        return (self.get_subtotal() / Decimal('2')).quantize(Decimal('0.01'))

    def get_remaining_due(self):
        """Остаток к оплате после первого взноса."""
        prepaid = self.prepayment_amount or self.get_prepayment_due()
        return max(Decimal('0'), self.get_total() - prepaid).quantize(Decimal('0.01'))


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

    def get_line_total(self, discount_percent=None):
        """Сумма по позиции. Если передан discount_percent (скидка заказчика), применяется к этой вещи."""
        total = (self.unit_price * self.quantity * self.get_multiplier() * self.complexity).quantize(Decimal('0.01'))
        if discount_percent is not None and discount_percent > 0:
            total = (total * (Decimal('100') - discount_percent) / Decimal('100')).quantize(Decimal('0.01'))
        return total

    @property
    def line_total(self):
        """Сумма с учётом скидки заказа (для шаблонов, где нельзя передать аргумент)."""
        return self.get_line_total(self.order.discount_percent)
