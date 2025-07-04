from django.db import models
from django.core.validators import MinValueValidator

# ==========================================================================
# 1. النماذج الأساسية (Core Data Models)
# ==========================================================================

class Brand(models.Model):
    """يمثل ماركة تجارية، مثل Apple, Samsung, إلخ."""
    name = models.CharField(max_length=100, unique=True, verbose_name="الماركة")

    class Meta:
        verbose_name = "ماركة"
        verbose_name_plural = "الماركات"

    def __str__(self):
        return self.name

class Category(models.Model):
    """يمثل فئة للمنتجات، مثل هواتف ذكية، ساعات، إلخ."""
    name = models.CharField(max_length=100, unique=True, verbose_name="الفئة")

    class Meta:
        verbose_name = "فئة"
        verbose_name_plural = "الفئات"

    def __str__(self):
        return self.name

class Supplier(models.Model):
    """يمثل المورد الذي يرسل العروض."""
    name = models.CharField(max_length=255, unique=True, verbose_name="اسم المورد")
    contact_info = models.TextField(blank=True, verbose_name="بيانات التواصل")
    code = models.CharField(max_length=10, unique=True, blank=True, verbose_name="كود المورد")

    class Meta:
        verbose_name = "مورد"
        verbose_name_plural = "الموردون"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # يتم إنشاء الكود فقط عند إنشاء المورد لأول مرة
        if not self.pk:
            super().save(*args, **kwargs) # نحفظ أولاً للحصول على ID
            self.code = f"SUP-{self.pk:04d}"
            super().save(update_fields=['code']) # نحفظ مرة أخرى لتحديث الكود
        else:
            super().save(*args, **kwargs)


# ==========================================================================
# 2. نماذج التسعير والعملات (Pricing & Currency Models)
# ==========================================================================

class CurrencyRate(models.Model):
    """
    يخزن أسعار التحويل بين العملات لتوفير مصدر مركزي وموثوق.
    مثال: 1 USD = 3.75 SAR
    """
    from_currency = models.CharField(max_length=3, verbose_name="من عملة (e.g., USD)")
    to_currency = models.CharField(max_length=3, verbose_name="إلى عملة (e.g., SAR)")
    rate = models.DecimalField(max_digits=15, decimal_places=6, verbose_name="معامل التحويل (للضرب)")

    class Meta:
        unique_together = ('from_currency', 'to_currency')
        verbose_name = "سعر تحويل العملة"
        verbose_name_plural = "أسعار تحويل العملات"

    def __str__(self):
        return f"1 {self.from_currency} -> {self.rate} {self.to_currency}"

class ShippingRate(models.Model):
    """
    This model now stores your master shipping price list with bilingual keywords.
    """
    # جعلنا الحقول تقبل القيمة الفارغة لتسهيل عملية الإدخال من الواجهة
    product_keyword_en = models.CharField(
        max_length=255, 
        verbose_name="الكلمة المفتاحية (الإنجليزية)",
        unique=True, # كل كلمة إنجليزية يجب أن تكون فريدة
        null=True, blank=True
    )
    product_keyword_ar = models.CharField(
        max_length=255, 
        verbose_name="الكلمة المفتاحية (العربية)",
        null=True, blank=True
    )
    cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00,
        verbose_name="تكلفة الشحن"
    )
    currency = models.CharField(max_length=3, default="AED", verbose_name="عملة الشحن")

    class Meta:
        verbose_name = "سعر الشحن"
        verbose_name_plural = "أسعار الشحن"
        ordering = ['product_keyword_en']

    def __str__(self):
        return f"Shipping for '{self.product_keyword_en or self.product_keyword_ar}': {self.cost} {self.currency}"


# ==========================================================================
# 3. نماذج المشتركين وتفضيلاتهم (Subscriber & Preference Models)
# ==========================================================================

class Subscriber(models.Model):
    """يمثل العميل أو المشترك الذي سيستقبل الأسعار النهائية."""
    class SubscriberType(models.TextChoices):
        INTERNAL = 'INTERNAL', 'موظف/شريك (معفى من الرسوم)'
        EXTERNAL = 'EXTERNAL', 'عميل خارجي (تطبق الرسوم)'

    name = models.CharField(max_length=255, verbose_name="اسم المشترك")
    whatsapp_number = models.CharField(max_length=20, unique=True, verbose_name="رقم الواتساب")
    subscriber_type = models.CharField(max_length=10, choices=SubscriberType.choices, default=SubscriberType.EXTERNAL, verbose_name="نوع المشترك")
    is_active = models.BooleanField(default=True, verbose_name="نشط؟")
    target_currency = models.CharField(max_length=3, default="SAR", verbose_name="عملة التسعير النهائية")

    class Meta:
        verbose_name = "مشترك"
        verbose_name_plural = "المشتركون"

    def __str__(self):
        return self.name

class Preference(models.Model):
    """
    يحتوي على كل قواعد التصفية والتسعير الخاصة بمشترك واحد.
    """
    subscriber = models.OneToOneField(Subscriber, on_delete=models.CASCADE, related_name="preferences", verbose_name="المشترك")
    
    # --- تفضيلات التصفية ---
    # إذا كانت هذه القائمة فارغة، فهذا يعني أنه يرى كل الموردين
    allowed_suppliers = models.ManyToManyField(Supplier, blank=True, verbose_name="الموردون المسموح بهم (فارغ للكل)")
    
    # إذا كانت هذه القائمة فارغة، فهذا يعني أنه يرى كل الماركات
    interested_brands = models.ManyToManyField(Brand, blank=True, verbose_name="الماركات المهتم بها (فارغ للكل)")
    
    # إذا كانت هذه القائمة فارغة، فهذا يعني أنه يرى كل الفئات
    interested_categories = models.ManyToManyField(Category, blank=True, verbose_name="الفئات المهتم بها (فارغ للكل)")

    class Meta:
        verbose_name = "ملف تفضيلات"
        verbose_name_plural = "ملفات التفضيلات"

    def __str__(self):
        return f"تفضيلات {self.subscriber.name}"


# class PriceRule(models.Model):
#     """
#     قاعدة تسعير مخصصة لتطبيق زيادة (ربح) على ماركة أو فئة معينة للمشترك.
#     """
#     class AdjustmentType(models.TextChoices):
#         FIXED_AMOUNT = 'AMOUNT', 'مبلغ ثابت'
#         PERCENTAGE = 'PERCENT', 'نسبة مئوية'

#     preference = models.ForeignKey(Preference, on_delete=models.CASCADE, related_name="price_rules", verbose_name="ملف التفضيلات")
#     brand = models.ForeignKey(Brand, on_delete=models.CASCADE, null=True, blank=True, verbose_name="الماركة المستهدفة")
#     category = models.ForeignKey(Category, on_delete=models.CASCADE, null=True, blank=True, verbose_name="الفئة المستهدفة")
#     adjustment_type = models.CharField(max_length=10, choices=AdjustmentType.choices, default=AdjustmentType.FIXED_AMOUNT, verbose_name="نوع الإضافة")
#     value = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, validators=[MinValueValidator(0)], verbose_name="قيمة الإضافة")
    
#     class Meta:
#         verbose_name = "قاعدة تسعير"
#         verbose_name_plural = "قواعد التسعير"

#     def __str__(self):
#         target = self.brand.name if self.brand else (self.category.name if self.category else "الكل")
#         return f"قاعدة لـ {self.preference.subscriber.name}: أضف {self.value} على {target}"

class SubscriberDeviceFee(models.Model):
    """
    يخزن الرسوم الإجبارية لجهاز معين (بناء على كلمة مفتاحية) لمشترك معين.
    """
    subscriber = models.ForeignKey(Subscriber, on_delete=models.CASCADE, related_name="device_fees", verbose_name="المشترك")
    device_keyword = models.CharField(max_length=255, verbose_name="الكلمة المفتاحية للجهاز")
    fee = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], verbose_name="الرسم الإجباري")
    currency = models.CharField(max_length=3, default="AED", verbose_name="عملة الرسم")

    class Meta:
        unique_together = ('subscriber', 'device_keyword')
        verbose_name = "رسم جهاز للمشترك"
        verbose_name_plural = "رسوم الأجهزة للمشتركين"

    def __str__(self):
        return f"رسم '{self.device_keyword}' لـ {self.subscriber.name}: {self.fee} {self.currency}"

# ==========================================================================
# 4. النموذج الرئيسي (The Main Transactional Model)
# ==========================================================================

class Offer(models.Model):
    """
    يمثل العرض الواحد المستلم من المورد بعد تحليله وتخزينه.
    """
    
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, verbose_name="المورد")
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="الماركة")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="الفئة")

    # تفاصيل المنتج المحللة
    name = models.CharField(max_length=255, verbose_name="اسم المنتج/الموديل")
    storage = models.CharField(max_length=50, blank=True, null=True, verbose_name="السعة")
    condition = models.CharField(max_length=100, blank=True, null=True, verbose_name="الحالة")
    spec_region = models.CharField(max_length=100, blank=True, null=True, verbose_name="المواصفة/المنطقة")
    color = models.CharField(max_length=100, blank=True, null=True, verbose_name="اللون")
    quantity = models.PositiveIntegerField(null=True, blank=True, verbose_name="الكمية")

    # بيانات السعر الأصلي
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="السعر الأصلي")
    currency = models.CharField(max_length=10, null=True, blank=True, verbose_name="عملة السعر الأصلي")
    
    # بيانات الشحن المحسوبة
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="تكلفة الشحن")
    shipping_currency = models.CharField(max_length=10, null=True, blank=True, verbose_name="عملة الشحن")
    
    # بيانات إضافية
    code = models.CharField(max_length=10, unique=True, blank=True, null=True, verbose_name="كود العرض")
    original_text = models.TextField(blank=True, null=True, help_text="النص الأصلي من رسالة المورد", verbose_name="النص الأصلي")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "عرض"
        verbose_name_plural = "العروض"

    def __str__(self):
        return f"{self.name} من {self.supplier.name}"

    def save(self, *args, **kwargs):
        if not self.pk:
            super().save(*args, **kwargs)
            self.code = f"OFF-{self.pk:05d}"
            super().save(update_fields=['code'])
        else:
            super().save(*args, **kwargs)