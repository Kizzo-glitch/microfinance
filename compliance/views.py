from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse_lazy
from django.urls import reverse
from django.views.generic import (
    DetailView, CreateView, UpdateView, DeleteView, ListView, View
)
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from compliance.compliace_services import ComplianceDashboardService
from lenders.models import LenderProfile
from .models import ComplianceProfile, PersonnelProfile
from .forms import ComplianceProfileForm, ComplianceUpdateForm, PersonnelProfileForm, AddPersonnelForm




# ================================
# MIXIN: Lender Ownership Check
# ================================


class LenderOwnerMixin:

    def get_lender(self):
        # Case A: URL has 'lender_id' (e.g., Dashboard or Create Personnel)
        if 'lender_id' in self.kwargs:
            return get_object_or_404(LenderProfile, pk=self.kwargs['lender_id'])
        
        # Case B: URL has 'pk' (e.g., Update/Delete Personnel)
        if 'pk' in self.kwargs:
            # We fetch the actual object (Personnel, ComplianceProfile, etc.)
            # and get the lender from it.
            obj = get_object_or_404(self.model, pk=self.kwargs['pk'])
            
            # If the object is the LenderProfile itself
            if isinstance(obj, LenderProfile):
                return obj
            # If the object is Personnel or ComplianceProfile (which have .lender)
            if hasattr(obj, 'lender'):
                return obj.lender
        
        return None

    def dispatch(self, request, *args, **kwargs):
        lender = self.get_lender()
        
        # Security Check: Compare logged-in user with lender owner
        if lender and request.user != lender.user and not request.user.is_staff:
            raise PermissionDenied
            
        return super().dispatch(request, *args, **kwargs)
    

# ================================
# 1. INSTITUTIONAL COMPLIANCE VIEWS
# ================================


class ComplianceProfileDetailView(LoginRequiredMixin, LenderOwnerMixin, DetailView):
    model = ComplianceProfile
    template_name = 'compliance_detail.html'
    context_object_name = 'compliance'

    def get_object(self):
        lender = self.get_lender()
        compliance, _ = ComplianceProfile.objects.get_or_create(lender=lender)
        return compliance
   

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lender = self.object.lender
        context['lender'] = lender
        context['compliance'] = self.object
        context['personnel_list'] = lender.personnel.all()

        service = ComplianceDashboardService(lender)
        context['stats'] = service.get_dashboard_data()

        # Build the doc dict for only this tier's required fields
        required_fields = service._get_required_docs()
        context['compliance_docs'] = {
            field: ComplianceProfile.DOCUMENT_LABELS[field]
            for field in required_fields
            if field in ComplianceProfile.DOCUMENT_LABELS
        }
        return context
    
    """
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['lender'] = self.object.lender
        context['compliance'] = self.object          # explicit, matches context_object_name
        context['personnel_list'] = self.object.lender.personnel.all()
        service = ComplianceDashboardService(self.object.lender)
        context['stats'] = service.get_dashboard_data()
        return context

    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Use the lender attached to the compliance profile object
        context['lender'] = self.object.lender 
        
        # Add your personnel and stats as before
        context['personnel_list'] = self.object.lender.personnel.all()
        service = ComplianceDashboardService(self.object.lender)
        context['stats'] = service.get_dashboard_data()
        
        return context"""


class ComplianceUpdateView(LoginRequiredMixin, LenderOwnerMixin, UpdateView):
    model = ComplianceProfile
    form_class = ComplianceUpdateForm
    template_name = 'compliance_form.html'

    def get_object(self):
        return ComplianceProfile.objects.get(lender__id=self.kwargs['lender_id'])


    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Pass the lender to the form so it can filter the fields
        kwargs['lender'] = self.get_object().lender
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['lender'] = self.get_lender()
        return context
    
    def form_valid(self, form):
        # Just save — the dashboard service recalculates stage on next read.
        # Do not call update_stage() — that method is now deprecated.
        return super().form_valid(form)
    
    """
    def form_valid(self, form):
        response = super().form_valid(form)
        # Trigger the stage update after documents are saved
        self.object.update_stage()
        return response """

    def get_success_url(self):
        return reverse_lazy('compliance:compliance_detail', kwargs={'lender_id': self.object.lender.id})


# ================================
# 2. PERSONNEL VIEWS
# ================================

class PersonnelCreateView(LoginRequiredMixin, LenderOwnerMixin, CreateView):
    model = PersonnelProfile
    form_class = PersonnelProfileForm
    template_name = 'personnel_form.html'

    def form_valid(self, form):
        form.instance.lender = self.get_lender()
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['lender'] = self.get_lender()
        return context

    def get_success_url(self):
        return reverse('compliance:compliance_detail',
                       kwargs={'lender_id': self.kwargs['lender_id']})
    

class PersonnelCreateView2(LoginRequiredMixin, CreateView):
    model = PersonnelProfile
    form_class = PersonnelProfileForm
    template_name = 'personnel_form.html'
    #fields = ['full_name', 'role', 'id_number', 'email', 'phone'] # Adjust based on your model

    def form_valid(self, form):
        # 1. Get the lender based on the ID in the URL
        lender = get_object_or_404(LenderProfile, id=self.kwargs['lender_id'])
        
        # 2. Attach this lender to the personnel instance before saving
        form.instance.lender = lender
        
        # 3. Save and return response
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pass lender to template for the "Back" button or header
        context['lender'] = get_object_or_404(LenderProfile, id=self.kwargs['lender_id'])
        return context

    def get_success_url(self):
        # Redirect back to the compliance dashboard
        return reverse('compliance:compliance_detail', kwargs={'lender_id': self.kwargs['lender_id']})



class PersonnelUpdateView(LoginRequiredMixin, LenderOwnerMixin, UpdateView):
    model = PersonnelProfile
    form_class = PersonnelProfileForm
    template_name = 'personnel_form.html'

    def get_queryset(self):
        lender = self.get_lender()
        return PersonnelProfile.objects.filter(lender=lender)
    
    def form_valid(self, form):
        if 'submit_final' in self.request.POST:
            form.instance.fit_proper_questionnaire_submitted = True
            form.instance.schedule_iii_submitted = True

        # Let super() do the single save — don't call form.save() manually
        return super().form_valid(form)

    def get_success_url(self):
        # Redirecting back to the Dashboard is usually better for UX 
        # than the separate personnel list.
        return reverse_lazy('compliance:compliance_detail', 
                            kwargs={'lender_id': self.object.lender.id})




class PersonnelListView(LoginRequiredMixin, LenderOwnerMixin, ListView):
    model = PersonnelProfile
    template_name = 'personnel_list.html'
    context_object_name = 'personnel_list'

    def get_queryset(self):
        lender = self.get_lender()
        return PersonnelProfile.objects.filter(lender=lender)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['lender'] = self.get_lender()
        return context
    

# ================================
# 2. PAYMENT and SUBMISSIONS
# ================================    

class PayInvestigationFeeView(LoginRequiredMixin, LenderOwnerMixin, View):
    template_name = 'payment_form.html'

    def get(self, request, lender_id):
        lender = self.get_lender()
        return render(request, self.template_name, {'lender': lender})

    def post(self, request, lender_id):
        lender = self.get_lender()
        compliance = lender.compliance
        proof = request.FILES.get('payment_proof')

        if not proof:
            messages.error(request, "Please select a file to upload.")
            return render(request, self.template_name, {'lender': lender})

        compliance.investigation_fee_proof  = proof
        compliance.investigation_fee_paid   = True
        compliance.investigation_fee_paid_at = timezone.now()
        compliance.save(update_fields=[
            'investigation_fee_proof',
            'investigation_fee_paid',
            'investigation_fee_paid_at',
        ])

        # Explicitly advance stage now that fee is paid
        service = ComplianceDashboardService(lender)
        service.advance_stage('investigation_fee_pending')

        messages.success(request, "Payment proof uploaded. Your application is ready for submission.")
        return redirect('compliance:compliance_detail', lender_id=lender.id)


def pay_investigation_fee2(request, lender_id):
    lender = get_object_or_404(LenderProfile, id=lender_id)
    compliance = lender.compliance
    
    if request.method == 'POST':
        proof = request.FILES.get('payment_proof')
        if proof:
            compliance.investigation_fee_proof = proof
            compliance.investigation_fee_paid = True
            compliance.date_paid = timezone.now()
            compliance.save()
            
            messages.success(request, "Payment proof uploaded successfully. Your application status has been updated.")
            return redirect('compliance:compliance_detail', lender_id=lender.id)
        else:
            messages.error(request, "Please select a file to upload.")

    return render(request, 'payment_form.html', {'lender': lender})



class SubmitApplicationView(LoginRequiredMixin, LenderOwnerMixin, View):

    def post(self, request, lender_id):
        lender = self.get_lender()
        service = ComplianceDashboardService(lender)

        # Guard: only allow submission if all pre-submission gates are met
        data = service.get_dashboard_data()
        if data['progress'] < 100:
            messages.error(
                request,
                "Your application is not yet complete. "
                f"Please resolve: {data['status_message']}"
            )
            return redirect('compliance:compliance_detail', lender_id=lender_id)

        service.advance_stage('submitted')
        lender.compliance.submission_date = timezone.now()
        lender.compliance.save(update_fields=['submission_date'])

        messages.success(request, "Application submitted to CBL successfully.")
        return redirect('compliance:compliance_detail', lender_id=lender_id)

    def get(self, request, lender_id):
        # Never render on GET — always redirect
        return redirect('compliance:compliance_detail', lender_id=lender_id)
    


def submit_application2(request, lender_id): # Ensure this matches your URL parameter
    # 1. Look up by lender_id to stay consistent with your other views
    profile = get_object_or_404(ComplianceProfile, lender__id=lender_id)
    
    if request.method == 'POST':
        # 2. Update the stage
        profile.current_stage = 'under_review'
        profile.submission_date = timezone.now()
        profile.save()
        
        # 3. Add a success message
        messages.success(request, "Application submitted successfully! It is now under review.")
        
        # 4. ALWAYS return a redirect after a successful POST
        return redirect('compliance:compliance_detail', lender_id=lender_id)

    # 5. FALLBACK: If someone accidentally navigates here via GET, 
    # just send them back to the dashboard.
    return redirect('compliance:compliance_detail', lender_id=lender_id)


def submission_receipt(request, lender_id):
    profile = get_object_or_404(ComplianceProfile, lender__id=lender_id)
    
    if profile.current_stage != 'under_review':
        messages.error(request, "Receipt only available after submission.")
        return redirect('compliance:compliance_detail', lender_id=lender_id)
        
    return render(request, 'receipt.html', {
        'profile': profile,
        'lender': profile.lender
    })


class PersonnelDeleteView(LoginRequiredMixin, LenderOwnerMixin, DeleteView):
    model = PersonnelProfile
    template_name = 'personnel_confirm_delete.html'

    def get_queryset(self):
        lender = self.get_lender()
        return PersonnelProfile.objects.filter(lender=lender)

    def get_success_url(self):
        messages.success(self.request, "Personnel removed.")
        return reverse_lazy('compliance:personnel_list', kwargs={'lender_id': self.get_lender().pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['lender'] = self.get_lender()
        return context


