import uuid
import stripe
import json
from django.shortcuts import redirect
from django.contrib import messages
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from apps.core.models import Plan, TempSubscription

stripe.api_key = settings.STRIPE_SECRET_KEY

class StripeHandler:
    """
    Handler class for all Stripe related operations
    """

    
    @staticmethod
    def create_checkout_session(request, plan_id):
        """
        Create a Stripe checkout session for subscription
        
        Args:
            request: The HTTP request object
            plan_id: The ID of the plan to subscribe to
            
        Returns:
            tuple: (success, result)
                - success (bool): Whether the operation was successful
                - result: Either the redirect URL or an error message
        """
        try:
            plan = Plan.objects.get(id=plan_id)
            temp_id = str(uuid.uuid4())        
            request.session['temp_subscription_id'] = temp_id
            request.session['selected_plan_id'] = plan_id        
            
            metadata = {
                'plan_id': str(plan.id),
                'temp_id': temp_id,
                'payment_first': 'true'
            }        
            
            success_url = request.build_absolute_uri("/register-after-payment/") + "?session_id={CHECKOUT_SESSION_ID}"
            
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{
                    "price": plan.stripe_price_id,
                    "quantity": 1,
                }],
                mode="subscription",
                success_url=success_url,
                cancel_url=request.build_absolute_uri("/"),
                allow_promotion_codes=True,

                metadata=metadata
            )
            
            return True, checkout_session.url
            
        except Plan.DoesNotExist:
            return False, "Invalid plan selected."
        except stripe.error.StripeError as e:
            return False, f"Stripe error: {str(e)}"
        except Exception as e:
            return False, f"An error occurred: {str(e)}"
    
    @staticmethod
    def create_temp_subscription(session_id, customer_id, subscription_id, plan_id):
        """
        Create a temporary subscription record for a successful checkout
        
        Args:
            session_id: The Stripe checkout session ID
            customer_id: The Stripe customer ID
            subscription_id: The Stripe subscription ID
            plan_id: The internal plan ID
            
        Returns:
            tuple: (success, result)
                - success (bool): Whether the operation was successful
                - result: The TempSubscription object or error message
        """
        try:
            # Set expiration time to 24 hours from now
            expires_at = timezone.now() + timedelta(hours=24)
            
            # Create temporary subscription record
            temp_sub = TempSubscription.objects.create(
                temp_id=str(uuid.uuid4()),
                stripe_customer_id=customer_id,
                stripe_subscription_id=subscription_id,
                plan_id=plan_id,
                session_id=session_id,
                expires_at=expires_at
            )
            
            return True, temp_sub
            
        except Exception as e:
            return False, f"Failed to create temporary subscription: {str(e)}"
            
    @staticmethod
    def process_webhook_event(payload, sig_header, webhook_secret):
        """
        Process Stripe webhook events
        
        Args:
            payload: The request body from Stripe
            sig_header: The Stripe signature header
            webhook_secret: The webhook secret to verify the signature
            
        Returns:
            tuple: (success, event)
                - success (bool): Whether the event was properly validated
                - event: The Stripe event object or error message
        """
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
            return True, event
        except ValueError as e:
            return False, "Invalid payload"
        except stripe.error.SignatureVerificationError as e:
            return False, "Invalid signature"
            
    @staticmethod
    def cancel_subscription(subscription_id):
        """
        Cancel a Stripe subscription
        
        Args:
            subscription_id: The Stripe subscription ID to cancel
            
        Returns:
            tuple: (success, result)
                - success (bool): Whether the operation was successful
                - result: The subscription object or error message
        """
        try:
            subscription = stripe.Subscription.modify(
                subscription_id,
                cancel_at_period_end=True
            )
            return True, subscription
        except stripe.error.StripeError as e:
            return False, f"Stripe error: {str(e)}"
        except Exception as e:
            return False, f"An error occurred: {str(e)}"
            
    @staticmethod
    def get_subscription_details(subscription_id):
        """
        Get details of a Stripe subscription
        
        Args:
            subscription_id: The Stripe subscription ID
            
        Returns:
            tuple: (success, result)
                - success (bool): Whether the operation was successful
                - result: The subscription details or error message
        """
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            return True, subscription
        except stripe.error.StripeError as e:
            return False, f"Stripe error: {str(e)}"
        except Exception as e:
            return False, f"An error occurred: {str(e)}"
    
    @staticmethod
    def update_subscription(subscription_id, new_price_id):
        """
        Update a subscription to a new plan/price
        
        Args:
            subscription_id: The Stripe subscription ID
            new_price_id: The new Stripe price ID
            
        Returns:
            tuple: (success, result)
                - success (bool): Whether the operation was successful
                - result: The updated subscription or error message
        """
        try:
            items = [{
                'id': stripe.Subscription.retrieve(subscription_id)['items']['data'][0].id,
                'price': new_price_id,
            }]
            
            updated_subscription = stripe.Subscription.modify(
                subscription_id,
                items=items,
                cancel_at_period_end=False,
            )
            return True, updated_subscription
        except stripe.error.StripeError as e:
            return False, f"Stripe error: {str(e)}"
        except Exception as e:
            return False, f"An error occurred: {str(e)}"
    
    @staticmethod
    def create_customer(email, name=None, metadata=None):
        """
        Create a new Stripe customer
        
        Args:
            email: Customer's email address
            name: Customer's name (optional)
            metadata: Additional metadata (optional)
            
        Returns:
            tuple: (success, result)
                - success (bool): Whether the operation was successful
                - result: The customer object or error message
        """
        try:
            customer = stripe.Customer.create(
                email=email,
                name=name,
                metadata=metadata
            )
            return True, customer
        except stripe.error.StripeError as e:
            return False, f"Stripe error: {str(e)}"
        except Exception as e:
            return False, f"An error occurred: {str(e)}"
            
    @staticmethod
    def get_payment_method(payment_method_id):
        """
        Get details of a payment method
        
        Args:
            payment_method_id: The payment method ID
            
        Returns:
            tuple: (success, result)
                - success (bool): Whether the operation was successful
                - result: The payment method details or error message
        """
        try:
            payment_method = stripe.PaymentMethod.retrieve(payment_method_id)
            return True, payment_method
        except stripe.error.StripeError as e:
            return False, f"Stripe error: {str(e)}"
        except Exception as e:
            return False, f"An error occurred: {str(e)}"