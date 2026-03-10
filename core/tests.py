from decimal import Decimal
from django.test import TestCase, Client as TestClient
from django.urls import reverse
from django.contrib.auth import get_user_model

from core.models import Client, Service, ServiceCategory, Order, OrderItem
from customer.models import ChatRoom, ChatMessage

User = get_user_model()


def make_user(phone='89991234567', is_staff=True, is_active=True, **kwargs):
    return User.objects.create_user(
        phone=phone,
        password='testpass123',
        first_name=kwargs.get('first_name', 'Test'),
        last_name=kwargs.get('last_name', 'User'),
        patronymic=kwargs.get('patronymic', 'Pat'),
        is_staff=is_staff,
        is_active=is_active,
        **{k: v for k, v in kwargs.items() if k not in ('first_name', 'last_name', 'patronymic')}
    )


class ClientModelTest(TestCase):
    """Проверка метода completed_orders_count у клиента."""

    def test_completed_orders_count_zero(self):
        client = Client.objects.create(name='Иван Иванов', phone='89991111111')
        self.assertEqual(client.completed_orders_count(), 0)

    def test_completed_orders_count_two_issued(self):
        client = Client.objects.create(name='Петр Петров', phone='89992222222')
        Order.objects.create(client=client, status=Order.STATUS_ISSUED)
        Order.objects.create(client=client, status=Order.STATUS_ISSUED)
        Order.objects.create(client=client, status=Order.STATUS_ACCEPTED)
        self.assertEqual(client.completed_orders_count(), 2)


class OrderItemTotalTest(TestCase):
    """Проверка расчёта суммы по позиции заказа."""

    def setUp(self):
        self.cat = ServiceCategory.objects.create(name='Тест', slug='test')
        self.service = Service.objects.create(
            name='Рубашка',
            price=Decimal('500'),
            category=self.cat,
        )
        self.client_obj = Client.objects.create(name='Клиент', phone='89993333333')

    def test_line_total_simple(self):
        order = Order.objects.create(client=self.client_obj)
        item = OrderItem.objects.create(
            order=order,
            service=self.service,
            unit_price=Decimal('500'),
            quantity=2,
            complexity=Decimal('1.0'),
        )
        self.assertEqual(item.get_line_total(), Decimal('1000.00'))

    def test_line_total_with_complexity(self):
        order = Order.objects.create(client=self.client_obj)
        item = OrderItem.objects.create(
            order=order,
            service=self.service,
            unit_price=Decimal('1000'),
            quantity=1,
            complexity=Decimal('1.5'),
        )
        self.assertEqual(item.get_line_total(), Decimal('1500.00'))

    def test_order_total_with_discount(self):
        order = Order.objects.create(
            client=self.client_obj,
            discount_percent=Decimal('3'),
        )
        OrderItem.objects.create(
            order=order,
            service=self.service,
            unit_price=Decimal('1000'),
            quantity=1,
            complexity=Decimal('1.0'),
        )
        self.assertEqual(order.get_total(), Decimal('970.00'))


class StaffHomeViewTest(TestCase):
    """Главный экран сотрудника."""

    def setUp(self):
        self.user = make_user()
        self.client = TestClient()
        self.client.force_login(self.user)

    def test_home_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse('core:home'))
        self.assertEqual(resp.status_code, 302)

    def test_home_returns_200(self):
        resp = self.client.get(reverse('core:home'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('in_work', resp.context)
        self.assertIn('ready_count', resp.context)
        self.assertIn('urgent_orders', resp.context)

    def test_home_search_by_order_id(self):
        cl = Client.objects.create(name='Поиск', phone='89994444444')
        order = Order.objects.create(client=cl)
        resp = self.client.get(reverse('core:home'), {'q': str(order.pk)})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['search_results']), 1)
        self.assertEqual(resp.context['search_results'][0].pk, order.pk)


class ApiClientSearchTest(TestCase):
    """Живой поиск клиентов."""

    def setUp(self):
        self.user = make_user()
        self.client = TestClient()
        self.client.force_login(self.user)
        Client.objects.create(name='Алексей Иванов', phone='89995555555')
        Client.objects.create(name='Анна Петрова', phone='89996666666')

    def test_search_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse('core:api_client_search'), {'q': 'Алексей'})
        self.assertEqual(resp.status_code, 302)

    def test_search_short_query_returns_empty(self):
        resp = self.client.get(reverse('core:api_client_search'), {'q': 'А'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['clients'], [])

    def test_search_by_name(self):
        resp = self.client.get(reverse('core:api_client_search'), {'q': 'Алексей'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data['clients']), 1)
        self.assertIn('Алексей', data['clients'][0]['name'])

    def test_search_by_phone(self):
        resp = self.client.get(reverse('core:api_client_search'), {'q': '89996666666'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data['clients']), 1)
        self.assertEqual(data['clients'][0]['phone'], '89996666666')


class OrderCreateViewTest(TestCase):
    """Оформление заказа сотрудником."""

    def setUp(self):
        self.user = make_user()
        self.client = TestClient()
        self.client.force_login(self.user)
        self.cat = ServiceCategory.objects.create(name='Одежда', slug='odezhda')
        self.svc = Service.objects.create(
            name='Пиджак',
            price=Decimal('1500'),
            category=self.cat,
        )
        self.client_obj = Client.objects.create(name='Заказчик', phone='89997777777')

    def test_order_create_get_200(self):
        resp = self.client.get(reverse('core:order_create'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('form', resp.context)
        self.assertIn('services', resp.context)

    def test_order_create_post_creates_order_and_items(self):
        from django.utils import timezone
        ready = (timezone.localdate() + timezone.timedelta(days=3)).strftime('%Y-%m-%d')
        resp = self.client.post(reverse('core:order_create'), {
            'client_id': self.client_obj.pk,
            'services': [self.svc.pk],
            'ready_by': ready,
            f'complexity_{self.svc.pk}': '1.0',
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Order.objects.count(), 1)
        order = Order.objects.first()
        self.assertEqual(order.client_id, self.client_obj.pk)
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.items.first().service_id, self.svc.pk)

    def test_order_create_applies_discount_for_loyal_client(self):
        from django.utils import timezone
        Order.objects.create(client=self.client_obj, status=Order.STATUS_ISSUED)
        Order.objects.create(client=self.client_obj, status=Order.STATUS_ISSUED)
        ready = (timezone.localdate() + timezone.timedelta(days=3)).strftime('%Y-%m-%d')
        self.client.post(reverse('core:order_create'), {
            'client_id': self.client_obj.pk,
            'services': [self.svc.pk],
            'ready_by': ready,
            f'complexity_{self.svc.pk}': '1.0',
        })
        order = Order.objects.order_by('-pk').first()
        self.assertEqual(order.discount_percent, Decimal('3'))


class StaffRegisterViewTest(TestCase):
    """Регистрация сотрудника — is_active=False до подтверждения."""

    def test_new_user_inactive(self):
        resp = self.client.post(reverse('core:register'), {
            'phone': '89998888888',
            'last_name': 'Новый',
            'first_name': 'Сотрудник',
            'patronymic': 'Тестович',
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        user = User.objects.get(phone='89998888888')
        self.assertFalse(user.is_active)


class StaffChatListTest(TestCase):
    """Список чатов для сотрудника."""

    def setUp(self):
        self.user = make_user()
        self.client = TestClient()
        self.client.force_login(self.user)

    def test_chat_list_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse('core:staff_chat_list'))
        self.assertEqual(resp.status_code, 302)

    def test_chat_list_200(self):
        resp = self.client.get(reverse('core:staff_chat_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('rooms', resp.context)
