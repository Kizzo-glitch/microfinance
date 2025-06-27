from django.contrib import admin

from .models import Loan, LoanApplication, RiskNotification, InterestRate, LoanPayment, CreditHistory, Rating, Notification




# Register your models here.

admin.site.register(Loan)
admin.site.register(LoanApplication)
admin.site.register(RiskNotification)
admin.site.register(InterestRate)
admin.site.register(LoanPayment)
admin.site.register(CreditHistory)
admin.site.register(Notification)
admin.site.register(Rating)


'''class LoanApplicationAdmin(admin.ModelAdmin):
    list_display = ('borrower', 'status', 'date_applied', 'status_last_updated')
    list_filter = ('status',)
    search_fields = ('borrower__user__username', 'lender__company_name')

    def get_rejection_reasons(self, obj):
        return ", ".join(obj.get_rejection_reasons_display())
    get_rejection_reasons.short_description = 'Rejection Reasons'

    def get_pending_reasons(self, obj):
        return ", ".join(obj.get_pending_reasons_display())
    get_pending_reasons.short_description = 'Pending Reasons' '''



