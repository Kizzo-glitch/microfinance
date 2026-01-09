from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse_lazy
from django.urls import reverse
from django.views.generic import (
    DetailView, CreateView, UpdateView, DeleteView, ListView
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
    """
    Ensures only the lender (or admin) can access their compliance data.
    Works for both /lender/20/... and /personnel/4/edit/
    """
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
    

class LenderOwnerMixin2:
    """
    Ensures only the lender (or admin) can access their compliance data.
    """
    def get_lender(self):
        return get_object_or_404(LenderProfile, pk=self.kwargs['lender_id'])

    def dispatch(self, request, *args, **kwargs):
        lender = self.get_lender()
        if request.user != lender.user and not request.user.is_staff:
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
        # Use the lender attached to the compliance profile object
        context['lender'] = self.object.lender 
        
        # Add your personnel and stats as before
        context['personnel_list'] = self.object.lender.personnel.all()
        service = ComplianceDashboardService(self.object.lender)
        context['stats'] = service.get_dashboard_data()
        
        return context


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
        response = super().form_valid(form)
        # Trigger the stage update after documents are saved
        self.object.update_stage()
        return response

    def get_success_url(self):
        return reverse_lazy('compliance:compliance_detail', kwargs={'lender_id': self.object.lender.id})


# ================================
# 2. PERSONNEL VIEWS
# ================================

class PersonnelCreateView(LoginRequiredMixin, CreateView):
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
        # 1. Save the form but don't commit to DB yet
        self.object = form.save(commit=False)
        
        # 2. Check if the "Submit Final" button was pressed
        if 'submit_final' in self.request.POST:
            self.object.fit_proper_questionnaire_submitted = True
            self.object.schedule_iii_submitted = True
        
        # 3. Save the object
        self.object.save()
        
        # 4. Trigger the stage update on the compliance profile
        self.object.lender.compliance.update_stage()
        
        return super().form_valid(form)

    def get_success_url(self):
        # Redirecting back to the Dashboard is usually better for UX 
        # than the separate personnel list.
        return reverse_lazy('compliance:compliance_detail', 
                            kwargs={'lender_id': self.object.lender.id})



# ================================
# 2. PERSONNEL VIEWS
# ================================

class PayInvestigationFeeView(LoginRequiredMixin, LenderOwnerMixin, UpdateView):
    model = ComplianceProfile
    template_name = 'payment_form.html'
    fields = ['investigation_fee_paid', 'payment_reference'] 
   
    def get_object(self):
        # We find the profile using the lender_id from the URL
        return get_object_or_404(ComplianceProfile, lender__id=self.kwargs['lender_id'])
  
    def get_success_url(self):
        return reverse('compliance:compliance_detail', kwargs={'lender_id': self.kwargs['lender_id']})
    

def pay_investigation_fee(request, lender_id):
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



def submit_application(request, lender_id): # Ensure this matches your URL parameter
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


def submit_application2(request, pk):
    profile = get_object_or_404(ComplianceProfile, pk=pk)
    
    if request.method == 'POST':
        # Change the stage to 'under_review'
        profile.current_stage = 'under_review'
        profile.submission_date = timezone.now()
        profile.save()
        
        messages.success(request, "Application submitted successfully! The CBL will now begin the review process.")
        return redirect('compliance:compliance_detail', lender_id=profile.lender.id)
    return redirect('compliance:compliance_detail', lender_id=pk)


def submit_application2(request, pk):
    if request.method == 'POST':
        # 1. Fetch the compliance profile
        compliance = get_object_or_404(ComplianceProfile, pk=pk)
        
        # 2. Update the stage to 'submitted'
        compliance.current_stage = 'submitted' # Or whatever your final status is
        compliance.save()
        
        # 3. Add a success message
        messages.success(request, "Application successfully submitted to the CBL. Your files are now under review.")
        
        # 4. Redirect back to the dashboard
        return redirect('compliance:compliance_detail', lender_id=compliance.lender.id)
    
    return redirect('compliance:compliance_detail', lender_id=compliance.lender.id)

"""
def personnel_update(request, pk):
    personnel = get_object_or_404(PersonnelProfile, pk=pk)
    
    if request.method == 'POST':
        form = PersonnelProfileForm(request.POST, request.FILES, instance=personnel)
        if form.is_valid():
            instance = form.save(commit=False)
            
            # Check which button was clicked
            if 'submit_final' in request.POST:
                instance.fit_proper_questionnaire_submitted = True
                instance.schedule_iii_submitted = True
            
            instance.save()
            
            # Update the Stage on the main Compliance Profile
            personnel.lender.compliance.update_stage()
            
            messages.success(request, f"Profile for {instance.full_name} updated.")
            return redirect('compliance:compliance_detail', lender_id=personnel.lender.id)
    else:
        form = PersonnelProfileForm(instance=personnel)
        
    return render(request, 'personnel_form.html', {'form': form})
"""

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


"""
class PersonnelUpdateView(LoginRequiredMixin, LenderOwnerMixin, UpdateView):
    model = PersonnelProfile
    form_class = PersonnelProfileForm
    template_name = 'personnel_form.html'

    def get_queryset(self):
        lender = self.get_lender()
        return PersonnelProfile.objects.filter(lender=lender)

    def get_success_url(self):
        messages.success(self.request, "Personnel updated successfully.")
        return reverse_lazy('compliance:personnel_list', kwargs={'lender_id': self.get_lender().pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['lender'] = self.get_lender()
        return context
"""

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


