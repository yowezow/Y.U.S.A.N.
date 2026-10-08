from yusan_core.intents import Intent, IntentRouter


def test_routes_safari_as_an_application() -> None:
    result = IntentRouter().route("Safari'yi aç")
    assert result.intent is Intent.OPEN_APP
    assert result.value == "Safari"


def test_routes_google_query() -> None:
    result = IntentRouter().route("Google'da Porsche 911 GT3 RS ara")
    assert result.intent is Intent.WEB_SEARCH
    assert result.value == "Porsche 911 GT3 RS"


def test_routes_general_questions_to_llm() -> None:
    assert IntentRouter().route("Kuantum bilgisayar nasıl çalışır?").intent is Intent.LLM


def test_routes_time_without_llm() -> None:
    assert IntentRouter().route("Saat kaç?").intent is Intent.GET_TIME
