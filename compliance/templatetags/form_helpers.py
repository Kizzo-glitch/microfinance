from django import template

register = template.Library()


@register.filter
def get_item(form, field_name):
    """Allow {{ form|get_item:"field_name" }} in templates."""
    return form[field_name]
