import json
from types import SimpleNamespace

from app.services.consultation import ConsultationEngine
from app.services.gemini import GeminiClient


def test_translate_remedies_batches_and_rejects_number_changes(monkeypatch):
    client = GeminiClient("test-key", "test-model")
    calls = []

    def generate(system, user, json_mode, max_tokens):
        calls.append((system, user, json_mode, max_tokens))
        return json.dumps(
            {
                "translations": [
                    {"index": 0, "text": "Translated remedy with 2 leaves"},
                    {"index": 1, "text": "Translated remedy with 3 leaves"},
                ]
            }
        )

    monkeypatch.setattr(client, "_generate", generate)

    result = client.translate_remedies(["Remedy with 2 leaves", "Remedy with 4 leaves"], "hi")

    assert result == ["Translated remedy with 2 leaves", None]
    assert len(calls) == 1
    assert calls[0][2] is True
    assert calls[0][3] == 1900


def test_cards_translate_all_remedies_in_one_call():
    class Dataset:
        def get(self, record_id):
            return {"record_id": record_id}

        def public(self, record):
            return {
                **record,
                "remedy_en": f"Remedy {record['record_id']}",
                "problem_en": "problem",
                "symptom_en": "symptom",
            }

    class Gemini:
        enabled = True

        def __init__(self):
            self.calls = []

        def translate_remedies(self, texts, language):
            self.calls.append((texts, language))
            return [f"Translated {text}" for text in texts]

    gemini = Gemini()
    engine = ConsultationEngine(
        SimpleNamespace(ds=Dataset(), gemini=gemini),
        {},
    )
    items = [
        {"record_id": "one", "matched_symptoms": ["cough"], "score": 0.9},
        {"record_id": "two", "matched_symptoms": ["fever"], "score": 0.8},
    ]

    cards = engine._cards(items, "te")

    assert len(gemini.calls) == 1
    assert gemini.calls[0] == (["Remedy one", "Remedy two"], "te")
    assert [card["translation"] for card in cards] == [
        "Translated Remedy one",
        "Translated Remedy two",
    ]


def test_simple_deterministic_followup_skips_gemini_extraction():
    class Gemini:
        enabled = True
        calls = 0

        def extract(self, text, known):
            self.calls += 1
            return None

    gemini = Gemini()
    engine = ConsultationEngine(SimpleNamespace(gemini=gemini), {})
    state = {"pending": "warning", "slots": {"symptoms": ["cough"]}}

    result = engine._extract("no", state, None)

    assert result.yes_no == "no"
    assert gemini.calls == 0
