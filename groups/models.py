from django.db import models
#from micro.models import User
#from borrowers.models import BorrowerProfile
#from lenders.models import LenderProfile
import uuid


class BorrowerGroup(models.Model):
	"""Represents a group (stokvel, union, society, etc.)."""
	GROUP_TYPES = [
		('society', 'Society'),
		('stokvel', 'Stokvel'),
		('union', 'Employer Union'),
		('other', 'Other'),
	]
	name = models.CharField(max_length=255, unique=True)
	group_type = models.CharField(max_length=50, choices=GROUP_TYPES, blank=True, null=True)
	description = models.TextField(blank=True, null=True)
	created_at = models.DateTimeField(auto_now_add=True)

	# Group creator (main admin)
	admin = models.ForeignKey(
		"borrowers.BorrowerProfile",
		on_delete=models.CASCADE,
		related_name="admin_groups"
	)

	# Sub-admins (optional 2 helpers)
	sub_admins = models.ManyToManyField(
		"borrowers.BorrowerProfile",
		related_name="sub_admin_groups",
		blank=True
	)

	# Membership (borrowers who belong to this group)
	members = models.ManyToManyField(
		"borrowers.BorrowerProfile",
		through="GroupMembership",
		related_name="groups"
	)

	# Extra details
	is_verified = models.BooleanField(default=False)  # platform verifies group
	invited_lenders = models.ManyToManyField(
		"lenders.LenderProfile", 
		related_name="subscribed_groups", 
		blank=True
	)

	def __str__(self):
		return self.name



class GroupMembership(models.Model):
	"""Through table for BorrowerGroup.members"""
	ROLE_CHOICES = [
		("member", "Member"),
		("sub_admin", "Sub-Admin"),
		("admin", "Admin"),
	]

	borrower = models.ForeignKey("borrowers.BorrowerProfile", on_delete=models.CASCADE)
	group = models.ForeignKey(BorrowerGroup, on_delete=models.CASCADE)
	role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="member")
	joined_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		unique_together = ("borrower", "group")

	def __str__(self):
		return f"{self.borrower.user.username} - {self.group.name} ({self.role})"


class GroupInvite(models.Model):
	"""Invite links for new members to join groups"""
	group = models.ForeignKey(BorrowerGroup, on_delete=models.CASCADE, related_name="invites")
	code = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
	email = models.EmailField(blank=True, null=True)  # can pre-fill email invite
	invited_by = models.ForeignKey("borrowers.BorrowerProfile", on_delete=models.CASCADE)
	created_at = models.DateTimeField(auto_now_add=True)
	is_used = models.BooleanField(default=False)

	def __str__(self):
		return f"Invite to {self.group.name} - {self.code}"


class GroupRequest(models.Model):
	"""Borrower requests to join group instead of being invited"""
	borrower = models.ForeignKey("borrowers.BorrowerProfile", on_delete=models.CASCADE)
	group = models.ForeignKey(BorrowerGroup, on_delete=models.CASCADE, related_name="join_requests")
	status = models.CharField(
		max_length=20,
		choices=[("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")],
		default="pending"
	)
	requested_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return f"{self.borrower.user.username} request to {self.group.name} ({self.status})"

