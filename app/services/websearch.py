"""Controlled web-search fallback.

Used ONLY when the Ayurvedic dataset has no sufficiently relevant record.
Safeguards:
  * query is built from de-identified symptom terms only (no personal data);
  * results are restricted to an allow-list of authoritative domains, https only;
  * every result is re-verified against the allow-list after retrieval;
  * output is clearly labelled external and is never turned into a personalised prescription.
Provider: Google Programmable Search (Custom Search JSON API). Disabled when keys are absent.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)

TRUSTED_DOMAINS = [
    "ayush.gov.in", "main.ayush.gov.in", "who.int", "mohfw.gov.in", "nhp.gov.in", "nhm.gov.in", "icmr.gov.in",
    "pubmed.ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov", "nih.gov", "medlineplus.gov", "cdc.gov",
    "nhs.uk", "mayoclinic.org", "clevelandclinic.org", "aiims.edu", "tnhealth.tn.gov.in", "cochrane.org",
]
TRUSTED_SUFFIXES = (".gov.in", ".nic.in", ".gov", ".gov.uk")
SOURCE_NAMES = {"who.int": "World Health Organization", "ayush.gov.in": "Ministry of AYUSH", "mohfw.gov.in": "Ministry of Health & Family Welfare",
                "nhp.gov.in": "National Health Portal", "icmr.gov.in": "ICMR", "nih.gov": "NIH", "ncbi.nlm.nih.gov": "NCBI / PubMed",
                "pubmed.ncbi.nlm.nih.gov": "PubMed", "cdc.gov": "CDC", "nhs.uk": "NHS (UK)", "mayoclinic.org": "Mayo Clinic",
                "clevelandclinic.org": "Cleveland Clinic", "aiims.edu": "AIIMS", "medlineplus.gov": "MedlinePlus"}


def is_trusted(url: str) -> bool:
    try:
        u = urlparse(url)
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not host:
        return False
    return any(host == d or host.endswith("." + d) for d in TRUSTED_DOMAINS) or host.endswith(TRUSTED_SUFFIXES)


def source_name(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    for d, n in SOURCE_NAMES.items():
        if host == d or host.endswith("." + d):
            return n
    return host


class WebSearch:
    def __init__(self, api_key: str, cx: str):
        self.api_key, self.cx = api_key, cx

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.cx)

    @staticmethod
    def build_query(symptoms: list[str], purpose: str = "symptoms") -> str:
        terms = [re.sub(r"[^\w\s-]", "", s)[:40] for s in symptoms[:4]]
        return " ".join(terms + ["causes self-care when to see a doctor"]) if purpose == "symptoms" else " ".join(terms)

    def search(self, query: str, n: int = 5) -> list[dict]:
        if not self.enabled:
            return []
        try:
            r = requests.get("https://www.googleapis.com/customsearch/v1",
                             params={"key": self.api_key, "cx": self.cx, "q": query, "num": min(n * 2, 10), "safe": "active"},
                             timeout=10)
            r.raise_for_status()
            items = r.json().get("items", [])
        except Exception as exc:
            log.warning("Web search failed: %s", type(exc).__name__)
            return []
        out = []
        for it in items:
            url = it.get("link", "")
            snippet = (it.get("snippet") or "").strip()
            if not is_trusted(url) or not snippet:
                continue  # verification step: untrusted / empty results are discarded
            meta = (it.get("pagemap", {}).get("metatags") or [{}])[0]
            date = meta.get("article:modified_time") or meta.get("article:published_time") or meta.get("date") or None
            out.append({"title": it.get("title", "")[:160], "url": url, "snippet": snippet[:320],
                        "source": source_name(url), "date": (date or "")[:10] or None})
            if len(out) >= n:
                break
        return out
