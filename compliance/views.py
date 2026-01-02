from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import (
    DetailView, CreateView, UpdateView, DeleteView, ListView
)
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

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


# ================================
# 3. QUICK ADD PERSONNEL (for onboarding flow)
# ================================

@login_required
def add_personnel_quick(request, lender_id):
    lender = get_object_or_404(LenderProfile, pk=lender_id)
    if request.user != lender.user and not request.user.is_staff:
        raise PermissionDenied

    if request.method == 'POST':
        form = AddPersonnelForm(request.POST)
        if form.is_valid():
            personnel = form.save(commit=False)
            personnel.lender = lender
            personnel.save()
            # Redirect to full form to complete declarations/docs
            return redirect('compliance:personnel_update', pk=personnel.pk, lender_id=lender_id)
    else:
        form = AddPersonnelForm()

    return render(request, 'add_personnel_quick.html', {
        'form': form,
        'lender': lender
    })