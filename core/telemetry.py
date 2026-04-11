import logging

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def get_endpoint_api(base: str, type: str) -> str:
    match type:
        case "logs":
            return f"{base}/v1/logs"
        case "traces":
            return f"{base}/v1/traces"
        case "metrics":
            return f"{base}/v1/metrics"


class Telemetry:
    def __init__(
        self,
        service_name: str = None,
        collector_endpoint: str = None,
        log_interval: int = None,
        trace_interval: int = None,
        metric_interval: int = None,
    ):
        self.service_name = service_name or "core"
        self.resource = Resource.create({SERVICE_NAME: self.service_name})
        self.collector_endpoint = collector_endpoint or "http://alloy:4317"

    def configure_tracer(self):
        traces_endpoint = get_endpoint_api(self.collector_endpoint, "traces")

        tracer_provider = TracerProvider(resource=self.resource)
        tracer_provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=traces_endpoint, insecure=True)
            )
        )

        trace.set_tracer_provider(tracer_provider)

    def configure_meter(self):
        meter_endpoint = get_endpoint_api(self.collector_endpoint, "metrics")
        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=meter_endpoint, insecure=True),
            export_interval_millis=10000,
        )
        meter_provider = MeterProvider(
            resource=self.resource, metric_readers=[metric_reader]
        )

        metrics.set_meter_provider(meter_provider)

    def configure_logger(self):
        logs_endpoint = get_endpoint_api(self.collector_endpoint, "logs")
        logger_provider = LoggerProvider(resource=self.resource)
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(
                OTLPLogExporter(endpoint=logs_endpoint, insecure=True)
            )
        )

        handler = LoggingHandler(level=0, logger_provider=logger_provider)
        logging.getLogger().addHandler(handler)

    def setup(self):
        self.configure_tracer()
        self.configure_meter()
        self.configure_logger()

        DjangoInstrumentor().instrument()
