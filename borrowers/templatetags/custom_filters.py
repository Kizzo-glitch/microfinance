from django import template

register = template.Library()

@register.filter
def range(value):
	"""
	Returns a range from 1 to the specified value (inclusive).
	"""
	return range(1, value + 1)