from django import template

register = template.Library()

@register.filter
def stars(rating):
    return "★" * rating