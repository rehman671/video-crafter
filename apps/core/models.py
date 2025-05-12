from django.db import models
from django.contrib.auth.models import User

# Create your models here.
class Font(models.Model):
    name = models.CharField(max_length=255)
    font_path = models.CharField(max_length=255)

    def __str__(self):
        return self.name
    

class Plan(models.Model):
    name = models.CharField(max_length=50, unique=True)
    price_per_month = models.DecimalField(max_digits=6, decimal_places=2)
    description = models.TextField(blank=True)
    ad_variations_per_month = models.IntegerField(default=0)
    stripe_price_id = models.CharField(max_length=100, unique=True, default="default_price_id")
    credits_price = models.DecimalField(default=0, decimal_places=2, max_digits=10)
    show_on_frontend = models.BooleanField(default=True)
  # Added default

    def __str__(self):
        return self.name

class Subscription(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=[('active', 'Active'), ('canceled', 'Canceled'), ('canceling', 'Canceling'), ('past_due', 'Past Due')], default='active')
    unused_credits = models.PositiveIntegerField(default=0)
    stripe_subscription_id = models.CharField(max_length=100, default="default_subscription_id")
    current_period_end = models.DateTimeField(null=True, blank=True)  # New field for credit expiration

    def __str__(self):
        return f"{self.user.username} - {self.plan.name} ({self.status})"
    
    @property
    def credit_price(self):
        """Return the price per credit based on plan"""
        plan_name = self.plan.name.lower()
        if plan_name == 'premium':
            return 0.66
        elif plan_name == 'pro':
            return 0.99
        else:
            return 1.25
    
    @property
    def days_until_expiry(self):
        """Return the number of days until credits expire"""
        if not self.current_period_end:
            return None
        
        import datetime
        from django.utils import timezone
        
        now = timezone.now()
        if now > self.current_period_end:
            return 0
        
        # Calculate days remaining
        delta = self.current_period_end - now
        return delta.days
    
class BillingInfo(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='billing_info')
    stripe_customer_id = models.CharField(max_length=100, blank=True, null=True)
    default_payment_method_id = models.CharField(max_length=100, blank=True, null=True)
    card_last4 = models.CharField(max_length=4, blank=True, null=True)
    card_brand = models.CharField(max_length=20, blank=True, null=True)
    card_exp_month = models.IntegerField(blank=True, null=True)
    card_exp_year = models.IntegerField(blank=True, null=True)
    billing_address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(max_length=2, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Billing info for {self.user.username}"
    
    @property
    def has_payment_method(self):
        return bool(self.default_payment_method_id)
    
    @property
    def card_display(self):
        if self.card_brand and self.card_last4:
            return f"{self.card_brand.title()} •••• {self.card_last4}"
        return "No card on file"
    
    @property
    def card_expiry(self):
        if self.card_exp_month and self.card_exp_year:
            return f"{self.card_exp_month:02d}/{self.card_exp_year % 100:02d}"
        return ""
    

class TempSubscription(models.Model):
    """Temporary storage for subscription info before user registration"""
    temp_id = models.CharField(max_length=100, unique=True)
    stripe_customer_id = models.CharField(max_length=100)
    stripe_subscription_id = models.CharField(max_length=100)
    plan_id = models.IntegerField()
    session_id = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    
    def __str__(self):
        return f"Temp subscription {self.temp_id}"

class UserAsset(models.Model):
    """Tracks user-uploaded assets stored in S3"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assets')
    key = models.CharField(max_length=512)  # S3 key (path)
    filename = models.CharField(max_length=255)
    file_size = models.PositiveBigIntegerField(default=0)  # Size in bytes
    content_type = models.CharField(max_length=100, blank=True)
    is_folder = models.BooleanField(default=False)
    parent_folder = models.CharField(max_length=512, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'key')
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.user.username} - {self.filename} ({self.key})"

    def save(self, *args, **kwargs):
        # Ensure consistent formatting of keys and parent folders
        # Make sure folders end with a slash
        if self.is_folder and not self.key.endswith('/'):
            self.key += '/'
            
        # Make sure parent_folder is correctly set
        if not self.parent_folder and '/' in self.key:
            self.parent_folder = self.key.rsplit('/', 2)[0] if self.key.endswith('/') else self.key.rsplit('/', 1)[0]
            
        # Remove any double slashes
        self.key = self.key.replace('//', '/')
        if self.parent_folder:
            self.parent_folder = self.parent_folder.replace('//', '/')
            
        super().save(*args, **kwargs)

    @property
    def s3_url(self):
        """Get the S3 URL for this asset"""
        from django.conf import settings
        return f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/{self.key}"
    
    @property
    def file_size_display(self):
        """Return human-readable file size"""
        if not self.file_size:
            return "0 B"
        
        size = self.file_size
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"