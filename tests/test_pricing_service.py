from __future__ import annotations

import datetime as dt

from app.core.services.pricing import PricingService, build_generation_cost_report, build_project_budget_report


def test_openrouter_catalog_extracts_text_model_prices(tmp_path):
    service = PricingService(path=str(tmp_path / "pricing.json"))
    service._openrouter.fetch_models = lambda **kwargs: {
        "data": [
            {
                "id": "openai/gpt-5-mini",
                "name": "OpenAI: GPT-5 Mini",
                "architecture": {"modality": "text+image->text", "output_modalities": ["text"]},
                "pricing": {
                    "prompt": "0.00000025",
                    "completion": "0.000002",
                    "input_cache_read": "0.000000025",
                    "web_search": "0.01",
                },
            },
            {
                "id": "google/gemini-2.0-flash",
                "name": "Google: Gemini 2.0 Flash",
                "architecture": {"modality": "text->text", "output_modalities": ["text"]},
                "pricing": {
                    "prompt": "0.0000001",
                    "completion": "0.0000004",
                    "input_cache_read": "0.000000025",
                },
            },
        ]
    }  # type: ignore[method-assign]

    records = service._fetch_openrouter_catalog()

    openai_record = next(item for item in records if item["canonical_model_id"] == "openai/gpt-5-mini")
    gemini_record = next(item for item in records if item["canonical_model_id"] == "google/gemini-2.0-flash")
    assert openai_record["provider"] == "openai"
    assert openai_record["model"] == "gpt-5-mini"
    assert openai_record["input_price_per_1m_tokens"] == 0.25
    assert openai_record["output_price_per_1m_tokens"] == 2.0
    assert openai_record["cached_input_price_per_1m_tokens"] == 0.025
    assert openai_record["pricing_origin"] == "openrouter_api"
    assert gemini_record["provider"] == "google"
    assert gemini_record["model"] == "gemini-2.0-flash"


def test_openrouter_endpoint_pricing_enriches_selected_model(tmp_path):
    service = PricingService(path=str(tmp_path / "pricing.json"))
    service._persist_records(
        [
            {
                "provider": "openai",
                "model": "gpt-5-mini",
                "canonical_model_id": "openai/gpt-5-mini",
                "display_name": "OpenAI: GPT-5 Mini",
                "input_price_per_1m_tokens": 0.25,
                "output_price_per_1m_tokens": 2.0,
                "cached_input_price_per_1m_tokens": 0.025,
                "currency": "USD",
                "pricing_mode": "cached_input_supported",
                "modality": "text",
                "source_url": "https://openrouter.ai/api/v1/models",
                "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "pricing_source": "updated",
                "pricing_origin": "openrouter_api",
                "available": True,
            }
        ]
    )
    service._openrouter.fetch_model_endpoints = lambda author, slug: {
        "data": {
            "endpoints": [
                {
                    "provider_name": "OpenAI",
                    "tag": "openai",
                    "pricing": {
                        "prompt": "0.00000025",
                        "completion": "0.000002",
                        "input_cache_read": "0.000000025",
                    },
                }
            ]
        }
    }  # type: ignore[method-assign]

    pricing = service.get_pricing("openai", "gpt-5-mini")

    assert pricing["endpoint_provider"] == "OpenAI"
    assert pricing["endpoint_tag"] == "openai"
    assert pricing["source_url"].endswith("/models/openai/gpt-5-mini/endpoints")
    assert pricing["input_price_per_1m_tokens"] == 0.25


def test_openai_pricing_parser_extracts_model_prices(tmp_path):
    service = PricingService(path=str(tmp_path / "pricing.json"))
    html = """
    <html><body>
    &quot;gpt-5-mini&quot;],[0,0.25],[0,0.025],[0,2]
    &quot;gpt-4.1-mini&quot;],[0,0.4],[0,0.1],[0,1.6]
    </body></html>
    """
    service._fetch_text = lambda url: html  # type: ignore[method-assign]

    records = service._fetch_openai_catalog()

    record = next(item for item in records if item["model"] == "gpt-5-mini")
    assert record["input_price_per_1m_tokens"] == 0.25
    assert record["cached_input_price_per_1m_tokens"] == 0.025
    assert record["output_price_per_1m_tokens"] == 2.0
    assert record["source_url"]


def test_openai_marketing_pricing_parser_extracts_model_prices(tmp_path):
    service = PricingService(path=str(tmp_path / "pricing.json"))
    html = """
    <html><body>
    <h2>Modelos insignia</h2>
    <h3>GPT-5.4</h3>
    <div>Precio</div>
    <div>Entrada:</div>
    <div>USD 2.50/1 millón de tokens</div>
    <div>Entrada en caché:</div>
    <div>USD 0.25/1 millón de tokens</div>
    <div>Salida:</div>
    <div>USD 15.00/1 millón de tokens</div>
    <h3>GPT-5.4 mini</h3>
    <div>Precio</div>
    <div>Entrada:</div>
    <div>USD 0.40/1 millón de tokens</div>
    <div>Salida:</div>
    <div>USD 3.20/1 millón de tokens</div>
    </body></html>
    """

    records = service._parse_openai_marketing_catalog(
        html,
        source_url="https://openai.com/es-419/api/pricing/",
        fetched_at="2026-03-20T10:00:00Z",
    )

    flagship = next(item for item in records if item["model"] == "gpt-5.4")
    mini = next(item for item in records if item["model"] == "gpt-5.4-mini")
    assert flagship["input_price_per_1m_tokens"] == 2.5
    assert flagship["cached_input_price_per_1m_tokens"] == 0.25
    assert flagship["output_price_per_1m_tokens"] == 15.0
    assert mini["input_price_per_1m_tokens"] == 0.4
    assert mini["output_price_per_1m_tokens"] == 3.2


def test_gemini_pricing_parser_extracts_text_and_cache_prices(tmp_path):
    service = PricingService(path=str(tmp_path / "pricing.json"))
    html = """
    <div>Gemini 2.0 Flash</div>
    <div>gemini-2.0-flash</div>
    <div>Estándar</div>
    <div>Precio de entrada</div>
    <div>Sin costo</div>
    <div>USD 0.10 (texto, imagen o video)</div>
    <div>USD 0.70 (audio)</div>
    <div>Precio de salida</div>
    <div>Sin costo</div>
    <div>$0.40</div>
    <div>Precio del almacenamiento de contexto en caché</div>
    <div>Sin costo</div>
    <div>USD 0.025 por 1,000,000 de tokens (texto, imagen o video)</div>
    </div>
    """
    service._fetch_text = lambda url: html  # type: ignore[method-assign]

    records = service._fetch_gemini_catalog()

    record = next(item for item in records if item["model"] == "gemini-2.0-flash")
    assert record["input_price_per_1m_tokens"] == 0.1
    assert record["output_price_per_1m_tokens"] == 0.4
    assert record["cached_input_price_per_1m_tokens"] == 0.025
    assert record["pricing_mode"] == "tiered"


def test_pricing_service_falls_back_to_cached_record_when_refresh_fails(tmp_path):
    service = PricingService(path=str(tmp_path / "pricing.json"))
    stale_record = {
        "provider": "openai",
        "model": "gpt-5-mini",
        "input_price_per_1m_tokens": 0.25,
        "output_price_per_1m_tokens": 2.0,
        "cached_input_price_per_1m_tokens": 0.025,
        "currency": "USD",
        "pricing_mode": "cached_input_supported",
        "threshold_rule": "",
        "modality": "text",
        "source_url": "https://developers.openai.com/api/docs/pricing",
        "fetched_at": (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3)).isoformat(),
        "available": True,
    }
    service._persist_records([stale_record])
    service._refresh_provider = lambda provider: False  # type: ignore[method-assign]

    pricing = service.get_pricing("openai", "gpt-5-mini")

    assert pricing["pricing_source"] == "cached"
    assert pricing["is_cached_fallback"] is True
    assert pricing["input_price_per_1m_tokens"] == 0.25


def test_generation_cost_report_calculates_section_and_project_totals():
    class _PricingStub:
        def get_pricing(self, provider: str, model: str):
            return {
                "provider": provider,
                "model": model,
                "input_price_per_1m_tokens": 0.25,
                "output_price_per_1m_tokens": 2.0,
                "cached_input_price_per_1m_tokens": 0.025,
                "currency": "USD",
                "pricing_mode": "cached_input_supported",
                "threshold_rule": "",
                "modality": "text",
                "source_url": "https://developers.openai.com/api/docs/pricing",
                "fetched_at": "2026-03-19T10:00:00Z",
                "pricing_source": "cached",
                "is_cached_fallback": False,
                "available": True,
            }

    usage_report = {
        "attempts": [
            {
                "provider": "openai",
                "model": "gpt-5-mini",
                "section_id": "sec-1",
                "section_path": "Introduccion",
                "section_title": "Introduccion",
                "input_tokens": 1200,
                "output_tokens": 800,
                "total_tokens": 2000,
                "attempt": 1,
                "source": "reported_by_provider",
                "estimated": False,
            },
            {
                "provider": "openai",
                "model": "gpt-5-mini",
                "section_id": "sec-2",
                "section_path": "Marco teorico",
                "section_title": "Marco teorico",
                "input_tokens": 1000,
                "output_tokens": 500,
                "total_tokens": 1500,
                "attempt": 1,
                "source": "reported_by_provider",
                "estimated": False,
            },
        ],
        "current_section": {"section_id": "sec-2", "section_path": "Marco teorico", "section_title": "Marco teorico"},
    }

    report = build_generation_cost_report(usage_report, pricing_service=_PricingStub())

    assert report["priced_calls"] == 2
    assert report["unpriced_calls"] == 0
    assert report["total_cost_usd"] == 0.00315
    assert any(item["estimated_cost_usd"] == 0.0019 for item in report["sections"])
    assert report["current_section"]["section_path"] == "Marco teorico"


def test_project_budget_report_uses_historical_tokens_and_selected_model():
    class _PricingStub:
        def list_pricing_catalog(self, **kwargs):
            return [
                {
                    "provider": "openai",
                    "model": "gpt-5.4-mini",
                    "canonical_model_id": "openai/gpt-5.4-mini",
                    "display_name": "OpenAI: GPT-5.4 Mini",
                    "input_price_per_1m_tokens": 0.4,
                    "output_price_per_1m_tokens": 3.2,
                    "cached_input_price_per_1m_tokens": 0.04,
                    "currency": "USD",
                    "pricing_mode": "cached_input_supported",
                    "threshold_rule": "",
                    "modality": "text",
                    "source_url": "https://openrouter.ai/api/v1/models",
                    "fetched_at": "2026-03-20T10:00:00Z",
                    "pricing_source": "updated",
                    "pricing_origin": "openrouter_api",
                    "is_cached_fallback": False,
                    "available": True,
                },
                {
                    "provider": "google",
                    "model": "gemini-2.0-flash",
                    "canonical_model_id": "google/gemini-2.0-flash",
                    "display_name": "Google: Gemini 2.0 Flash",
                    "input_price_per_1m_tokens": 0.1,
                    "output_price_per_1m_tokens": 0.4,
                    "cached_input_price_per_1m_tokens": 0.025,
                    "currency": "USD",
                    "pricing_mode": "tiered",
                    "threshold_rule": "texto <= 200000 tokens",
                    "modality": "text",
                    "source_url": "https://openrouter.ai/api/v1/models",
                    "fetched_at": "2026-03-20T10:00:00Z",
                    "pricing_source": "updated",
                    "pricing_origin": "openrouter_api",
                    "is_cached_fallback": False,
                    "available": True,
                },
            ]

        def get_pricing(self, provider, model):
            return next(
                item for item in self.list_pricing_catalog()
                if item["provider"] == provider and item["model"] == model
            )

    project = {
        "id": "proj_001",
        "title": "Proyecto presupuesto",
        "format_name": "Tesis",
        "status": "completed",
        "token_usage": {
            "input_tokens_total": 2400,
            "output_tokens_total": 900,
            "total_tokens": 3300,
            "calls_total": 2,
            "reported_calls": 2,
            "estimated_calls": 0,
            "has_estimated_usage": False,
            "sections": [
                {
                    "section_id": "sec-1",
                    "section_path": "Introduccion",
                    "section_title": "Introduccion",
                    "input_tokens_total": 1200,
                    "output_tokens_total": 400,
                    "total_tokens": 1600,
                },
                {
                    "section_id": "sec-2",
                    "section_path": "Marco teorico",
                    "section_title": "Marco teorico",
                    "input_tokens_total": 1200,
                    "output_tokens_total": 500,
                    "total_tokens": 1700,
                },
            ],
            "providers": [
                {
                    "provider": "mistral",
                    "model": "mistral-medium-2505",
                    "input_tokens_total": 2400,
                    "output_tokens_total": 900,
                    "total_tokens": 3300,
                }
            ],
        },
    }

    report = build_project_budget_report(
        project,
        pricing_service=_PricingStub(),
        selected_provider="gemini",
        selected_model="gemini-2.0-flash",
    )

    assert report["usage"]["input_tokens_total"] == 2400
    assert report["usage"]["output_tokens_total"] == 900
    assert report["selected_pricing"]["provider"] == "google"
    assert report["selected_pricing"]["model"] == "gemini-2.0-flash"
    assert report["selected_pricing"]["pricing_origin"] == "openrouter_api"
    assert report["estimate"]["estimated_input_cost"] == 0.00024
    assert report["estimate"]["estimated_output_cost"] == 0.00036
    assert report["estimate"]["estimated_total_cost"] == 0.0006
    assert report["comparisons"][0]["provider"] == "google"
    assert len(report["comparisons"]) == 2
