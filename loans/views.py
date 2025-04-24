from django.shortcuts import render

from rest_framework import generics
from .models import Loan, Notification
from .serializers import LoanSerializer


class LoanListView(generics.ListAPIView):
	queryset = Loan.objects.all()
	serializer_class = LoanSerializer



