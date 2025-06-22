from django import template

register = template.Library()

# For Borrowers
@register.filter
def range(value):
	"""
	Returns a range from 1 to the specified value (inclusive).
	"""
	return range(1, value + 1)

@register.filter
def get_item(dictionary, key):
	return dictionary.get(key)



# For Lenders
@register.filter
def getattribute(obj, attr_name):
	return getattr(obj, attr_name, None)



