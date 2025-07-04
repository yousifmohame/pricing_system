# management/forms.py

from django import forms
from .models import Preference, Supplier, Subscriber, ShippingRate, CurrencyRate

class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['name', 'contact_info']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'mt-1 block w-full p-2 border border-gray-300 rounded-md shadow-sm'}),
            'contact_info': forms.Textarea(attrs={'class': 'mt-1 block w-full p-2 border border-gray-300 rounded-md shadow-sm', 'rows': 4}),
        }
        labels = {
            'name': 'اسم المورد',
            'contact_info': 'بيانات التواصل',
        }

class SubscriberForm(forms.ModelForm):
    class Meta:
        model = Subscriber
        fields = ['name', 'whatsapp_number', 'subscriber_type', 'target_currency', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'mt-1 block w-full p-2 border border-gray-300 rounded-md shadow-sm'}),
            'whatsapp_number': forms.TextInput(attrs={'class': 'mt-1 block w-full p-2 border border-gray-300 rounded-md shadow-sm', 'placeholder': '+201001234567'}),
            'subscriber_type': forms.Select(attrs={'class': 'mt-1 block w-full p-2 border border-gray-300 rounded-md shadow-sm'}),
            'target_currency': forms.TextInput(attrs={'class': 'mt-1 block w-full p-2 border border-gray-300 rounded-md shadow-sm', 'placeholder': 'SAR'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'h-4 w-4 text-indigo-600 border-gray-300 rounded'}),
        }
        labels = {
            'name': 'اسم المشترك',
            'whatsapp_number': 'رقم الواتساب (بالصيغة الدولية)',
            'subscriber_type': 'نوع المشترك',
            'target_currency': 'عملة التسعير النهائية',
            'is_active': 'نشط؟',
        }

class ShippingRateForm(forms.ModelForm):
    class Meta:
        model = ShippingRate
        # --- الإصلاح هنا: استخدام أسماء الحقول الصحيحة ---
        fields = ['product_keyword_en', 'product_keyword_ar', 'cost', 'currency']
        widgets = {
            'product_keyword_en': forms.TextInput(attrs={'class': 'mt-1 block w-full p-2 border border-gray-300 rounded-md shadow-sm'}),
            'product_keyword_ar': forms.TextInput(attrs={'class': 'mt-1 block w-full p-2 border border-gray-300 rounded-md shadow-sm'}),
            'cost': forms.NumberInput(attrs={'class': 'mt-1 block w-full p-2 border border-gray-300 rounded-md shadow-sm'}),
            'currency': forms.TextInput(attrs={'class': 'mt-1 block w-full p-2 border border-gray-300 rounded-md shadow-sm', 'placeholder': 'AED'}),
        }
        labels = {
            'product_keyword_en': 'الكلمة المفتاحية (الإنجليزية)',
            'product_keyword_ar': 'الكلمة المفتاحية (العربية)',
            'cost': 'تكلفة الشحن',
            'currency': 'العملة',
        }

class CurrencyRateForm(forms.ModelForm):
    class Meta:
        model = CurrencyRate
        fields = ['from_currency', 'to_currency', 'rate']
        widgets = {
            'from_currency': forms.TextInput(attrs={'class': 'mt-1 block w-full p-2 border border-gray-300 rounded-md shadow-sm', 'placeholder': 'USD'}),
            'to_currency': forms.TextInput(attrs={'class': 'mt-1 block w-full p-2 border border-gray-300 rounded-md shadow-sm', 'placeholder': 'SAR'}),
            'rate': forms.NumberInput(attrs={'class': 'mt-1 block w-full p-2 border border-gray-300 rounded-md shadow-sm'}),
        }
        labels = {
            'from_currency': 'من عملة',
            'to_currency': 'إلى عملة',
            'rate': 'معامل التحويل (للضرب)',
        }

class PreferenceForm(forms.ModelForm):
    class Meta:
        model = Preference
        fields = ['allowed_suppliers', 'interested_brands', 'interested_categories']
        # سنستخدم CheckboxSelectMultiple لعرض الخيارات بشكل أفضل
        widgets = {
            'allowed_suppliers': forms.CheckboxSelectMultiple,
            'interested_brands': forms.CheckboxSelectMultiple,
            'interested_categories': forms.CheckboxSelectMultiple,
        }
        labels = {
            'allowed_suppliers': 'الموردون المسموح بهم',
            'interested_brands': 'الماركات المهتم بها',
            'interested_categories': 'الفئات المهتم بها',
        }
