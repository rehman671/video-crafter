import functools
from django.utils import timezone
from .models import Subscription

def check_subscription_credits(view_func):
    """
    Decorator that checks if a user's subscription credits have expired and resets if needed.
    This ensures credits are only available during the current billing period.
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated:
            # Get the user's active subscription
            subscription = Subscription.objects.filter(
                user=request.user, 
                status__in=['active', 'canceling']
            ).first()
            
            if subscription and subscription.current_period_end:
                now = timezone.now()
                
                # Check if we've passed the expiration date
                if now > subscription.current_period_end:
                    # We're in a new billing period but haven't been updated by Stripe yet
                    old_credits = subscription.unused_credits
                    
                    # Reset credits to plan default
                    subscription.unused_credits = subscription.plan.ad_variations_per_month
                    
                    # If this is a canceling subscription that's now expired, mark as canceled
                    if subscription.status == 'canceling':
                        subscription.status = 'canceled'
                    
                    subscription.save()
                    
                    print(f"Reset expired credits for {request.user.username} from {old_credits} to {subscription.unused_credits}")
        
        # Call the original view function
        return view_func(request, *args, **kwargs)
    
    return wrapper