# views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from decimal import Decimal
from django.utils import timezone

from .compliace_services import CBLRegistrationService, ComplianceDashboardService, ComplianceProgressService, ComplianceWorkflowService

from .models import CBLRegistration, ComplianceChecklist, KeyPersonnel, ComplianceDocument

from lenders.models import LenderProfile

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views.generic import TemplateView
from django.views import View


from .forms import ComplianceTierSelectionForm, GovernanceSetupForm, ComplianceCompanyInfoForm



from django.views.generic import TemplateView
from django.views.generic import FormView



from django.views.generic import UpdateView
from django.urls import reverse


class ComplianceWizardResumeView(LoginRequiredMixin, View):
    """
    Redirect lender to the correct compliance wizard step
    based on their current registration stage.
    """

    def get(self, request, *args, **kwargs):
        lender = request.user.lender

        registration, _ = CBLRegistration.objects.get_or_create(
            lender_profile=lender
        )

        next_url = CBLRegistrationService.get_next_step_url(registration)
        return redirect(next_url)


class ComplianceDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "compliance_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        registration = CBLRegistration.objects.get(
            lender_profile=self.request.user.lender
        )

        dashboard = ComplianceDashboardService(registration)

        context.update({
            'registration': registration,
            'completion_percentage': dashboard.completion_percentage(),
            'missing_requirements': dashboard.missing_requirements(),
            'next_action': dashboard.next_action(),
        })

        return context


class ComplianceWizardBaseView(FormView):
    registration_stage = None

    def dispatch(self, request, *args, **kwargs):
        self.registration = CBLRegistration.objects.get(
            lender_profile=request.user.lender
        )
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.save()
        ComplianceWorkflowService(self.registration).advance()
        return redirect(self.get_next_url())

    def get_next_url(self):
        raise NotImplementedError


class ComplianceTierSelectionView(ComplianceWizardBaseView, FormView):
    template_name = 'compliance_tier_selection.html'
    form_class = ComplianceTierSelectionForm
    stage = 'initiated'

    def form_valid(self, form):
        tier = form.cleaned_data['target_tier']

        self.registration.target_tier = tier
        self.registration.current_stage = 'company_info'
        self.registration.set_tier_requirements()
        self.registration.save()

        return redirect('compliance:company')


class ComplianceCompanyInfoView(ComplianceWizardBaseView, UpdateView):
    model = LenderProfile
    form_class = ComplianceCompanyInfoForm
    template_name = 'compliance_company_info.html'
    stage = 'company_info'

    def get_object(self):
        return self.lender

    def form_valid(self, form):
        response = super().form_valid(form)
        self.advance_stage('directors_info')
        return response

    def get_success_url(self):
        return reverse('compliance:directors')



class ComplianceDirectorsView(ComplianceWizardBaseView):
    template_name = 'compliance_directors.html'
    stage = 'directors_info'

    def post(self, request, *args, **kwargs):
        progress = ComplianceProgressService(self.registration)

        if progress.directors_complete():
            self.advance_stage('governance_setup')
            return redirect('compliance:governance')

        return self.get(request, *args, **kwargs)



class ComplianceGovernanceView(ComplianceWizardBaseView, UpdateView):
    model = CBLRegistration
    form_class = GovernanceSetupForm
    template_name = 'compliance_governance.html'
    stage = 'governance_setup'

    def get_object(self):
        return self.registration

    def form_valid(self, form):
        response = super().form_valid(form)
        self.advance_stage('document_collection')
        return response

    def get_success_url(self):
        return reverse('compliance:documents')




class ComplianceDocumentsView(ComplianceWizardBaseView):
    template_name = 'compliance/compliance_documents.html'
    stage = 'document_collection'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        checklist = ComplianceChecklist(self.registration)

        context['required_documents'] = checklist.get_missing_documents()
        context['completion'] = self.registration.get_completion_percentage()
        return context

    def post(self, request, *args, **kwargs):
        if self.registration.get_completion_percentage() == 100:
            self.advance_stage('document_review')
            return redirect('compliance:review')

        return self.get(request, *args, **kwargs)



class ComplianceReviewView(ComplianceWizardBaseView):
    template_name = 'compliance_review.html'
    stage = 'document_review'

    def post(self, request, *args, **kwargs):
        self.registration.submitted_to_cbl = True
        self.registration.cbl_submission_date = timezone.now()
        self.registration.current_stage = 'cbl_submission'
        self.registration.save()

        return redirect('compliance:dashboard')









"""
@login_required
def registration_start(request):
    #Step 1: Initial assessment and tier recommendation
    
    # Check if user already has a profile
    if hasattr(request.user, 'lender_profile'):
        return redirect('lenders:dashboard')
    
    if request.method == 'POST':
        # Gather assessment data
        capital = Decimal(request.POST.get('available_capital', '0').replace(',', ''))
        assets = Decimal(request.POST.get('total_assets', '0').replace(',', '') or '0')
        wants_deposits = request.POST.get('wants_deposits') == 'yes'
        has_public_debt = request.POST.get('has_public_debt') == 'yes'
        has_team = request.POST.get('has_team') == 'yes'
        
        # Get tier recommendation
        tier, reasoning, requirements = TierAssessmentService.assess(
            capital=capital,
            assets=assets,
            wants_deposits=wants_deposits,
            has_public_debt=has_public_debt,
            has_team=has_team
        )
        
        # Store in session for next step
        request.session['tier_assessment'] = {
            'tier': tier,
            'reasoning': reasoning,
            'capital': str(capital),
            'assets': str(assets),
        }
        
        return redirect('lenders:tier_confirmation')
    
    return render(request, 'lenders/registration/start.html')



@login_required
def tier_confirmation(request):
    #Step 2: Confirm tier selection and show requirements
    
    assessment = request.session.get('tier_assessment')
    if not assessment:
        return redirect('lenders:registration_start')
    
    tier = assessment['tier']
    requirements = TierAssessmentService.get_tier_requirements(tier)
    
    if request.method == 'POST':
        confirmed_tier = request.POST.get('confirmed_tier', tier)
        
        # Create lender profile
        profile = LenderProfile.objects.create(
            user=request.user,
            cbl_tier=confirmed_tier,
            stated_capital=Decimal(assessment['capital']),
            total_assets=Decimal(assessment['assets']) if assessment['assets'] else None,
            verification_status='documents_pending'
        )
        
        # Create CBL registration if needed
        if confirmed_tier in ['tier1', 'tier2', 'tier3']:
            CBLRegistration.objects.create(
                lender_profile=profile,
                target_tier=confirmed_tier,
                proposed_capital=Decimal(assessment['capital']),
                current_stage='company_info'
            )
        
        # Clear session
        del request.session['tier_assessment']
        
        messages.success(request, f'Registration started as {profile.get_cbl_tier_display()}')
        return redirect('lenders:registration_company_info')
    
    context = {
        'assessment': assessment,
        'tier': tier,
        'tier_display': dict(LenderProfile.CBL_TIER_CHOICES).get(tier, tier),
        'requirements': requirements,
        'all_tiers': TierAssessmentService.TIER_THRESHOLDS,
    }
    
    return render(request, 'lenders/registration/tier_confirmation.html', context)


@login_required
def registration_company_info(request):
    #Step 3: Company information
    
    profile = get_object_or_404(LenderProfile, user=request.user)
    
    if request.method == 'POST':
        # Update profile with company info
        profile.company_name = request.POST.get('company_name')
        profile.trading_name = request.POST.get('trading_name', '')
        profile.registration_number = request.POST.get('registration_number', '')
        profile.tax_identification_number = request.POST.get('tax_number', '')
        profile.date_of_establishment = request.POST.get('date_established') or None
        profile.ownership_type = request.POST.get('ownership_type', '')
        
        # Contact info
        profile.business_email = request.POST.get('business_email')
        profile.phone_number = request.POST.get('phone_number')
        profile.physical_address = request.POST.get('physical_address')
        profile.city = request.POST.get('city', 'Maseru')
        profile.district = request.POST.get('district', '')
        
        # CEO info
        profile.ceo_first_name = request.POST.get('ceo_first_name')
        profile.ceo_last_name = request.POST.get('ceo_last_name')
        profile.ceo_email = request.POST.get('ceo_email', '')
        profile.ceo_phone = request.POST.get('ceo_phone', '')
        
        profile.save()
        
        # Advance registration stage
        if hasattr(profile, 'cbl_registration'):
            reg = profile.cbl_registration
            if reg.current_stage == 'company_info':
                reg.current_stage = 'directors_info'
                reg.save()
        
        messages.success(request, 'Company information saved')
        return redirect('lenders:registration_directors')
    
    context = {
        'profile': profile,
        'step': 3,
        'total_steps': 7,
    }
    
    return render(request, 'lenders/registration/company_info.html', context)


@login_required
def registration_directors(request):
    #Step 4: Directors and key personnel
    
    profile = get_object_or_404(LenderProfile, user=request.user)
    registration = get_object_or_404(CBLRegistration, lender_profile=profile)
    
    personnel = registration.key_personnel.all()
    min_directors = profile.minimum_board_size
    current_directors = personnel.filter(role__in=['director', 'chairman']).count()
    
    context = {
        'profile': profile,
        'registration': registration,
        'personnel': personnel,
        'min_directors': min_directors,
        'current_directors': current_directors,
        'can_proceed': current_directors >= min_directors,
        'step': 4,
        'total_steps': 7,
    }
    
    return render(request, 'lenders/registration/directors.html', context)


@login_required
def add_personnel(request, registration_id):
    #Add a director or key personnel
    
    registration = get_object_or_404(
        CBLRegistration, 
        id=registration_id,
        lender_profile__user=request.user
    )
    
    if request.method == 'POST':
        personnel = KeyPersonnel.objects.create(
            registration=registration,
            first_name=request.POST.get('first_name'),
            last_name=request.POST.get('last_name'),
            national_id=request.POST.get('national_id'),
            date_of_birth=request.POST.get('date_of_birth'),
            email=request.POST.get('email'),
            phone=request.POST.get('phone'),
            physical_address=request.POST.get('physical_address'),
            role=request.POST.get('role'),
            is_executive=request.POST.get('is_executive') == 'yes',
            qualifications=request.POST.get('qualifications', ''),
            years_of_experience=int(request.POST.get('experience', 0)),
        )
        
        messages.success(request, f'{personnel.full_name} added successfully')
        return redirect('lenders:registration_directors')
    
    context = {
        'registration': registration,
        'roles': KeyPersonnel.ROLE_CHOICES,
    }
    
    return render(request, 'lenders/registration/add_personnel.html', context)


@login_required
def registration_documents(request):
    #Step 5: Document upload
    
    profile = get_object_or_404(LenderProfile, user=request.user)
    registration = get_object_or_404(CBLRegistration, lender_profile=profile)
    
    # Get required documents based on tier
    required_docs = get_required_documents(registration.target_tier)
    uploaded_docs = registration.documents.filter(is_current=True)
    uploaded_types = set(uploaded_docs.values_list('document_type', flat=True))
    
    doc_status = []
    for doc_type, doc_name, mandatory in required_docs:
        doc_status.append({
            'type': doc_type,
            'name': doc_name,
            'mandatory': mandatory,
            'uploaded': doc_type in uploaded_types,
            'document': uploaded_docs.filter(document_type=doc_type).first(),
        })
    
    context = {
        'profile': profile,
        'registration': registration,
        'doc_status': doc_status,
        'step': 5,
        'total_steps': 7,
    }
    
    return render(request, 'lenders/registration/documents.html', context)


def get_required_documents(tier):
    #Get list of required documents for a tier
    
    common = [
        ('company_registration', 'Company Registration Certificate', True),
        ('memorandum_articles', 'Memorandum & Articles', True),
        ('tax_clearance_company', 'Company Tax Clearance', True),
        ('bank_statement', 'Bank Statement (Capital Proof)', True),
        ('aml_manual', 'AML/CFT Policy Manual', True),
        ('complaints_procedure', 'Consumer Complaints Procedure', True),
        ('application_form_schedule1', 'Application Form (Schedule I)', True),
        ('application_form_schedule2', 'Application Form (Schedule II)', True),
    ]
    
    tier12_docs = [
        ('business_plan', 'Business Plan', True),
        ('audited_financials', 'Audited Financial Statements', True),
        ('risk_manual', 'Risk Management Manual', True),
        ('organizational_chart', 'Organizational Chart', True),
    ]
    
    tier3_docs = [
        ('certified_accounts', 'Certified Accountant Statement', True),
    ]
    
    if tier == 'tier1':
        return common + tier12_docs
    elif tier == 'tier2':
        return common + tier12_docs
    elif tier == 'tier3':
        return common + tier3_docs
    
    return common


@login_required
def upload_document(request, registration_id):
    #Handle document upload
    
    registration = get_object_or_404(
        CBLRegistration,
        id=registration_id,
        lender_profile__user=request.user
    )
    
    if request.method == 'POST' and request.FILES.get('document'):
        doc_type = request.POST.get('document_type')
        doc_file = request.FILES['document']
        
        # Validate file type
        allowed_types = ['application/pdf', 'image/jpeg', 'image/png']
        if doc_file.content_type not in allowed_types:
            messages.error(request, 'Only PDF and image files are allowed')
            return redirect('lenders:registration_documents')
        
        # Create document
        doc = ComplianceDocument.objects.create(
            cbl_registration=registration,
            document_type=doc_type,
            title=dict(ComplianceDocument.DOCUMENT_TYPE_CHOICES).get(doc_type, doc_type),
            file=doc_file,
            category='company' if 'company' in doc_type else 'compliance',
            uploaded_by=request.user,
            status='uploaded',
        )
        
        messages.success(request, f'{doc.title} uploaded successfully')
    
    return redirect('lenders:registration_documents')


@login_required
def registration_review(request):
    #Step 6: Review application before submission
    
    profile = get_object_or_404(LenderProfile, user=request.user)
    registration = get_object_or_404(CBLRegistration, lender_profile=profile)
    
    # Get completion status
    completion = registration.get_completion_percentage()
    requirements = registration.get_all_requirements()
    
    # Group by category
    grouped_reqs = {}
    for req in requirements:
        cat = req['category']
        if cat not in grouped_reqs:
            grouped_reqs[cat] = []
        grouped_reqs[cat].append(req)
    
    workflow = RegistrationWorkflowService(registration)
    can_submit = completion >= 100
    next_actions = workflow.get_next_actions() if not can_submit else []
    
    context = {
        'profile': profile,
        'registration': registration,
        'completion': completion,
        'grouped_requirements': grouped_reqs,
        'can_submit': can_submit,
        'next_actions': next_actions,
        'step': 6,
        'total_steps': 7,
    }
    
    return render(request, 'lenders/registration/review.html', context)


@login_required
def registration_submit(request):
    #Step 7: Submit application to CBL
    
    profile = get_object_or_404(LenderProfile, user=request.user)
    registration = get_object_or_404(CBLRegistration, lender_profile=profile)
    
    if request.method == 'POST':
        # Verify completion
        completion = registration.get_completion_percentage()
        if completion < 100:
            messages.error(request, 'Application is not complete')
            return redirect('lenders:registration_review')
        
        # Mark as submitted
        registration.submitted_to_cbl = True
        registration.cbl_submission_date = timezone.now()
        registration.current_stage = 'cbl_submission'
        registration.save()
        
        # Update profile status
        profile.verification_status = 'cbl_pending'
        profile.save()
        
        messages.success(
            request, 
            'Application submitted successfully! '
            'You will be notified of CBL\'s decision.'
        )
        return redirect('lenders:dashboard')
    
    # Show payment/submission confirmation page
    context = {
        'profile': profile,
        'registration': registration,
        'investigation_fee': Decimal('50000'),  # CBL investigation fee
        'step': 7,
        'total_steps': 7,
    }
    
    return render(request, 'lenders/registration/submit.html', context)


@login_required
def compliance_dashboard(request):
    #Lender dashboard with compliance status
    
    profile = get_object_or_404(LenderProfile, user=request.user)
    
    context = {
        'profile': profile,
        'compliance_score': profile.get_compliance_score(),
    }
    
    # Add registration progress if applicable
    if hasattr(profile, 'cbl_registration'):
        reg = profile.cbl_registration
        context['registration'] = reg
        context['completion'] = reg.get_completion_percentage()
        
        workflow = RegistrationWorkflowService(reg)
        context['next_actions'] = workflow.get_next_actions()[:5]
    
    # Add ongoing compliance if licensed
    if profile.is_licensed:
        from .services import OngoingComplianceService
        compliance_service = OngoingComplianceService(profile)
        
        context['upcoming_deadlines'] = compliance_service.get_upcoming_deadlines()
        context['overdue_reports'] = compliance_service.get_overdue_reports()
    
    return render(request, 'compliance_dashboard.html', context)
"""

"""
from django.shortcuts import render
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required

from compliance.forms import *
from .models import ComplianceFunction, Director, LenderComplianceRecord, RegistrationDocument, RequirementEvaluatorService
from services.document_status import DocumentStatusService


@login_required
def compliance_dashboard(request):
    registration = LenderComplianceRecord.objects.filter(applicant=request.user).first()

    if not registration:
        return redirect('compliance:compliance_tier_selection')

    evaluator = RequirementEvaluatorService(registration)
    doc_service = DocumentStatusService(registration)

    return render(request, 'compliance_dashboard.html', {
        'registration': registration,
        'completion': evaluator.completion_percentage(),
        'missing_docs': doc_service.missing_documents(),
        'next_action': evaluator.next_action(),
        'next_url': evaluator.next_url(),
    })



@login_required
def compliance_tier_selection(request):
    registration, created = LenderComplianceRecord.objects.get_or_create(applicant=request.user)

    if request.method == 'POST':
        form = TierSelectionForm(request.POST, instance=registration)
        if form.is_valid():
            form.save()
            registration.current_step = 'company_info'
            registration.save()
            return redirect('compliance:compliance_company_info')

    else:
        form = TierSelectionForm(instance=registration)

    return render(request, 'compliance_tier_selection.html', {
        'form': form,
    })


@login_required
def compliance_company_info(request):
    registration = get_object_or_404(ComplianceFunction, applicant=request.user)

    if request.method == 'POST':
        form = CompanyInfoForm(request.POST, request.FILES, instance=registration)
        if form.is_valid():
            form.save()
            registration.current_step = 'directors'
            registration.save()
            return redirect('compliance:compliance_directors')

    else:
        form = CompanyInfoForm(instance=registration)

    return render(request, 'compliance_company_info.html', {
        'form': form,
    })


@login_required
def compliance_directors(request):
    registration = get_object_or_404(Director, applicant=request.user)

    if request.method == 'POST':
        form = DirectorForm(request.POST, request.FILES)
        if form.is_valid():
            director = form.save(commit=False)
            director.registration = registration
            director.save()

            evaluator = RequirementEvaluatorService(registration)
            if evaluator.directors_complete():
                registration.current_step = 'governance'
                registration.save()
                return redirect('compliance:compliance_governance')

    else:
        form = DirectorForm()

    return render(request, 'compliance_directors.html', {
        'form': form,
        'directors': registration.directors.all()
    })


@login_required
def compliance_governance(request):
    registration = get_object_or_404(ComplianceFunction, applicant=request.user)

    if request.method == 'POST':
        f_form = FinanceOfficerForm(request.POST, request.FILES, instance=registration.finance_officer)
        c_form = ComplianceOfficerForm(request.POST, request.FILES, instance=registration.compliance_officer)

        if f_form.is_valid() and c_form.is_valid():
            f_form.save()
            c_form.save()
            registration.current_step = 'documents'
            registration.save()
            return redirect('compliance:compliance_documents')

    else:
        f_form = FinanceOfficerForm(instance=registration.finance_officer)
        c_form = ComplianceOfficerForm(instance=registration.compliance_officer)

    return render(request, 'compliance_governance.html', {
        'finance_form': f_form,
        'compliance_form': c_form,
    })


@login_required
def compliance_documents(request):
    registration = get_object_or_404(LenderComplianceRecord, applicant=request.user)
    doc_service = RegistrationDocument(registration)

    if request.method == 'POST':
        form = ComplianceDocumentForm(request.POST, request.FILES)
        files = request.FILES.getlist('documents')

        if form.is_valid():
            doc_service.save_documents(files)

            if doc_service.all_required_uploaded():
                registration.current_step = 'review'
                registration.save()
                return redirect('compliance:compliance_review')

    else:
        form = ComplianceDocumentForm()

    return render(request, 'compliance_documents.html', {
        'form': form,
        'missing': doc_service.missing_documents(),
    })


@login_required
def compliance_review(request):
    registration = get_object_or_404(LenderComplianceRecord, applicant=request.user)
    evaluator = RequirementEvaluatorService(registration)

    if request.method == 'POST':
        form = FinalReviewForm(request.POST)
        if form.is_valid():
            registration.current_step = 'submitted'
            registration.save()
            return redirect('compliance:compliance_dashboard')

    else:
        form = FinalReviewForm()

    return render(request, 'compliance_review.html', {
        'form': form,
        'requirements': evaluator.list_requirements(),
        'completion': evaluator.completion_percentage(),
    })

"""