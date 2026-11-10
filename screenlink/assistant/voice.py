from . import speech, whispercpp


def engine_kind(settings):
    if settings.get("voice_engine") == "vosk":
        return "vosk"
    if whispercpp.find_server():
        return "whisper"
    return "vosk"


def required(settings):
    if engine_kind(settings) == "vosk":
        return [("vosk", "speech model", 40, speech.have_model())]
    items = []
    wake = settings.get("wake_model")
    dictation = settings.get("dictation_model")
    if settings.get("wake_word"):
        items.append((wake, "wake-word model", whispercpp.model_size_mb(wake), whispercpp.have_model(wake)))
    if dictation != wake or not settings.get("wake_word"):
        items.append((dictation, "dictation model", whispercpp.model_size_mb(dictation),
                      whispercpp.have_model(dictation)))
    return items


def missing(settings):
    return [item for item in required(settings) if not item[3]]


def have_all(settings):
    return not missing(settings)


def missing_mb(settings):
    return sum(item[2] for item in missing(settings))


def download_missing(settings, progress=None, opener=None):
    todo = missing(settings)
    for index, (key, label, mb, _) in enumerate(todo):
        def report(frac, index=index, label=label):
            if progress:
                progress(frac, label, index + 1, len(todo))
        if key == "vosk":
            speech.download_model(report, opener=opener)
        else:
            whispercpp.download_model(key, report, opener=opener)


def make_listener(settings, on_wake, on_text, on_status, wake_enabled):
    if engine_kind(settings) == "vosk":
        return speech.Listener(on_wake, on_text, on_status, wake_enabled=wake_enabled)
    engine = whispercpp.Engine(whispercpp.find_server(), settings.get("wake_model"),
                               settings.get("dictation_model"), gpu=bool(settings.get("use_gpu")))
    return speech.WhisperListener(on_wake, on_text, on_status, engine, wake_enabled=wake_enabled)


def describe(settings):
    kind = engine_kind(settings)
    if kind == "vosk":
        return "Voice: offline Vosk (small)"
    return "Voice: Whisper %s on %s" % (settings.get("dictation_model"), "GPU" if settings.get("use_gpu") else "CPU")
