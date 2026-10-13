"""Optional sparse outfitting writes; availability freshness stays in its parent."""
from __future__ import annotations
import json
import os
from urllib.request import urlopen


def shared_outfitting_writes_enabled():
    return os.environ.get("EDFRAME_SHARED_OUTFITTING_FRESHNESS", "0") == "1"


def require_outfitting_reader():
    """Never enable sparse writes before the compatible API reader is running."""
    if not shared_outfitting_writes_enabled():
        return
    url = os.environ.get("EDFRAME_INTERNAL_API_URL", "http://api:8000")
    with urlopen(url.rstrip("/") + "/healthz", timeout=5) as response:
        health = json.load(response)
    if health.get("capabilities", {}).get("sharedOutfittingFreshness") is not True:
        raise RuntimeError("Sparse outfitting writes require the shared-freshness API reader")


def outfitting_content_changed(retained, incoming, incoming_id):
    # All identifiers are internal SQL aliases, never client inputs.
    return f"""
        {retained}.module_id IS DISTINCT FROM
            COALESCE({incoming_id}, {retained}.module_id)
        OR (
            {incoming}.buy_price IS NOT NULL
            AND ({retained}.price_observed_at IS NULL
                 OR {incoming}.price_observed_at >= {retained}.price_observed_at)
            AND ({retained}.buy_price, {retained}.buy_merc_coins_price,
                 {retained}.price_observed_at, {retained}.price_source)
                IS DISTINCT FROM
                ({incoming}.buy_price, {incoming}.buy_merc_coins_price,
                 {incoming}.price_observed_at, {incoming}.price_source)
        )
    """
