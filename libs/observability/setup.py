# libs/observability/setup.py

import sys
import os
import logging
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from .config import ObservabilityConfig

logger = logging.getLogger(__name__)

def configure_observability(config: ObservabilityConfig):
    # 1. Globales Root-Logging initialisieren
    root_logger = logging.getLogger()
    root_logger.setLevel(config.global_log_level.upper())
    
    # Bestehende Root-Handler aufräumen
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Fallback Console Handler für das Root-System
    root_console_handler = logging.StreamHandler(sys.stdout)
    root_console_handler.setLevel(config.global_log_level.upper())
    root_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    root_console_handler.setFormatter(root_formatter)
    root_logger.addHandler(root_console_handler)

    # 2. Namespace Levels & Framework Propagation
    # Alle definierten Logger (uvicorn, httpx, etc.) werden an Root gekoppelt
    for logger_name, level in config.namespace_levels.items():
        ns_logger = logging.getLogger(logger_name)
        ns_logger.setLevel(level.upper())
        ns_logger.handlers.clear()  # Verhindert Duplikate durch Framework-Defaults
        ns_logger.propagate = True  # Erzwingt Weitergabe an den Root-Logger

    # 3. OpenTelemetry TracerProvider initialisieren
    resource = Resource.create(attributes={"service.name": config.service_name})
    provider = TracerProvider(resource=resource)

    # Tracken, ob Tracing-Exporter bereits hinzugefügt wurden
    trace_processors_added = False

    # 4. Custom Channels & Sinks konfigurieren
    for channel_name, channel_config in config.channels.items():
        channel_logger_name = f"libs.observability.{channel_name}"
        target_logger = logging.getLogger(channel_logger_name)
        target_logger.setLevel(channel_config.log_level.upper())
        
        # OTLP / Logging Entkopplung:
        # Alle Custom-Kanäle handhaben ihre Sinks isoliert (propagate = False),
        # um doppelte Logs mit dem Root-Logger zu vermeiden.
        target_logger.propagate = False
        
        if target_logger.hasHandlers():
            target_logger.handlers.clear()

        for sink in channel_config.enabled_sinks:
            # A) Standard Console Sink für Text-Logs
            if sink == "console":
                ch = logging.StreamHandler(sys.stdout)
                ch.setLevel(channel_config.log_level.upper())
                prefix = f"[{channel_name.upper()}] "
                ch.setFormatter(logging.Formatter(f'%(asctime)s [%(levelname)s] {prefix}%(name)s: %(message)s'))
                target_logger.addHandler(ch)

            # B) File-Based JSONL / Log Sink
            elif sink == "jsonl":
                log_dir = os.path.dirname(config.jsonl_filepath)
                if log_dir:
                    os.makedirs(log_dir, exist_ok=True)
                fh = logging.FileHandler(config.jsonl_filepath, encoding="utf-8")
                fmt = logging.Formatter('%(message)s') if channel_name == "data" else logging.Formatter('%(asctime)s [%(levelname)s] [%(name)s]: %(message)s')
                fh.setFormatter(fmt)
                target_logger.addHandler(fh)

            # C) OpenTelemetry Span Exporter (NUR für den 'trace'-Kanal)
            if channel_name == "trace" and not trace_processors_added:
                if sink == "otlp" and config.otlp_enabled:
                    try:
                        # Gemäß OpenTelemetry-Standard: Den Basis-Endpoint übergeben.
                        # OTLPSpanExporter hängt /v1/traces intern automatisch an.
                        otlp_exporter = OTLPSpanExporter(endpoint=config.otlp_endpoint)
                        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
                    except Exception as e:
                        root_logger.error(f"OTLP SpanExporter Fehler: {e}")

                elif sink == "console":
                    console_exporter = ConsoleSpanExporter()
                    provider.add_span_processor(BatchSpanProcessor(console_exporter))

        if channel_name == "trace":
            trace_processors_added = True

    # 5. TracerProvider global aktivieren
    try:
        trace.set_tracer_provider(provider)
    except Exception as e:
        root_logger.debug(f"TracerProvider bereits gesetzt: {e}")


def configure_observability_old(config: ObservabilityConfig):
    # 1. Globales Root-Logging vorbereiten
    root_logger = logging.getLogger()
    root_logger.setLevel(config.global_log_level.upper())
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Standard-Konsolen-Handler für das Applikations-Logging einrichten
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(config.global_log_level.upper())
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 2. Namespace Levels anwenden
    for ns, level in config.namespace_levels.items():
        logging.getLogger(ns).setLevel(level.upper())

    # 3. OpenTelemetry TracerProvider initialisieren
    resource = Resource.create(attributes={"service.name": config.service_name})
    provider = TracerProvider(resource=resource)
    
    # 4. Exporter basierend auf der Konfiguration registrieren
    # Wir schauen, ob OTLP aktiviert ist oder ob wir standardmäßig in die Konsole tracen
    otlp_configured = False

    for channel_name, channel_config in config.channels.items():
        for sink in channel_config.enabled_sinks:
            if sink == "otlp" and config.otlp_enabled and not otlp_configured:
                try:
                    otlp_endpoint = f"{config.otlp_endpoint}/v1/traces"
                    otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
                    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
                    otlp_configured = True
                    logger.info(f"OpenTelemetry OTLP SpanExporter aktiv: {otlp_endpoint}")
                except Exception as e:
                    logger.error(f"Konnte OTLP SpanExporter nicht initialisieren: {e}")

            elif sink == "console" and channel_name == "trace":
                # Nur wenn explizit gewünscht oder kein OTLP aktiv ist, Console Exporter nutzen
                if not otlp_configured:
                    console_exporter = ConsoleSpanExporter()
                    provider.add_span_processor(BatchSpanProcessor(console_exporter))

    # TracerProvider global registrieren
    try:
        trace.set_tracer_provider(provider)
    except Exception as e:
        logger.debug(f"TracerProvider konnte nicht neu gesetzt werden (bereits registriert): {e}")

