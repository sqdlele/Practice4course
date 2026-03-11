from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client as TestClient
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from core.models import Client, Service, ServiceCategory, Order, OrderItem, DeliveryOption

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


# --------------- Model Tests ---------------

class ClientModelTest(TestCase):
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
    def setUp(self):
        self.cat = ServiceCategory.objects.create(name='Тест', slug='test')
        self.service = Service.objects.create(name='Рубашка', price=Decimal('500'), category=self.cat)
        self.client_obj = Client.objects.create(name='Клиент', phone='89993333333')

    def test_line_total_simple(self):
        order = Order.objects.create(client=self.client_obj)
        item = OrderItem.objects.create(
            order=order, service=self.service,
            unit_price=Decimal('500'), quantity=2, complexity=Decimal('1.0'),
        )
        self.assertEqual(item.get_line_total(), Decimal('1000.00'))

    def test_line_total_with_complexity(self):
        order = Order.objects.create(client=self.client_obj)
        item = OrderItem.objects.create(
            order=order, service=self.service,
            unit_price=Decimal('1000'), quantity=1, complexity=Decimal('1.5'),
        )
        self.assertEqual(item.get_line_total(), Decimal('1500.00'))

    def test_line_total_with_discount(self):
        order = Order.objects.create(client=self.client_obj, discount_percent=Decimal('3'))
        item = OrderItem.objects.create(
            order=order, service=self.service,
            unit_price=Decimal('1000'), quantity=1, complexity=Decimal('1.0'),
        )
        self.assertEqual(item.get_line_total(Decimal('3')), Decimal('970.00'))

    def test_line_total_property_uses_order_discount(self):
        order = Order.objects.create(client=self.client_obj, discount_percent=Decimal('3'))
        item = OrderItem.objects.create(
            order=order, service=self.service,
            unit_price=Decimal('1000'), quantity=1, complexity=Decimal('1.0'),
        )
        self.assertEqual(item.line_total, Decimal('970.00'))

    def test_get_multiplier_dimensions(self):
        order = Order.objects.create(client=self.client_obj)
        item = OrderItem.objects.create(
            order=order, service=self.service,
            unit_price=Decimal('100'), quantity=1, complexity=Decimal('1.0'),
            width=Decimal('2'), length=Decimal('3'),
        )
        self.assertEqual(item.get_multiplier(), Decimal('6'))
        self.assertEqual(item.get_line_total(), Decimal('600.00'))

    def test_get_multiplier_weight(self):
        order = Order.objects.create(client=self.client_obj)
        item = OrderItem.objects.create(
            order=order, service=self.service,
            unit_price=Decimal('200'), quantity=1, complexity=Decimal('1.0'),
            weight=Decimal('3.5'),
        )
        self.assertEqual(item.get_multiplier(), Decimal('3.5'))
        self.assertEqual(item.get_line_total(), Decimal('700.00'))

    def test_order_total_with_discount(self):
        order = Order.objects.create(client=self.client_obj, discount_percent=Decimal('3'))
        OrderItem.objects.create(
            order=order, service=self.service,
            unit_price=Decimal('1000'), quantity=1, complexity=Decimal('1.0'),
        )
        self.assertEqual(order.get_total(), Decimal('970.00'))

    def test_order_total_with_delivery(self):
        order = Order.objects.create(
            client=self.client_obj, delivery_cost=Decimal('300'),
        )
        OrderItem.objects.create(
            order=order, service=self.service,
            unit_price=Decimal('1000'), quantity=1, complexity=Decimal('1.0'),
        )
        self.assertEqual(order.get_total(), Decimal('1300.00'))
        self.assertEqual(order.get_subtotal(), Decimal('1000.00'))


class DeliveryOptionTest(TestCase):
    def test_pickup_free(self):
        opt, _ = DeliveryOption.objects.get_or_create(
            slug='pickup',
            defaults={'name': 'Самовывоз', 'base_price': Decimal('0')},
        )
        self.assertEqual(opt.compute_cost(Decimal('5000')), Decimal('0'))

    def test_delivery_base_cost(self):
        opt, _ = DeliveryOption.objects.get_or_create(
            slug='delivery',
            defaults={'name': 'Доставка', 'base_price': Decimal('300')},
        )
        opt.base_price = Decimal('300')
        opt.free_if_order_total_above = Decimal('5000')
        opt.save()
        self.assertEqual(opt.compute_cost(Decimal('1000')), Decimal('300.00'))

    def test_delivery_free_above_threshold(self):
        opt, _ = DeliveryOption.objects.get_or_create(
            slug='delivery',
            defaults={'name': 'Доставка', 'base_price': Decimal('300')},
        )
        opt.base_price = Decimal('300')
        opt.free_if_order_total_above = Decimal('5000')
        opt.save()
        self.assertEqual(opt.compute_cost(Decimal('6000')), Decimal('0.00'))

    def test_delivery_weight_surcharge(self):
        opt, _ = DeliveryOption.objects.get_or_create(
            slug='delivery',
            defaults={'name': 'Доставка', 'base_price': Decimal('300')},
        )
        opt.base_price = Decimal('300')
        opt.free_kg = Decimal('5')
        opt.extra_per_kg = Decimal('20')
        opt.save()
        cost = opt.compute_cost(Decimal('1000'), Decimal('8'))
        self.assertEqual(cost, Decimal('360.00'))


# --------------- Staff Home View ---------------

class StaffHomeViewTest(TestCase):
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

    def test_home_counters(self):
        cl = Client.objects.create(name='Тест', phone='89990000000')
        Order.objects.create(client=cl, status=Order.STATUS_ACCEPTED)
        Order.objects.create(client=cl, status=Order.STATUS_IN_PROGRESS)
        Order.objects.create(client=cl, status=Order.STATUS_READY)
        Order.objects.create(client=cl, status=Order.STATUS_ISSUED)
        resp = self.client.get(reverse('core:home'))
        self.assertEqual(resp.context['in_work'], 2)
        self.assertEqual(resp.context['ready_count'], 1)

    def test_home_web_orders_badge(self):
        cl = Client.objects.create(name='Web', phone='89990000001')
        Order.objects.create(client=cl, status=Order.STATUS_ACCEPTED, source=Order.SOURCE_WEB)
        Order.objects.create(client=cl, status=Order.STATUS_IN_PROGRESS, source=Order.SOURCE_WEB)
        resp = self.client.get(reverse('core:home'))
        self.assertEqual(resp.context['web_orders_new_count'], 1)

    def test_home_urgent_orders(self):
        cl = Client.objects.create(name='Срочный', phone='89990000002')
        Order.objects.create(
            client=cl, status=Order.STATUS_ACCEPTED,
            ready_by=timezone.localdate() - timedelta(days=1),
        )
        resp = self.client.get(reverse('core:home'))
        self.assertEqual(len(resp.context['urgent_orders']), 1)

    def test_home_search_by_order_id(self):
        cl = Client.objects.create(name='Поиск', phone='89994444444')
        order = Order.objects.create(client=cl)
        resp = self.client.get(reverse('core:home'), {'q': str(order.pk)})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['search_results']), 1)
        self.assertEqual(resp.context['search_results'][0].pk, order.pk)


# --------------- API Client Search ---------------

class ApiClientSearchTest(TestCase):
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
        data = resp.json()
        self.assertEqual(data['clients'], [])

    def test_search_by_name(self):
        resp = self.client.get(reverse('core:api_client_search'), {'q': 'Алексей'})
        data = resp.json()
        self.assertEqual(len(data['clients']), 1)
        self.assertIn('Алексей', data['clients'][0]['name'])

    def test_search_by_phone(self):
        resp = self.client.get(reverse('core:api_client_search'), {'q': '89996666666'})
        data = resp.json()
        self.assertEqual(len(data['clients']), 1)
        self.assertEqual(data['clients'][0]['phone'], '89996666666')


# --------------- API Order Search ---------------

class ApiOrderSearchTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = TestClient()
        self.client.force_login(self.user)
        self.cl = Client.objects.create(name='Тестов Клиент', phone='89990001111')

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse('core:api_order_search'), {'q': '1'})
        self.assertEqual(resp.status_code, 302)

    def test_empty_query(self):
        resp = self.client.get(reverse('core:api_order_search'), {'q': ''})
        data = resp.json()
        self.assertEqual(data['orders'], [])

    def test_search_by_id(self):
        order = Order.objects.create(client=self.cl)
        resp = self.client.get(reverse('core:api_order_search'), {'q': str(order.pk)})
        data = resp.json()
        self.assertEqual(len(data['orders']), 1)
        self.assertEqual(data['orders'][0]['id'], order.pk)

    def test_search_by_client_name(self):
        Order.objects.create(client=self.cl)
        resp = self.client.get(reverse('core:api_order_search'), {'q': 'Тестов'})
        data = resp.json()
        self.assertEqual(len(data['orders']), 1)
        self.assertEqual(data['orders'][0]['client_name'], 'Тестов Клиент')

    def test_search_json_fields(self):
        order = Order.objects.create(
            client=self.cl, ready_by=date(2026, 3, 15),
        )
        resp = self.client.get(reverse('core:api_order_search'), {'q': str(order.pk)})
        entry = resp.json()['orders'][0]
        self.assertIn('status_display', entry)
        self.assertEqual(entry['ready_by'], '15.03.2026')


# --------------- Staff Order Create ---------------

class OrderCreateViewTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = TestClient()
        self.client.force_login(self.user)
        self.cat = ServiceCategory.objects.create(name='Одежда', slug='odezhda')
        self.svc = Service.objects.create(name='Пиджак', price=Decimal('1500'), category=self.cat)
        self.client_obj = Client.objects.create(name='Заказчик', phone='89997777777')

    def test_order_create_get_200(self):
        resp = self.client.get(reverse('core:order_create'))
        self.assertEqual(resp.status_code, 200)

    def test_order_create_post_creates_order_and_items(self):
        ready = (timezone.localdate() + timedelta(days=3)).strftime('%Y-%m-%d')
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

    def test_order_create_applies_discount_for_loyal_client(self):
        Order.objects.create(client=self.client_obj, status=Order.STATUS_ISSUED)
        Order.objects.create(client=self.client_obj, status=Order.STATUS_ISSUED)
        ready = (timezone.localdate() + timedelta(days=3)).strftime('%Y-%m-%d')
        self.client.post(reverse('core:order_create'), {
            'client_id': self.client_obj.pk,
            'services': [self.svc.pk],
            'ready_by': ready,
            f'complexity_{self.svc.pk}': '1.0',
        })
        order = Order.objects.order_by('-pk').first()
        self.assertEqual(order.discount_percent, Decimal('3'))

    def test_order_create_with_weight(self):
        svc_kg = Service.objects.create(
            name='Бельё', price=Decimal('200'), category=self.cat,
            price_unit='kg', has_weight=True,
        )
        ready = (timezone.localdate() + timedelta(days=3)).strftime('%Y-%m-%d')
        self.client.post(reverse('core:order_create'), {
            'client_id': self.client_obj.pk,
            'services': [svc_kg.pk],
            'ready_by': ready,
            f'complexity_{svc_kg.pk}': '1.0',
            f'weight_{svc_kg.pk}': '5.0',
        })
        item = OrderItem.objects.first()
        self.assertEqual(item.weight, Decimal('5.0'))
        self.assertEqual(item.get_line_total(), Decimal('1000.00'))

    def test_order_create_with_dimensions(self):
        svc_m2 = Service.objects.create(
            name='Ковёр', price=Decimal('300'), category=self.cat,
            price_unit='m2', has_dimensions=True,
        )
        ready = (timezone.localdate() + timedelta(days=3)).strftime('%Y-%m-%d')
        self.client.post(reverse('core:order_create'), {
            'client_id': self.client_obj.pk,
            'services': [svc_m2.pk],
            'ready_by': ready,
            f'complexity_{svc_m2.pk}': '1.0',
            f'width_{svc_m2.pk}': '2.0',
            f'length_{svc_m2.pk}': '3.0',
        })
        item = OrderItem.objects.first()
        self.assertEqual(item.width, Decimal('2.0'))
        self.assertEqual(item.length, Decimal('3.0'))
        self.assertEqual(item.get_line_total(), Decimal('1800.00'))


# --------------- Staff Order Detail ---------------

class OrderDetailViewTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = TestClient()
        self.client.force_login(self.user)
        self.cat = ServiceCategory.objects.create(name='Тест', slug='test')
        self.svc = Service.objects.create(name='Рубашка', price=Decimal('500'), category=self.cat)
        self.cl = Client.objects.create(name='Клиент', phone='89990009999')
        self.order = Order.objects.create(client=self.cl, status=Order.STATUS_ACCEPTED)
        self.item = OrderItem.objects.create(
            order=self.order, service=self.svc,
            unit_price=Decimal('500'), quantity=2, complexity=Decimal('1.0'),
        )

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse('core:order_detail', kwargs={'pk': self.order.pk}))
        self.assertEqual(resp.status_code, 302)

    def test_get_200(self):
        resp = self.client.get(reverse('core:order_detail', kwargs={'pk': self.order.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['order'].pk, self.order.pk)

    def test_next_statuses_for_accepted(self):
        resp = self.client.get(reverse('core:order_detail', kwargs={'pk': self.order.pk}))
        next_s = resp.context['next_statuses']
        self.assertEqual(len(next_s), 1)
        self.assertEqual(next_s[0]['value'], Order.STATUS_IN_PROGRESS)

    def test_change_status(self):
        resp = self.client.post(
            reverse('core:order_detail', kwargs={'pk': self.order.pk}),
            {'action': 'change_status', 'status': Order.STATUS_IN_PROGRESS},
        )
        self.assertEqual(resp.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_IN_PROGRESS)

    def test_set_ready_by(self):
        resp = self.client.post(
            reverse('core:order_detail', kwargs={'pk': self.order.pk}),
            {'action': 'set_ready_by', 'ready_by': '2026-04-01'},
        )
        self.assertEqual(resp.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.ready_by, date(2026, 4, 1))

    def test_set_ready_by_invalid(self):
        resp = self.client.post(
            reverse('core:order_detail', kwargs={'pk': self.order.pk}),
            {'action': 'set_ready_by', 'ready_by': 'invalid'},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)

    def test_update_items(self):
        resp = self.client.post(
            reverse('core:order_detail', kwargs={'pk': self.order.pk}),
            {
                'action': 'update_items',
                f'price_{self.item.pk}': '600',
                f'qty_{self.item.pk}': '3',
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.unit_price, Decimal('600'))
        self.assertEqual(self.item.quantity, 3)

    def test_delete_item(self):
        resp = self.client.post(
            reverse('core:order_detail', kwargs={'pk': self.order.pk}),
            {'action': 'delete_item', 'item_id': self.item.pk},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(self.order.items.exists())

    def test_404_nonexistent(self):
        resp = self.client.get(reverse('core:order_detail', kwargs={'pk': 99999}))
        self.assertEqual(resp.status_code, 404)

    def test_status_transition_chain(self):
        url = reverse('core:order_detail', kwargs={'pk': self.order.pk})
        self.client.post(url, {'action': 'change_status', 'status': Order.STATUS_IN_PROGRESS})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_IN_PROGRESS)

        self.client.post(url, {'action': 'change_status', 'status': Order.STATUS_READY})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_READY)

        self.client.post(url, {'action': 'change_status', 'status': Order.STATUS_ISSUED})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_ISSUED)


# --------------- Web Orders ---------------

class WebOrdersViewTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = TestClient()
        self.client.force_login(self.user)

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse('core:web_orders'))
        self.assertEqual(resp.status_code, 302)

    def test_empty_200(self):
        resp = self.client.get(reverse('core:web_orders'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['orders']), 0)
        self.assertEqual(resp.context['new_count'], 0)

    def test_shows_web_orders_only(self):
        cl = Client.objects.create(name='Web', phone='89990001111')
        Order.objects.create(client=cl, source=Order.SOURCE_WEB)
        Order.objects.create(client=cl, source=Order.SOURCE_STAFF)
        resp = self.client.get(reverse('core:web_orders'))
        self.assertEqual(len(resp.context['orders']), 1)

    def test_new_count(self):
        cl = Client.objects.create(name='Web', phone='89990001112')
        Order.objects.create(client=cl, source=Order.SOURCE_WEB, status=Order.STATUS_ACCEPTED)
        Order.objects.create(client=cl, source=Order.SOURCE_WEB, status=Order.STATUS_IN_PROGRESS)
        resp = self.client.get(reverse('core:web_orders'))
        self.assertEqual(resp.context['new_count'], 1)


class ApiWebOrdersCountTest(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client = TestClient()
        self.client.force_login(self.user)

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse('core:api_web_orders_count'))
        self.assertEqual(resp.status_code, 302)

    def test_returns_count(self):
        cl = Client.objects.create(name='Web', phone='89990002222')
        Order.objects.create(client=cl, source=Order.SOURCE_WEB, status=Order.STATUS_ACCEPTED)
        Order.objects.create(client=cl, source=Order.SOURCE_WEB, status=Order.STATUS_ACCEPTED)
        Order.objects.create(client=cl, source=Order.SOURCE_WEB, status=Order.STATUS_READY)
        resp = self.client.get(reverse('core:api_web_orders_count'))
        data = resp.json()
        self.assertEqual(data['count'], 2)


# --------------- Finance (staff) ---------------

class FinanceViewTest(TestCase):
    def setUp(self):
        self.staff = make_user()
        self.client.force_login(self.staff)

    def test_finance_requires_staff(self):
        self.staff.is_staff = False
        self.staff.save()
        resp = self.client.get(reverse('core:finance'))
        self.assertEqual(resp.status_code, 403)

    def test_finance_200(self):
        resp = self.client.get(reverse('core:finance'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('month_revenue', resp.context)
        self.assertIn('month_tax', resp.context)
        self.assertIn('month_net', resp.context)
        self.assertIn('tax_percent', resp.context)
        self.assertIn('months_choices', resp.context)
        self.assertEqual(resp.context['tax_percent'], 13)

    def test_finance_period_param(self):
        resp = self.client.get(reverse('core:finance'), {'period': '2025-6'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['year'], 2025)
        self.assertEqual(resp.context['month'], 6)


# --------------- Staff Register ---------------

class StaffRegisterViewTest(TestCase):
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


# --------------- Staff Chat ---------------

class StaffChatListTest(TestCase):
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


class StaffChatRoomTest(TestCase):
    def setUp(self):
        self.staff = make_user()
        self.customer = make_user(phone='89990005555', is_staff=False)
        from customer.models import ChatRoom
        self.room = ChatRoom.objects.create(user=self.customer)
        self.client = TestClient()
        self.client.force_login(self.staff)

    def test_chat_room_get_200(self):
        resp = self.client.get(reverse('core:staff_chat', kwargs={'room_id': self.room.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['room'].pk, self.room.pk)

    def test_chat_room_send_message(self):
        import json
        resp = self.client.post(
            reverse('core:staff_chat', kwargs={'room_id': self.room.pk}),
            json.dumps({'text': 'Ответ от поддержки'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['is_staff'])
        self.assertEqual(data['text'], 'Ответ от поддержки')

    def test_chat_room_ajax_messages(self):
        resp = self.client.get(
            reverse('core:staff_chat', kwargs={'room_id': self.room.pk}),
            {'after': '0'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('messages', data)
