from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.CustomLogoutView.as_view(), name='logout'),
    path('register/', views.RegisterView.as_view(), name='register'),
    path('order/new/', views.order_create, name='order_create'),
    path('api/clients/', views.api_client_search, name='api_client_search'),
    path('api/orders/search/', views.api_order_search, name='api_order_search'),
    path('chat/<int:room_id>/', views.staff_chat, name='staff_chat'),
    path('chats/', views.staff_chat_list, name='staff_chat_list'),
]
