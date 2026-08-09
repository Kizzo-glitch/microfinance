from django.shortcuts import redirect

def handle_stage_navigation(request, form, loan_app, next_stage_redirect=None):
	"""
	Handles saving a stage form and navigating based on user action.

	Args:
		request: Django request object.
		form: The bound form for this stage.
		loan_app: The LoanApplication instance.
		next_stage_redirect: A string or callable returning the redirect for 'Save & Continue'.

	Returns:
		redirect response or None (if form is not valid).
	"""
	if form.is_valid():
		loan_app = form.save(commit=False)

		action = request.POST.get("action")

		if action == "continue" and next_stage_redirect:
			loan_app.save()
			if callable(next_stage_redirect):
				return redirect(next_stage_redirect(loan_app))
			return redirect(next_stage_redirect)

		elif action == "exit":
			loan_app.save()
			return redirect("borrowers:borrower_index")

	return None



