from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import LenderComplianceRecord
from .forms import *
from .services.requirement_evaluator import RequirementEvaluatorService
from .services.document_status import DocumentStatusService

WIZARD_STEPS = [
    'tier_selection',
    'company_info',
    'directors',
    'governance',
    'documents',
    'review',
]

def get_next_step(current_step):
    idx = WIZARD_STEPS.index(current_step)
    if idx + 1 < len(WIZARD_STEPS):
        return WIZARD_STEPS[idx+1]
    return None
