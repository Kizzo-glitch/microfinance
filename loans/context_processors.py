from .models import Notification
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.db.models import Q
from collections import defaultdict
from django.db.models import Q



def topbar_notifications(request):
	if request.user.is_authenticated and hasattr(request.user, 'lender'):
		
		# Unread notifications
		unread_loan_applications = Notification.objects.filter(category="loan_application", is_read=False, user=request.user).order_by('-date_created')
		unread_loan_payments = Notification.objects.filter(category="loan_payment", is_read=False, user=request.user).order_by('-date_created')

		# Read notifications
		read_loan_applications = Notification.objects.filter(category="loan_application", is_read=True, user=request.user).order_by('-date_created')
		read_loan_payments = Notification.objects.filter(category="loan_payment", is_read=True, user=request.user).order_by('-date_created')
	
		return {
			'unread_loan_applications': unread_loan_applications,
			'unread_loan_payments': unread_loan_payments,
			'unread_loan_applications_count': unread_loan_applications.count(),
			'unread_loan_payments_count': unread_loan_payments.count(),
			'read_loan_applications': read_loan_applications,
			'read_loan_payments': read_loan_payments,
		}
	return {}

def pending_loan_update_notifications(request):
	if request.user.is_authenticated and hasattr(request.user, 'lender'):
		unread_notifications = Notification.objects.filter(
			Q(category="loan_update") | Q(category="document_update") | Q(category="loan_deleted"),
			user=request.user,
			is_read=False
		).select_related('loan_application', 'loan_application__borrower').order_by('-date_created')

		read_notifications = Notification.objects.filter(
			Q(category="loan_update") | Q(category="document_update") | Q(category="loan_deleted"),
			user=request.user,
			is_read=True
		).select_related('loan_application', 'loan_application__borrower').order_by('-date_created')

		return {
			'unread_loan_pending': unread_notifications,
			'unread_loan_pending_count': unread_notifications.count(),
			'read_loan_pending': read_notifications,
		}
	return {}


def borrower_notifications(request):
    if request.user.is_authenticated and hasattr(request.user, 'borrower'):
        User = request.user

        def unread(cat): return Notification.objects.filter(user=User, category=cat, is_read=False).order_by('-date_created')
        def read(cat):   return Notification.objects.filter(user=User, category=cat, is_read=True).order_by('-date_created')

        return {
            'unread_loan_approved': unread('loan_approved')[:3],
            'read_loan_approved':   read('loan_approved')[:3],
            'unread_loan_approved_count': unread('loan_approved').count(),

            'unread_loan_rejected': unread('loan_rejected')[:3],
            'read_loan_rejected':   read('loan_rejected')[:3],
            'unread_loan_rejected_count': unread('loan_rejected').count(),

            'unread_loan_pending': unread('loan_pending')[:3],
            'read_loan_pending':   read('loan_pending')[:3],
            'unread_loan_pending_count': unread('loan_pending').count(),

            # NEW — payment outcomes (confirmed / rejected)
            'unread_payment_update': unread('payment_update')[:3],
            'read_payment_update':   read('payment_update')[:3],
            'unread_payment_update_count': unread('payment_update').count(),
        }
    return {}

"""
def borrower_notifications(request):
	if request.user.is_authenticated and hasattr(request.user, 'borrower'):
		borrower = request.user.borrower

		unread_loan_approved = Notification.objects.filter(user=request.user, category='loan_approved', is_read=False)
		read_loan_approved = Notification.objects.filter(user=request.user, category='loan_approved', is_read=True)
		unread_loan_approved_all = Notification.objects.filter(user=request.user, category='loan_approved', is_read=False)
		read_loan_approved_all = Notification.objects.filter(user=request.user, category='loan_approved', is_read=True)

		unread_loan_rejected = Notification.objects.filter(user=request.user, category='loan_rejected', is_read=False)
		unread_loan_rejected_all = Notification.objects.filter(user=request.user, category='loan_rejected', is_read=False)
		read_loan_rejected = Notification.objects.filter(user=request.user, category='loan_rejected', is_read=True)
		read_loan_rejected_all = Notification.objects.filter(user=request.user, category='loan_rejected', is_read=True)

		unread_loan_pending = Notification.objects.filter(user=request.user, category='loan_pending', is_read=False)		
		unread_loan_pending_all = Notification.objects.filter(user=request.user, category='loan_pending', is_read=False)
		read_loan_pending = Notification.objects.filter(user=request.user, category='loan_pending', is_read=True)
		read_loan_pending_all = Notification.objects.filter(user=request.user, category='loan_pending', is_read=True)

		return {
			'unread_loan_approved': unread_loan_approved,
			'read_loan_approved': read_loan_approved,
			'unread_loan_approved_count': unread_loan_approved.count(),

			'unread_loan_rejected': unread_loan_rejected,
			'read_loan_rejected': read_loan_rejected,
			'unread_loan_rejected_count': unread_loan_rejected.count(),

			'unread_loan_pending': unread_loan_pending,
			'read_loan_pending': read_loan_pending,
			'unread_loan_pending_count': unread_loan_pending.count(),

			'unread_loan_approved': unread_loan_approved_all.order_by('-date_created')[:3],
			'read_loan_approved': read_loan_approved_all.order_by('-date_created')[:3],

			'unread_loan_rejected': unread_loan_rejected_all.order_by('-date_created')[:3],
			#'unread_loan_rejected': unread_loan_rejected_all.order_by('-date_created')[:3],

			'unread_loan_pending': unread_loan_pending_all.order_by('-date_created')[:3],
			#'unread_loan_pending': unread_loan_pending_all.order_by('-date_created')[:3],

			'unread_loan_approved_count': unread_loan_approved_all.count(),
			'unread_loan_rejected_count': unread_loan_rejected_all.count(),
			'unread_loan_pending_count': unread_loan_pending_all.count(),
		}

	return {}
"""





'''def pending_loan_update_notifications(request):
	if request.user.is_authenticated and hasattr(request.user, 'lender'):

		# Filter for unread notifications related to updated/deleted loans or reuploaded documents
		unread_pending_loan_updates = Notification.objects.filter(
			Q(category="loan_update") | Q(category="document_update") | Q(category="loan_deleted"),
			user=request.user,
			is_read=False
		).order_by('-date_created')

		read_pending_loan_updates = Notification.objects.filter(
			Q(category="loan_update") | Q(category="document_update") | Q(category="loan_deleted"),
			user=request.user,
			is_read=True
		).order_by('-date_created')

		return {
			'unread_pending_loan_updates': unread_pending_loan_updates,
			'read_pending_loan_updates': read_pending_loan_updates,
			'unread_pending_loan_updates_count': unread_pending_loan_updates.count(),
			'read_pending_loan_updates_count': read_pending_loan_updates.count(),
		}
		
	return {}'''




