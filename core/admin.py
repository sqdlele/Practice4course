from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth import get_user_model

from .models import Client, Order, Service, ServiceCategory, OrderItem, HeroBanner, Review, AboutPage, AboutFeature, AboutStep, DeliveryOption

User = get_user_model()


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'order')
    list_editable = ('order',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'category', 'price', 'price_unit', 'cleaning_time', 'is_popular','svg_code')
    list_editable = ('price', 'price_unit', 'cleaning_time', 'is_popular')
    list_filter = ('category', 'parent', 'price_unit', 'has_dimensions', 'has_weight', 'is_popular')
    raw_id_fields = ('parent',)
    
    fieldsets = (
        (None, {
            'fields': ('name', 'parent', 'category', 'price', 'price_unit', 'cleaning_time', 'is_popular')
        }),
        ('Визуал (Фото или SVG)', {
            'fields': ('image', 'svg_code'),
            'description': 'Если загружено фото, оно будет в приоритете. Если нет — выведется SVG.'
        }),
        ('Дополнительные параметры', {
            'fields': ('has_dimensions', 'has_weight'),
        }),
    )

    @admin.display(boolean=True, description='SVG')
    def has_svg(self, obj):
        return bool(obj.svg_code)


@admin.register(HeroBanner)
class HeroBannerAdmin(admin.ModelAdmin):
    list_display = ('title', 'order')
    list_editable = ('order',)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('author_name', 'rating', 'created_at')


@admin.register(AboutPage)
class AboutPageAdmin(admin.ModelAdmin):
    list_display = ('hero_title', 'years_experience')


@admin.register(AboutFeature)
class AboutFeatureAdmin(admin.ModelAdmin):
    list_display = ('title', 'order')
    list_editable = ('order',)


@admin.register(AboutStep)
class AboutStepAdmin(admin.ModelAdmin):
    list_display = ('step_number', 'title', 'order')
    list_editable = ('order',)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone')
    search_fields = ('name', 'phone')


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ('service', 'unit_price', 'quantity', 'complexity', 'width', 'length', 'weight')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'client', 'source', 'status', 'pickup_method', 'pickup_cost',
        'payment_method', 'prepayment_amount', 'discount_percent',
        'delivery_option', 'delivery_cost', 'ready_by', 'created_at',
    )
    list_filter = ('status', 'source', 'pickup_method')
    search_fields = ('client__name', 'client__phone')
    date_hierarchy = 'ready_by'
    inlines = [OrderItemInline]


@admin.register(DeliveryOption)
class DeliveryOptionAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'base_price', 'free_if_order_total_above', 'free_kg', 'extra_per_kg', 'order')
    list_editable = ('base_price', 'free_if_order_total_above', 'free_kg', 'extra_per_kg', 'order')


@admin.action(description='Подтвердить (разрешить вход)')
def approve_users(modeladmin, request, queryset):
    queryset.update(is_active=True)


@admin.register(User)
class CustomUserAdmin(BaseUserAdmin):
    list_display = ('phone', 'last_name', 'first_name', 'patronymic', 'is_staff', 'is_active', 'date_joined')
    list_filter = ('is_active', 'is_staff', 'is_superuser')
    search_fields = ('phone', 'first_name', 'last_name', 'patronymic')
    ordering = ('-date_joined',)
    actions = [approve_users]
    fieldsets = (
        (None, {'fields': ('phone', 'password')}),
        ('Персональные данные', {'fields': ('last_name', 'first_name', 'patronymic', 'email')}),
        ('Права', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Даты', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('phone', 'last_name', 'first_name', 'patronymic', 'password1', 'password2'),
        }),
    )
