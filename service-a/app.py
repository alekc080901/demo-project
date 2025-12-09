from fastapi import FastAPI, HTTPException
import httpx
import os
import time
import atexit
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource

# Configure OpenTelemetry BEFORE creating the app
resource = Resource.create({"service.name": "service-a"})
trace_provider = TracerProvider(resource=resource)
trace.set_tracer_provider(trace_provider)

# Configure Jaeger exporter using HTTP collector endpoint
# Jaeger HTTP collector endpoint: http://jaeger:14268/api/traces
jaeger_host = os.getenv("JAEGER_AGENT_HOST", "jaeger")
jaeger_collector_endpoint = f"http://{jaeger_host}:14268/api/traces"
print(f"[service-a] Configuring Jaeger exporter with endpoint: {jaeger_collector_endpoint}")
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
app = FastAPI(title="Service A")

# Instrument FastAPI and HTTPX - they will use the tracer provider we set above
FastAPIInstrumentor.instrument_app(app)
HTTPXClientInstrumentor().instrument()

tracer = trace.get_tracer(__name__)

SERVICE_B_URL = os.getenv("SERVICE_B_URL", "http://service-b:8001")


@app.get("/")
async def root():
    """Root endpoint"""
    return {"service": "service-a", "status": "running"}


@app.get("/request-info")
async def request_info():
    time.sleep(1)
    """Endpoint that requests information from service-b"""
    with tracer.start_as_current_span("request_info_from_service_b") as span:
        span.set_attribute("service_b_url", SERVICE_B_URL)
        
        try:
            async with httpx.AsyncClient() as client:
                span.add_event("Making HTTP request to service-b")
                response = await client.get(f"{SERVICE_B_URL}/info", timeout=5.0)
                response.raise_for_status()
                data = response.json()
                
                span.set_attribute("response.status_code", response.status_code)
                span.add_event("Received response from service-b")
                
                return {
                    "service": "service-a",
                    "message": "Successfully retrieved information from service-b",
                    "data": data
                }
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get information from service-b: {str(e)}"
            )

