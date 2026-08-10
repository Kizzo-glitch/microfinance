
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from datetime import datetime
from django.urls import reverse
from django.core.exceptions import ObjectDoesNotExist

from .compliace_services import ComplianceDashboardService
from .models import ComplianceProfile

# Import the document generators
from .document_generators import (
    FinancialProjectionModel,
    ScheduleIIGenerator,
    FitProperGenerator,
    ScheduleIGenerator,  
    BusinessPlanGenerator,  
    AMLPolicyGenerator,
    #RiskManualGenerator,
    #GovernanceDocumentGenerator,
    #GovernanceDocumentGenerator,
    #GovernanceDocumentGenerator,  
)


class DocumentGenerationService:
    """
    Service for automated document generation in the CBL compliance process
    """
    
    # Documents that can be auto-generated - mapped to exact ComplianceProfile field names
    GENERATABLE_DOCUMENTS = {
        'schedule_i': {
            'generator_class': ScheduleIGenerator,
            'confidence_threshold': 0.85,
            'required_data': ['company_info', 'financial_data'],
            'estimated_time': 120,  # seconds
        },
        'schedule_ii': {
            'generator_class': ScheduleIIGenerator,
            'confidence_threshold': 0.90,
            'required_data': ['company_info', 'personnel_full', 'ownership_data'],
            'estimated_time': 180,
        },
        'business_plan': {
            'generator_class': BusinessPlanGenerator,
            'confidence_threshold': 0.75,
            'required_data': ['company_info', 'financial_data', 'market_data'],
            'estimated_time': 240,
        },
        'aml_cft_manual': {
            'generator_class': AMLPolicyGenerator,
            'confidence_threshold': 0.90,
            'required_data': ['company_info', 'cbl_tier'],
            'estimated_time': 150,
        },
        'risk_management_policy': {
            'generator_class': AMLPolicyGenerator, #RiskManualGenerator,
            'confidence_threshold': 0.85,
            'required_data': ['company_info', 'financial_data', 'business_activities'],
            'estimated_time': 180,
        },
        'internal_audit_charter': {
            'generator_class': AMLPolicyGenerator,
            'confidence_threshold': 0.80,
            'required_data': ['company_info', 'cbl_tier'],
            'estimated_time': 120,
        },
        'audit_committee_charter': {
            'generator_class': AMLPolicyGenerator,
            'confidence_threshold': 0.80,
            'required_data': ['company_info', 'cbl_tier', 'personnel_basic'],
            'estimated_time': 120,
        },
        'credit_committee_charter': {
            'generator_class': AMLPolicyGenerator,
            'confidence_threshold': 0.80,
            'required_data': ['company_info', 'cbl_tier', 'personnel_basic'],
            'estimated_time': 120,
        }
    }
    
    def __init__(self, lender):
        self.lender = lender
        try:
            self.compliance = lender.compliance
        except ObjectDoesNotExist:
            self.compliance, _ = ComplianceProfile.objects.get_or_create(lender=lender)
        
        self.personnel = list(lender.personnel.all())
        
        # Cache for required docs to prevent multiple calls
        self._required_docs_cache = None
        
    def can_generate_any(self) -> bool:
        """Check if any documents can be generated"""
        readiness = self.get_readiness_status()
        return readiness['can_generate_count'] > 0
    
    def get_readiness_status(self) -> Dict:
        """Get overall document generation readiness status"""
        required_docs = self._get_required_docs()
        
        generatable_count = 0
        total_confidence = 0.0
        missing_data_categories = set()
        generatable_docs = []
        
        for doc_field in required_docs:
            if self.can_generate_document(doc_field):
                generatable_count += 1
                confidence = self.get_generation_confidence(doc_field)
                total_confidence += confidence
                generatable_docs.append({
                    'field': doc_field,
                    'confidence': confidence
                })
            else:
                missing_data = self._get_missing_data_for_document(doc_field)
                missing_data_categories.update(missing_data)
        
        avg_confidence = (total_confidence / generatable_count) if generatable_count > 0 else 0
        completeness = self._calculate_profile_completeness()
        
        # Estimate generation time based on document complexity
        estimated_time = self._estimate_generation_time_detailed(generatable_docs)
        
        return {
            'can_generate_count': generatable_count,
            'generatable_docs': generatable_docs,
            'total_required': len(required_docs),
            'completeness': int(completeness * 100),
            'average_confidence': round(avg_confidence, 2),
            'estimated_time': estimated_time,
            'missing_data_categories': list(missing_data_categories),
            'ready': generatable_count > 0 and completeness > 0.6,
            'profile_strength': self._assess_profile_strength(),
        }
    
    def can_generate_document(self, field_name: str) -> bool:
        """Check if specific document can be generated"""
        if field_name not in self.GENERATABLE_DOCUMENTS:
            return False
        
        generator_info = self.GENERATABLE_DOCUMENTS[field_name]
        confidence = self.get_generation_confidence(field_name)
        threshold = generator_info['confidence_threshold']
        
        return confidence >= threshold
    
    def get_generation_confidence(self, field_name: str) -> float:
        """Get confidence score (0.0-1.0) for generating specific document"""
        if field_name not in self.GENERATABLE_DOCUMENTS:
            return 0.0
        
        generator_info = self.GENERATABLE_DOCUMENTS[field_name]
        required_data = generator_info['required_data']
        data_availability = self._assess_data_availability(required_data)
        
        # Calculate weighted confidence based on data criticality
        weights = self._get_data_category_weights(field_name)
        total_score = 0.0
        total_weight = 0.0
        
        for data_category in required_data:
            score = data_availability.get(data_category, 0.0)
            weight = weights.get(data_category, 1.0)
            total_score += score * weight
            total_weight += weight
        
        confidence = total_score / total_weight if total_weight > 0 else 0.0
        
        # Apply document-specific adjustments
        confidence = self._apply_document_specific_adjustments(field_name, confidence)
        
        return min(max(confidence, 0.0), 1.0)  # Clamp to 0-1 range
    
    def _get_required_docs(self) -> List[str]:
        """Get unique list of required document fields based on CBL tier - PREVENTS INFINITE LOOPS"""
        if self._required_docs_cache is not None:
            return self._required_docs_cache    
        try:
            dashboard_service = ComplianceDashboardService(self.lender)
            required_docs = dashboard_service._get_required_docs()
            
            # Ensure we have a list and remove any duplicates while preserving order
            if isinstance(required_docs, (set, frozenset)):
                required_docs = list(required_docs)
            
            # Remove duplicates while preserving order
            seen = set()
            unique_docs = []
            for doc in required_docs:
                if doc not in seen and doc:  # Also filter out empty strings
                    seen.add(doc)
                    unique_docs.append(doc)
            
            # Cache the result to prevent multiple calls
            self._required_docs_cache = unique_docs
            return unique_docs
            
        except Exception as e:
            # Fallback to basic required docs if service fails
            print(f"Warning: Could not get required docs from dashboard service: {e}")
            basic_docs = self._get_fallback_required_docs()
            self._required_docs_cache = basic_docs
            return basic_docs
    
    def _get_fallback_required_docs(self) -> List[str]:
        """Fallback required documents if dashboard service fails"""
        tier = self.lender.cbl_tier
        
        base_docs = [
            'schedule_i',
            'schedule_ii',
            'business_plan',
            'aml_cft_manual',
            'tax_clearance_institution'
        ]
        
        if tier == 'tier1':
            return base_docs + [
                'memorandum_articles',
                'board_resolution',
                'audit_committee_charter', 
                'credit_committee_charter',
                'risk_management_policy'
            ]
        elif tier == 'tier2':
            return base_docs + [
                'memorandum_articles',
                'board_resolution',
                'internal_audit_charter',
                'risk_management_policy'
            ]
        elif tier == 'tier3':
            return base_docs + [
                'company_profile'
            ]
        
        return base_docs
    
    def _assess_data_availability(self, required_data: List[str]) -> Dict[str, float]:
        """Assess availability of required data categories"""
        availability = {}
        
        for data_category in required_data:
            if data_category == 'company_info':
                availability[data_category] = self._assess_company_info_completeness()
            elif data_category == 'financial_data':
                availability[data_category] = self._assess_financial_data_completeness()
            elif data_category == 'personnel_basic':
                availability[data_category] = self._assess_personnel_basic_completeness()
            elif data_category == 'personnel_full':
                availability[data_category] = self._assess_personnel_full_completeness()
            elif data_category == 'ownership_data':
                availability[data_category] = self._assess_ownership_data_completeness()
            elif data_category == 'market_data':
                availability[data_category] = self._assess_market_data_completeness()
            elif data_category == 'cbl_tier':
                availability[data_category] = 1.0 if self.lender.cbl_tier else 0.0
            elif data_category == 'business_activities':
                availability[data_category] = self._assess_business_activities_completeness()
            else:
                availability[data_category] = 0.5  # Default moderate availability
        
        return availability
    
    def _assess_company_info_completeness(self) -> float:
        """Assess completeness of basic company information"""
        required_fields = [
            'company_name', 'registration_number', 'date_of_establishment',
            'physical_address', 'business_email', 'phone_number', 'cbl_tier'
        ]
        
        completed = 0
        for field in required_fields:
            value = getattr(self.lender, field, None)
            if value and str(value).strip():
                completed += 1
        
        # Bonus points for optional but valuable fields
        optional_fields = ['postal_address', 'website', 'district']
        for field in optional_fields:
            value = getattr(self.lender, field, None)
            if value and str(value).strip():
                completed += 0.5
        
        return min(completed / len(required_fields), 1.0)
    
    def _assess_financial_data_completeness(self) -> float:
        """Assess completeness of financial information"""
        score = 0.0
        
        # Critical fields
        if self.lender.stated_capital and self.lender.stated_capital > 0:
            score += 0.4
        if self.lender.total_assets and self.lender.total_assets > 0:
            score += 0.3
        
        # Additional financial data
        financial_fields = ['revenue_last_year', 'net_income_last_year', 'number_of_employees']
        for field in financial_fields:
            value = getattr(self.lender, field, None)
            if value and (isinstance(value, (int, float)) and value > 0):
                score += 0.1
        
        return min(score, 1.0)
    
    def _assess_personnel_basic_completeness(self) -> float:
        """Assess basic personnel information completeness"""
        if not self.personnel:
            return 0.0
        
        # Check if minimum required personnel exists
        required_roles = {'ceo'}
        if self.lender.cbl_tier in ['tier1', 'tier2']:
            required_roles.update(['finance_officer', 'compliance_officer'])
        
        existing_roles = {p.role for p in self.personnel if p.role}
        role_coverage = len(required_roles.intersection(existing_roles)) / len(required_roles)
        
        # Check basic info completeness for existing personnel
        basic_fields = ['full_name', 'role', 'nationality']
        total_score = 0
        
        for person in self.personnel:
            person_score = 0
            for field in basic_fields:
                value = getattr(person, field, None)
                if value and str(value).strip():
                    person_score += 1
            total_score += person_score / len(basic_fields)
        
        personnel_quality = total_score / len(self.personnel) if self.personnel else 0.0
        
        return (role_coverage * 0.6) + (personnel_quality * 0.4)
    
    def _assess_personnel_full_completeness(self) -> float:
        """Assess full personnel information completeness"""
        if not self.personnel:
            return 0.0
        
        required_fields = [
            'full_name', 'role', 'nationality', 'date_of_birth', 
            'id_or_passport_number', 'professional_qualifications',
            'employment_history_10_years'
        ]
        
        document_fields = [
            'curriculum_vitae', 'police_clearance', 'tax_clearance_individual',
            'character_ref_1', 'character_ref_2'
        ]
        
        total_score = 0
        for person in self.personnel:
            # Basic info score
            basic_score = 0
            for field in required_fields:
                value = getattr(person, field, None)
                if value and str(value).strip():
                    basic_score += 1
            
            # Document upload score
            doc_score = 0
            for field in document_fields:
                if getattr(person, field, None):
                    doc_score += 1
            
            # Combined score for this person
            person_total = (basic_score / len(required_fields)) * 0.7 + (doc_score / len(document_fields)) * 0.3
            total_score += person_total
        
        return total_score / len(self.personnel)
    
    def _assess_ownership_data_completeness(self) -> float:
        """Assess ownership structure information completeness"""
        score = 0.5  # Base score for having basic company info
        
        # Check if we have detailed company structure info
        if hasattr(self.lender, 'shareholders') and self.lender.shareholders.exists():
            score += 0.3
        
        # Check if beneficial ownership is documented
        if hasattr(self.compliance, 'beneficial_ownership_declared'):
            score += 0.2
        
        return min(score, 1.0)
    
    def _assess_market_data_completeness(self) -> float:
        """Assess market and business model information"""
        score = 0.3  # Base score for tier information
        
        # Target market information
        if hasattr(self.lender, 'target_market_description') and self.lender.target_market_description:
            score += 0.25
        if hasattr(self.lender, 'target_market_size') and self.lender.target_market_size:
            score += 0.25
        
        # Geographic coverage
        if hasattr(self.lender, 'geographic_coverage') and self.lender.geographic_coverage:
            score += 0.2
        
        return min(score, 1.0)
    
    def _assess_business_activities_completeness(self) -> float:
        """Assess business activities information"""
        score = 0.4 if self.lender.cbl_tier else 0.0
        
        # Product/service information
        if hasattr(self.lender, 'primary_products') and self.lender.primary_products:
            score += 0.3
        
        # Interest rates and terms
        if hasattr(self.lender, 'interest_rate_range') and self.lender.interest_rate_range:
            score += 0.3
        
        return min(score, 1.0)
    
    def _get_data_category_weights(self, field_name: str) -> Dict[str, float]:
        """Get importance weights for different data categories by document type"""
        weights = {
            'schedule_i': {
                'company_info': 1.2,
                'financial_data': 1.0,
                'personnel_basic': 0.8,
            },
            'schedule_ii': {
                'company_info': 1.0,
                'personnel_full': 1.3,
                'ownership_data': 1.1,
            },
            'business_plan': {
                'company_info': 0.9,
                'financial_data': 1.3,
                'market_data': 1.2,
            },
            'aml_cft_manual': {
                'company_info': 1.0,
                'cbl_tier': 1.5,
            }
        }
        
        return weights.get(field_name, {})
    
    def _apply_document_specific_adjustments(self, field_name: str, confidence: float) -> float:
        """Apply document-specific confidence adjustments"""
        # Schedule II requires comprehensive personnel info
        if field_name == 'schedule_ii':
            director_count = sum(1 for p in self.personnel if p.role == 'director')
            if self.lender.cbl_tier in ['tier1', 'tier2'] and director_count < 5:
                confidence *= 0.8  # Reduce confidence if insufficient directors
        
        # Business plan requires substantial financial data
        if field_name == 'business_plan':
            if not (self.lender.stated_capital and self.lender.stated_capital > 500000):
                confidence *= 0.9  # Slight reduction for low capital
        
        # AML policy is mostly template-based, boost confidence
        if field_name == 'aml_cft_manual':
            confidence = min(confidence * 1.1, 1.0)
        
        return confidence
    
    def _calculate_profile_completeness(self) -> float:
        """Calculate overall profile completeness for generation"""
        categories = ['company_info', 'financial_data', 'personnel_basic']
        availability = self._assess_data_availability(categories)
        
        weights = {'company_info': 0.4, 'financial_data': 0.3, 'personnel_basic': 0.3}
        total_score = sum(availability[cat] * weights[cat] for cat in categories)
        
        return total_score
    
    def _assess_profile_strength(self) -> str:
        """Assess overall profile strength for user feedback"""
        completeness = self._calculate_profile_completeness()
        
        if completeness >= 0.9:
            return "Excellent"
        elif completeness >= 0.75:
            return "Good" 
        elif completeness >= 0.6:
            return "Fair"
        elif completeness >= 0.4:
            return "Poor"
        else:
            return "Incomplete"
    
    def _estimate_generation_time_detailed(self, generatable_docs: List[Dict]) -> str:
        """Estimate time required for document generation with details"""
        if not generatable_docs:
            return "N/A"
        
        total_seconds = sum(
            self.GENERATABLE_DOCUMENTS[doc['field']]['estimated_time'] 
            for doc in generatable_docs 
            if doc['field'] in self.GENERATABLE_DOCUMENTS
        )
        
        if total_seconds < 120:
            return "1-2 minutes"
        elif total_seconds < 300:
            return "3-5 minutes"
        elif total_seconds < 600:
            return "5-10 minutes"
        else:
            return "10+ minutes"
    
    def _get_missing_data_for_document(self, field_name: str) -> List[str]:
        """Get list of missing data categories for specific document"""
        if field_name not in self.GENERATABLE_DOCUMENTS:
            return []
        
        generator_info = self.GENERATABLE_DOCUMENTS[field_name]
        required_data = generator_info['required_data']
        data_availability = self._assess_data_availability(required_data)
        
        missing = []
        threshold = 0.5  # 50% completeness threshold
        
        for data_category, availability in data_availability.items():
            if availability < threshold:
                missing.append(data_category)
        
        return missing
    
    # Document Generation Methods
    def generate_schedule_ii(self) -> Dict:
        """Generate Schedule II Information Sheet"""
        try:
            lender_data = self._extract_comprehensive_lender_data()
            generator = ScheduleIIGenerator(lender_data)
            document = generator.generate()
            
            return {
                'success': True,
                'document': document,
                'filename': f'Schedule_II_{self.lender.company_name.replace(" ", "_")}_{datetime.now().strftime("%Y%m%d")}.docx',
                'generation_time': datetime.now(),
                'metadata': {
                    'pages_estimated': '8-10',
                    'sections': 7,
                    'confidence': self.get_generation_confidence('schedule_ii')
                }
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'Failed to generate Schedule II: {str(e)[:100]}...'
            }
    
    def generate_business_plan(self) -> Dict:
        """Generate comprehensive business plan using financial projections"""
        try:
            lender_data = self._extract_comprehensive_lender_data()
            
            # Generate financial projections first
            projection_model = FinancialProjectionModel(lender_data)
            projections = projection_model.generate_complete_projections()
            
            # TODO: Implement BusinessPlanGenerator
            # For now, return projections that can be used to build the plan
            
            return {
                'success': True,
                'projections': projections,
                'filename': f'Business_Plan_{self.lender.company_name.replace(" ", "_")}_{datetime.now().strftime("%Y%m%d")}.docx',
                'generation_time': datetime.now(),
                'metadata': {
                    'pages_estimated': '15-20',
                    'sections': 8,
                    'confidence': self.get_generation_confidence('business_plan')
                }
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'Failed to generate business plan: {str(e)[:100]}...'
            }
    
    def generate_fit_proper_forms(self) -> Dict:
        """Generate fit & proper forms for all personnel"""
        try:
            generated_forms = {}
            
            for person in self.personnel:
                personnel_data = self._extract_personnel_data(person)
                lender_context = self._extract_comprehensive_lender_data()
                
                generator = FitProperGenerator(personnel_data, lender_context)
                
                document = generator.generate()
                assessment = generator.generate_assessment_summary()
                
                generated_forms[person.id] = {
                    'document': document,
                    'assessment': assessment,
                    'filename': f'Fit_Proper_{person.full_name.replace(" ", "_")}_{datetime.now().strftime("%Y%m%d")}.docx',
                    'metadata': {
                        'pages_estimated': '10-12',
                        'overall_rating': assessment.get('overall_rating', 'Unknown')
                    }
                }
            
            return {
                'success': True,
                'forms': generated_forms,
                'count': len(generated_forms),
                'generation_time': datetime.now(),
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'Failed to generate fit & proper forms: {str(e)[:100]}...'
            }
    
    def _extract_comprehensive_lender_data(self) -> Dict:
        """Extract comprehensive lender data for document generation"""
        return {
            # Basic company information
            'company_name': self.lender.company_name or '',
            'registration_number': self.lender.registration_number or '',
            'date_of_establishment': self.lender.date_of_establishment,
            'physical_address': self.lender.physical_address or '',
            'postal_address': getattr(self.lender, 'postal_address', ''),
            'business_email': self.lender.business_email or '',
            'phone_number': self.lender.phone_number or '',
            'website': getattr(self.lender, 'website', ''),
            
            # Financial information
            'cbl_tier': self.lender.cbl_tier or '',
            'stated_capital': float(self.lender.stated_capital or 0),
            'total_assets': float(self.lender.total_assets or 0),
            
            # Business information
            'target_market_size': getattr(self.lender, 'target_market_size', 1000),
            'district': getattr(self.lender, 'district', 'Maseru'),
            
            # Leadership
            'ceo_first_name': self.lender.ceo_first_name or '',
            'ceo_last_name': self.lender.ceo_last_name or '',
            
            # Related data
            'personnel': [self._extract_personnel_data(p) for p in self.personnel],
            'compliance_data': self._extract_compliance_data(),
            
            # Generation metadata
            'generation_date': datetime.now(),
            'profile_completeness': self._calculate_profile_completeness(),
        }
    
    def _extract_personnel_data(self, person) -> Dict:
        """Extract personnel data for document generation"""
        return {
            'id': person.id,
            'full_name': person.full_name or '',
            'role': person.role or '',
            'nationality': person.nationality or '',
            'country_of_residence': person.country_of_residence or '',
            'date_of_birth': person.date_of_birth,
            'place_of_birth': getattr(person, 'place_of_birth', ''),
            'id_or_passport_number': person.id_or_passport_number or '',
            'residential_address': getattr(person, 'residential_address', ''),
            'business_address': getattr(person, 'business_address', ''),
            'professional_qualifications': person.professional_qualifications or '',
            'employment_history_10_years': person.employment_history_10_years or '',
            'other_affiliations': person.other_affiliations or '',
            'family_business_affiliations': person.family_business_affiliations or '',
            
            # Legal declarations
            'criminal_conviction': getattr(person, 'criminal_conviction', False),
            'criminal_conviction_details': getattr(person, 'criminal_conviction_details', ''),
            'legal_proceedings': getattr(person, 'legal_proceedings', False),
            'legal_proceedings_details': getattr(person, 'legal_proceedings_details', ''),
            'bankruptcy': getattr(person, 'bankruptcy', False),
            'bankruptcy_details': getattr(person, 'bankruptcy_details', ''),
            'ever_disqualified': getattr(person, 'ever_disqualified', False),
            'disqualification_details': getattr(person, 'disqualification_details', ''),
            'dismissed_or_resigned': getattr(person, 'dismissed_or_resigned', False),
            'dismissal_details': getattr(person, 'dismissal_details', ''),
            
            # Board-specific fields
            'is_chairman': getattr(person, 'is_chairman', False),
            'is_non_executive': getattr(person, 'is_non_executive', False),
            
            # Document upload status
            'fit_proper_form': bool(person.fit_proper_form),
            'curriculum_vitae': bool(person.curriculum_vitae),
            'police_clearance': bool(person.police_clearance),
            'tax_clearance_individual': bool(person.tax_clearance_individual),
            'id_copy': bool(person.id_copy),
            'statement_assets_liabilities': bool(person.statement_assets_liabilities),
            'character_ref_1': bool(person.character_ref_1),
            'character_ref_2': bool(person.character_ref_2),
            'financial_ref_1': bool(person.financial_ref_1),
            'financial_ref_2': bool(person.financial_ref_2),
        }
    
    def _extract_compliance_data(self) -> Dict:
        """Extract compliance profile data"""
        return {
            'current_stage': self.compliance.current_stage or '',
            'submission_date': self.compliance.submission_date,
            'investigation_fee_paid': getattr(self.compliance, 'investigation_fee_paid', False),
            'registration_fee_paid': getattr(self.compliance, 'registration_fee_paid', False),
            'license_fee_paid': getattr(self.compliance, 'license_fee_paid', False),
            
            # Document upload status
            'schedule_i': bool(self.compliance.schedule_i),
            'schedule_ii': bool(self.compliance.schedule_ii),
            'business_plan': bool(self.compliance.business_plan),
            'aml_cft_manual': bool(self.compliance.aml_cft_manual),
            'risk_management_policy': bool(getattr(self.compliance, 'risk_management_policy', None)),
        }