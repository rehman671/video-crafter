from django.contrib import admin
from .models import Font, Plan, Subscription, BillingInfo, TempSubscription, UserAsset, AppVariables, Transitions

# Register your models here.
@admin.register(Font)
class FontAdmin(admin.ModelAdmin):
    list_display = ('name', 'font_path', 'css_name')
    search_fields = ('name',)
    ordering = ('name',)

@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'price_per_month', 'ad_variations_per_month', 'credits_price', 'show_on_frontend')
    search_fields = ('name',)
    list_filter = ('show_on_frontend',)
    ordering = ('price_per_month',)

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'status', 'unused_credits', 'current_period_end', 'days_until_expiry')
    search_fields = ('user__username', 'user__email', 'plan__name')
    list_filter = ('status', 'plan')
    raw_id_fields = ('user', 'plan')

@admin.register(BillingInfo)
class BillingInfoAdmin(admin.ModelAdmin):
    list_display = ('user', 'card_display', 'card_expiry', 'country', 'updated_at', 'has_payment_method')
    search_fields = ('user__username', 'user__email', 'card_last4', 'postal_code')
    list_filter = ('country', 'updated_at')
    raw_id_fields = ('user',)

@admin.register(TempSubscription)
class TempSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('temp_id', 'plan_id', 'created_at', 'expires_at')
    search_fields = ('temp_id', 'stripe_customer_id', 'session_id')
    list_filter = ('created_at', 'expires_at')
    readonly_fields = ('created_at',)

@admin.register(UserAsset)
class UserAssetAdmin(admin.ModelAdmin):
    list_display = ('user', 'filename', 'key', 'file_size_display', 'is_folder', 'updated_at', 'created_at')
    search_fields = ('user__username', 'user__email', 'filename', 'key')
    list_filter = ('is_folder', 'content_type', 'created_at', 'updated_at')
    raw_id_fields = ('user',)
    readonly_fields = ('file_size_display', 's3_url')

@admin.register(AppVariables)
class AppVariablesAdmin(admin.ModelAdmin):
    list_display = ('key', 'value', 'created_at', 'updated_at')
    search_fields = ('key', 'value')
    ordering = ('key',)
    fields = ('key', 'value', 'description')
    readonly_fields = ('key', )

@admin.register(Transitions)
class TransitionsAdmin(admin.ModelAdmin):
    list_display = ('name', 'duration', 'slug')
    search_fields = ('name', 'slug')
    ordering = ('name',)
    fields = ('name', 'duration', 'slug')
    readonly_fields = ('slug', )