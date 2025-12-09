from fastapi import FastAPI
import os
import atexit
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource

# Configure OpenTelemetry BEFORE creating the app
resource = Resource.create({"service.name": "service-b"})
trace_provider = TracerProvider(resource=resource)
trace.set_tracer_provider(trace_provider)

# Configure Jaeger exporter using HTTP collector endpoint
# Jaeger HTTP collector endpoint: http://jaeger:14268/api/traces
jaeger_host = os.getenv("JAEGER_AGENT_HOST", "jaeger")
jaeger_collector_endpoint = f"http://{jaeger_host}:14268/api/traces"
print(f"[service-b] Configuring Jaeger exporter with endpoint: {jaeger_collector_endpoint}")
jaeger_exporter = JaegerExporter(
    collector_endpoint=jaeger_collector_endpoint,
)
jaeger_span_processor = BatchSpanProcessor(jaeger_exporter)
trace_provider.add_span_processor(jaeger_span_processor)

# Add console exporter for debugging
console_exporter = ConsoleSpanExporter()
console_span_processor = BatchSpanProcessor(console_exporter)
trace_provider.add_span_processor(console_span_processor)

# Ensure spans are flushed on shutdown
atexit.register(lambda: trace_provider.force_flush())

# Initialize FastAPI app AFTER tracer provider is configured
app = FastAPI(title="Service B")

# Instrument FastAPI - it will use the tracer provider we set above
FastAPIInstrumentor.instrument_app(app)

tracer = trace.get_tracer(__name__)


@app.get("/")
async def root():
    """Root endpoint"""
    return {"service": "service-b", "status": "running"}


@app.get("/info")
async def get_info():
    """Endpoint that provides information"""
    with tracer.start_as_current_span("get_info") as span:
        span.add_event("Processing information request")
        
        # Simulate some processing
        import time
        time.sleep(0.1)  # Small delay to make tracing visible
        
        info = {
            "service": "service-b",
            "message": "This is information from service-b",
            "timestamp": trace.get_current_span().get_span_context().span_id if trace.get_current_span() else None
        }
        
        span.set_attribute("info.message", info["message"])
        span.add_event("Information prepared")
        
        return info

