from django.urls import path
from . import views

app_name = 'customer'

urlpatterns = [
    path('', views.customer_home, name='home'),
    path('about/', views.about, name='about'),
    path('services/', views.catalog, name='catalog'),
    path('services/<slug:slug>/', views.category_detail, name='category'),
    path('services/<slug:slug>/<int:pk>/', views.service_detail, name='service_detail'),
    path('cart/', views.cart_page, name='cart'),
    path('account/', views.account, name='account'),
    # path('account/edit/', views.account_edit, name='account_edit'),  # replaced by modal in account.html
    path('login/', views.CustomerLoginView.as_view(), name='login'),
    path('logout/', views.CustomerLogoutView.as_view(), name='logout'),
    path('register/', views.CustomerRegisterView.as_view(), name='register'),
    path('api/services/', views.api_services, name='api_services'),
    # path('api/delivery-options/', views.api_delivery_options, name='api_delivery_options'),  # unused after pickup_method change
    path('api/order/', views.api_create_order, name='api_create_order'),
    path('api/order/<int:pk>/request-delivery/', views.api_request_return_delivery, name='api_request_return_delivery'),
    path('order/<int:pk>/payment/', views.order_payment, name='order_payment'),
    path('order/<int:pk>/complete/', views.order_complete, name='order_complete'),
    path('order/<int:pk>/receipt/', views.order_receipt_pdf, name='order_receipt_pdf'),
    path('api/chat/messages/', views.chat_messages, name='chat_messages'),
    path('api/chat/send/', views.chat_send, name='chat_send'),
]
