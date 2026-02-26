
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from compliance.models import ComplianceProfile
from .forms import RegulatorProfileForm # You'll need to create this form

from django.contrib.auth.decorators import login_required
from lenders.models import LenderProfile # Adjust based on your actual model name




@login_required
def regulator_profile(request):
    # Get the profile linked to the logged-in user
    profile = request.user.regulator 
    
    if request.method == 'POST':
        form = RegulatorProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            return redirect('regulator:regulator_dashboard') # Finally send them to the dashboard
    else:
        form = RegulatorProfileForm(instance=profile)
    
    return render(request, 'regulator_profile.html', {'form': form})




@login_required
def regulator_dashboard(request):
    # Security: Ensure only regulators can access this
    if request.user.role != 'regulator':
        return redirect('landing')

    # Data Aggregation
    lenders = LenderProfile.objects.select_related('compliance').all().order_by('-created_at')
    pending_lenders = LenderProfile.objects.filter(is_approved=False).order_by('-created_at')
    active_lenders_count = LenderProfile.objects.filter(is_approved=True).count()
    total_lenders_count = LenderProfile.objects.count()
    
    # Optional: Filter by Tier for the summary cards
    tier_1_count = LenderProfile.objects.filter(cbl_tier='tier1', is_approved=True).count()
    tier_2_count = LenderProfile.objects.filter(cbl_tier='tier2', is_approved=True).count()
    tier_3_count = LenderProfile.objects.filter(cbl_tier='tier3', is_approved=True).count()
    individual_count = LenderProfile.objects.filter(cbl_tier='individual', is_approved=True).count()
    p2p_count = LenderProfile.objects.filter(cbl_tier='p2p', is_approved=True).count()
    
    context = {
        'pending_lenders': pending_lenders,
        'active_count': active_lenders_count,
        'total_count': total_lenders_count,
        'tier_1_count': tier_1_count,
        'tier_2_count': tier_2_count,
        'tier_3_count': tier_3_count,
        'individual_count': individual_count,
        'p2p_count': p2p_count,
        'pending_count': pending_lenders.count(),

        'lenders': lenders,
        'pending_review': lenders.filter(compliance__current_stage='under_review').count(),
        'fit_proper': lenders.filter(compliance__current_stage='fit_proper_pending').count(),
    }
    
    return render(request, 'regulator_dashboard.html', context)


def review_lender(request, lender_id):
    lender = get_object_or_404(LenderProfile, id=lender_id)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'approve':
            lender.is_approved = True
            lender.rejection_reason = "" # Clear any old reasons
            lender.save()
            messages.success(request, f"Institution {lender.company_name} has been authorized.")
            return redirect('regulator:regulator_dashboard')
            
        elif action == 'reject':
            reason = request.POST.get('rejection_reason')
            if not reason:
                messages.error(request, "Please provide a reason for rejection.")
            else:
                lender.is_approved = False
                lender.rejection_reason = reason
                lender.save()
                messages.warning(request, f"Application for {lender.company_name} has been sent back for corrections.")
                return redirect('regulator:regulator_dashboard')

    return render(request, 'review_lender.html', {'lender': lender})