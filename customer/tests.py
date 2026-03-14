from decimal import Decimal
import json
from django.test import TestCase, Client as TestClient
from django.urls import reverse
from django.contrib.auth import get_user_model

from core.models import (
    Client, Service, ServiceCategory, Order, OrderItem,
    DeliveryOption, HeroBanner, Review,
)
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


# --------------- Customer Home ---------------

class CustomerHomeViewTest(TestCase):
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
        services = list(resp.context['services'])
        self.assertEqual(len(services), 1)
        self.assertEqual(services[0].name, 'Пиджак')

    def test_home_shows_reviews(self):
        Review.objects.create(author_name='Тест', text='Всё отлично', rating=5)
        resp = TestClient().get(reverse('customer:home'))
        self.assertIn('reviews', resp.context)
        self.assertEqual(len(resp.context['reviews']), 1)


# --------------- About Page ---------------

class AboutPageViewTest(TestCase):
    def test_about_200(self):
        resp = TestClient().get(reverse('customer:about'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('about', resp.context)
        self.assertIn('about_features', resp.context)
        self.assertIn('about_steps', resp.context)
        self.assertIn('stats', resp.context)

    def test_about_default_features(self):
        resp = TestClient().get(reverse('customer:about'))
        self.assertTrue(len(resp.context['about_features']) >= 5)


# --------------- Catalog ---------------

class CatalogViewTest(TestCase):
    def test_catalog_200(self):
        resp = TestClient().get(reverse('customer:catalog'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('categories', resp.context)

    def test_catalog_shows_categories(self):
        ServiceCategory.objects.create(name='Одежда', slug='odezhda')
        ServiceCategory.objects.create(name='Дом', slug='dom')
        resp = TestClient().get(reverse('customer:catalog'))
        self.assertEqual(len(resp.context['categories']), 2)


# --------------- Category Detail ---------------

class CategoryDetailViewTest(TestCase):
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

    def test_category_hides_children(self):
        parent = Service.objects.create(name='Костюм', price=Decimal('2000'), category=self.cat)
        Service.objects.create(name='Пиджак+брюки', price=Decimal('2800'), category=self.cat, parent=parent)
        resp = TestClient().get(reverse('customer:category', kwargs={'slug': 'odezhda'}))
        names = [s.name for s in resp.context['services']]
        self.assertNotIn('Пиджак+брюки', names)


# --------------- Service Detail ---------------

class ServiceDetailViewTest(TestCase):
    def setUp(self):
        self.cat = ServiceCategory.objects.create(name='Одежда', slug='odezhda')
        self.parent = Service.objects.create(
            name='Деловой костюм', price=Decimal('2000'), category=self.cat,
        )
        self.child = Service.objects.create(
            name='Пиджак+брюки', price=Decimal('2840'), category=self.cat,
            parent=self.parent,
        )

    def test_service_detail_200(self):
        resp = TestClient().get(reverse(
            'customer:service_detail',
            kwargs={'slug': 'odezhda', 'pk': self.parent.pk},
        ))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['service'].pk, self.parent.pk)
        children = list(resp.context['children'])
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0].name, 'Пиджак+брюки')

    def test_service_detail_404_child(self):
        resp = TestClient().get(reverse(
            'customer:service_detail',
            kwargs={'slug': 'odezhda', 'pk': self.child.pk},
        ))
        self.assertEqual(resp.status_code, 404)


# --------------- Cart Page ---------------

class CartPageTest(TestCase):
    def test_cart_200_anonymous(self):
        resp = TestClient().get(reverse('customer:cart'))
        self.assertEqual(resp.status_code, 200)

    def test_cart_200_authenticated(self):
        user = make_customer_user()
        client = TestClient()
        client.force_login(user)
        resp = client.get(reverse('customer:cart'))
        self.assertEqual(resp.status_code, 200)


# --------------- Account ---------------

class AccountViewTest(TestCase):
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

    def test_account_profile_update(self):
        resp = self.client.post(reverse('customer:account'), {
            'first_name': 'Новое',
            'last_name': 'Имя',
            'patronymic': 'Отчество',
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Новое')

    def test_account_creates_client_if_missing(self):
        self.assertFalse(Client.objects.filter(phone=self.user.phone).exists())
        self.client.get(reverse('customer:account'))
        self.assertTrue(Client.objects.filter(phone=self.user.phone).exists())


# --------------- API Services ---------------

class ApiServicesTest(TestCase):
    def test_api_services_returns_json(self):
        cat = ServiceCategory.objects.create(name='Тест', slug='test')
        Service.objects.create(name='Услуга', price=Decimal('100'), category=cat)
        resp = TestClient().get(reverse('customer:api_services'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('services', data)
        self.assertEqual(len(data['services']), 1)
        self.assertEqual(data['services'][0]['name'], 'Услуга')

    def test_api_services_includes_weight_and_dims(self):
        cat = ServiceCategory.objects.create(name='Тест', slug='test')
        Service.objects.create(
            name='Ковёр', price=Decimal('300'), category=cat,
            has_dimensions=True, has_weight=False,
        )
        Service.objects.create(
            name='Бельё', price=Decimal('200'), category=cat,
            has_dimensions=False, has_weight=True,
        )
        resp = TestClient().get(reverse('customer:api_services'))
        data = resp.json()
        svcs = {s['name']: s for s in data['services']}
        self.assertTrue(svcs['Ковёр']['has_dimensions'])
        self.assertFalse(svcs['Ковёр']['has_weight'])
        self.assertFalse(svcs['Бельё']['has_dimensions'])
        self.assertTrue(svcs['Бельё']['has_weight'])


# --------------- API Create Order ---------------

class ApiCreateOrderTest(TestCase):
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
        self.assertIn('payment_url', data)
        self.assertIn('prepayment_amount', data)
        order = Order.objects.get(pk=data['order_id'])
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.items.first().quantity, 2)
        self.assertEqual(order.source, Order.SOURCE_WEB)

    def test_api_create_order_self_bring(self):
        resp = self.client.post(
            reverse('customer:api_create_order'),
            json.dumps({
                'items': [{'service_id': self.svc.pk, 'qty': 1}],
                'pickup_method': 'self_bring',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        order = Order.objects.get(pk=resp.json()['order_id'])
        self.assertEqual(order.pickup_method, Order.PICKUP_SELF)
        self.assertEqual(order.courier_address, '')
        self.assertEqual(order.pickup_cost, Decimal('0'))

    def test_api_create_order_courier_with_address(self):
        resp = self.client.post(
            reverse('customer:api_create_order'),
            json.dumps({
                'items': [{'service_id': self.svc.pk, 'qty': 1}],
                'pickup_method': 'courier_pickup',
                'courier_address': 'ул. Ленина, д. 5, кв. 10',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        order = Order.objects.get(pk=data['order_id'])
        self.assertEqual(order.pickup_method, Order.PICKUP_COURIER)
        self.assertIn('Ленина', order.courier_address)
        self.assertEqual(order.pickup_cost, Decimal('400.00'))
        self.assertEqual(order.get_total(), Decimal('1200.00'))
        self.assertEqual(Decimal(data['prepayment_amount']), Decimal('400.00'))

    def test_api_create_order_courier_no_address_400(self):
        resp = self.client.post(
            reverse('customer:api_create_order'),
            json.dumps({
                'items': [{'service_id': self.svc.pk, 'qty': 1}],
                'pickup_method': 'courier_pickup',
                'courier_address': '',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('адрес', resp.json()['error'].lower())

    def test_api_create_order_with_weight(self):
        svc_kg = Service.objects.create(
            name='Бельё', price=Decimal('200'), category=self.cat,
            has_weight=True, price_unit='kg',
        )
        resp = self.client.post(
            reverse('customer:api_create_order'),
            json.dumps({'items': [{'service_id': svc_kg.pk, 'qty': 1, 'weight': 5.0}]}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        order = Order.objects.get(pk=resp.json()['order_id'])
        item = order.items.first()
        self.assertEqual(item.weight, Decimal('5'))
        self.assertEqual(item.get_line_total(), Decimal('1000.00'))

    def test_api_create_order_with_dimensions(self):
        svc_m2 = Service.objects.create(
            name='Ковёр', price=Decimal('300'), category=self.cat,
            has_dimensions=True, price_unit='m2',
        )
        resp = self.client.post(
            reverse('customer:api_create_order'),
            json.dumps({'items': [{
                'service_id': svc_m2.pk, 'qty': 1,
                'width': 2.0, 'length': 3.0,
            }]}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        item = Order.objects.get(pk=resp.json()['order_id']).items.first()
        self.assertEqual(item.width, Decimal('2'))
        self.assertEqual(item.length, Decimal('3'))
        self.assertEqual(item.get_line_total(), Decimal('1800.00'))

    def test_api_create_order_invalid_service_ids_400(self):
        resp = self.client.post(
            reverse('customer:api_create_order'),
            json.dumps({'items': [{'service_id': 99999, 'qty': 1}]}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)

    def test_api_create_order_discount_3pct(self):
        client_obj, _ = Client.objects.get_or_create(
            phone=self.user.phone, defaults={'name': 'Test'},
        )
        Order.objects.create(client=client_obj, status=Order.STATUS_ISSUED)
        Order.objects.create(client=client_obj, status=Order.STATUS_ISSUED)
        resp = self.client.post(
            reverse('customer:api_create_order'),
            json.dumps({'items': [{'service_id': self.svc.pk, 'qty': 1}]}),
            content_type='application/json',
        )
        order = Order.objects.get(pk=resp.json()['order_id'])
        self.assertEqual(order.discount_percent, Decimal('3'))
        self.assertEqual(order.get_total(), Decimal('776.00'))
        self.assertEqual(order.get_prepayment_due(), Decimal('388.00'))

    def test_api_create_order_no_discount_without_two_issued(self):
        """Без 2 выданных заказов скидка 3% не применяется."""
        client_obj, _ = Client.objects.get_or_create(
            phone=self.user.phone, defaults={'name': 'Test'},
        )
        # 0 или 1 выданный заказ — скидки нет
        resp = self.client.post(
            reverse('customer:api_create_order'),
            json.dumps({'items': [{'service_id': self.svc.pk, 'qty': 1}]}),
            content_type='application/json',
        )
        order = Order.objects.get(pk=resp.json()['order_id'])
        self.assertEqual(order.discount_percent, Decimal('0'))
        self.assertEqual(order.get_total(), Decimal('800.00'))
        self.assertEqual(Decimal(resp.json()['total']), Decimal('800.00'))
        self.assertEqual(Decimal(resp.json()['prepayment_amount']), Decimal('400.00'))

    def test_api_create_order_discount_reflected_in_response(self):
        """Суммы в ответе API уже со скидкой 3%."""
        client_obj, _ = Client.objects.get_or_create(
            phone=self.user.phone, defaults={'name': 'Test'},
        )
        Order.objects.create(client=client_obj, status=Order.STATUS_ISSUED)
        Order.objects.create(client=client_obj, status=Order.STATUS_ISSUED)
        resp = self.client.post(
            reverse('customer:api_create_order'),
            json.dumps({'items': [{'service_id': self.svc.pk, 'qty': 1}]}),
            content_type='application/json',
        )
        data = resp.json()
        self.assertEqual(Decimal(data['total']), Decimal('776.00'))
        self.assertEqual(Decimal(data['prepayment_amount']), Decimal('388.00'))

    def test_api_create_order_invalid_pickup_method_defaults(self):
        resp = self.client.post(
            reverse('customer:api_create_order'),
            json.dumps({
                'items': [{'service_id': self.svc.pk, 'qty': 1}],
                'pickup_method': 'invalid_method',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        order = Order.objects.get(pk=resp.json()['order_id'])
        self.assertEqual(order.pickup_method, Order.PICKUP_SELF)
        self.assertEqual(order.pickup_cost, Decimal('0'))


class OrderPaymentFlowTest(TestCase):
    def setUp(self):
        self.user = make_customer_user(phone='89991119999')
        self.client = TestClient()
        self.client.force_login(self.user)
        self.client_obj, _ = Client.objects.get_or_create(
            phone=self.user.phone, defaults={'name': self.user.get_full_name()},
        )
        self.cat = ServiceCategory.objects.create(name='Одежда', slug='odezhda-pay')
        self.svc = Service.objects.create(name='Пальто', price=Decimal('2000'), category=self.cat)
        self.order = Order.objects.create(
            client=self.client_obj,
            pickup_method=Order.PICKUP_COURIER,
            pickup_cost=Decimal('400.00'),
            courier_address='ул. Пушкина, д. 10',
            source=Order.SOURCE_WEB,
        )
        OrderItem.objects.create(
            order=self.order,
            service=self.svc,
            unit_price=Decimal('2000'),
            quantity=1,
            complexity=Decimal('1.0'),
        )

    def test_order_payment_page_200(self):
        resp = self.client.get(reverse('customer:order_payment', kwargs={'pk': self.order.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Первый взнос')
        self.assertContains(resp, 'Банковской картой')

    def test_order_payment_post_saves_method_and_redirects(self):
        resp = self.client.post(
            reverse('customer:order_payment', kwargs={'pk': self.order.pk}),
            {'payment_method': Order.PAYMENT_CARD_ON_HAND},
        )
        self.assertEqual(resp.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_method, Order.PAYMENT_CARD_ON_HAND)
        self.assertEqual(self.order.prepayment_amount, Decimal('1000.00'))

    def test_order_complete_requires_selected_payment(self):
        resp = self.client.get(reverse('customer:order_complete', kwargs={'pk': self.order.pk}))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('customer:order_payment', kwargs={'pk': self.order.pk}), resp.url)

    def test_order_complete_shows_receipt_after_payment(self):
        self.order.payment_method = Order.PAYMENT_CARD_ON_HAND
        self.order.prepayment_amount = self.order.get_prepayment_due()
        self.order.save(update_fields=['payment_method', 'prepayment_amount'])
        resp = self.client.get(reverse('customer:order_complete', kwargs={'pk': self.order.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'PDF-квитанция')
        self.assertContains(resp, 'Остаток к оплате')


# --------------- Order Review (after issued) ---------------

class OrderReviewTest(TestCase):
    def setUp(self):
        self.user = make_customer_user(phone='89991118888')
        self.client = TestClient()
        self.client.force_login(self.user)
        self.client_obj, _ = Client.objects.get_or_create(
            phone=self.user.phone, defaults={'name': 'Test'},
        )
        self.cat = ServiceCategory.objects.create(name='Тест', slug='test-review')
        self.svc = Service.objects.create(name='Услуга', price=Decimal('500'), category=self.cat)
        self.order = Order.objects.create(
            client=self.client_obj,
            status=Order.STATUS_ISSUED,
            source=Order.SOURCE_WEB,
        )
        OrderItem.objects.create(
            order=self.order,
            service=self.svc,
            unit_price=Decimal('500'),
            quantity=1,
            complexity=Decimal('1.0'),
        )

    def test_order_review_page_200_for_issued(self):
        resp = self.client.get(reverse('customer:order_review', kwargs={'pk': self.order.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Оставить отзыв')
        self.assertContains(resp, 'Оценка')

    def test_order_review_redirects_if_not_issued(self):
        self.order.status = Order.STATUS_READY
        self.order.save(update_fields=['status'])
        resp = self.client.get(reverse('customer:order_review', kwargs={'pk': self.order.pk}))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('customer:account'), resp.url)

    def test_order_review_post_creates_review(self):
        resp = self.client.post(
            reverse('customer:order_review', kwargs={'pk': self.order.pk}),
            {'text': 'Всё отлично, работа выполнена качественно!', 'rating': '5'},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('customer:account'), resp.url)
        review = Review.objects.get(order=self.order)
        self.assertEqual(review.rating, 5)
        self.assertIn('качественно', review.text)
        self.assertEqual(review.author_name, self.user.get_full_name() or self.user.phone)

    def test_order_review_already_reviewed_redirects(self):
        Review.objects.create(
            order=self.order,
            author_name='Test',
            text='Уже был отзыв',
            rating=4,
        )
        resp = self.client.get(reverse('customer:order_review', kwargs={'pk': self.order.pk}))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('customer:account'), resp.url)


# --------------- API Request Return Delivery ---------------

class ApiRequestReturnDeliveryTest(TestCase):
    def setUp(self):
        self.user = make_customer_user(phone='89991113333')
        self.client = TestClient()
        self.client.force_login(self.user)
        self.client_obj, _ = Client.objects.get_or_create(
            phone=self.user.phone, defaults={'name': 'Test'},
        )
        self.cat = ServiceCategory.objects.create(name='Тест', slug='test')
        self.svc = Service.objects.create(name='Рубашка', price=Decimal('500'), category=self.cat)
        self.delivery_opt, _ = DeliveryOption.objects.get_or_create(
            slug='delivery',
            defaults={'name': 'Доставка', 'base_price': Decimal('300')},
        )

    def _make_order(self, status=Order.STATUS_READY):
        order = Order.objects.create(client=self.client_obj, status=status)
        OrderItem.objects.create(
            order=order, service=self.svc,
            unit_price=Decimal('500'), quantity=1, complexity=Decimal('1.0'),
        )
        return order

    def test_requires_login(self):
        order = self._make_order()
        self.client.logout()
        resp = self.client.post(reverse('customer:api_request_return_delivery', kwargs={'pk': order.pk}))
        self.assertEqual(resp.status_code, 302)

    def test_success(self):
        order = self._make_order(Order.STATUS_READY)
        resp = self.client.post(reverse('customer:api_request_return_delivery', kwargs={'pk': order.pk}))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['ok'])
        order.refresh_from_db()
        self.assertTrue(order.return_delivery_requested)
        self.assertEqual(order.delivery_option, self.delivery_opt)
        self.assertEqual(order.delivery_cost, Decimal('300.00'))

    def test_not_ready_400(self):
        order = self._make_order(Order.STATUS_ACCEPTED)
        resp = self.client.post(reverse('customer:api_request_return_delivery', kwargs={'pk': order.pk}))
        self.assertEqual(resp.status_code, 400)
        self.assertIn('не готов', resp.json()['error'].lower())

    def test_already_requested_400(self):
        order = self._make_order(Order.STATUS_READY)
        order.return_delivery_requested = True
        order.save()
        resp = self.client.post(reverse('customer:api_request_return_delivery', kwargs={'pk': order.pk}))
        self.assertEqual(resp.status_code, 400)

    def test_wrong_client_404(self):
        other_cl = Client.objects.create(name='Другой', phone='89990008888')
        order = Order.objects.create(client=other_cl, status=Order.STATUS_READY)
        resp = self.client.post(reverse('customer:api_request_return_delivery', kwargs={'pk': order.pk}))
        self.assertEqual(resp.status_code, 404)


# --------------- PDF Receipt ---------------

class OrderReceiptPdfTest(TestCase):
    def setUp(self):
        self.user = make_customer_user(phone='89991114444')
        self.client = TestClient()
        self.client.force_login(self.user)
        self.client_obj, _ = Client.objects.get_or_create(
            phone=self.user.phone, defaults={'name': 'Тестовый Клиент'},
        )
        self.cat = ServiceCategory.objects.create(name='Тест', slug='test')
        self.svc = Service.objects.create(name='Рубашка', price=Decimal('500'), category=self.cat)
        self.order = Order.objects.create(client=self.client_obj)
        OrderItem.objects.create(
            order=self.order, service=self.svc,
            unit_price=Decimal('500'), quantity=2, complexity=Decimal('1.0'),
        )

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse('customer:order_receipt_pdf', kwargs={'pk': self.order.pk}))
        self.assertEqual(resp.status_code, 302)

    def test_returns_pdf(self):
        resp = self.client.get(reverse('customer:order_receipt_pdf', kwargs={'pk': self.order.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertIn(b'%PDF', resp.content[:10])

    def test_wrong_client_404(self):
        other_cl = Client.objects.create(name='Другой', phone='89990007777')
        other_order = Order.objects.create(client=other_cl)
        resp = self.client.get(reverse('customer:order_receipt_pdf', kwargs={'pk': other_order.pk}))
        self.assertEqual(resp.status_code, 404)

    def test_pdf_with_discount(self):
        order = Order.objects.create(client=self.client_obj, discount_percent=Decimal('3'))
        OrderItem.objects.create(
            order=order, service=self.svc,
            unit_price=Decimal('1000'), quantity=1, complexity=Decimal('1.0'),
        )
        resp = self.client.get(reverse('customer:order_receipt_pdf', kwargs={'pk': order.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')


# --------------- Customer Auth ---------------

class CustomerLoginTest(TestCase):
    def setUp(self):
        self.user = make_customer_user(phone='89991115555')

    def test_login_page_200(self):
        resp = TestClient().get(reverse('customer:login'))
        self.assertEqual(resp.status_code, 200)

    def test_login_success_redirect(self):
        resp = TestClient().post(reverse('customer:login'), {
            'username': '89991115555',
            'password': 'testpass123',
        })
        self.assertEqual(resp.status_code, 302)

    def test_login_wrong_password(self):
        resp = TestClient().post(reverse('customer:login'), {
            'username': '89991115555',
            'password': 'wrong',
        })
        self.assertEqual(resp.status_code, 200)


class CustomerRegisterTest(TestCase):
    def test_register_page_200(self):
        resp = TestClient().get(reverse('customer:register'))
        self.assertEqual(resp.status_code, 200)

    def test_register_creates_user(self):
        resp = TestClient().post(reverse('customer:register'), {
            'phone': '89991116666',
            'first_name': 'Новый',
            'last_name': 'Клиент',
            'patronymic': 'Тестович',
            'password1': 'SecurePass123!',
            'password2': 'SecurePass123!',
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        user = User.objects.get(phone='89991116666')
        self.assertFalse(user.is_staff)
        self.assertTrue(user.is_active)

    def test_register_with_next_redirects(self):
        resp = TestClient().post(
            reverse('customer:register') + '?next=' + reverse('customer:cart'),
            {
                'phone': '89991117777',
                'first_name': 'Новый',
                'last_name': 'Клиент',
                'patronymic': 'Тестович',
                'password1': 'SecurePass123!',
                'password2': 'SecurePass123!',
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/cart/', resp.url)


# --------------- Chat API ---------------

class ChatApiTest(TestCase):
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

    def test_chat_welcome_message(self):
        resp = self.client.get(reverse('customer:chat_messages'))
        data = resp.json()
        self.assertEqual(len(data['messages']), 1)
        self.assertTrue(data['messages'][0]['is_staff'])

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

    def test_chat_messages_after_send(self):
        self.client.post(
            reverse('customer:chat_send'),
            json.dumps({'text': 'Первое'}),
            content_type='application/json',
        )
        msg = ChatMessage.objects.first()
        resp = self.client.get(reverse('customer:chat_messages'), {'after': msg.pk})
        data = resp.json()
        self.assertEqual(len(data['messages']), 0)

        self.client.post(
            reverse('customer:chat_send'),
            json.dumps({'text': 'Второе'}),
            content_type='application/json',
        )
        resp = self.client.get(reverse('customer:chat_messages'), {'after': msg.pk})
        data = resp.json()
        self.assertEqual(len(data['messages']), 1)
        self.assertEqual(data['messages'][0]['text'], 'Второе')


# --------------- URL Smoke Tests ---------------

class CustomerUrlSmokeTest(TestCase):
    """Verify all public customer URLs return 200."""

    def setUp(self):
        self.cat = ServiceCategory.objects.create(name='Одежда', slug='odezhda')
        self.svc = Service.objects.create(name='Пиджак', price=Decimal('1500'), category=self.cat)

    def test_home(self):
        self.assertEqual(TestClient().get(reverse('customer:home')).status_code, 200)

    def test_about(self):
        self.assertEqual(TestClient().get(reverse('customer:about')).status_code, 200)

    def test_catalog(self):
        self.assertEqual(TestClient().get(reverse('customer:catalog')).status_code, 200)

    def test_category(self):
        self.assertEqual(TestClient().get(reverse('customer:category', kwargs={'slug': 'odezhda'})).status_code, 200)

    def test_service_detail(self):
        self.assertEqual(TestClient().get(reverse('customer:service_detail', kwargs={'slug': 'odezhda', 'pk': self.svc.pk})).status_code, 200)

    def test_cart(self):
        self.assertEqual(TestClient().get(reverse('customer:cart')).status_code, 200)

    def test_login(self):
        self.assertEqual(TestClient().get(reverse('customer:login')).status_code, 200)

    def test_register(self):
        self.assertEqual(TestClient().get(reverse('customer:register')).status_code, 200)

    def test_api_services(self):
        self.assertEqual(TestClient().get(reverse('customer:api_services')).status_code, 200)
