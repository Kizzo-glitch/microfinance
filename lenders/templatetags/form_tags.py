from django import template

register = template.Library()

@register.simple_tag
def render_field(field):
	css_class = field.field.widget.attrs.get('class', '')

	# Always ensure 'form-control' is present
	if 'form-control' not in css_class:
		css_class = 'form-control ' + css_class

	# Add is-invalid if field has errors
	if field.errors:
		css_class += ' is-invalid'

	return field.as_widget(attrs={"class": css_class})

#@register.filter(name='add_class')
#def add_class(field, css_class):
#	return field.as_widget(attrs={"class": css_class})


@register.filter(name='add_class')
def add_class(field, css_class):
	if field.errors:
		return field.as_widget(attrs={"class": f"{css_class} is-invalid"})
	return field.as_widget(attrs={"class": css_class})



@register.filter(name='add_error_class')
def add_error_class(field):
	css_classes = field.field.widget.attrs.get('class', '')
	if field.errors:
		css_classes += ' is-invalid'
	return field.as_widget(attrs={'class': css_classes})