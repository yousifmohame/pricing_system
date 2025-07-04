# management/views.py

# --- Imports ---
import base64
from django.shortcuts import get_object_or_404, render, redirect
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.db import transaction
from django.conf import settings
from collections import defaultdict
from decimal import Decimal
import re
import requests
import json
import pprint

# --- استيراد النماذج والنماذج (Forms) والمحرك ---
from .forms import SupplierForm, SubscriberForm, ShippingRateForm, CurrencyRateForm, PreferenceForm
from .parser import parse_document_with_ai, parse_with_ai, find_best_shipping_keyword_with_ai
from .engine import DistributionEngine, distribute_offers_to_subscribers
from .models import Offer, Brand, Category, Supplier, ShippingRate, Subscriber, CurrencyRate, SubscriberDeviceFee, Preference

# ==============================================================================
# 1. Main Application Views
# ==============================================================================

def analyze_offer_view(request):
    """Handles analysis and prepares offer groups for the template."""
    context = {'suppliers': Supplier.objects.all()}
    if request.method == 'POST':
        offer_text = request.POST.get('offer_text', '')
        selected_supplier_id = request.POST.get('supplier_id')
        context['selected_supplier_id'] = selected_supplier_id
        if offer_text and selected_supplier_id:
            try:
                offer_groups = parse_with_ai(offer_text)
                if isinstance(offer_groups, list) and offer_groups and 'error' in offer_groups[0]:
                    context['error_message'] = offer_groups[0]['error']
                else:
                    all_shipping_rates = list(ShippingRate.objects.all())
                    for group in offer_groups:
                        group_name_for_search = group.get('grouping_name', '').lower()
                        best_match_rate = None
                        if group_name_for_search:
                            # --- بداية الإصلاح ---
                            for rate in all_shipping_rates:
                                # استخدام الحقل الصحيح 'product_keyword_en'
                                keyword = rate.product_keyword_en.lower() if rate.product_keyword_en else ''
                                if keyword and keyword in group_name_for_search:
                                    if best_match_rate is None or len(keyword) > len(best_match_rate.product_keyword_en):
                                        best_match_rate = rate
                            # --- نهاية الإصلاح ---
                            if best_match_rate is None:
                                best_keyword = find_best_shipping_keyword_with_ai(group_name_for_search, all_shipping_rates)
                                if best_keyword: 
                                    best_match_rate = next((r for r in all_shipping_rates if r.product_keyword_en == best_keyword), None)
                        
                        for variant in group.get('variants', []):
                            variant['shipping_cost'] = best_match_rate.cost if best_match_rate else 0.00
                            variant['shipping_currency'] = best_match_rate.currency if best_match_rate else 'N/A'
                    context['offer_groups'] = offer_groups
            except Exception as e:
                context['error_message'] = f"An unexpected error occurred: {e}"
    return render(request, 'management/analyze_offer.html', context)

@transaction.atomic
def save_and_distribute_view(request):
    """
    يعالج الحفظ والتوزيع مع منطق تحقق من الرسوم على مرحلتين.
    """
    if request.method != 'POST':
        return HttpResponse("This method is not allowed.", status=405)

    # --- المرحلة 1: إعادة بناء البيانات من النموذج ---
    reconstructed_data = defaultdict(lambda: {'variants': defaultdict(dict)})
    device_names_for_validation = set()
    
    # استخراج كل البيانات وأسماء الأجهزة للتحقق
    for key, value in request.POST.items():
        if key.startswith('group-') and key.endswith('-grouping_name') and value:
            device_names_for_validation.add(value.strip())
        
        variant_match = re.match(r'group-(\d+)-variant-(\d+)-(\w+)', key)
        group_match = re.match(r'group-(\d+)-(\w+)', key)
        if variant_match:
            g_idx, v_idx, f_name = variant_match.groups()
            if value: reconstructed_data[int(g_idx)]['variants'][int(v_idx)][f_name] = value
        elif group_match:
            g_idx, f_name = group_match.groups()
            if value: reconstructed_data[int(g_idx)][f_name] = value
            
    if not reconstructed_data:
        messages.warning(request, "لم يتم العثور على بيانات صالحة للحفظ.")
        return redirect('analyze-offer')

    # --- المرحلة 2: التحقق من الرسوم الإجبارية قبل الحفظ ---
    external_subscribers = Subscriber.objects.filter(is_active=True, subscriber_type='EXTERNAL')
    missing_fees_data = []
    if external_subscribers.exists() and device_names_for_validation:
        for sub in external_subscribers:
            existing_fees = set(SubscriberDeviceFee.objects.filter(subscriber=sub).values_list('device_keyword', flat=True))
            missing_for_this_sub = list(device_names_for_validation - existing_fees)
            if missing_for_this_sub:
                missing_fees_data.append({
                    "subscriber_id": sub.id,
                    "subscriber_name": sub.name,
                    "missing_devices": missing_for_this_sub
                })

    # إذا كانت هناك رسوم ناقصة، توقف وأعد عرض الصفحة مع بيانات النافذة المنبثقة
    if missing_fees_data:
        messages.warning(request, "تنبيه: توجد رسوم إجبارية ناقصة. يرجى إدخالها للمتابعة.")
        
        # إعادة بناء السياق الكامل لإعادة عرض الصفحة بنفس البيانات
        context = {
            'suppliers': Supplier.objects.all(),
            'selected_supplier_id': request.POST.get('supplier_id'),
            'offer_groups': list(reconstructed_data.values()), # Pass the data back to the template
            'show_fees_modal': True, # Flag to trigger the modal in JavaScript
            'missing_fees_data': json.dumps(missing_fees_data) # بيانات الرسوم الناقصة
        }
        return render(request, 'management/analyze_offer.html', context)

    # --- المرحلة 3: إذا نجح التحقق، قم بالحفظ والتوزيع ---
    saved_offers = []
    try:
        supplier_id = request.POST.get('supplier_id')
        if not supplier_id: raise Exception("لم يتم تحديد المورد.")
        supplier_obj = Supplier.objects.get(id=supplier_id)

        for group_index, group_data in sorted(reconstructed_data.items()):
            group_name = group_data.get('grouping_name', '').strip()
            if not group_name: continue
            brand_obj, _ = Brand.objects.get_or_create(name=group_data.get('brand_name', 'Unknown').strip())
            category_obj, _ = Category.objects.get_or_create(name=group_data.get('category_name', 'Uncategorized').strip())
            
            for variant_index, variant_data in sorted(group_data['variants'].items()):
                variant_name = variant_data.get('name', '')
                full_name = f"{group_name} - {variant_name}" if variant_name else group_name
                new_offer = Offer.objects.create(
                    supplier=supplier_obj, brand=brand_obj, category=category_obj, name=full_name,
                    price=Decimal(variant_data.get('price') or '0.0'),
                    currency=variant_data.get('currency') or 'USD',
                    quantity=int(variant_data.get('quantity') or 0),
                    storage=variant_data.get('storage') or '',
                    condition=variant_data.get('condition') or 'New',
                    spec_region=variant_data.get('spec_region') or '',
                    color=variant_data.get('color') or '',
                    shipping_cost=Decimal(variant_data.get('shipping_cost') or '0.0'),
                    shipping_currency=variant_data.get('shipping_currency') or 'N/A'
                )
                saved_offers.append(new_offer)
        
        if saved_offers:
            transaction.on_commit(lambda: DistributionEngine.distribute(saved_offers, supplier_obj))
            messages.success(request, f"تم حفظ {len(saved_offers)} عرض بنجاح، وجاري إرسالها للمشتركين.")
        else:
            messages.warning(request, "لم يتم العثور على بيانات صالحة للحفظ.")
    except Exception as e:
        messages.error(request, f"حدث خطأ فادح: {e}")
    return redirect('analyze-offer')


# ==============================================================================
# 2. API Views (for JavaScript)
# ==============================================================================

def validate_fees_api(request):
    """API to check for missing mandatory fees for external subscribers."""
    if request.method != 'POST': return JsonResponse({'error': 'Invalid request method'}, status=405)
    try:
        data = json.loads(request.body)
        device_names = set(data.get('device_names', []))
        if not device_names: return JsonResponse([])
        external_subscribers = Subscriber.objects.filter(is_active=True, subscriber_type='EXTERNAL')
        missing_fees_data = []
        for sub in external_subscribers:
            existing_fees_for_sub = set(SubscriberDeviceFee.objects.filter(subscriber=sub).values_list('device_keyword', flat=True))
            missing_for_this_sub = list(device_names - existing_fees_for_sub)
            if missing_for_this_sub:
                missing_fees_data.append({"subscriber_id": sub.id, "subscriber_name": sub.name, "missing_devices": missing_for_this_sub})
        return JsonResponse(missing_fees_data, safe=False)
    except json.JSONDecodeError: return JsonResponse({'error': 'Invalid JSON'}, status=400)


@transaction.atomic
def subscriber_fees_api_view(request, pk):
    """API لجلب وحفظ رسوم الأجهزة لمشترك معين."""
    subscriber = get_object_or_404(Subscriber, pk=pk)
    
    if request.method == 'GET':
        fees = subscriber.device_fees.all().order_by('device_keyword')
        data = list(fees.values('device_keyword', 'fee', 'currency'))
        return JsonResponse(data, safe=False)
        
    if request.method == 'POST':
        try:
            fees_data = json.loads(request.body).get('fees', [])
            for fee_item in fees_data:
                keyword = fee_item.get('device_keyword')
                if keyword and fee_item.get('fee'):
                    SubscriberDeviceFee.objects.create(
                        subscriber=subscriber,
                        device_keyword=keyword,
                        fee=Decimal(fee_item.get('fee')),
                        currency=fee_item.get('currency', 'AED')
                    )
            return JsonResponse({'message': f"تم تحديث رسوم المشترك '{subscriber.name}' بنجاح."})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
            
    return JsonResponse({'error': 'Invalid method'}, status=405)


# ==============================================================================
# 3. CRUD Management Views
# ==============================================================================

def offers_dashboard_view(request):
    queryset = Offer.objects.select_related('supplier', 'brand', 'category').order_by('-created_at')
    search_query = request.GET.get('q', '')
    if search_query: queryset = queryset.filter(name__icontains=search_query)
    supplier_filter = request.GET.get('supplier', '')
    if supplier_filter: queryset = queryset.filter(supplier_id=supplier_filter)
    context = {'offers': queryset, 'suppliers': Supplier.objects.all(), 'search_query': search_query, 'selected_supplier': supplier_filter}
    return render(request, 'management/offers_dashboard.html', context)

# --- Supplier CRUD ---
def supplier_list_view(request):
    search_query = request.GET.get('q', '')
    suppliers = Supplier.objects.filter(name__icontains=search_query).order_by('name')
    return render(request, 'management/supplier_list.html', {'suppliers': suppliers})

def supplier_create_view(request):
    if request.method == 'POST':
        form = SupplierForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "تمت إضافة المورد بنجاح.")
            return redirect('supplier-list')
    else:
        form = SupplierForm()
    return render(request, 'management/supplier_form.html', {'form': form, 'title': 'إضافة مورد جديد'})

def supplier_update_view(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == 'POST':
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث بيانات المورد بنجاح.")
            return redirect('supplier-list')
    else:
        form = SupplierForm(instance=supplier)
    return render(request, 'management/supplier_form.html', {'form': form, 'title': f'تعديل المورد: {supplier.name}'})

def supplier_delete_view(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == 'POST':
        supplier.delete()
        messages.success(request, "تم حذف المورد بنجاح.")
        return redirect('supplier-list')
    return render(request, 'management/confirm_delete.html', {'object': supplier, 'cancel_url': 'supplier-list'})


# --- Subscriber CRUD (النسخة النهائية والمحسّنة) ---
def subscriber_list_view(request):
    search_query = request.GET.get('q', '')
    subscribers = Subscriber.objects.filter(name__icontains=search_query).order_by('name')
    return render(request, 'management/subscriber_list.html', {'subscribers': subscribers})

def subscriber_create_view(request):
    """يعالج إنشاء مشترك جديد مع ملف تفضيلاته."""
    if request.method == 'POST':
        form = SubscriberForm(request.POST)
        if form.is_valid():
            subscriber = form.save()
            Preference.objects.create(subscriber=subscriber)
            messages.success(request, f"تمت إضافة المشترك '{subscriber.name}' بنجاح. يمكنك الآن تعديل تفضيلاته.")
            return redirect('subscriber-update', pk=subscriber.pk)
    else:
        form = SubscriberForm()
    return render(request, 'management/subscriber_form.html', {'sub_form': form, 'title': 'إضافة مشترك جديد'})

def subscriber_update_view(request, pk):
    """يعالج تعديل بيانات المشترك وملف تفضيلاته معًا."""
    subscriber = get_object_or_404(Subscriber, pk=pk)
    preference, created = Preference.objects.get_or_create(subscriber=subscriber)
    if request.method == 'POST':
        sub_form = SubscriberForm(request.POST, instance=subscriber)
        pref_form = PreferenceForm(request.POST, instance=preference)
        if sub_form.is_valid() and pref_form.is_valid():
            sub_form.save()
            pref_form.save()
            messages.success(request, "تم تحديث بيانات المشترك وتفضيلاته بنجاح.")
            return redirect('subscriber-list')
    else:
        sub_form = SubscriberForm(instance=subscriber)
        pref_form = PreferenceForm(instance=preference)
    context = {
        'sub_form': sub_form,
        'pref_form': pref_form,
        'title': f'تعديل المشترك: {subscriber.name}'
    }
    return render(request, 'management/subscriber_form.html', context)

def subscriber_delete_view(request, pk):
    subscriber = get_object_or_404(Subscriber, pk=pk)
    if request.method == 'POST':
        subscriber.delete()
        messages.success(request, "تم حذف المشترك بنجاح.")
        return redirect('subscriber-list')
    return render(request, 'management/confirm_delete.html', {'object': subscriber, 'cancel_url': 'subscriber-list'})


# --- ShippingRate & CurrencyRate CRUD (تبقى كما هي) ---
def shipping_rate_list_view(request):
    search_query = request.GET.get('q', '')
    rates = ShippingRate.objects.filter(product_keyword__icontains=search_query).order_by('product_keyword')
    return render(request, 'management/shipping_rate_list.html', {'rates': rates})

def shipping_rate_create_view(request):
    if request.method == 'POST':
        form = ShippingRateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "تمت إضافة سعر الشحن بنجاح.")
            return redirect('shipping-rate-list')
    else:
        form = ShippingRateForm()
    return render(request, 'management/shipping_rate_form.html', {'form': form, 'title': 'إضافة سعر شحن جديد'})

def shipping_rate_update_view(request, pk):
    rate = get_object_or_404(ShippingRate, pk=pk)
    if request.method == 'POST':
        form = ShippingRateForm(request.POST, instance=rate)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث سعر الشحن بنجاح.")
            return redirect('shipping-rate-list')
    else:
        form = ShippingRateForm(instance=rate)
    return render(request, 'management/shipping_rate_form.html', {'form': form, 'title': f'تعديل سعر شحن'})

def shipping_rate_delete_view(request, pk):
    rate = get_object_or_404(ShippingRate, pk=pk)
    if request.method == 'POST':
        rate.delete()
        messages.success(request, "تم حذف سعر الشحن بنجاح.")
        return redirect('shipping-rate-list')
    return render(request, 'management/confirm_delete.html', {'object': rate, 'cancel_url': 'shipping-rate-list'})

def currency_rate_list_view(request):
    rates = CurrencyRate.objects.all().order_by('from_currency', 'to_currency')
    return render(request, 'management/currency_rate_list.html', {'rates': rates})

def currency_rate_create_view(request):
    if request.method == 'POST':
        form = CurrencyRateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "تمت إضافة سعر الصرف بنجاح.")
            return redirect('currency-rate-list')
    else:
        form = CurrencyRateForm()
    return render(request, 'management/currency_rate_form.html', {'form': form, 'title': 'إضافة سعر صرف جديد'})

def currency_rate_update_view(request, pk):
    rate = get_object_or_404(CurrencyRate, pk=pk)
    if request.method == 'POST':
        form = CurrencyRateForm(request.POST, instance=rate)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تحديث سعر الصرف بنجاح.")
            return redirect('currency-rate-list')
    else:
        form = CurrencyRateForm(instance=rate)
    return render(request, 'management/currency_rate_form.html', {'form': form, 'title': f'تعديل سعر الصرف'})

def currency_rate_delete_view(request, pk):
    rate = get_object_or_404(CurrencyRate, pk=pk)
    if request.method == 'POST':
        rate.delete()
        messages.success(request, "تم حذف سعر الصرف بنجاح.")
        return redirect('currency-rate-list')
    return render(request, 'management/confirm_delete.html', {'object': rate, 'cancel_url': 'currency-rate-list'})


def send_to_single_view(request):
    """
    يعالج طلب تحليل النص لعرضه في صفحة الإرسال الفردي.
    (النسخة المصححة)
    """
    context = {
        'suppliers': Supplier.objects.all(),
        'subscribers': Subscriber.objects.filter(is_active=True)
    }
    if request.method == 'POST':
        offer_text = request.POST.get('offer_text', '')
        selected_supplier_id = request.POST.get('supplier_id')
        selected_subscriber_id = request.POST.get('subscriber_id')
        
        context['selected_supplier_id'] = selected_supplier_id
        context['selected_subscriber_id'] = selected_subscriber_id

        if offer_text and selected_supplier_id and selected_subscriber_id:
            try:
                # --- بداية الإصلاح ---
                # استخدام اسم المتغير الصحيح "offer_groups"
                offer_groups = parse_with_ai(offer_text)
                
                if isinstance(offer_groups, list) and offer_groups and 'error' in offer_groups[0]:
                    context['error_message'] = offer_groups[0]['error']
                else:
                    # منطق حساب الشحن (يعمل بشكل سليم)
                    all_shipping_rates = list(ShippingRate.objects.all())
                    for group in offer_groups:
                        group_name_for_search = group.get('grouping_name', '').lower()
                        best_match_rate = None
                        if group_name_for_search:
                            for rate in all_shipping_rates:
                                # استخدام الحقل الصحيح 'product_keyword_en'
                                keyword = rate.product_keyword_en.lower() if rate.product_keyword_en else ''
                                if keyword and keyword in group_name_for_search:
                                    if best_match_rate is None or len(keyword) > len(best_match_rate.product_keyword_en):
                                        best_match_rate = rate
                            if best_match_rate is None:
                                best_keyword = find_best_shipping_keyword_with_ai(group_name_for_search, all_shipping_rates)
                                if best_keyword:
                                    best_match_rate = next((r for r in all_shipping_rates if r.product_keyword_en == best_keyword), None)
                        
                        for variant in group.get('variants', []):
                            variant['shipping_cost'] = best_match_rate.cost if best_match_rate else 0.00
                            variant['shipping_currency'] = best_match_rate.currency if best_match_rate else 'N/A'
                    
                    # تمرير المتغير بالاسم الصحيح إلى القالب
                    context['offer_groups'] = offer_groups
                # --- نهاية الإصلاح ---

            except Exception as e:
                context['error_message'] = f"An unexpected error occurred: {e}"
    
    return render(request, 'management/send_to_single.html', context)


@transaction.atomic
def save_and_send_to_single_view(request):
    """
    يحفظ العروض ويرسلها إلى مشترك واحد محدد فقط.
    (النسخة النهائية والمصححة)
    """
    if request.method != 'POST':
        return HttpResponse("This method is not allowed.", status=405)
    
    # --- بداية الإصلاح: استخدام نفس منطق إعادة البناء الموثوق ---
    reconstructed_data = defaultdict(lambda: {'variants': defaultdict(dict)})
    for key, value in request.POST.items():
        if key == 'csrfmiddlewaretoken': continue
        
        variant_match = re.match(r'group-(\d+)-variant-(\d+)-(\w+)', key)
        group_match = re.match(r'group-(\d+)-(\w+)', key)

        if variant_match:
            group_index, variant_index, field_name = variant_match.groups()
            if value: reconstructed_data[int(group_index)]['variants'][int(variant_index)][field_name] = value
        elif group_match:
            group_index, field_name = group_match.groups()
            if value: reconstructed_data[int(group_index)][field_name] = value
    # --- نهاية الإصلاح ---

    if not reconstructed_data:
        messages.warning(request, "لم يتم العثور على بيانات صالحة للحفظ.")
        return redirect('send-to-single')

    saved_offers = []
    try:
        supplier_id = request.POST.get('supplier_id')
        subscriber_id = request.POST.get('subscriber_id')
        
        if not supplier_id or not subscriber_id:
            raise Exception("لم يتم تحديد المورد أو المشترك.")
            
        supplier_obj = Supplier.objects.get(id=supplier_id)
        subscriber_obj = Subscriber.objects.get(id=subscriber_id)

        for group_index, group_data in sorted(reconstructed_data.items()):
            group_name = group_data.get('grouping_name', '').strip()
            if not group_name: continue

            brand_obj, _ = Brand.objects.get_or_create(name=group_data.get('brand_name', 'Unknown').strip())
            category_obj, _ = Category.objects.get_or_create(name=group_data.get('category_name', 'Uncategorized').strip())
            
            for variant_index, variant_data in sorted(group_data['variants'].items()):
                variant_name = variant_data.get('name', '')
                full_name = f"{group_name} - {variant_name}" if variant_name else group_name
                
                new_offer = Offer.objects.create(
                    supplier=supplier_obj, brand=brand_obj, category=category_obj, name=full_name,
                    price=Decimal(variant_data.get('price') or '0.0'),
                    currency=variant_data.get('currency') or 'USD',
                    quantity=int(variant_data.get('quantity') or 0),
                    storage=variant_data.get('storage') or '',
                    condition=variant_data.get('condition') or 'New',
                    spec_region=variant_data.get('spec_region') or '',
                    color=variant_data.get('color') or '',
                    shipping_cost=Decimal(variant_data.get('shipping_cost') or '0.0'),
                    shipping_currency=variant_data.get('shipping_currency') or 'N/A'
                )
                saved_offers.append(new_offer)
        
        if saved_offers:
            transaction.on_commit(lambda: DistributionEngine.distribute(saved_offers, supplier_obj, single_subscriber=subscriber_obj))
            messages.success(request, f"تم حفظ {len(saved_offers)} عرض بنجاح، وجاري إرسالها إلى {subscriber_obj.name}.")
        else:
            messages.warning(request, "لم يتم العثور على بيانات صالحة للحفظ.")
            
    except Exception as e:
        messages.error(request, f"حدث خطأ فادح: {e}")

    return redirect('send-to-single')


def shipping_rate_manager_view(request):
    """Renders the new interactive shipping rate manager page."""
    return render(request, 'management/shipping_rate_manager.html')


def shipping_rates_api(request):
    """API for handling shipping rates (GET all, POST to save all)."""
    if request.method == 'GET':
        rates = ShippingRate.objects.all().order_by('product_keyword_en')
        data = list(rates.values('id', 'product_keyword_en', 'product_keyword_ar', 'cost', 'currency'))
        return JsonResponse(data, safe=False)

    if request.method == 'POST':
        try:
            rates_data = json.loads(request.body).get('shipping_rates', [])
            with transaction.atomic():
                # Get all existing keywords to manage updates and creations
                existing_keywords = set(ShippingRate.objects.values_list('product_keyword_en', flat=True))
                received_keywords = set(rate.get('product_keyword_en') for rate in rates_data if rate.get('product_keyword_en'))

                # Delete rates that are no longer in the list
                ShippingRate.objects.filter(product_keyword_en__in=(existing_keywords - received_keywords)).delete()

                # Update or create rates
                for rate_item in rates_data:
                    keyword_en = rate_item.get('product_keyword_en')
                    if keyword_en: # Process only if there's an English keyword
                        ShippingRate.objects.update_or_create(
                            product_keyword_en=keyword_en,
                            defaults={
                                'product_keyword_ar': rate_item.get('product_keyword_ar', ''),
                                'cost': Decimal(rate_item.get('cost') or '0.0'),
                                'currency': rate_item.get('currency', 'AED'),
                            }
                        )
            return JsonResponse({'message': f"تم تحديث قائمة أسعار الشحن بنجاح."})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({'error': 'Invalid method'}, status=405)


def shipping_rate_analysis_api(request):
    """API to analyze a shipping rate list file using AI."""
    if request.method == 'POST':
        file_obj = request.FILES.get('file')
        if not file_obj:
            return JsonResponse({"error": "No file provided."}, status=400)
        
        try:
            file_content_base64 = base64.b64encode(file_obj.read()).decode('utf-8')
            mime_type = file_obj.content_type
            
            # Call the parser function
            extracted_data = parse_document_with_ai(file_content_base64, mime_type)
            
            return JsonResponse(extracted_data, safe=False)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid method'}, status=405)


def manage_subscriber_fees_view(request, pk):
    """
    يعرض الصفحة التفاعلية لإدارة رسوم الأجهزة لمشترك معين.
    """
    subscriber = get_object_or_404(Subscriber, pk=pk)
    return render(request, 'management/manage_subscriber_fees.html', {'subscriber': subscriber})
