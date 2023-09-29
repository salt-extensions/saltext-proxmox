def fqn(obj=None):
    """
    Get the fully qualified name of a class or method as string
    """
    return ".".join([obj.__module__, obj.__qualname__])
