# libs/observability/wrapper.py 

import functools
import json
from opentelemetry import trace
from pydantic import BaseModel

tracer = trace.get_tracer("pipeline.wrapper")

def trace_step(step_name: str):
    """Dekorator für die reine Ausführungs-Performance (Spans, Laufzeit, Fehler)."""
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            with tracer.start_as_current_span(f"step.{step_name}") as span:
                span.set_attribute("step.name", step_name)
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(trace.StatusCode.OK)
                    return result
                except Exception as e:
                    span.set_status(trace.StatusCode.ERROR, str(e))
                    span.record_exception(e)
                    raise
        return async_wrapper
    return decorator


def trace_data(name: str = "data.payload"):
    """
    Counterpart für Data-Payloads (Inputs/Outputs).
    Extrahiert strukturierte Daten (insb. Pydantic-Modelle) und 
    schreibt sie als Attribute oder Events in den aktiven OTEL-Span.
    """
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            span = trace.get_current_span()
            
            # Input-Daten optional erfassen (wenn Pydantic oder serialisierbar)
            if args and isinstance(args[0], BaseModel):
                span.set_attribute(f"{name}.input_model", args[0].__class__.__name__)
                # Hier könnten wir je nach Config/Field-Filterung Details anhängen
            
            result = await func(*args, **kwargs)
            
            # Output-Daten erfassen
            if isinstance(result, BaseModel):
                span.set_attribute(f"{name}.output_model", result.__class__.__name__)
                # Optional: JSON-Representation als Attribut (sofern nicht zu groß)
                # span.set_attribute(f"{name}.output_json", result.model_dump_json())
                
            return result
        return async_wrapper
    return decorator
