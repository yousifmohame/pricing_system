# management/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # --- المسارات الرئيسية ---
    path('', views.analyze_offer_view, name='analyze-offer'),
    path('save-and-distribute/', views.save_and_distribute_view, name='save-and-distribute'),
    path('send-to-single/', views.send_to_single_view, name='send-to-single'),
    path('save-and-send-single/', views.save_and_send_to_single_view, name='save-and-send-single'),

    # --- واجهات الإدارة ---
    path('offers-dashboard/', views.offers_dashboard_view, name='offers-dashboard'),
    
    # Suppliers
    path('suppliers/', views.supplier_list_view, name='supplier-list'),
    path('suppliers/new/', views.supplier_create_view, name='supplier-create'),
    path('suppliers/<int:pk>/edit/', views.supplier_update_view, name='supplier-update'),
    path('suppliers/<int:pk>/delete/', views.supplier_delete_view, name='supplier-delete'),
    
    # Subscribers
    path('subscribers/', views.subscriber_list_view, name='subscriber-list'),
    path('subscribers/new/', views.subscriber_create_view, name='subscriber-create'),
    path('subscribers/<int:pk>/edit/', views.subscriber_update_view, name='subscriber-update'),
    path('subscribers/<int:pk>/delete/', views.subscriber_delete_view, name='subscriber-delete'),
    path('subscribers/<int:pk>/manage-fees/', views.manage_subscriber_fees_view, name='manage-subscriber-fees'),

    # Shipping
    path('shipping-manager/', views.shipping_rate_manager_view, name='shipping-manager'),
    
    # Currency Rates
    path('currency-rates/', views.currency_rate_list_view, name='currency-rate-list'),
    path('currency-rates/new/', views.currency_rate_create_view, name='currency-rate-create'),
    path('currency-rates/<int:pk>/edit/', views.currency_rate_update_view, name='currency-rate-update'),
    path('currency-rates/<int:pk>/delete/', views.currency_rate_delete_view, name='currency-rate-delete'),

    # --- واجهات API ---
    path('api/validate-fees/', views.validate_fees_api, name='validate-fees-api'),
    # --- بداية الإصلاح ---
    path('api/subscribers/<int:pk>/fees/', views.subscriber_fees_api_view, name='subscriber-fees-api'),
    # --- نهاية الإصلاح ---
    path('api/shipping-rates/', views.shipping_rates_api, name='shipping-rates-api'),
    path('api/shipping-rate-analysis/', views.shipping_rate_analysis_api, name='shipping-rate-analysis-api'),
]
