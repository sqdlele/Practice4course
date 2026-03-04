from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import Client, Order, Service, OrderItem


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'price')


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone')
    search_fields = ('name', 'phone')


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'status', 'complexity', 'discount_percent', 'ready_by', 'created_at')
    list_filter = ('status',)
    search_fields = ('client__name', 'client__phone')
    date_hierarchy = 'ready_by'
    inlines = [OrderItemInline]


@admin.action(description='Подтвердить (разрешить вход)')
def approve_users(modeladmin, request, queryset):
    queryset.update(is_active=True)


admin.site.unregister(User)


@admin.register(User)
class CustomUserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active', 'date_joined')
    list_filter = ('is_active', 'is_staff', 'is_superuser')
    actions = [approve_users]
