from decimal import Decimal
import json
from django.test import TestCase, Client as TestClient
from django.urls import reverse
from django.contrib.auth import get_user_model

from core.models import Client, Service, ServiceCategory, Order
from customer.models import ChatRoom, ChatMessage

User = get_user_model()


def make_customer_user(phone='89991234567', **kwargs):
    return User.objects.create_user(
        phone=phone,
        password='testpass123',
        first_name=kwargs.get('first_name', 'Client'),
        last_name=kwargs.get('last_name', 'User'),
        patronymic=kwargs.get('patronymic', 'Pat'),
        is_staff=False,
        is_active=True,
        **{k: v for k, v in kwargs.items() if k not in ('first_name', 'last_name', 'patronymic')}
    )


class CustomerHomeViewTest(TestCase):
    """Главная страница клиентского сайта."""

    def test_home_anonymous_200(self):
        resp = TestClient().get(reverse('customer:home'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('services', resp.context)
        self.assertIn('categories', resp.context)
        self.assertIn('banners', resp.context)

    def test_home_has_popular_services(self):
        cat = ServiceCategory.objects.create(name='Одежда', slug='odezhda')
        Service.objects.create(name='Пиджак', price=Decimal('1000'), category=cat, is_popular=True)
        resp = TestClient().get(reverse('customer:home'))
        self.assertEqual(resp.status_code, 200)
        services = list(resp.context['services'])
        self.assertEqual(len(services), 1)
        self.assertEqual(services[0].name, 'Пиджак')


class CategoryDetailViewTest(TestCase):
    """Страница категории услуг."""

    def setUp(self):
        self.cat = ServiceCategory.objects.create(name='Одежда', slug='odezhda')
        Service.objects.create(name='Пиджак', price=Decimal('500'), category=self.cat, parent=None)

    def test_category_200(self):
        resp = TestClient().get(reverse('customer:category', kwargs={'slug': 'odezhda'}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['category'].slug, 'odezhda')
        self.assertEqual(len(resp.context['services']), 1)

    def test_category_404_invalid_slug(self):
        resp = TestClient().get(reverse('customer:category', kwargs={'slug': 'netakoy'}))
        self.assertEqual(resp.status_code, 404)


class ServiceDetailViewTest(TestCase):
    """Страница услуги с вариантами."""

    def setUp(self):
        self.cat = ServiceCategory.objects.create(name='Одежда', slug='odezhda')
        self.parent = Service.objects.create(
            name='Деловой костюм',
            price=Decimal('2000'),
            category=self.cat,
            parent=None,
        )
        self.child = Service.objects.create(
            name='Пиджак+брюки',
            price=Decimal('2840'),
            category=self.cat,
            parent=self.parent,
        )

    def test_service_detail_200(self):
        resp = TestClient().get(reverse('customer:service_detail', kwargs={'slug': 'odezhda', 'pk': self.parent.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['service'].pk, self.parent.pk)
        children = list(resp.context['children'])
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0].name, 'Пиджак+брюки')


class AccountViewTest(TestCase):
    """Личный кабинет клиента."""

    def setUp(self):
        self.user = make_customer_user()
        self.client = TestClient()
        self.client.force_login(self.user)

    def test_account_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse('customer:account'))
        self.assertEqual(resp.status_code, 302)

    def test_account_200_shows_orders(self):
        client_obj, _ = Client.objects.get_or_create(
            phone=self.user.phone,
            defaults={'name': self.user.get_full_name()},
        )
        Order.objects.create(client=client_obj)
        resp = self.client.get(reverse('customer:account'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['orders']), 1)


class ApiServicesTest(TestCase):
    """API списка услуг для корзины."""

    def test_api_services_returns_json(self):
        cat = ServiceCategory.objects.create(name='Тест', slug='test')
        Service.objects.create(name='Услуга', price=Decimal('100'), category=cat)
        resp = TestClient().get(reverse('customer:api_services'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('services', data)
        self.assertEqual(len(data['services']), 1)
        self.assertEqual(data['services'][0]['name'], 'Услуга')
        self.assertIn(data['services'][0]['price'], ('100', '100.00'))


class ApiCreateOrderTest(TestCase):
    """Создание заказа из корзины (API)."""

    def setUp(self):
        self.user = make_customer_user(phone='89991112222')
        self.client = TestClient()
        self.client.force_login(self.user)
        self.cat = ServiceCategory.objects.create(name='Одежда', slug='odezhda')
        self.svc = Service.objects.create(name='Рубашка', price=Decimal('800'), category=self.cat)

    def test_api_create_order_requires_login(self):
        self.client.logout()
        resp = self.client.post(
            reverse('customer:api_create_order'),
            json.dumps({'items': [{'service_id': self.svc.pk, 'qty': 1}]}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 302)

    def test_api_create_order_empty_400(self):
        resp = self.client.post(
            reverse('customer:api_create_order'),
            json.dumps({'items': []}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_api_create_order_creates_order_and_client(self):
        resp = self.client.post(
            reverse('customer:api_create_order'),
            json.dumps({'items': [{'service_id': self.svc.pk, 'qty': 2}]}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('order_id', data)
        self.assertIn('total', data)
        order = Order.objects.get(pk=data['order_id'])
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.items.first().quantity, 2)
        client = Client.objects.get(phone=self.user.phone)
        self.assertEqual(order.client_id, client.pk)


class ChatApiTest(TestCase):
    """Чат: получение и отправка сообщений."""

    def setUp(self):
        self.user = make_customer_user(phone='89993334444')
        self.client = TestClient()
        self.client.force_login(self.user)

    def test_chat_messages_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse('customer:chat_messages'))
        self.assertEqual(resp.status_code, 302)

    def test_chat_messages_returns_json(self):
        resp = self.client.get(reverse('customer:chat_messages'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('messages', data)
        self.assertIsInstance(data['messages'], list)

    def test_chat_send_creates_message(self):
        resp = self.client.post(
            reverse('customer:chat_send'),
            json.dumps({'text': 'Привет'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['text'], 'Привет')
        self.assertFalse(data['is_staff'])
        self.assertEqual(ChatMessage.objects.filter(room__user=self.user).count(), 1)

    def test_chat_send_empty_400(self):
        resp = self.client.post(
            reverse('customer:chat_send'),
            json.dumps({'text': '   '}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
