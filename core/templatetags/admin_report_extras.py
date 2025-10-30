from django import template

register = template.Library()

@register.filter
def get_item(mapping, key):
    """
    Template filter to retrieve mapping[key] safely.

    Usage: {{ row|get_item:header }}
    Works for dict-like objects. Returns empty string if key missing.
    """
    try:
        # mapping may be a dict-like or model instance with attribute access.
        if mapping is None:
            return ""
        # If mapping supports __getitem__
        try:
            return mapping[key]
        except Exception:
            # Fallback to getattr
            return getattr(mapping, key, "")
    except Exception:
        return ""