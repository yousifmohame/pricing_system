import requests
import json
from django.conf import settings
from decimal import Decimal, InvalidOperation
from .models import CurrencyRate, Subscriber, SubscriberDeviceFee, Preference, Offer

REGION_FLAGS = {
    "USA": "🇺🇸", "JAPAN": "🇯🇵", "VIETNAM": "🇻🇳",
    "HONG KONG": "🇭🇰", "UAE": "🇦🇪", "KSA": "🇸🇦",
    "EUROPE": "🇪🇺", "UK": "🇬🇧", "CHINA": "🇨🇳",
    "GLOBAL": "🌍", "INTERNATIONAL": "🌍",
}

def get_country_flag(region_string):
    """
    يبحث عن علم مطابق في نص المواصفة.
    """
    if not region_string:
        return ""
    # البحث عن أول كلمة مفتاحية مطابقة في نص المواصفة
    for country, flag in REGION_FLAGS.items():
        if country.lower() in region_string.lower():
            return flag + " "  # نضيف مسافة بعد العلم
    return ""  # إرجاع سلسلة فارغة إذا لم يتم العثور على تطابق


class PricingEngine:
    """محرك احترافي مسؤول عن كل حسابات التسعير وتحويل العملات."""
    @staticmethod
    def get_conversion_rate(from_currency, to_currency):
        if not from_currency or not to_currency or from_currency.upper() == to_currency.upper():
            return Decimal('1.0')
        try:
            rate = CurrencyRate.objects.get(from_currency__iexact=from_currency, to_currency__iexact=to_currency).rate
            return Decimal(rate)
        except CurrencyRate.DoesNotExist:
            try:
                inverse_rate = CurrencyRate.objects.get(from_currency__iexact=to_currency, to_currency__iexact=from_currency).rate
                return Decimal(1) / Decimal(inverse_rate)
            except (CurrencyRate.DoesNotExist, ZeroDivisionError):
                return None

    @staticmethod
    def calculate_final_price(offer, subscriber):
        """
        محرك التسعير الاحترافي: إذا كان السعر الأساسي صفراً، يتوقف عن الحساب.
        """
        print(f"\n--- Calculating price for Offer '{offer.name}' (ID: {offer.id}) for Subscriber '{subscriber.name}' ---")
        target_currency = subscriber.target_currency
        if not target_currency: return {"error": "Subscriber has no target currency."}
        
        base_price = Decimal(offer.price or '0.0')
        
        if base_price <= 0:
            print(f"--- Offer '{offer.name}' has no base price. Skipping fee calculations. ---")
            return {"price": 0, "currency": target_currency, "no_charge": True}
        
        final_price = base_price
        
        # 1. Base Price Conversion
        price_rate = PricingEngine.get_conversion_rate(offer.currency, target_currency)
        if price_rate is None: return {"error": f"Missing rate: {offer.currency} -> {target_currency}"}
        final_price *= price_rate
        print(f"1. Base Price: {offer.price} {offer.currency} -> {final_price:.2f} {target_currency}")

        # 2. Add Shipping Cost
        shipping_cost = Decimal(offer.shipping_cost or '0.0')
        if shipping_cost > 0 and offer.shipping_currency and offer.shipping_currency != 'N/A':
            shipping_rate = PricingEngine.get_conversion_rate(offer.shipping_currency, target_currency)
            if shipping_rate:
                converted_shipping = shipping_cost * shipping_rate
                final_price += converted_shipping
                print(f"2. + Shipping: {shipping_cost} {offer.shipping_currency} -> {converted_shipping:.2f} {target_currency}. Subtotal: {final_price:.2f}")

        # --- بداية الإصلاح: منطق ذكي للبحث عن الرسوم الإجبارية ---
        if subscriber.subscriber_type == 'EXTERNAL':
            all_fees_for_sub = subscriber.device_fees.all()
            best_match_fee = None
            
            # البحث عن الكلمة المفتاحية الأطول (الأكثر تحديدًا) التي تطابق اسم العرض
            for fee in all_fees_for_sub:
                if fee.device_keyword.lower() in offer.name.lower():
                    if best_match_fee is None or len(fee.device_keyword) > len(best_match_fee.device_keyword):
                        best_match_fee = fee
            
            if best_match_fee:
                fee_cost = Decimal(best_match_fee.fee or '0.0')
                if fee_cost > 0:
                    fee_rate = PricingEngine.get_conversion_rate(best_match_fee.currency, target_currency)
                    if fee_rate:
                        converted_fee = fee_cost * fee_rate
                        final_price += converted_fee
                        print(f"3. + Device Fee '{best_match_fee.device_keyword}': {fee_cost} {best_match_fee.currency} -> {converted_fee:.2f} {target_currency}. Subtotal: {final_price:.2f}")
        # --- نهاية الإصلاح ---
        
        print(f"--- Final Price for '{subscriber.name}': {final_price:.2f} {target_currency} ---")
        return {"price": round(final_price, 2), "currency": target_currency}

class NotificationEngine:
    """
    Handles all communication with subscribers including WhatsApp messaging
    """
    
    @staticmethod
    def send_whatsapp_message(recipient_number, message_body):
        """Sends message via WhatsApp API"""
        if not hasattr(settings, 'ULTRAMSG_INSTANCE_ID') or not hasattr(settings, 'ULTRAMSG_TOKEN'):
            print("ERROR: WhatsApp credentials not configured")
            return False, "WhatsApp credentials not configured"
        
        # Clean and validate phone number
        formatted_number = ''.join(c for c in recipient_number if c.isdigit())
        if not formatted_number:
            return False, "Invalid phone number"
        
        # Add country code if missing (default +966 for KSA)
        if not formatted_number.startswith('966') and len(formatted_number) < 10:
            formatted_number = '966' + formatted_number.lstrip('0')
        
        url = f"https://api.ultramsg.com/{settings.ULTRAMSG_INSTANCE_ID}/messages/chat"
        payload = {
            "token": settings.ULTRAMSG_TOKEN,
            "to": formatted_number,
            "body": message_body
        }
        headers = {'content-type': 'application/x-www-form-urlencoded'}
        
        try:
            response = requests.post(url, data=payload, headers=headers, timeout=20)
            response.raise_for_status()
            response_data = response.json()
            
            if response_data.get('sent') == 'true':
                print(f"SUCCESS: Message sent to {formatted_number}")
                return True, response_data
            
            error_msg = response_data.get('error', 'Unknown error')
            print(f"ERROR: Failed to send to {formatted_number} - {error_msg}")
            return False, error_msg
        
        except requests.exceptions.RequestException as e:
            error_msg = f"HTTP error: {str(e)}"
            print(f"EXCEPTION: Failed to send to {formatted_number} - {error_msg}")
            return False, error_msg
        except json.JSONDecodeError:
            error_msg = "Invalid response from WhatsApp API"
            print(f"EXCEPTION: Failed to parse response for {formatted_number}")
            return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            print(f"EXCEPTION: Failed to send to {formatted_number} - {error_msg}")
            return False, error_msg

    @staticmethod
    def build_offer_message(subscriber, offers, supplier):
        """Builds personalized offer message"""
        message_lines = [
            f"عزيزي {subscriber.name}،",
            f"لدينا عروض جديدة من {supplier.code} تناسب اهتماماتك:",
            "=" * 40
        ]
        
        for offer in offers:
            price_data = PricingEngine.calculate_final_price(offer, subscriber)
            price_str = f"{price_data['price']} {price_data['currency']}" if 'price' in price_data else "السعر غير متوفر"
            flag = get_country_flag(offer.spec_region)

            # التحقق من وجود سعر قبل عرضه
            if price_data.get("no_charge"):
                price_str = "عند الطلب"
            else:
                price_str = f"*{price_data['price']} {price_data['currency']}*"

            offer_details = [
                f"📱 {offer.brand.name if offer.brand else 'عام'} - {offer.name}",
                f"💾 {offer.storage}" if offer.storage else "",
                f"🎨 {offer.color}" if offer.color else "",
                f"{flag} الدولة: {offer.spec_region}",
                f"💰 السعر: {price_str}",
                f"🛒 الكمية: {offer.quantity}" if offer.quantity else "",
                f"🆔 كود العرض: {offer.code}",
                "-" * 30
            ]
            message_lines.extend([line for line in offer_details if line])
        
        message_lines.append("للاستفسار أو الطلب، راسلنا على هذا الرقم")
        return "\n".join(message_lines)


class DistributionEngine:
    """
    محرك التوزيع الذكي: يفلتر العروض ويرسلها للمشتركين المهتمين.
    """
    
    @staticmethod
    def _filter_offers_for_subscriber(offers, subscriber):
        """
        دالة مساعدة خاصة تقوم بتصفية العروض بناءً على تفضيلات مشترك معين.
        """
        try:
            preferences = subscriber.preferences
        except Preference.DoesNotExist:
            # إذا لم يكن للمشترك ملف تفضيلات، فإنه يرى كل شيء (لا يتم تطبيق أي فلتر)
            print(f"WARNING: No preference profile for {subscriber.name}. Sending all offers.")
            return offers
        
        # جلب قوائم التفضيلات مرة واحدة لتحسين الأداء
        allowed_suppliers = preferences.allowed_suppliers.all()
        interested_brands = preferences.interested_brands.all()
        interested_categories = preferences.interested_categories.all()
        
        # إذا كانت كل قوائم التفضيلات فارغة، فالمشترك مهتم بكل شيء
        if not allowed_suppliers.exists() and not interested_brands.exists() and not interested_categories.exists():
            return offers

        filtered_offers = []
        for offer in offers:
            # التحقق من المورد المسموح به
            if allowed_suppliers.exists() and offer.supplier not in allowed_suppliers:
                continue
                
            # التحقق من الماركة المهتم بها
            if interested_brands.exists() and offer.brand not in interested_brands:
                continue
                
            # التحقق من الفئة المهتم بها
            if interested_categories.exists() and offer.category not in interested_categories:
                continue
                
            # إذا مر العرض من كل الفلاتر، قم بإضافته
            filtered_offers.append(offer)
        
        return filtered_offers

    @staticmethod
    def distribute(saved_offers, supplier_obj, single_subscriber=None):
        """
        الدالة الرئيسية للتوزيع: ترسل العروض للكل، أو لمشترك واحد محدد.
        """
        if single_subscriber:
            # إذا تم تحديد مشترك واحد، ضعه في قائمة للمعالجة
            subscribers_to_process = [single_subscriber]
        else:
            # وإلا، احصل على كل المشتركين النشطين
            subscribers_to_process = Subscriber.objects.filter(
                is_active=True
            ).prefetch_related(
                'preferences__allowed_suppliers',
                'preferences__interested_brands', 
                'preferences__interested_categories'
            )
        
        for subscriber in subscribers_to_process:
            # فلترة العروض لهذا المشترك المحدد
            filtered_offers = DistributionEngine._filter_offers_for_subscriber(saved_offers, subscriber)
            
            # إذا كانت هناك عروض متبقية بعد الفلترة، قم ببناء وإرسال الرسالة
            if filtered_offers:
                # Build the message
                message = NotificationEngine.build_offer_message(subscriber, filtered_offers, supplier_obj)
                # Send the message
                NotificationEngine.send_whatsapp_message(subscriber.whatsapp_number, message)

# Legacy functions for backward compatibility
def get_conversion_rate(from_currency, to_currency):
    return PricingEngine.get_conversion_rate(from_currency, to_currency)

def calculate_final_price(offer, subscriber):
    return PricingEngine.calculate_final_price(offer, subscriber)

def send_whatsapp_message(recipient_number, message_body):
    return NotificationEngine.send_whatsapp_message(recipient_number, message_body)

def distribute_offers_to_subscribers(saved_offers, supplier_obj):
    DistributionEngine.distribute(saved_offers, supplier_obj)