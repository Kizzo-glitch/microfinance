"""
Document Generation Service
Integrates FinancialProjectionModel, ScheduleIIGenerator, and FitProperGenerator
with the Django ComplianceProfileDetailView
"""

from typing import Dict, List, Optional, Tuple
from decimal import Decimal
from datetime import datetime
from django.urls import reverse

from .models import ComplianceProfile

from .compliace_services import ComplianceDashboardService

from .document_generators2 import FinancialProjectionModel, ScheduleIIGenerator, FitProperGenerator, ScheduleIGenerator



class DocumentGenerationService:
    """
    Service for automated document generation in the CBL compliance process
    Integrates with ComplianceProfileDetailView and ComplianceDashboardService
    """
    
    # Documents that can be auto-generated
    GENERATABLE_DOCUMENTS = {
        'schedule_i': {
            'generator_class': ScheduleIGenerator,  # To be implemented
            'confidence_threshold': 0.8,
            'required_data': ['company_info', 'financial_data', 'personnel_basic'],
        },
        'schedule_ii': {
            'generator_class': ScheduleIIGenerator,
            'confidence_threshold': 0.9,
            'required_data': ['company_info', 'personnel_full', 'ownership_data'],
        },
        'business_plan': {
            'generator_class': 'BusinessPlanGenerator',  # Uses FinancialProjectionModel
            'confidence_threshold': 0.7,
            'required_data': ['company_info', 'financial_data', 'market_data'],
        },
        'aml_policy': {
            'generator_class': 'AMLPolicyGenerator',  # To be implemented
            'confidence_threshold': 0.9,
            'required_data': ['company_info', 'cbl_tier'],
        },
        'risk_manual': {
            'generator_class': 'RiskManualGenerator',  # To be implemented
            'confidence_threshold': 0.8,
            'required_data': ['company_info', 'financial_data', 'business_activities'],
        },
        'fit_proper_forms': {
            'generator_class': FitProperGenerator,
            'confidence_threshold': 0.8,
            'required_data': ['personnel_full'],
        }
    }
    
    # Mapping of ComplianceProfile field names to generator types
    FIELD_TO_GENERATOR = {
        'schedule_i': 'schedule_i',
        'schedule_ii': 'schedule_ii',
        'business_plan': 'business_plan',
        'aml_cft_manual': 'aml_policy',
        'risk_management_policy': 'risk_manual',
        'memorandum_articles': 'legal_documents',  # To be implemented
        'board_resolution': 'legal_documents',
        'audit_committee_charter': 'governance_documents',  # To be implemented
        'credit_committee_charter': 'governance_documents',
    }
    
    def __init__(self, lender):
        self.lender = lender
        try:
            self.compliance = lender.compliance
        except: 
            self.compliance, _ = ComplianceProfile.objects.get_or_create(lender=lender)
        
        self.personnel = list(lender.personnel.all())
        
    def can_generate_any(self) -> bool:
        """Check if any documents can be generated"""
        readiness = self.get_readiness_status()
        return readiness['can_generate_count'] > 0
    """
    def get_readiness_status(self) -> Dict:
        required_docs = self._get_required_docs()
        
        generatable_count = 0
        total_confidence = 0.0
        missing_data_categories = set()
        
        for doc_field in required_docs:
            if self.can_generate_document(doc_field):
                generatable_count += 1
                total_confidence += self.get_generation_confidence(doc_field)
            else:
                # Track what data is missing
                missing_data = self._get_missing_data_for_document(doc_field)
                missing_data_categories.update(missing_data)
        
        avg_confidence = (total_confidence / generatable_count) if generatable_count > 0 else 0
        completeness = self._calculate_profile_completeness()
        
        # Estimate generation time based on document complexity
        estimated_time = self._estimate_generation_time(generatable_count)
        
        return {
            'can_generate_count': generatable_count,
            'total_required': len(required_docs),
            'completeness': int(completeness * 100),
            'average_confidence': avg_confidence,
            'estimated_time': estimated_time,
            'missing_data_categories': list(missing_data_categories),
            'ready': generatable_count > 0 and completeness > 0.6,
        }
        """
    def get_readiness_status(self) -> Dict:
        """Get overall document generation readiness status"""
        required_docs = self._get_required_docs()
        
        generatable_count = 0
        total_confidence = 0.0
        missing_data_categories = set()
        generatable_docs = []  # Track which docs can be generated
        avg_confidence = (total_confidence / generatable_count) if generatable_count > 0 else 0
        completeness = self._calculate_profile_completeness()
        estimated_time = self._estimate_generation_time(generatable_count)
        
        for doc_field in required_docs:
            if self.can_generate_document(doc_field):
                generatable_count += 1
                total_confidence += self.get_generation_confidence(doc_field)
                generatable_docs.append(doc_field)  # Add this line
            else:
                missing_data = self._get_missing_data_for_document(doc_field)
                missing_data_categories.update(missing_data)
        
        return {
            'can_generate_count': generatable_count,
            'generatable_docs': generatable_docs,  # Add this line
            'total_required': len(required_docs),
            'completeness': int(completeness * 100),
            'average_confidence': avg_confidence,
            'estimated_time': estimated_time,
            'missing_data_categories': list(missing_data_categories),
            'ready': generatable_count > 0 and completeness > 0.6,
        }
    
    def can_generate_document(self, field_name: str) -> bool:
        """Check if specific document can be generated"""
        generator_type = self.FIELD_TO_GENERATOR.get(field_name)
        if not generator_type:
            return False
        
        generator_info = self.GENERATABLE_DOCUMENTS.get(generator_type)
        if not generator_info:
            return False
        
        # Check if required data is available
        confidence = self.get_generation_confidence(field_name)
        threshold = generator_info['confidence_threshold']
        
        return confidence >= threshold
    
    def get_generation_confidence(self, field_name: str) -> float:
        """Get confidence score (0.0-1.0) for generating specific document"""
        generator_type = self.FIELD_TO_GENERATOR.get(field_name)
        if not generator_type:
            return 0.0
        
        generator_info = self.GENERATABLE_DOCUMENTS.get(generator_type)
        if not generator_info:
            return 0.0
        
        required_data = generator_info['required_data']
        data_availability = self._assess_data_availability(required_data)
        
        # Calculate confidence based on available data
        total_score = 0.0
        for data_category in required_data:
            score = data_availability.get(data_category, 0.0)
            total_score += score
        
        return total_score / len(required_data) if required_data else 0.0
    
    def _get_required_docs(self) -> List[str]:
        """Get list of required document fields based on CBL tier"""
        # Import here to avoid circular imports
        dashboard_service = ComplianceDashboardService(self.lender)
        return list(dashboard_service._get_required_docs())
    
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
            if getattr(self.lender, field, None):
                completed += 1
        
        return completed / len(required_fields)
    
    def _assess_financial_data_completeness(self) -> float:
        """Assess completeness of financial information"""
        required_fields = [
            'stated_capital', 'total_assets'
        ]
        
        completed = 0
        for field in required_fields:
            value = getattr(self.lender, field, None)
            if value and value > 0:
                completed += 1
        
        # Bonus points for additional financial data
        bonus_fields = ['revenue_last_year', 'net_income_last_year']
        for field in bonus_fields:
            if getattr(self.lender, field, None):
                completed += 0.5
        
        return min(completed / len(required_fields), 1.0)
    
    def _assess_personnel_basic_completeness(self) -> float:
        """Assess basic personnel information completeness"""
        if not self.personnel:
            return 0.0
        
        # Check if at least CEO is added
        ceo_exists = any(p.role == 'ceo' for p in self.personnel)
        if not ceo_exists:
            return 0.2
        
        # Check basic info for key personnel
        basic_fields = ['full_name', 'role', 'nationality']
        total_score = 0
        
        for person in self.personnel:
            person_score = 0
            for field in basic_fields:
                if getattr(person, field, None):
                    person_score += 1
            total_score += person_score / len(basic_fields)
        
        return min(total_score / len(self.personnel), 1.0)
    
    def _assess_personnel_full_completeness(self) -> float:
        """Assess full personnel information completeness"""
        if not self.personnel:
            return 0.0
        
        required_fields = [
            'full_name', 'role', 'nationality', 'date_of_birth', 
            'id_or_passport_number', 'professional_qualifications',
            'employment_history_10_years'
        ]
        
        total_score = 0
        for person in self.personnel:
            person_score = 0
            for field in required_fields:
                if getattr(person, field, None):
                    person_score += 1
            total_score += person_score / len(required_fields)
        
        return total_score / len(self.personnel) if self.personnel else 0.0
    
    def _assess_ownership_data_completeness(self) -> float:
        """Assess ownership structure information completeness"""
        # For now, return moderate score - would need ownership models
        return 0.7 if self.lender.company_name else 0.3
    
    def _assess_market_data_completeness(self) -> float:
        """Assess market and business model information"""
        score = 0.5  # Base score for tier information
        
        # Check if target market info is available
        if hasattr(self.lender, 'target_market_size') and self.lender.target_market_size:
            score += 0.3
        
        # Check if business description exists
        if hasattr(self.lender, 'business_description') and self.lender.business_description:
            score += 0.2
        
        return min(score, 1.0)
    
    def _assess_business_activities_completeness(self) -> float:
        """Assess business activities information"""
        score = 0.4  # Base score for tier-based activities
        
        if self.lender.cbl_tier:
            score += 0.4
        
        if hasattr(self.lender, 'primary_business_activities'):
            score += 0.2
        
        return min(score, 1.0)
    
    def _get_missing_data_for_document(self, field_name: str) -> List[str]:
        """Get list of missing data categories for specific document"""
        generator_type = self.FIELD_TO_GENERATOR.get(field_name)
        if not generator_type:
            return []
        
        generator_info = self.GENERATABLE_DOCUMENTS.get(generator_type)
        if not generator_info:
            return []
        
        required_data = generator_info['required_data']
        data_availability = self._assess_data_availability(required_data)
        
        missing = []
        for data_category, availability in data_availability.items():
            if availability < 0.5:  # Less than 50% complete
                missing.append(data_category)
        
        return missing
    
    def _calculate_profile_completeness(self) -> float:
        """Calculate overall profile completeness for generation"""
        categories = ['company_info', 'financial_data', 'personnel_basic']
        availability = self._assess_data_availability(categories)
        
        total = sum(availability.values())
        return total / len(categories)
    
    def _estimate_generation_time(self, document_count: int) -> str:
        """Estimate time required for document generation"""
        if document_count == 0:
            return "N/A"
        elif document_count <= 2:
            return "1-2 minutes"
        elif document_count <= 5:
            return "3-5 minutes"
        else:
            return "5-10 minutes"
    
    # Document generation methods
    def generate_schedule_ii(self) -> Dict:
        """Generate Schedule II Information Sheet"""
        try:
            # Prepare data for generator
            lender_data = self._extract_lender_data()
            
            generator = ScheduleIIGenerator(lender_data)
            document = generator.generate()
            
            return {
                'success': True,
                'document': document,
                'filename': f'Schedule_II_{self.lender.company_name}_{datetime.now().strftime("%Y%m%d")}.docx',
                'generation_time': datetime.now(),
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Failed to generate Schedule II document'
            }
    
    def generate_business_plan(self) -> Dict:
        """Generate comprehensive business plan using financial projections"""
        try:
            # Generate financial projections first
            lender_data = self._extract_lender_data()
            
            projection_model = FinancialProjectionModel(lender_data)
            projections = projection_model.generate_complete_projections()
            
            # Create business plan document (would need BusinessPlanGenerator)
            # For now, return projections data that can be used to build plan
            
            return {
                'success': True,
                'projections': projections,
                'filename': f'Business_Plan_{self.lender.company_name}_{datetime.now().strftime("%Y%m%d")}.docx',
                'generation_time': datetime.now(),
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Failed to generate business plan'
            }
    
    def generate_fit_proper_forms(self) -> Dict:
        """Generate fit & proper forms for all personnel"""
        try:
            generated_forms = {}
            
            for person in self.personnel:
                personnel_data = self._extract_personnel_data(person)
                lender_context = self._extract_lender_data()
                
                generator = FitProperGenerator(personnel_data, lender_context)
                
                # Generate both the document and assessment
                document = generator.generate()
                assessment = generator.generate_assessment_summary()
                
                generated_forms[person.id] = {
                    'document': document,
                    'assessment': assessment,
                    'filename': f'Fit_Proper_{person.full_name.replace(" ", "_")}_{datetime.now().strftime("%Y%m%d")}.docx',
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
                'message': 'Failed to generate fit & proper forms'
            }
    
    def generate_all_documents(self, selected_documents: Optional[List[str]] = None) -> Dict:
        """Generate all possible documents or selected subset"""
        try:
            results = {}
            
            if not selected_documents:
                # Generate all documents that can be generated
                required_docs = self._get_required_docs()
                selected_documents = [doc for doc in required_docs if self.can_generate_document(doc)]
            
            for doc_field in selected_documents:
                generator_type = self.FIELD_TO_GENERATOR.get(doc_field)
                
                if generator_type == 'schedule_ii':
                    results[doc_field] = self.generate_schedule_ii()
                elif generator_type == 'business_plan':
                    results[doc_field] = self.generate_business_plan()
                elif generator_type == 'fit_proper_forms':
                    results[doc_field] = self.generate_fit_proper_forms()
                else:
                    # Placeholder for other generators
                    results[doc_field] = {
                        'success': False,
                        'message': f'Generator for {generator_type} not yet implemented'
                    }
            
            successful = sum(1 for result in results.values() if result.get('success'))
            
            return {
                'success': successful > 0,
                'total_attempted': len(selected_documents),
                'successful_count': successful,
                'results': results,
                'generation_time': datetime.now(),
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': 'Failed to generate documents'
            }
    
    # Data extraction methods
    def _extract_lender_data(self) -> Dict:
        """Extract lender data for document generation"""
        return {
            'company_name': self.lender.company_name,
            'registration_number': self.lender.registration_number,
            'date_of_establishment': self.lender.date_of_establishment,
            'physical_address': self.lender.physical_address,
            'postal_address': getattr(self.lender, 'postal_address', ''),
            'business_email': self.lender.business_email,
            'phone_number': self.lender.phone_number,
            'website': getattr(self.lender, 'website', ''),
            'cbl_tier': self.lender.cbl_tier,
            'stated_capital': float(self.lender.stated_capital or 0),
            'total_assets': float(self.lender.total_assets or 0),
            'target_market_size': getattr(self.lender, 'target_market_size', 1000),
            'district': getattr(self.lender, 'district', 'Maseru'),
            'ceo_first_name': self.lender.ceo_first_name,
            'ceo_last_name': self.lender.ceo_last_name,
            
            # Include personnel and compliance data
            'personnel': [self._extract_personnel_data(p) for p in self.personnel],
            'compliance_data': self._extract_compliance_data(),
        }
    
    def _extract_personnel_data(self, person) -> Dict:
        """Extract personnel data for document generation"""
        return {
            'id': person.id,
            'full_name': person.full_name,
            'role': person.role,
            'nationality': person.nationality,
            'country_of_residence': person.country_of_residence,
            'date_of_birth': person.date_of_birth,
            'place_of_birth': person.place_of_birth,
            'id_or_passport_number': person.id_or_passport_number,
            'residential_address': getattr(person, 'residential_address', ''),
            'business_address': getattr(person, 'business_address', ''),
            'professional_qualifications': person.professional_qualifications,
            'employment_history_10_years': person.employment_history_10_years,
            'other_affiliations': person.other_affiliations,
            'family_business_affiliations': person.family_business_affiliations,
            
            # Legal declarations
            'criminal_conviction': person.criminal_conviction,
            'criminal_conviction_details': person.criminal_conviction_details,
            'legal_proceedings': person.legal_proceedings,
            'legal_proceedings_details': person.legal_proceedings_details,
            'bankruptcy': person.bankruptcy,
            'bankruptcy_details': person.bankruptcy_details,
            'ever_disqualified': person.ever_disqualified,
            'disqualification_details': person.disqualification_details,
            'dismissed_or_resigned': getattr(person, 'dismissed_or_resigned', False),
            'dismissal_details': getattr(person, 'dismissal_details', ''),
            
            # Board-specific fields
            'is_chairman': getattr(person, 'is_chairman', False),
            'is_non_executive': getattr(person, 'is_non_executive', False),
            
            # Document uploads (for status checking)
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
            'current_stage': self.compliance.current_stage,
            'submission_date': self.compliance.submission_date,
            'investigation_fee_paid': self.compliance.investigation_fee_paid,
            'registration_fee_paid': getattr(self.compliance, 'registration_fee_paid', False),
            'license_fee_paid': getattr(self.compliance, 'license_fee_paid', False),
            
            # Document upload status
            'schedule_i': bool(self.compliance.schedule_i),
            'schedule_ii': bool(self.compliance.schedule_ii),
            'business_plan': bool(self.compliance.business_plan),
            'aml_cft_manual': bool(self.compliance.aml_cft_manual),
            'risk_management_policy': bool(getattr(self.compliance, 'risk_management_policy', None)),
        }