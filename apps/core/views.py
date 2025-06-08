import uuid
import stripe
import json
import os

from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required

from django.contrib import messages
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings

from apps.core.models import Plan, TempSubscription, Subscription, BillingInfo, Font
from apps.core.handler.stripe_handler import StripeHandler
from apps.core.decorators import check_subscription_credits

from apps.processors.models import Video, Clips, Subclip, BackgroundMusic
from apps.processors.handler.elevenlabs import ElevenLabsHandler
from apps.processors.utils import generate_clips_from_text_file
from django.urls import reverse
from django.http import HttpResponse, JsonResponse, FileResponse
from datetime import datetime, timedelta
from django.conf import settings
from apps.core.models import UserAsset
from django.utils.encoding import force_bytes, force_str
from apps.processors.utils import generate_signed_url, generate_signed_url_for_upload
from apps.core.utils import process_video_speed


def index(request):
    plans = Plan.objects.filter(show_on_frontend=True).order_by('price_per_month')
    return render(request, 'index.html', {'plans': plans})


def subscribe(request, plan_id):
    success, result = StripeHandler.create_checkout_session(request, plan_id)
    if success:
        return redirect(result)
    else:
        print(request, result)
        return redirect("index")
  
   
@csrf_exempt
def register_after_payment(request):
    """Registration page after successful payment"""
    session_id = request.GET.get('session_id')
    
    if not session_id:
        print(request, "Invalid session. Please try again.")
        return redirect("index")
    
    try:
        # Verify the checkout session
        checkout = stripe.checkout.Session.retrieve(session_id)
        
        # Verify payment status
        if checkout.payment_status != 'paid':
            print(request, "Payment not completed. Please try again.")
            return redirect("index")
        
        # Get customer and subscription info from Stripe
        customer_id = checkout.customer
        subscription_id = checkout.subscription
        
        # Try to get email from Stripe
        stripe_email = None
        try:
            # First check if email is in the checkout session
            stripe_email = checkout.customer_details.get('email')
            
            # If not, try to get from customer object
            if not stripe_email and customer_id:
                customer = stripe.Customer.retrieve(customer_id)
                stripe_email = customer.get('email')
        except Exception as e:
            print(f"Could not retrieve email from Stripe: {str(e)}")
        
        # Store in session for registration completion
        request.session['stripe_customer_id'] = customer_id
        request.session['stripe_subscription_id'] = subscription_id
        if stripe_email:
            request.session['stripe_email'] = stripe_email
        
        # Get plan information for display
        plan_id = checkout.metadata.get('plan_id')
        plan = None
        if plan_id:
            try:
                plan = Plan.objects.get(id=plan_id)
            except Plan.DoesNotExist:
                pass
        
        if request.method == "POST":
            username = request.POST.get("username")
            email = request.POST.get("email")
            password = request.POST.get("password")
            confirm_password = request.POST.get("confirm_password")            
            # Validate form
            if not all([username, email, password, confirm_password]):
                print(request, "All fields are required.")
                return render(request, "accounts/after-payment.html", {
                    "plan": plan, 
                    "email": email or stripe_email,
                    "error_message": "All fields are required."
                })
            
            if password != confirm_password:
                print(request, "Passwords do not match.")
                return render(request, "accounts/after-payment.html", {
                    "plan": plan, 
                    "email": email,
                    "error_message": "Passwords do not match."
                })
            
            if User.objects.filter(email=email).exists():
                print(request, "Email already registered.")
                return render(request, "accounts/after-payment.html", {
                    "plan": plan, 
                    "email": email,
                    "error_message": "Email already registered."
                })
            
            try:
                # Create the user with email
                user = User.objects.create_user(
                    first_name=username,
                    username=f"{email}",
                    email=email,
                    password=password
                )
                
                # Create billing info
                billing_info = BillingInfo.objects.create(
                    user=user,
                    stripe_customer_id=customer_id
                )
                
                # Update customer info in Stripe
                stripe.Customer.modify(
                    customer_id,
                    name=username,
                    email=email
                )
                
                # Get subscription details from Stripe
                # Get subscription details from Stripe to get the actual period end
                stripe_subscription = stripe.Subscription.retrieve(subscription_id)

                # Calculate period end date from Stripe subscription
                try:
                    if stripe_subscription and stripe_subscription.current_period_end:
                        # Convert Stripe timestamp to Django datetime
                        period_end = timezone.datetime.fromtimestamp(
                            stripe_subscription.current_period_end, 
                            tz=timezone.utc
                        )
                        print(f"Period end from Stripe: {period_end}")
                    else:
                        # Fallback: 30 days from now if Stripe data is unavailable
                        period_end = timezone.now() + timedelta(days=30)
                        print(f"Fallback period end: {period_end}")
                except:
                    period_end = timezone.now() + timedelta(days=30)
                    print(f"Fallback period end: {period_end}")

                
                # Create subscription in our database
                if plan:
                    subscription = Subscription.objects.create(
                        user=user,
                        plan=plan,
                        status='active',
                        stripe_subscription_id=subscription_id,
                        unused_credits=plan.ad_variations_per_month,
                        current_period_end=period_end
                    )
                
                # Log the user in
                login(request, user)
                
                # Clean up session data
                for key in ['stripe_customer_id', 'stripe_subscription_id', 
                           'temp_subscription_id', 'selected_plan_id', 'stripe_email']:
                    if key in request.session:
                        del request.session[key]
                
                print(request, f"Welcome! Your {plan.name if plan else 'subscription'} has been activated.")
                return redirect("preview")
                
            except Exception as e:
                print(request, f"Error creating account: {str(e)}")
                print(f"Error creating account: {str(e)}")
        
        # Pre-fill email from Stripe if available
        return render(request, "accounts/after-payment.html", {
            "plan": plan,
            "email": stripe_email
        })
        
    except stripe.error.StripeError as e:
        print(request, f"Stripe error: {str(e)}")
        print(f"Stripe error: {str(e)}")
        return redirect("index")
    except Exception as e:
        print(request, f"An error occurred: {str(e)}")
        print(f"An error occurred: {str(e)}")
        return redirect("index")
    
@check_subscription_credits
def user_logout(request):
    logout(request)
    return redirect("login")  # Redirect to login

def user_login(request):
    if request.user.is_authenticated:
        return redirect('preview')
    error_message = None
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        try:
            user = authenticate(request, username=email, password=password)
            
            if user is not None:
                login(request, user)
                return redirect("preview")
            else:
                error_message = "Invalid email or password."
                print(request, error_message)
        except User.DoesNotExist:
            error_message = "Invalid email or password."
            print(request, error_message)
            
    return render(request, "accounts/login.html", {'error_message': error_message})


# @login_required(login_url='login')
# @check_subscription_credits
# def preview(request):
#     user_subscription = None
#     error_message = None
#     if request.user.is_authenticated:
#         print(f"Authenticated user: {request.user.first_name}")
#         user_subscription = Subscription.objects.filter(user=request.user).first()
#     else:
#         return redirect('login')
    
#     if request.method == 'POST':
            
#         try:
#             resolution = request.POST.get('resolution')
#             elevenlabs_api_key = request.POST.get('elevenlabs_apikey')
#             elevenlabs_voice_id = request.POST.get('voiceid')
#             print(request.POST.get('font_select'))
#             font = Font.objects.get(name=request.POST.get('font_select'))
#             font_color = request.POST.get('font_color')
#             subtitle_box_color = request.POST.get('subtitle_box_color')
#             font_size = int(request.POST.get('font_size1'))
#             box_radius = request.POST.get('box_radius')
#             elv_handler = ElevenLabsHandler(api_key=request.POST.get('elevenlabs_apikey'), voice_id=request.POST.get('voiceid'))
#             try:
#                 elv_handler._verify_api_key()
#             except:
#                 raise Exception("Invalid ElevenLabs API Key.")
#             try:
#                 elv_handler._verify_voice_id()
#             except:
#                 raise Exception("Invalid ElevenLabs Voice ID.")
            
#             video = Video.objects.create(
#                 user=request.user,
#                 dimensions=resolution,
#                 elevenlabs_api_key=elevenlabs_api_key,
#                 voice_id=elevenlabs_voice_id,
#                 subtitle_font=font,
#                 font_color=font_color,
#                 subtitle_box_color=subtitle_box_color,
#                 font_size=font_size,
#                 box_roundness=box_radius
#             )
#             return redirect("scene_view", video_id=video.id)
#         except Exception as e:
#             error_message = f"{str(e)}"
#             print(f"Error: {error_message}")
#             print(request, error_message)
#     return render(request, "home/preview.html", {"form": None, "user_subscription": user_subscription, "fonts": Font.objects.all(), 'error_message': error_message})


@login_required(login_url='login')
@check_subscription_credits
def preview(request):
    user_subscription = None
    error_message = None
    form_data = {}  # Initialize form_data to store user inputs
    
    if request.user.is_authenticated:
        print(f"Authenticated user: {request.user.first_name}")
        user_subscription = Subscription.objects.filter(user=request.user).first()
    else:
        return redirect('login')
    
    if request.method == 'POST':
        # Store all POST data in form_data
        form_data = {
            'resolution': request.POST.get('resolution', '1:1'),
            'elevenlabs_apikey': request.POST.get('elevenlabs_apikey', ''),
            'voiceid': request.POST.get('voiceid', ''),
            'font_select': request.POST.get('font_select', ''),
            'font_color': request.POST.get('font_color', '#ffffff'),
            'subtitle_box_color': request.POST.get('subtitle_box_color', '#000000'),
            'font_size1': request.POST.get('font_size1', '22'),
            'box_radius': request.POST.get('box_radius', '26')
        }
            
        try:
            resolution = form_data['resolution']
            elevenlabs_api_key = form_data['elevenlabs_apikey']
            elevenlabs_voice_id = form_data['voiceid']
            
            # Only get Font if font_select is not empty
            font = None
            if form_data['font_select']:
                font = Font.objects.get(css_name=form_data['font_select'])
            else:
                raise Exception("Please select a font.")
                
            font_color = form_data['font_color']
            subtitle_box_color = form_data['subtitle_box_color']
            font_size = int(form_data['font_size1'])
            box_radius = form_data['box_radius']
            
            elv_handler = ElevenLabsHandler(api_key=elevenlabs_api_key, voice_id=elevenlabs_voice_id)
            try:
                elv_handler._verify_api_key()
            except:
                raise Exception("Invalid ElevenLabs API Key.")
            try:
                elv_handler._verify_voice_id()
            except:
                raise Exception("Invalid ElevenLabs Voice ID.")
            
            video = Video.objects.create(
                user=request.user,
                dimensions=resolution,
                elevenlabs_api_key=elevenlabs_api_key,
                voice_id=elevenlabs_voice_id,
                subtitle_font=font,
                font_color=font_color,
                subtitle_box_color=subtitle_box_color,
                font_size=font_size,
                box_roundness=box_radius
            )
            return redirect("scene_view", video_id=video.id)
        except Exception as e:
            error_message = f"{str(e)}"
            print(f"Error: {error_message}")
    
    # Pass form_data to the template
    return render(request, "home/preview.html", {
        "form": None, 
        "user_subscription": user_subscription, 
        "fonts": Font.objects.all(), 
        "error_message": error_message,
        "form_data": form_data  # Pass form data to the template
    })

@login_required(login_url='login')
@check_subscription_credits
def scene_view(request, video_id):
    """
    View to display details for a specific video based on its ID
    """
    try:
        video = Video.objects.get(id=video_id, user=request.user)
        
        if Subscription.objects.filter(user=request.user, status__in=['active', 'canceled', 'cancelling']).first().unused_credits <= 0:
            messages.warning(request, "This video is currently being processed or has encountered an error.")
            return redirect(request.META.get('HTTP_REFERER', 'preview'))
        
        if request.method == "POST":
            if 'videotextfile' in request.FILES:
                print("GOT FILE")
                uploaded_file = request.FILES['videotextfile']
                
                # Read content of uploaded file
                uploaded_content = uploaded_file.read().decode('utf-8')
                
                # Check if video already has text file content
                existing_content = ''
                if video.text_file:
                    video.text_file.seek(0)
                    existing_content = video.text_file.read().decode('utf-8')
                
                # Only save and generate clips if content is different
                if uploaded_content != existing_content:
                    print("Content changed, updating text file")
                    video.text_file = uploaded_file
                    video.save()
                    generate_clips_from_text_file(video)
                else:
                    print("Text file content unchanged, skipping update")
        # Get clips in sequence order
        clips = Clips.objects.filter(video=video).order_by('sequence')
        asset_folders = UserAsset.objects.filter(user=request.user, is_folder=True).order_by('filename')
        user_folder_structure = []
        for folder in asset_folders:
            user_folder_structure.append({
                'name': folder.filename,
                'assets': UserAsset.objects.filter(parent_folder=folder.key.rstrip('/'), user=request.user).order_by('filename')
            })
        
        # Get all subclips for this video
        subclip_objects = []
        for clip in clips:
            # Get subclips for each clip
            clip_subclips = Subclip.objects.filter(clip=clip)
            subclip_objects.extend(clip_subclips)
        
        context = {
            'video': video,
            'fonts': Font.objects.all(),
            'clips': clips,
            'subclips': subclip_objects,
            'asset_folders': user_folder_structure,
            'user_subscription': Subscription.objects.filter(user=request.user).first(),
        }
        
        return render(request, "home/scene.html", context)
    
    except Video.DoesNotExist:
        print("Video not found or you don't have permission to view it.")
        print(request, "Video not found or you don't have permission to view it.")
        return redirect('preview')
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        print(request, f"An error occurred: {str(e)}")
        return redirect('preview')


@login_required(login_url='login')
def download_video(request, video_id):
    """
    View to download the final video based on its ID
    """
    from apps.processors.services.video_processor import VideoProcessorService
    try:
        video = Video.objects.get(id=video_id, user=request.user)
        
        # Get all background music tracks for this video
        bg_music_queryset = BackgroundMusic.objects.filter(video=video)
        
        # Check if there's background music to apply
        if bg_music_queryset.exists():
            # Create background music version using the batch processing method
            video_processor = VideoProcessorService(video)
            
            # Apply all background music tracks at once
            print("------------------------------------------------------------------")
            print("------------------------------------------------------------------")
            result = video_processor.apply_background_music(bg_music_queryset)
            print("------------------------------------------------------------------")
            print("------------------------------------------------------------------")
            print("------------------------------------------------------------------")
            print("------------------------------------------------------------------")
            if result:
                print(f"Successfully applied {bg_music_queryset.count()} background music tracks to video {video.id}")
            else:
                print(f"Failed to apply background music to video {video.id}")
            
            # Apply background music to watermarked version
            result_watermark = video_processor.apply_all_background_music_watermark(bg_music_queryset)
            if result_watermark:
                print(f"Successfully applied {bg_music_queryset.count()} background music tracks to watermarked video {video.id}")
            else:
                print(f"Failed to apply background music to watermarked video {video.id}")
                
        else:
            # If no background music, use original outputs
            video.output_with_bg = video.output
            video.output_with_bg_watermark = video.output_with_watermark
            video.save()
            print(f"No background music found for video {video.id}, using original outputs")

        video_url = None
        video_url_preview = None
        
        if video.output_with_bg and video.output_with_bg.name:
            # Generate a signed URL that's valid for 2 hours
            if BackgroundMusic.objects.filter(video=video).exists():
                video_url = generate_signed_url_for_upload(video.output_with_bg.name, expires_in=7200)
                video_url_preview = generate_signed_url_for_upload(video.output_with_bg_watermark.name, expires_in=7200)
            else:
                video_url = generate_signed_url(video.output_with_bg.name, expires_in=7200)
                video_url_preview = generate_signed_url(video.output_with_bg_watermark.name, expires_in=7200)
            
            if video_url:
                print(f"Successfully generated signed URL for video: {video_url}")
            else:
                # Fall back to the regular URL if signed URL generation fails
                video_url = video.output_with_bg.url
                video_url_preview = video.output_with_bg_watermark.url
                print(f"Failed to generate signed URL, falling back to: {video_url}")
        else:
            print(f"Video has no output file. Video ID: {video.id}")
            return redirect("scene_view", video_id=video.id)

        return render(request, "home/download-scene.html", {
            'video': video,
            'user_subscription': Subscription.objects.filter(user=request.user).first(),
            'video_url': video_url,
            'video_url_preview': video_url_preview,
        })
    
    except Video.DoesNotExist:
        print(f"Video not found or user doesn't have permission. Video ID: {video_id}, User: {request.user}")
        return redirect('preview')
    except Exception as e:
        print(f"An error occurred while processing video {video_id}: {str(e)}")
        import traceback
        traceback.print_exc()  # This will print the full stack trace for debugging
        return redirect('preview')
    
@login_required(login_url='login')
@check_subscription_credits
def manage_subscription(request):
    plans = Plan.objects.all().order_by('price_per_month').exclude(name__icontains='free')  # Fetch all plans
    user_subscription = None

    if request.user.is_authenticated:
        user_subscription = Subscription.objects.filter(user=request.user).first()

    return render(request, "manage/manage-subscription.html", {"plans": plans, "user_subscription": user_subscription})
    




@login_required(login_url='login')
def stripe_billing_portal(request):
    """
    Redirect the user to Stripe Customer Portal to manage their billing info
    """
    try:
        # Add debugging
        print("Starting stripe_billing_portal function")        
        subscription = Subscription.objects.get(user=request.user, status__in=['active', 'canceling', 'canceled'])
        print(f"Found subscription: {subscription.id}, status: {subscription.status}")
        
        billing_info, created = BillingInfo.objects.get_or_create(user=request.user)
        print(f"Billing info - created: {created}, has customer ID: {bool(billing_info.stripe_customer_id)}")
        
        # If we don't have a customer ID in our billing info, try to get it from Stripe
        if not billing_info.stripe_customer_id and subscription.stripe_subscription_id:
            print(f"Looking up customer ID from subscription: {subscription.stripe_subscription_id}")
            try:
                # Get subscription details from Stripe to find customer ID
                stripe_subscription = stripe.Subscription.retrieve(subscription.stripe_subscription_id)
                if stripe_subscription and stripe_subscription.customer:
                    print(f"Found customer ID in Stripe: {stripe_subscription.customer}")
                    billing_info.stripe_customer_id = stripe_subscription.customer
                    billing_info.save()
                    print(f"Saved customer ID: {billing_info.stripe_customer_id}")
            except stripe.error.StripeError as e:
                print(f"Error retrieving subscription from Stripe: {str(e)}")
        
        # If we still don't have a customer ID, we need to create one
        if not billing_info.stripe_customer_id:
            print("Creating new Stripe customer")
            # Create a new customer in Stripe
            customer = stripe.Customer.create(
                email=request.user.email,
                name=f"{request.user.first_name} {request.user.last_name}".strip() or request.user.first_name,
                metadata={"user_id": str(request.user.id)}
            )
            billing_info.stripe_customer_id = customer.id
            billing_info.save()
            print(f"Created new customer: {customer.id}")
        
        # Now verify that this customer has the subscription assigned in Stripe
        try:
            stripe_subscriptions = stripe.Subscription.list(customer=billing_info.stripe_customer_id)
            found_subscription = False
            
            for stripe_sub in stripe_subscriptions.data:
                if stripe_sub.id == subscription.stripe_subscription_id:
                    found_subscription = True
                    break
            
            if not found_subscription and stripe_subscriptions.data:
                # Update our database with the subscription ID from Stripe
                subscription.stripe_subscription_id = stripe_subscriptions.data[0].id
                subscription.save()
                print(f"Updated subscription ID to match Stripe: {subscription.stripe_subscription_id}")
            elif not found_subscription:
                # This is a problem - customer exists but has no subscriptions in Stripe
                print("Warning: Customer exists in Stripe but has no subscriptions")
                
                # Try to retrieve the subscription from its ID
                try:
                    stripe_sub = stripe.Subscription.retrieve(subscription.stripe_subscription_id)
                    
                    # If the subscription exists but is assigned to a different customer,
                    # we need to update our records to match reality
                    if stripe_sub.customer != billing_info.stripe_customer_id:
                        print(f"Subscription belongs to different customer: {stripe_sub.customer}")
                        billing_info.stripe_customer_id = stripe_sub.customer
                        billing_info.save()
                except stripe.error.StripeError as e:
                    print(f"Error retrieving subscription: {str(e)}")
                    
        except stripe.error.StripeError as e:
            print(f"Error listing customer subscriptions: {str(e)}")
        
        print(f"Creating portal session for customer: {billing_info.stripe_customer_id}")
        # Create Stripe billing portal session
        try:
            # Try creating a session with flow data
            session = stripe.billing_portal.Session.create(
                customer=billing_info.stripe_customer_id,
                return_url=request.build_absolute_uri(reverse('manage_subscription')),
                flow_data={
                    'type': 'subscription_cancel',
                    'subscription_cancel': {
                        'subscription': subscription.stripe_subscription_id,
                    }
                }
            )
        except stripe.error.StripeError:
            # Fall back to basic session if flow data fails
            session = stripe.billing_portal.Session.create(
                customer=billing_info.stripe_customer_id,
                return_url=request.build_absolute_uri(reverse('manage_subscription'))
            )
        
        print(f"Redirecting to portal URL: {session.url}")
        # Redirect to the portal
        return redirect(session.url)
        
    except Subscription.DoesNotExist:
        print("Error: No active subscription found")
        print(request, "You need an active subscription to access billing information.")
        return redirect('preview')  
    except stripe.error.StripeError as e:
        print(f"Stripe error: {str(e)}")
        print(request, f"Stripe error: {str(e)}")
        return redirect('preview')  
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        print(request, f"An error occurred: {str(e)}")
        return redirect('preview')


@login_required(login_url='login')
def purchase_credits(request):
    """View to handle purchasing additional credits with payment"""
    try:
        # Get credits amount from form
        credits_amount = int(request.POST.get('credits_number', 10))
        
        # Validate input
        if credits_amount < 1:
            print(request, "Please enter a valid number of credits (minimum 1).")
            return redirect('manage_subscription')
            
        # Get the current subscription
        subscription = Subscription.objects.get(user=request.user, status='active')
        
        # Get the plan
        plan = subscription.plan
        
        credit_price = plan.credits_price
        # Calculate total price in cents
        total_price_cents = int(credit_price * credits_amount * 100)
        
        # Create metadata for the checkout session
        metadata = {
            'purchase_type': 'credits',
            'user_id': str(request.user.id),
            'credits_amount': str(credits_amount),
            'subscription_id': str(subscription.id)
        }
        
        # Get or create customer info
        billing_info, created = BillingInfo.objects.get_or_create(user=request.user)
        
        # Create checkout session
        checkout_params = {
            'payment_method_types': ['card'],
            'line_items': [{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': f'{credits_amount} Extra Video Credits',
                        'description': f'Additional video processing credits for your {plan.name} subscription'
                    },
                    'unit_amount': total_price_cents,
                },
                'quantity': 1,
            }],
            'mode': 'payment',
            'success_url': request.build_absolute_uri(reverse('credits_success')) + '?session_id={CHECKOUT_SESSION_ID}',
            'cancel_url': request.build_absolute_uri(reverse('manage_subscription')),
            'metadata': metadata
        }
        
        # Use existing customer if we have one
        if billing_info.stripe_customer_id:
            checkout_params['customer'] = billing_info.stripe_customer_id
        else:
            checkout_params['customer_email'] = request.user.email
        
        # Create the checkout session
        checkout_session = stripe.checkout.Session.create(**checkout_params)
        
        # Redirect to Stripe checkout
        return redirect(checkout_session.url)
        
    except Subscription.DoesNotExist:
        print(request, "No active subscription found.")
        return redirect('manage_subscription')
    except ValueError:
        print(request, "Please enter a valid number of credits.")
        return redirect('manage_subscription')
    except Exception as e:
        print(request, f"Error adding credits: {str(e)}")
        return redirect('manage_subscription')

CREDITS_PRICE_ID="price_1RGKTgB13B1g6neBlqrG27V7"

@login_required(login_url='login')
def credits_success(request):
    """Handle successful additional credits purchase"""
    session_id = request.GET.get('session_id')
    
    if not session_id:
        print(request, "No session ID provided.")
        return redirect('manage_subscription')
        
    try:
        # Retrieve the checkout session
        session = stripe.checkout.Session.retrieve(session_id)
        
        # Check payment status
        if session.payment_status != 'paid':
            print(request, "Payment not completed.")
            return redirect('manage_subscription')
            
        # Get metadata
        user_id = session.metadata.get('user_id')
        credits_amount = int(session.metadata.get('credits_amount', 0))
        subscription_id = session.metadata.get('subscription_id')
        
        # Verify this is for the current user
        if str(request.user.id) != user_id:
            print(request, "Session user ID does not match current user.")
            return redirect('manage_subscription')
            
        # Add the credits to the subscription
        # subscription = Subscription.objects.get(id=subscription_id)
        # subscription.unused_credits += credits_amount
        # subscription.save()
        
        print(request, f"Successfully added {credits_amount} credits to your account!")
        
    except stripe.error.StripeError as e:
        print(request, f"Stripe error: {str(e)}")
    except Subscription.DoesNotExist:
        print(request, "Subscription not found.")
    except Exception as e:
        print(request, f"Error processing credits: {str(e)}")
        
    return redirect('manage_subscription')


@csrf_exempt
def stripe_webhook(request):
    """Webhook handler for Stripe events"""
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    
    print(f"Webhook received: {request.META.get('HTTP_STRIPE_EVENT_TYPE', 'Unknown event type')}")
    
    # For development without webhook signature
    if settings.DEBUG and not settings.STRIPE_WEBHOOK_SECRET:
        try:
            event = json.loads(payload)
            event_type = event['type']
            event_data = event['data']['object']
        except (ValueError, KeyError) as e:
            print(f"Error parsing webhook JSON: {e}")
            return HttpResponse(status=400)
    else:
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
            event_type = event['type']
            event_data = event['data']['object']
        except ValueError as e:
            print("Invalid payload:", e)
            return HttpResponse(status=400)
        except stripe.error.SignatureVerificationError as e:
            print("Invalid signature:", e)
            return HttpResponse(status=400)
    
    print(f"Processing event type: {event_type}")
    
    # Handle the event
    if event_type == 'checkout.session.completed':
        handle_checkout_completed(event_data)
        
    elif event_type == 'customer.subscription.created':
        handle_subscription_created(event_data)
        
    elif event_type == 'customer.subscription.updated':
        handle_subscription_updated(event_data)
        
    elif event_type == 'customer.subscription.deleted':
        handle_subscription_deleted(event_data)
        
    elif event_type == 'invoice.payment_succeeded':
        handle_invoice_payment_succeeded(event_data)
        
    elif event_type == 'invoice.payment_failed':
        handle_invoice_payment_failed(event_data)
    
    return HttpResponse(status=200)

def handle_checkout_completed(session):
    """Handle checkout.session.completed event"""
    print(f"Checkout completed - Session ID: {session.id}")
    print(f"Metadata: {session.get('metadata', {})}")
    
    # Extract metadata
    metadata = session.get('metadata', {})
    
    # Check if this is a payment-first flow
    if metadata and metadata.get('payment_first') == 'true':
        print("Processing payment-first flow")
        
        # Get IDs from the session
        temp_id = metadata.get('temp_id')
        plan_id = metadata.get('plan_id')
        customer_id = session.get('customer')
        subscription_id = session.get('subscription')
        
        print(f"Payment-first flow data: temp_id={temp_id}, plan_id={plan_id}")
        print(f"Customer: {customer_id}, Subscription: {subscription_id}")
        
        # Store the session info in our temporary table
        try:
            from django.utils import timezone
            import datetime
            
            # Calculate expiration time (24 hours from now)
            expires_at = timezone.now() + datetime.timedelta(hours=24)
            
            # Create or update the temporary subscription record
            TempSubscription.objects.update_or_create(
                temp_id=temp_id,
                defaults={
                    'stripe_customer_id': customer_id,
                    'stripe_subscription_id': subscription_id,
                    'plan_id': int(plan_id),
                    'session_id': session.id,
                    'expires_at': expires_at
                }
            )
            print(f"Stored payment info for temp_id: {temp_id}")
        except Exception as e:
            print(f"Error storing temp subscription info: {str(e)}")
    
    # Handle credits purchase
    elif metadata and metadata.get('purchase_type') == 'credits':
        handle_credits_purchase(session, metadata)
    
    # Handle plan upgrade
    elif metadata and metadata.get('is_upgrade') == 'true':
        handle_plan_upgrade(session, metadata)
    
    # Handle new subscription
    elif session.get('subscription'):
        handle_new_subscription(session, metadata)

def handle_subscription_created(subscription):
    """Handle customer.subscription.created event"""
    print(f"Subscription created: {subscription.id}")
    # Implementation for subscription creation event

def handle_subscription_updated(subscription):
    """Handle customer.subscription.updated event"""
    print(f"Subscription updated: {subscription.id}")
    
    try:
        # Find the subscription in our database
        db_subscription = Subscription.objects.filter(stripe_subscription_id=subscription.id).first()
        
        if db_subscription:
            # Update subscription status
            stripe_status = subscription.status
            if stripe_status == 'active' and db_subscription.status != 'active':
                db_subscription.status = 'active'
                db_subscription.save()
            elif stripe_status == 'canceled' and db_subscription.status != 'canceled':
                db_subscription.status = 'canceled'
                db_subscription.save()
            elif stripe_status == 'past_due' and db_subscription.status != 'past_due':
                db_subscription.status = 'past_due'
                db_subscription.save()
            
            # Check if subscription is set to cancel at period end
            cancel_at_period_end = getattr(subscription, 'cancel_at_period_end', False)
            if cancel_at_period_end and db_subscription.status != 'canceling':
                db_subscription.status = 'canceled'
                db_subscription.save()
            
            # Update period end date
            if hasattr(subscription, 'current_period_end') and subscription.current_period_end:
                import datetime
                from django.utils import timezone
                
                period_end = datetime.datetime.fromtimestamp(
                    subscription.current_period_end, 
                    tz=timezone.utc
                )
                db_subscription.current_period_end = period_end
                db_subscription.save()
                
                print(f"Updated subscription {db_subscription.id} period end to {period_end}")
    except Exception as e:
        print(f"Error processing subscription update: {str(e)}")

def handle_subscription_deleted(subscription):
    """Handle customer.subscription.deleted event"""
    print(f"Subscription deleted: {subscription.id}")
    
    try:
        # Find and update subscription in database
        db_subscription = Subscription.objects.filter(stripe_subscription_id=subscription.id).first()
        if db_subscription:
            db_subscription.status = 'canceled'
            db_subscription.save()
            print(f"Marked subscription {db_subscription.id} as canceled")
    except Exception as e:
        print(f"Error processing subscription deletion: {str(e)}")

def handle_invoice_payment_succeeded(invoice):
    """Handle invoice.payment_succeeded event"""
    print(f"Invoice payment succeeded: {invoice.id}")
    
    subscription_id = invoice.get('subscription')
    if not subscription_id:
        return
    
    try:
        # Find the subscription in our database
        subscription = Subscription.objects.filter(stripe_subscription_id=subscription_id).first()
        
        if subscription:
            # This is a recurring payment - add new credits
            if invoice.get('billing_reason') == 'subscription_cycle':
                subscription.unused_credits += subscription.plan.ad_variations_per_month
                
                # Update period end date
                stripe_subscription = stripe.Subscription.retrieve(subscription_id)
                if stripe_subscription and stripe_subscription.current_period_end:
                    import datetime
                    from django.utils import timezone
                    
                    period_end = datetime.datetime.fromtimestamp(
                        stripe_subscription.current_period_end, 
                        tz=timezone.utc
                    )
                    subscription.current_period_end = period_end
                
                subscription.save()
                print(f"Added {subscription.plan.ad_variations_per_month} credits to subscription {subscription.id}")
    except Exception as e:
        print(f"Error processing invoice payment: {str(e)}")

def handle_invoice_payment_failed(invoice):
    """Handle invoice.payment_failed event"""
    print(f"Invoice payment failed: {invoice.id}")
    
    subscription_id = invoice.get('subscription')
    if not subscription_id:
        return
    
    try:
        # Find the subscription in our database
        subscription = Subscription.objects.filter(stripe_subscription_id=subscription_id).first()
        
        if subscription:
            # Update status to past_due
            subscription.status = 'past_due'
            subscription.save()
            print(f"Marked subscription {subscription.id} as past_due")
    except Exception as e:
        print(f"Error processing invoice payment failure: {str(e)}")

def handle_credits_purchase(session, metadata):
    """Handle credits purchase checkout"""
    user_id = metadata.get('user_id')
    credits_amount = int(metadata.get('credits_amount', 0))
    subscription_id = metadata.get('subscription_id')
    customer_id = session.get('customer')
    
    print(f"Processing credits purchase - User ID: {user_id}, Credits: {credits_amount}")
    
    try:
        # Get the user
        user = User.objects.get(id=user_id)
        
        # Get the subscription
        subscription = Subscription.objects.get(id=subscription_id)
        
        # Add the credits
        subscription.unused_credits += credits_amount
        subscription.save()
        
        # Update billing info with customer ID if needed
        if customer_id:
            billing_info, created = BillingInfo.objects.get_or_create(user=user)
            if not billing_info.stripe_customer_id:
                billing_info.stripe_customer_id = customer_id
                billing_info.save()
        
        print(f"Successfully added {credits_amount} credits to user {user.first_name}")
    except User.DoesNotExist:
        print(f"Error: User with ID {user_id} not found")
    except Subscription.DoesNotExist:
        print(f"Error: Subscription with ID {subscription_id} not found")
    except Exception as e:
        print(f"Error processing credits: {str(e)}")



def handle_plan_upgrade(session, metadata):
    """Handle plan upgrade checkout"""
    user_id = metadata.get('user_id')
    plan_id = metadata.get('plan_id')
    old_subscription_id = metadata.get('old_subscription_id')
    new_subscription_id = session.get('subscription')
    customer_id = session.get('customer')
    
    print(f"Processing plan change - User ID: {user_id}, Old Sub: {old_subscription_id}, New Sub: {new_subscription_id}")
    
    try:
        # Get the user and plan
        user = User.objects.get(id=user_id)
        plan = Plan.objects.get(id=plan_id)
        
        print(f"Upgrading user {user.first_name} from {old_subscription_id} to {new_subscription_id}")
        print(f"New plan: {plan.name}")
        
        # Update billing info with customer ID if needed
        if customer_id:
            billing_info, created = BillingInfo.objects.get_or_create(user=user)
            if not billing_info.stripe_customer_id:
                billing_info.stripe_customer_id = customer_id
                billing_info.save()
        
        # Get current subscription to preserve remaining credits
        try:
            current_subscription = Subscription.objects.get(user=user)
            remaining_credits = current_subscription.unused_credits
            old_plan = current_subscription.plan
            
            print(f"Existing subscription found with {remaining_credits} credits remaining")
            print(f"Old plan: {old_plan.name}, New plan: {plan.name}")
            
            # Cancel the old subscription in Stripe if it's different from the new one
            if old_subscription_id and old_subscription_id != new_subscription_id:
                try:
                    print(f"Canceling old subscription in Stripe: {old_subscription_id}")
                    stripe.Subscription.delete(old_subscription_id)
                    print(f"Successfully canceled old subscription: {old_subscription_id}")
                except stripe.error.StripeError as e:
                    print(f"Error canceling old subscription: {str(e)}")
                    # Continue anyway - the important part is updating our database
            
            # Update subscription with new plan but keep remaining credits
            current_subscription.plan = plan
            current_subscription.status = 'active'
            current_subscription.stripe_subscription_id = new_subscription_id
            
            # Add new plan's credits to remaining credits
            current_subscription.unused_credits = remaining_credits + plan.ad_variations_per_month
            
            # Get period end date
            # Get period end date from Stripe subscription
            try:
                stripe_subscription = stripe.Subscription.retrieve(new_subscription_id)
                if stripe_subscription and stripe_subscription.current_period_end:
                    # Convert Stripe timestamp to Django datetime with UTC timezone
                    period_end = timezone.datetime.fromtimestamp(
                        stripe_subscription.current_period_end,
                        tz=timezone.utc
                    )
                    current_subscription.current_period_end = period_end
                    print(f"Updated period end date from Stripe: {period_end}")
                else:
                    # Fallback: 30 days from now if Stripe data is unavailable
                    period_end = timezone.now() + timedelta(days=30)
                    current_subscription.current_period_end = period_end
                    print(f"Fallback period end date: {period_end}")
            except Exception as e:
                print(f"Error getting period end date: {str(e)}")
                # Fallback on error
                period_end = timezone.now() + timedelta(days=30)
                current_subscription.current_period_end = period_end
                print(f"Error fallback period end date: {period_end}")
            
            # Save the updated subscription
            current_subscription.save()
            
            print(f"Successfully updated subscription for {user.first_name} to {plan.name}")
            print(f"New credits total: {current_subscription.unused_credits}")
            
        except Subscription.DoesNotExist:
            # If no existing subscription found, create a new one
            print(f"No existing subscription found, creating new one")
            
            subscription = Subscription.objects.create(
                user=user,
                plan=plan,
                status='active',
                stripe_subscription_id=new_subscription_id,
                unused_credits=plan.ad_variations_per_month
            )
            
            print(f"Created new subscription for {user.first_name} to {plan.name}")
        
    except User.DoesNotExist:
        print(f"Error: User with ID {user_id} not found")
    except Plan.DoesNotExist:
        print(f"Error: Plan with ID {plan_id} not found")
    except Exception as e:
        print(f"Error processing plan change: {str(e)}")
        import traceback
        traceback.print_exc()



def handle_new_subscription(session, metadata):
    """Handle new subscription checkout"""
    subscription_id = session.get('subscription')
    customer_id = session.get('customer')
    plan_id = metadata.get('plan_id')
    user_id = metadata.get('user_id')
    
    print(f"New subscription - Sub ID: {subscription_id}, Customer ID: {customer_id}")
    
    try:
        # Find the user either by ID from metadata or by email
        user = None
        if user_id:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                print(f"User with ID {user_id} not found")
        
        if not user and session.get('customer_email'):
            try:
                user = User.objects.get(email=session.get('customer_email'))
            except User.DoesNotExist:
                print(f"User with email {session.get('customer_email')} not found")
        
        if user and subscription_id and plan_id:
            # Get the plan
            plan = Plan.objects.get(id=plan_id)
            
            # Update billing info with customer ID
            if customer_id:
                billing_info, created = BillingInfo.objects.get_or_create(user=user)
                if not billing_info.stripe_customer_id:
                    billing_info.stripe_customer_id = customer_id
                    billing_info.save()
            
            # Get period end date
            # Get period end date from Stripe subscription
            period_end = None
            try:
                stripe_subscription = stripe.Subscription.retrieve(subscription_id)
                if stripe_subscription and stripe_subscription.current_period_end:
                    # Convert Stripe timestamp to Django datetime with UTC timezone
                    period_end = timezone.datetime.fromtimestamp(
                        stripe_subscription.current_period_end, 
                        tz=timezone.utc
                    )
                    print(f"Period end from Stripe: {period_end}")
                else:
                    # Fallback: 30 days from now if Stripe data is unavailable
                    period_end = timezone.now() + timedelta(days=30)
                    print(f"Fallback period end: {period_end}")
            except Exception as e:
                print(f"Error getting subscription details: {str(e)}")
                # Fallback on error
                period_end = timezone.now() + timedelta(days=30)
                print(f"Error fallback period end: {period_end}")
            
            # Create or update the subscription
            subscription, created = Subscription.objects.update_or_create(
                user=user,
                defaults={
                    'plan': plan,
                    'status': 'active',
                    'stripe_subscription_id': subscription_id,
                    'unused_credits': plan.ad_variations_per_month,
                    'current_period_end': period_end
                }
            )
            
            print(f"{'Created' if created else 'Updated'} subscription for {user.first_name} to {plan.name}")
    except Exception as e:
        print(f"Error processing new subscription: {str(e)}")


@login_required(login_url='login')
@csrf_exempt
def upgrade_plan(request, plan_id):
    """Handle upgrading to a new subscription plan"""
    try:
        # Get the user's current subscription
        current_subscription = Subscription.objects.get(user=request.user)
        
        # Get the new plan
        new_plan = Plan.objects.get(id=plan_id)
        metadata = {
            'is_upgrade': 'true',
            'user_id': str(request.user.id),
            'plan_id': str(plan_id),
            'old_subscription_id': current_subscription.stripe_subscription_id,
        }
        
        # Don't process if it's the same plan
        if current_subscription and current_subscription.stripe_subscription_id and not current_subscription.status in ['canceled', 'cancelling']:
            # This is an upgrade/downgrade
            print(f"User has existing subscription to {current_subscription.plan.name}")
            metadata["is_upgrade"] = "true"
            metadata["old_subscription_id"] = current_subscription.stripe_subscription_id
            
            # Check if this is a downgrade (new plan price is lower than current plan)
            is_downgrade = new_plan.price_per_month < current_subscription.plan.price_per_month
            
            if is_downgrade:
                # Handle downgrade: Update the subscription directly without charging
                print(f"Downgrading from {current_subscription.plan.name} to {new_plan.name}")
                
                try:
                    # Update the subscription in Stripe to the new plan
                    # This changes the subscription at the end of the current billing period
                    stripe_subscription = stripe.Subscription.retrieve(
                        current_subscription.stripe_subscription_id
                    )
                    
                    # Update to the new price, but apply at period end to avoid immediate charges
                    stripe.Subscription.modify(
                        current_subscription.stripe_subscription_id,
                        items=[{
                            'id': stripe_subscription['items']['data'][0]['id'],
                            'price': new_plan.stripe_price_id,
                        }],
                        proration_behavior='none',  # Don't prorate (don't charge or credit immediately)
                        cancel_at_period_end=False,  # Don't cancel, just change the plan
                    )
                    
                    # Update the subscription in our database
                    current_subscription.plan = new_plan
                    current_subscription.save()
                    
                    messages.success(request, f"Your subscription will be downgraded to {new_plan.name} at the end of your current billing period.")
                    return redirect('manage_subscription')
                    
                except stripe.error.StripeError as e:
                    print(f"Stripe error during downgrade: {str(e)}")
                    messages.error(request, f"Error processing downgrade: {str(e)}")
                    return redirect("manage_subscription")

        if current_subscription.plan.id == new_plan.id and current_subscription.status not in ['canceled', 'cancelling']:
            messages.info(request, f"You are already subscribed to the {new_plan.name} plan.")
            return redirect('manage_subscription')
        
        # Create metadata for Stripe

        # Get billing info for the customer ID
        billing_info, created = BillingInfo.objects.get_or_create(user=request.user)
        
        # Create the checkout session
        checkout_params = {
            'payment_method_types': ['card'],
            'line_items': [{
                'price': new_plan.stripe_price_id,
                'quantity': 1,
            }],
            'mode': 'subscription',
            'success_url': request.build_absolute_uri(reverse('manage_subscription')) + '?upgrade_success=true',
            'cancel_url': request.build_absolute_uri(reverse('manage_subscription')),
            'metadata': metadata
        }
        
        # Use existing customer if we have one
        if billing_info.stripe_customer_id:
            checkout_params['customer'] = billing_info.stripe_customer_id
        else:
            checkout_params['customer_email'] = request.user.email
        
        # Create the checkout session
        checkout_session = stripe.checkout.Session.create(**checkout_params)
        
        # Redirect to Stripe checkout
        return redirect(checkout_session.url)
        
    except Subscription.DoesNotExist:
        print(request, "You need an active subscription to upgrade plans.")
        return redirect('subscribe', plan_id=plan_id)
    except Plan.DoesNotExist:
        print(request, "The selected plan does not exist.")
        return redirect('manage_subscription')
    except Exception as e:
        print(request, f"Error upgrading plan: {str(e)}")
        return redirect('manage_subscription')



@login_required(login_url='login')
def asset_view(request):
    """View for asset library"""
    if request.method == 'POST':
        if 'zip_file' in request.FILES:
            zip_file = request.FILES['zip_file']
            try:
                # Use the extract_and_upload_zip function from s3_service
                from apps.core.services.s3_service import extract_and_upload_zip
                created_assets = extract_and_upload_zip(request.user, zip_file)
                
                if created_assets:
                    print(request, f'Successfully uploaded {len(created_assets)} assets')
                else:
                    messages.warning(request, 'No assets were found in the uploaded ZIP file')
                    
            except Exception as e:
                print(request, f'Error uploading ZIP file: {str(e)}')
                print(f'ZIP upload error: {str(e)}')
    
    # Get all user assets
    user_folders = UserAsset.objects.filter(user=request.user, is_folder=True)
    user_files = UserAsset.objects.filter(user=request.user, is_folder=False)
    
    # Organize assets into folders and their children
    folders = {}
    root_assets = []
    
    # First, identify all folders
    for folder in user_folders:
        folders[folder.key] = {
            'folder': folder,
            'children': []
        }
    
    # Identify files that belong to specific folders
    for file in user_files:
        # If the file has a parent folder, add it to that folder's children
        if file.parent_folder:
            # Clean the parent folder key to ensure consistent matching
            parent_key = file.parent_folder
            if not parent_key.endswith('/'):
                parent_key += '/'
                
            # Find the folder this file belongs to
            for folder_key in folders:
                if folder_key == parent_key or folder_key.rstrip('/') == file.parent_folder:
                    folders[folder_key]['children'].append(file)
                    break
            else:
                # If no folder found, add to root assets (this shouldn't typically happen)
                root_assets.append(file)
        else:
            # No parent folder, so it's a root asset
            root_assets.append(file)
    
    # Prepare the hierarchical structure for the template
    folder_structure = []
    
    # Add folders with their children
    for folder_key, folder_info in folders.items():
        # Get all files directly under this folder
        children = [child for child in user_files if 
                   (child.parent_folder == folder_key.rstrip('/') or 
                    child.parent_folder == folder_key)]
        
        folder_structure.append({
            'folder': folder_info['folder'],
            'children': sorted(children, key=lambda x: x.filename.lower())
        })
    
    # Sort folders by name
    folder_structure.sort(key=lambda x: x['folder'].filename.lower())
    
    # Sort root-level files
    root_assets.sort(key=lambda x: x.filename.lower())
    
    return render(request, "manage/asset-library.html", {
        "folder_structure": folder_structure,
        "root_assets": root_assets,
        "user_subscription": Subscription.objects.filter(user=request.user).first(),
    })

@login_required(login_url='login')
@csrf_exempt
def delete_asset(request, asset_id):
    """Delete an asset or folder and its contents"""
    try:
        # Get the asset
        asset = get_object_or_404(UserAsset, id=asset_id, user=request.user)
        
        # Log asset details
        print(f"Attempting to delete asset: ID={asset_id}, Key={asset.key}, IsFolder={asset.is_folder}")
        
        # Import S3 deletion functions
        from apps.core.services.s3_service import delete_from_s3, delete_folder_from_s3
        from django.db import transaction
        
        if asset.is_folder:
            # Delete the folder and its contents from S3
            success = delete_folder_from_s3(asset.key)
            print(f"S3 folder deletion result for {asset.key}: {success}")
            
            # Delete all child assets from database
            with transaction.atomic():
                # Count assets to be deleted for logging
                assets_to_delete = UserAsset.objects.filter(
                    user=request.user,
                    key__startswith=asset.key
                ).count()
                
                print(f"Deleting {assets_to_delete} database records for folder {asset.key}")
                
                # Perform the deletion
                deletion_count = UserAsset.objects.filter(
                    user=request.user,
                    key__startswith=asset.key
                ).delete()
                
                print(f"Database deletion result: {deletion_count}")
        else:
            # Delete single file from S3
            success = delete_from_s3(asset.key)
            print(f"S3 file deletion result for {asset.key}: {success}")
            
            if success:
                print(f"Deleting database record for file {asset.key}")
                asset.delete()
                print(f"Database record deleted for file {asset.key}")
        
        if success:
            print(request, f"Successfully deleted {asset.filename}")
            return JsonResponse({'success': True, 'message': f"Successfully deleted {asset.filename}"})
        else:
            print(request, f"Failed to delete {asset.filename} from storage")
            return JsonResponse({'success': False, 'error': f"Failed to delete {asset.filename} from storage"}, status=500)
        
    except Exception as e:
        print(f"Error in delete_asset view: {str(e)}")
        import traceback
        traceback.print_exc()
        print(request, f"Error deleting asset: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required(login_url='login')
@csrf_exempt
def rename_asset(request, asset_id):
    """Rename an asset or folder"""
    try:
        if request.method != 'POST':
            return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
        
        # Check if the request is a form submission or JSON
        if request.content_type and 'application/json' in request.content_type:
            # Handle JSON request (from fetch API)
            try:
                data = json.loads(request.body)
                new_name = data.get('new_name')
            except json.JSONDecodeError:
                print("ERROR: Invalid JSON in request body")
                return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
        else:
            # Handle form submission
            new_name = request.POST.get('new_name')
        
        print(f"DEBUG: Received rename request for asset ID {asset_id}, new name: {new_name}")
        
        if not new_name or not new_name.strip():
            print("DEBUG: New name is empty")
            if request.content_type and 'application/json' in request.content_type:
                return JsonResponse({'success': False, 'error': 'New name cannot be empty'}, status=400)
            else:
                print(request, "New name cannot be empty")
                return redirect('asset_library')
        
        # Get the asset
        asset = get_object_or_404(UserAsset, id=asset_id, user=request.user)
        print(f"DEBUG: Found asset: ID={asset_id}, Key={asset.key}, old name={asset.filename}")
        
        # Import S3 service functions
        from apps.core.services.s3_service import rename_in_s3
        from django.db import transaction
        
        # Store the old_key and filename for logging
        old_key = asset.key
        old_filename = asset.filename
        
        print(f"DEBUG: Starting rename transaction for {old_key} to {new_name}")
        
        # Rename the asset both in S3 and the database
        with transaction.atomic():
            # Update S3 key (path) - maintain the same directory structure
            if asset.is_folder:
                # For folders we need to update all child assets too
                folder_prefix = asset.key
                if not folder_prefix.endswith('/'):
                    folder_prefix += '/'
                    
                # Calculate the new folder key
                parent_path = os.path.dirname(old_key.rstrip('/'))
                if parent_path:
                    new_key = parent_path + '/' + new_name + '/'
                else:
                    new_key = new_name + '/'
                
                print(f"DEBUG: Renaming folder from {old_key} to {new_key}")
                
                # Rename all assets in the folder
                child_assets = UserAsset.objects.filter(
                    user=request.user, 
                    key__startswith=folder_prefix
                ).exclude(id=asset_id)
                
                print(f"DEBUG: Found {child_assets.count()} child assets to update")
                
                for child in child_assets:
                    child_new_key = child.key.replace(folder_prefix, new_key, 1)
                    print(f"DEBUG: Renaming child {child.key} to {child_new_key}")
                    
                    # Update S3
                    success = rename_in_s3(child.key, child_new_key)
                    print(f"DEBUG: S3 rename result for child: {success}")
                    
                    # Update the child's key and parent folder
                    child.key = child_new_key
                    child.parent_folder = os.path.dirname(child_new_key.rstrip('/'))
                    child.save()
                    print(f"DEBUG: Updated child in database: {child.key}, parent_folder={child.parent_folder}")
                
                # Update folder itself
                success = rename_in_s3(old_key, new_key)
                print(f"DEBUG: S3 rename result for folder: {success}")
                
                asset.key = new_key
                asset.filename = new_name
                asset.save()
                print(f"DEBUG: Updated folder in database: {asset.key}, filename={asset.filename}")
                
            else:
                # For files, rename just the file
                parent_path = os.path.dirname(old_key)
                new_key = parent_path + '/' + new_name if parent_path else new_name
                
                print(f"DEBUG: Renaming file from {old_key} to {new_key}")
                
                # Update S3
                success = rename_in_s3(old_key, new_key)
                print(f"DEBUG: S3 rename result for file: {success}")
                
                # Update database
                asset.key = new_key
                asset.filename = new_name
                asset.save()
                print(f"DEBUG: Updated file in database: {asset.key}, filename={asset.filename}")
        
        success_message = f"Successfully renamed {old_filename} to {new_name}"
        print(f"DEBUG: {success_message}")
        
        # Return success response based on request type
        if request.content_type and 'application/json' in request.content_type:
            return JsonResponse({
                'success': True, 
                'message': success_message,
                'old_key': old_key,
                'new_key': asset.key,
                'id': asset.id,
                'is_folder': asset.is_folder
            })
        else:
            print(request, success_message)
            return redirect('asset_library')
        
    except Exception as e:
        print(f"ERROR in rename_asset view: {str(e)}")
        import traceback
        traceback.print_exc()
        
        if request.content_type and 'application/json' in request.content_type:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
        else:
            print(request, f"Error renaming asset: {str(e)}")
            return redirect('asset_library')

@csrf_exempt
def register(request):
    if request.method == "POST":
        username = request.POST["username"]
        password = request.POST["password"]
        confirm_password = request.POST["confirm_password"]

        if password != confirm_password:
            print(request, "Passwords do not match.")
            return redirect("register")

        if User.objects.filter(username=username).exists():
            print(request, "Username already taken.")
            return redirect("register")

        user = User.objects.create_user(first_name=username, password=password)
        user.save()
        print(request, "Registration successful. Please log in.")
        return redirect("login")

    return render(request, "register.html")



def register_view(request):
    error_message = None
    if request.method == "POST":
        print("Got Register")
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")

        if not all([username, email, password, confirm_password]):
            error_message = "All fields are required."
            return render(request, "accounts/signup.html", {'error_message': error_message})

        if password != confirm_password:
            error_message = "Passwords do not match."
            return render(request, "accounts/signup.html", {'error_message': error_message})

        # if User.objects.filter(username=username).exists():
        #     error_message = "Username already taken."
        #     return render(request, "accounts/signup.html", {'error_message': error_message})

        if User.objects.filter(email=email).exists():
            error_message = "Email already registered."
            return render(request, "accounts/signup.html", {'error_message': error_message})

        try:
            # Create user
            user = User.objects.create_user(
                first_name=username,
                username= f"{email}_{username}",
                email=email,
                password=password,
                is_active=False  # User will be inactive until email verification
            )

            # Generate verification token
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            
            # Build verification URL
            verification_url = request.build_absolute_uri(
                reverse('verify-email', kwargs={'uidb64': uid, 'token': token})
            )

            # Send verification email
            context = {
                'user': user,
                'verification_url': verification_url,
                'site_name': 'VideoCrafter.io',
                'logo_url': request.build_absolute_uri('/static/images/logo.png')
            }
            email_subject = "Verify Your Email Address"
            email_body = render_to_string('auth/email_template.html', context)
            print(request.build_absolute_uri('/static/images/logo.png'))
            send_mail(
                email_subject,
                "Please verify your email address to complete registration",
                settings.DEFAULT_FROM_EMAIL,
                [email],
                html_message=email_body,
                fail_silently=False,
            )

            return render(request, "accounts/verify-sent.html")

        except Exception as e:
            error_message = f"Registration failed: {str(e)}"
            print(error_message)
            return render(request, "accounts/signup.html", {'error_message': error_message})

    return render(request, "accounts/signup.html")

def verify_email(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)

        if default_token_generator.check_token(user, token):
            user.is_active = True
            Subscription.objects.create(
                user=user,
                plan=Plan.objects.filter(name__icontains='free').first(),
                unused_credits=1
                )
            user.save()
            login(request, user)
            print(request, "Email verified successfully. Welcome!")
            print(request, "Email verified successfully. Welcome!")
            return redirect('preview')
        else:
            print(request, "Invalid verification link")
            return redirect('register')

    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        print(request, "Invalid verification link")
        print(request, "Invalid verification link")
        return redirect('register')




def password_reset_request(request):
    if request.method == "POST":
        email = request.POST.get('email')
        
        # Check if the email exists in the database
        try:
            user = User.objects.get(email=email)
            
            # Generate a token for the user
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            
            # Build the reset URL
            reset_url = request.build_absolute_uri(
                reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
            )
            
            # Create the email context
            context = {
                'user': user,
                'reset_url': reset_url,
                'site_name': 'Video Creator',
                'logo_url': request.build_absolute_uri('/static/images/logo.png')
            }
            
            # Render the email template
            email_subject = "Password Reset Request"
            email_body = render_to_string('auth/password_reset_template.html', context)
            
            # Send the email
            send_mail(
                email_subject,
                "Please use this link to reset your password",
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                html_message=email_body,
                fail_silently=False,
            )
            
            # Show success message
            print(request, "Password reset link has been sent to your email address.")
            return render(request, 'accounts/reset-done.html')

            
        except User.DoesNotExist:
            # Don't reveal if the email exists for security
            print(request, "Password reset link has been sent to your email address if it exists in our system.")
            return redirect('login')
    
    return render(request, 'accounts/password-reset.html')




def password_reset_confirm(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    
    # Check if the token is valid
    if user is not None and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            # Process the password reset
            password1 = request.POST.get('password1')
            password2 = request.POST.get('password2')
            
            if not password1 or not password2:
                print(request, "Both password fields are required")
                return render(request, 'accounts/password_reset_confirm.html', {'validlink': True})
            
            if password1 != password2:
                print(request, "Passwords don't match")
                return render(request, 'accounts/password_reset_confirm.html', {'validlink': True, 'error_message': "Passwords don't match"})
            
            if len(password1) < 8:
                print(request, "Password must be at least 8 characters long")
                return render(request, 'accounts/password_reset_confirm.html', {'validlink': True, 'error_message': "Password must be at least 8 characters long"})
            
            # Set the new password
            user.set_password(password1)
            user.save()
            
            # Log the user in
            login(request, user)
            
            print(request, "Your password has been reset successfully!")
            return redirect('preview')
        
        return render(request, 'accounts/password_reset_confirm.html', {'validlink': True})
    else:
        # Invalid token
        return render(request, 'accounts/password_reset_confirm.html', {'validlink': False, 'error_message': "This password reset link is invalid or has expired."})
    


def loading_view(request, video_id):
    """Loading view for video processing"""
    try:
        video = Video.objects.get(id=video_id, user=request.user)
        return render(request, "home/loading.html",{'video_id': video_id, 'video': video, "user_subscription": Subscription.objects.filter(user=request.user).first()})
    except Video.DoesNotExist:
        print(request, "Video not found.")
        return redirect('upload_videos')


@login_required(login_url='login')
def proxy_video_download(request, video_id):
    """
    Proxy for downloading videos from S3 to avoid CORS issues
    """
    try:
        import requests
        from django.http import StreamingHttpResponse
        print(request, f"Downloading video with ID: {video_id}")    
        # Verify the user owns this video
        video = get_object_or_404(Video, id=video_id, user=request.user)
        
        # Check if user has a paid plan
        user_subscription = Subscription.objects.filter(user=request.user).first()
        if 'free' in user_subscription.plan.name.lower():
            print(request, "You need to upgrade to download videos.")
            return redirect('download_video', video_id=video_id)
        
        # Get the signed URL
        if video.output_with_bg and video.output_with_bg.name:
            s3_url = generate_signed_url(video.output_with_bg.name, expires_in=3600)
        else:
            print(request, "Video file not found.")
            return redirect('download_video', video_id=video_id)
        
        # Get filename from the video key
        filename = video.output_with_bg.name.split('/')[-1]
        
        # Stream the file from S3 to the user
        response = requests.get(s3_url, stream=True)
        
        if response.status_code != 200:
            print(request, "Error accessing video file.")
            return redirect('download_video', video_id=video_id)
        
        # Create a streaming response
        proxy_response = StreamingHttpResponse(
            response.iter_content(chunk_size=8192),
            content_type=response.headers.get('Content-Type', 'video/mp4')
        )
        
        # Set the content disposition header to force download with the correct filename
        proxy_response['Content-Disposition'] = f'attachment; filename="{filename}"'
        user_subscription.unused_credits -= 1
        user_subscription.save()

        # The streaming response doesn't support redirects after download,
        # but we can add a JavaScript redirection using a cookie
        redirect_to = request.GET.get('redirect_to')
        if redirect_to:
            proxy_response.set_cookie('post_download_redirect', redirect_to)
            
        return proxy_response
        
    except Exception as e:
        print(request, f"Error downloading video: {str(e)}")
        return redirect('download_video', video_id=video_id)


@login_required(login_url='login')
def cancel_subscription(request):
    """View to handle subscription cancellation"""
    if request.method == "POST":
        try:
            # Get user's active subscription
            subscription = Subscription.objects.filter(
                user=request.user, 
                status__in=['active', 'canceling', 'canceled']
            ).first()
            
            if not subscription:
                messages.error(request, "No active subscription found.")
                return redirect('manage_subscription')
            
            # Cancel the subscription in Stripe
            stripe_subscription_id = subscription.stripe_subscription_id
            if stripe_subscription_id:
                try:
                    print(f"Canceling subscription in Stripe: {stripe_subscription_id}")
                    
                    # Cancel at period end instead of immediately
                    stripe_sub = stripe.Subscription.modify(
                        stripe_subscription_id,
                        cancel_at_period_end=True
                    )
                    
                    # Check if cancel_at_period_end is True, regardless of status
                    if stripe_sub.cancel_at_period_end:
                        subscription.status = 'canceled'
                        subscription.save()
                        print(f"Successfully canceled subscription, will end at period end")
                        messages.success(
                            request, 
                            "Your subscription has been canceled. You'll have access until the end of your billing period."
                        )
                    else:
                        print(f"Failed to cancel subscription: cancel_at_period_end is False")
                        messages.error(request, "Failed to cancel subscription. Please try again.")
                except stripe.error.StripeError as e:
                    print(f"Stripe error during cancellation: {str(e)}")
                    messages.error(request, f"Stripe error: {str(e)}")
            else:
                # No Stripe subscription, just mark as canceled in our database
                subscription.status = 'canceled'
                subscription.save()
                messages.success(request, "Your subscription has been canceled.")
                
        except Exception as e:
            print(f"Error during cancellation: {str(e)}")
            messages.error(request, f"An error occurred: {str(e)}")
        
        return redirect('manage_subscription')
    
    # If not POST, redirect to plans view
    return redirect('manage_subscription')




@login_required
def speed_up_video(request):
    if request.method == "POST":
        try:
            speed = float(request.POST.get("speed", 1.0))
            print(f"Processing video with speed {speed}x")
            
            # Check if file exists in request.FILES
            if 'file' in request.FILES:
                video_file = request.FILES['file']
            elif 'video_file' in request.FILES:
                video_file = request.FILES['video_file']
            else:
                print("No video file found in request")
                return JsonResponse({'error': 'No video file uploaded'}, status=400)

            print(f"Received file: {video_file.name}, size: {video_file.size} bytes")
            
            if video_file:
                processed_video_path = process_video_speed(video_file, speed)

                if processed_video_path:
                    try:
                        # Open the file in binary mode
                        video_file = open(processed_video_path, 'rb')
                        response = FileResponse(
                            video_file, 
                            content_type='video/mp4'
                        )
                        
                        # Set headers for download
                        response['Content-Disposition'] = 'attachment; filename="sped_up_video.mp4"'
                        response['Content-Length'] = os.path.getsize(processed_video_path)

                        # Delete the file after sending
                        os.remove(processed_video_path)
                        
                        return response

                    except Exception as e:
                        print(f"Error creating response: {str(e)}")
                        # Clean up in case of error
                        if os.path.exists(processed_video_path):
                            os.remove(processed_video_path)
                        return JsonResponse({'error': str(e)}, status=500)
                else:
                    return JsonResponse({'error': 'Failed to process video'}, status=500)
            else:
                return JsonResponse({'error': 'No video file uploaded'}, status=400)
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)

    # For GET requests, render the template
    context = {
        'user_subscription': Subscription.objects.filter(user=request.user).first(),
    }
    return render(request, 'home/speed-up-video.html', context)



def affiliate_program(request):
    """View for the affiliate program"""
    return render(request, "terms/affiliate-program.html")

def refund(request):
    """View for the affiliate program"""
    return render(request, "terms/refund.html")

def privacy(request):
    """View for the affiliate program"""
    return render(request, "terms/privacy.html")


def terms_and_condition(request):
    """View for the affiliate program"""
    return render(request, "terms/terms-and-conditions.html")