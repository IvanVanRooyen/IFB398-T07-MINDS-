import functools
import inspect

from opentelemetry import trace

tracer = trace.get_tracer(__name__)

def instrument(
    func=None, *, span_name=None, attributes=None, skip_args=None, record_args=True
):
    def decorator(fn):
        name = span_name or f"{fn.__module__}.{fn.__qualname__}"
        static_attrs = attributes or {}

        def _build_arg_attrs(fn, args, kwargs):
            if not record_args:
                return {}

            sig = inspect.signature(fn)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()

            return {
                f"arg.{k}": _safe_attr(v)
                for k, v in bound.arguments.items()
                if k != "self" and k not in (skip_args or set())
            }

        # handle async functions
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def wrapper(*args, **kwargs):
                arg_attrs = _build_arg_attrs(fn, args, kwargs)
                with tracer.start_as_current_span(
                    name, attributes={**static_attrs, **arg_attrs}
                ) as span:
                    try:
                        return await fn(*args, **kwargs)

                    except Exception as err:
                        span.set_status(trace.StatusCode.ERROR, str(err))
                        span.record_exception(err)

                        raise
        # non-async
        else:

            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                arg_attrs = _build_arg_attrs(fn, args, kwargs)
                with tracer.start_as_current_span(
                    name, attributes={**static_attrs, **arg_attrs}
                ) as span:
                    try:
                        return fn(*args, **kwargs)

                    except Exception as err:
                        span.set_status(trace.StatusCode.ERROR, str(err))
                        span.record_exception(err)

                        raise

        return wrapper

    if func is not None:
        return decorator(func)

    return decorator


def _safe_attr(value):
    """coerce value to OTEL-safe attr type (i.e. str, int, float, bool)"""
    if isinstance(value, (str, int, float, bool)):
        return value

    return str(value)
