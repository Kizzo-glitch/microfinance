from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse_lazy
from django.urls import reverse
from django.http import JsonResponse, HttpResponse, Http404
from django.views.generic import (
    DetailView, CreateView, UpdateView, DeleteView, ListView, View
)
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.utils import timezone

import json
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse
from django.views.generic import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils import timezone
from django.core.files.base import ContentFile
from io import BytesIO
import uuid

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
        
        # Existing context...
        context['lender'] = lender
        context['compliance'] = self.object
        context['personnel_list'] = lender.personnel.all()
        
        service = ComplianceDashboardService(lender)
        context['stats'] = service.get_dashboard_data()
        
        # NEW: Document generation context
        gen_service = DocumentGenerationService(lender)
        context.update({
            'can_generate_documents': gen_service.can_generate_any(),
            'generation_readiness': gen_service.get_readiness_status(),
            'compliance_docs': self._get_compliance_docs_with_generation_flags(lender),
        })
        
        return context

    def _get_compliance_docs_with_generation_flags(self, lender):
        service = DocumentGenerationService(lender)
        required_fields = service._get_required_docs()
        
        docs_with_flags = {}
        for field in required_fields:
            if field in ComplianceProfile.DOCUMENT_LABELS:
                docs_with_flags[field] = {
                    'label': ComplianceProfile.DOCUMENT_LABELS[field],
                    'can_generate': service.can_generate_document(field),
                    'generation_confidence': service.get_generation_confidence(field),
                }
        
        return docs_with_flags

      

class ComplianceProfileDetailView2(LoginRequiredMixin, LenderOwnerMixin, DetailView):
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


#=============================================================================================================
    # Fit & Proper Questionnaire Generator
    # Generates CBL-compliant fit and proper questionnaires for directors and key personnel
    # Based on CBL requirements and Schedule III formatting
#=================================================================================================================

class DocumentGenerationReadinessView(LoginRequiredMixin, LenderOwnerMixin, View):
    """Check if documents can be generated for this lender"""
    
    def get(self, request, lender_id):
        lender = self.get_lender()
        service = DocumentGenerationService(lender)
        
        readiness = service.get_readiness_status()
        
        return JsonResponse({
            'ready': readiness['ready'],
            'completeness': readiness['completeness'],
            'can_generate_count': readiness['can_generate_count'],
            'total_required': readiness['total_required'],
            'estimated_time': readiness['estimated_time'],
            'missing_data': readiness['missing_data_categories'],
            'average_confidence': readiness['average_confidence'],
        })


class GenerateDocumentsView(LoginRequiredMixin, LenderOwnerMixin, View):
    """Generate multiple documents with streaming progress updates"""
    
    def post(self, request, lender_id):
        lender = self.get_lender()
        service = DocumentGenerationService(lender)
        
        try:
            # Parse selected documents from request
            data = json.loads(request.body)
            selected_docs = data.get('selected_documents', [])
            
            if not selected_docs:
                # Auto-select all generatable documents
                required_docs = service._get_required_docs()
                selected_docs = [doc for doc in required_docs if service.can_generate_document(doc)]
            
            # Check readiness
            if not service.can_generate_any():
                return JsonResponse({
                    'success': False,
                    'message': 'Profile incomplete - cannot generate documents yet',
                    'missing_data': service.get_readiness_status()['missing_data_categories']
                })
            
            # Start generation process
            generation_id = str(uuid.uuid4())
            
            # Store generation task (in production, use Celery)
            request.session[f'generation_{generation_id}'] = {
                'lender_id': lender_id,
                'selected_docs': selected_docs,
                'status': 'started',
                'progress': 0,
            }
            
            return JsonResponse({
                'success': True,
                'generation_id': generation_id,
                'stream_url': reverse('compliance:generation_stream', kwargs={'generation_id': generation_id}),
                'estimated_time': service._estimate_generation_time(len(selected_docs)),
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e),
                'message': 'Failed to start document generation'
            })


class GenerationStreamView(LoginRequiredMixin, View):
    """Server-Sent Events stream for real-time generation progress"""
    
    def get(self, request, generation_id):
        def event_stream():
            try:
                # Get generation task from session
                task_key = f'generation_{generation_id}'
                task_data = request.session.get(task_key)
                
                if not task_data:
                    yield f"data: {json.dumps({'error': 'Generation task not found'})}\n\n"
                    return
                
                lender_id = task_data['lender_id']
                selected_docs = task_data['selected_docs']
                
                # Get lender (simplified - in production, verify ownership)
                from .models import LenderProfile
                lender = LenderProfile.objects.get(id=lender_id)
                service = DocumentGenerationService(lender)
                
                total_docs = len(selected_docs)
                
                # Send initial status
                yield f"data: {json.dumps({'progress': 0, 'current_step': 'Initializing document generation...', 'log_entry': 'Starting generation process'})}\n\n"
                
                results = {}
                successful_count = 0
                
                for i, doc_field in enumerate(selected_docs):
                    progress = int((i / total_docs) * 90)  # Reserve 10% for finalization
                    
                    # Update progress
                    yield f"data: {json.dumps({'progress': progress, 'current_step': f'Generating {doc_field}...', 'log_entry': f'Processing {doc_field}'})}\n\n"
                    
                    # Generate document
                    if doc_field == 'schedule_ii' or service.FIELD_TO_GENERATOR.get(doc_field) == 'schedule_ii':
                        result = service.generate_schedule_ii()
                    elif doc_field == 'business_plan' or service.FIELD_TO_GENERATOR.get(doc_field) == 'business_plan':
                        result = service.generate_business_plan()
                    elif doc_field in ['fit_proper_forms'] or any(p.role in ['director', 'ceo', 'finance_officer', 'compliance_officer'] for p in service.personnel):
                        result = service.generate_fit_proper_forms()
                    else:
                        result = {'success': False, 'message': f'Generator for {doc_field} not implemented yet'}
                    
                    results[doc_field] = result
                    
                    if result.get('success'):
                        successful_count += 1
                        # Save generated document to compliance profile
                        self._save_generated_document(lender.compliance, doc_field, result)
                        yield f"data: {json.dumps({'progress': progress + 5, 'log_entry': f'✓ {doc_field} generated successfully'})}\n\n"
                    else:
                        error_message = f'✗ {doc_field} generation failed: {result.get("message", "Unknown error")}'
                        yield f"data: {json.dumps({'progress': progress + 5, 'log_entry': error_message})}\n\n" 
                        #yield f"data: {json.dumps({'progress': progress + 5, 'log_entry': f'✗ {doc_field} generation failed: {result.get(\"message\", \"Unknown error\")}' })}\n\n"
                
                # Finalization
                yield f"data: {json.dumps({'progress': 95, 'current_step': 'Finalizing...', 'log_entry': 'Saving documents to compliance profile'})}\n\n"
                
                # Send completion
                completion_data = {
                    'complete': True,
                    'progress': 100,
                    'successful_count': successful_count,
                    'total_count': total_docs,
                    'generated_documents': [
                        {
                            'field': field,
                            'success': result.get('success', False),
                            'filename': result.get('filename', ''),
                            'message': result.get('message', '')
                        }
                        for field, result in results.items()
                    ]
                }
                
                yield f"data: {json.dumps(completion_data)}\n\n"
                
                # Clean up session data
                if task_key in request.session:
                    del request.session[task_key]
                
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e), 'complete': True})}\n\n"
        
        response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['Connection'] = 'keep-alive'
        response['X-Accel-Buffering'] = 'no'  # For nginx
        return response
    
    def _save_generated_document(self, compliance, doc_field, generation_result):
        """Save generated document to ComplianceProfile"""
        try:
            if not generation_result.get('success'):
                return
            
            document = generation_result.get('document')
            filename = generation_result.get('filename', f'{doc_field}.docx')
            
            if document:
                # Convert document to bytes
                if hasattr(document, 'save'):  # docx.Document object
                    buffer = BytesIO()
                    document.save(buffer)
                    buffer.seek(0)
                    file_content = buffer.getvalue()
                else:
                    file_content = document
                
                # Save to appropriate field
                content_file = ContentFile(file_content, name=filename)
                
                if hasattr(compliance, doc_field):
                    getattr(compliance, doc_field).save(filename, content_file, save=False)
                
                compliance.save()
                
        except Exception as e:
            print(f"Error saving generated document {doc_field}: {e}")


class GenerateSingleDocumentView(LoginRequiredMixin, LenderOwnerMixin, View):
    """Generate a single document (for individual generate buttons)"""
    
    def post(self, request, lender_id, document_field):
        lender = self.get_lender()
        service = DocumentGenerationService(lender)
        
        try:
            # Check if document can be generated
            if not service.can_generate_document(document_field):
                missing_data = service._get_missing_data_for_document(document_field)
                return JsonResponse({
                    'success': False,
                    'message': f'Cannot generate {document_field} - missing required data',
                    'missing_data': missing_data,
                    'confidence': service.get_generation_confidence(document_field)
                })
            
            # Generate the specific document
            generator_type = service.FIELD_TO_GENERATOR.get(document_field)
            
            if generator_type == 'schedule_ii':
                result = service.generate_schedule_ii()
            elif generator_type == 'business_plan':
                result = service.generate_business_plan()
            elif generator_type == 'fit_proper_forms':
                result = service.generate_fit_proper_forms()
            else:
                return JsonResponse({
                    'success': False,
                    'message': f'Generator for {generator_type} not yet implemented'
                })
            
            if result.get('success'):
                # Save to compliance profile
                generation_stream_view = GenerationStreamView()
                generation_stream_view._save_generated_document(lender.compliance, document_field, result)
                
                # Get file URL for frontend
                compliance = lender.compliance
                compliance.refresh_from_db()
                
                if hasattr(compliance, document_field):
                    field_file = getattr(compliance, document_field)
                    if field_file:
                        file_url = field_file.url
                    else:
                        file_url = None
                else:
                    file_url = None
                
                return JsonResponse({
                    'success': True,
                    'message': f'{document_field} generated successfully',
                    'filename': result.get('filename'),
                    'file_url': file_url,
                    'generation_time': timezone.now().isoformat(),
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': result.get('message', 'Generation failed'),
                    'error': result.get('error')
                })
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e),
                'message': f'Failed to generate {document_field}'
            })


class DocumentPreviewView(LoginRequiredMixin, LenderOwnerMixin, View):
    """Preview document content before generation"""
    
    def get(self, request, lender_id, document_type):
        lender = self.get_lender()
        service = DocumentGenerationService(lender)
        
        try:
            # Check if preview is available
            confidence = service.get_generation_confidence(document_type)
            can_generate = service.can_generate_document(document_type)
            
            if not can_generate:
                missing_data = service._get_missing_data_for_document(document_type)
                return JsonResponse({
                    'success': False,
                    'message': 'Cannot preview - insufficient data',
                    'missing_data': missing_data,
                    'confidence': confidence
                })
            
            # Generate preview content (HTML summary)
            preview_html = self._generate_preview_html(service, document_type)
            
            return JsonResponse({
                'success': True,
                'html': preview_html,
                'confidence': confidence,
                'can_generate': can_generate,
                'estimated_pages': self._estimate_document_pages(document_type),
                'generation_time_estimate': service._estimate_generation_time(1)
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e),
                'message': f'Failed to generate preview for {document_type}'
            })
    
    def _generate_preview_html(self, service, document_type):
        """Generate HTML preview of document content"""
        lender = service.lender
        
        if document_type == 'schedule_ii' or service.FIELD_TO_GENERATOR.get(document_type) == 'schedule_ii':
            return f"""
            <div class="document-preview">
                <h6>CBL Schedule II - Information Sheet</h6>
                <div class="row">
                    <div class="col-6">
                        <strong>Company Information:</strong>
                        <ul class="small mb-2">
                            <li>Name: {lender.company_name}</li>
                            <li>Registration: {lender.registration_number or 'To be provided'}</li>
                            <li>Tier: {lender.get_cbl_tier_display()}</li>
                        </ul>
                    </div>
                    <div class="col-6">
                        <strong>Personnel:</strong>
                        <ul class="small mb-2">
                            <li>{len(service.personnel)} key personnel listed</li>
                            <li>Board structure: {self._get_board_summary(service.personnel)}</li>
                        </ul>
                    </div>
                </div>
                <div class="alert alert-info small">
                    This 8-page document includes company details, ownership structure, 
                    board composition, and 3-year financial projections.
                </div>
            </div>
            """
        
        elif document_type == 'business_plan' or service.FIELD_TO_GENERATOR.get(document_type) == 'business_plan':
            return f"""
            <div class="document-preview">
                <h6>3-Year Business Plan</h6>
                <div class="row">
                    <div class="col-6">
                        <strong>Financial Highlights:</strong>
                        <ul class="small mb-2">
                            <li>Starting Capital: M{lender.stated_capital:,.0f}</li>
                            <li>Target Market: {getattr(lender, 'target_market_size', 'TBD')} clients</li>
                            <li>Business Model: {lender.get_cbl_tier_display()}</li>
                        </ul>
                    </div>
                    <div class="col-6">
                        <strong>Projections Include:</strong>
                        <ul class="small mb-2">
                            <li>Revenue & expense forecasts</li>
                            <li>Cash flow analysis</li>
                            <li>Break-even analysis</li>
                        </ul>
                    </div>
                </div>
                <div class="alert alert-info small">
                    Comprehensive 15-20 page business plan with financial models, 
                    market analysis, and regulatory compliance strategy.
                </div>
            </div>
            """
        
        elif document_type == 'fit_proper_forms':
            return f"""
            <div class="document-preview">
                <h6>Fit & Proper Questionnaires</h6>
                <div class="mb-2">
                    <strong>Personnel Forms ({len(service.personnel)}):</strong>
                </div>
                <div class="row">
                    {"".join([
                        f'''
                        <div class="col-6 mb-2">
                            <div class="border rounded p-2 small">
                                <strong>{p.full_name}</strong><br>
                                Role: {p.get_role_display()}<br>
                                Status: {'Complete' if service._assess_personnel_full_completeness() > 0.8 else 'Needs completion'}
                            </div>
                        </div>
                        '''
                        for p in service.personnel[:4]  # Show max 4
                    ])}
                </div>
                <div class="alert alert-info small">
                    Each form is 10-12 pages covering personal info, employment history, 
                    legal declarations, and character references.
                </div>
            </div>
            """
        
        else:
            return f"""
            <div class="document-preview">
                <h6>{document_type.replace('_', ' ').title()}</h6>
                <div class="alert alert-warning small">
                    Preview for this document type is not yet available.
                    The document can still be generated using available data.
                </div>
            </div>
            """
    
    def _get_board_summary(self, personnel):
        """Get summary of board composition"""
        directors = [p for p in personnel if p.role == 'director']
        if not directors:
            return "No directors added"
        
        independent = sum(1 for d in directors if getattr(d, 'is_non_executive', False))
        return f"{len(directors)} directors ({independent} independent)"
    
    def _estimate_document_pages(self, document_type):
        """Estimate number of pages in generated document"""
        page_estimates = {
            'schedule_i': '6-8 pages',
            'schedule_ii': '8-10 pages', 
            'business_plan': '15-20 pages',
            'aml_policy': '12-15 pages',
            'fit_proper_forms': '10-12 pages each',
            'risk_manual': '10-12 pages',
        }
        
        return page_estimates.get(document_type, '5-10 pages')










class GenerateDocumentsView(LoginRequiredMixin, LenderOwnerMixin, View):
    def post(self, request, lender_id):
        lender = self.get_lender()
        
        # Check if lender data is sufficient
        readiness = self._check_generation_readiness(lender)
        if not readiness['ready']:
            return JsonResponse({
                'success': False,
                'message': 'Please complete your profile first',
                'missing_data': readiness['missing']
            })
        
        # Generate documents
        workflow = AutoDocumentWorkflow(lender)
        result = workflow.generate_application_package()
        
        if result['success']:
            # Update dashboard service to reflect new documents
            service = ComplianceDashboardService(lender)
            service.advance_stage('document_gathering')  # Or appropriate stage
            
        return JsonResponse(result)


class DocumentPreviewView(LoginRequiredMixin, LenderOwnerMixin, DetailView):
    def get(self, request, lender_id, document_type):
        lender = self.get_lender()
        
        # Generate preview without saving
        generator = self._get_generator(document_type)
        preview_html = generator.generate_preview(lender)
        
        return JsonResponse({
            'html': preview_html,
            'can_generate': self._can_generate_full_document(lender),
            'missing_data': self._get_missing_data(lender, document_type)
        })