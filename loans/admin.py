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






