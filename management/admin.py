# management/admin.py

from django.contrib import admin
from .models import (
    Brand, Category, Preference, Supplier, CurrencyRate, ShippingRate,
    Subscriber, SubscriberDeviceFee, Offer
)

# 1. تخصيص عرض النماذج البسيطة
@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'contact_info')
    search_fields = ('name', 'code')
    readonly_fields = ('code',)

@admin.register(CurrencyRate)
class CurrencyRateAdmin(admin.ModelAdmin):
    list_display = ('from_currency', 'to_currency', 'rate')
    list_editable = ('rate',)

@admin.register(ShippingRate)
class ShippingRateAdmin(admin.ModelAdmin):
    # استخدام أسماء الحقول الجديدة
    list_display = ('product_keyword_en', 'product_keyword_ar', 'cost', 'currency')
    search_fields = ('product_keyword_en', 'product_keyword_ar')
    list_editable = ('cost', 'currency')
# --- نهاية الإصلاح ---


# 2. تخصيص عرض العروض
@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ('name', 'supplier', 'brand', 'price', 'currency', 'created_at')
    list_filter = ('supplier', 'brand', 'category', 'created_at')
    search_fields = ('name', 'code')
    readonly_fields = ('code', 'created_at')


class PreferenceInline(admin.StackedInline):
    model = Preference
    can_delete = False
    verbose_name_plural = 'ملف التفضيلات (قواعد التصفية)'
    # filter_horizontal يجعل اختيار الماركات والموردين أسهل بكثير
    filter_horizontal = ('allowed_suppliers', 'interested_brands', 'interested_categories')

class SubscriberDeviceFeeInline(admin.TabularInline):
    model = SubscriberDeviceFee
    extra = 1

@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
    list_display = ('name', 'whatsapp_number', 'subscriber_type', 'target_currency', 'is_active')
    list_filter = ('subscriber_type', 'is_active')
    search_fields = ('name', 'whatsapp_number')
    # إضافة واجهة التفضيلات المضمنة
    inlines = [PreferenceInline, SubscriberDeviceFeeInline]
