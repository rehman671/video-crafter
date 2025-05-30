import functools
from datetime import timedelta
from django.utils import timezone
from .models import Subscription

def check_subscription_credits(view_func):
    """
    Decorator that checks if a user's subscription credits have expired and resets if needed.
    This ensures credits are only available during the current billing period.
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            if request.user.is_authenticated:
                # Get the user's active subscription
                subscription = Subscription.objects.filter(
                    user=request.user, 
                    status__in=['active', 'canceling', 'canceled']
                ).first()
                
                if subscription and subscription.current_period_end:
                    now = timezone.now()
                    
                    # Check if we've passed the expiration date
                    if now > subscription.current_period_end:
                        old_credits = subscription.unused_credits
                        
                        # Handle different subscription statuses
                        if subscription.status == 'active':
                            # Active subscription: reset credits for new billing period
                            subscription.unused_credits = subscription.plan.ad_variations_per_month
                            # Update period end to next billing cycle (assuming monthly)
                            subscription.current_period_end = subscription.current_period_end + timedelta(days=30)
                            
                            print(f"Reset credits for active subscription {request.user.username} from {old_credits} to {subscription.unused_credits}")
                            print(f"Updated period end to: {subscription.current_period_end}")
                            
                        elif subscription.status == 'canceling':
                            # Canceling subscription that's now expired: mark as canceled and zero credits
                            subscription.status = 'canceled'
                            subscription.unused_credits = 0
                            
                            print(f"Subscription expired for {request.user.username}, status changed to canceled, credits set to 0")
                            
                        elif subscription.status == 'canceled':
                            # Already canceled: ensure credits are zero
                            if subscription.unused_credits > 0:
                                subscription.unused_credits = 0
                                print(f"Zeroed credits for canceled subscription {request.user.username}")
                        
                        subscription.save()
                
            # Call the original view function
            return view_func(request, *args, **kwargs)
            
        except Exception as e:
            # Handle any exceptions that occur during the process
            print(f"Error in check_subscription_credits decorator: {e}")
            # Still call the original view function to avoid breaking the request
            return view_func(request, *args, **kwargs)
            
    return wrapper