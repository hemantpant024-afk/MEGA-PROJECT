# Marcus - A simple voice assista
import os
import re
import uuid
import datetime
import webbrowser
from urllib.parse import quote_plus

import pygame
import requests
import pywhatkit
import wikipedia
import speech_recognition as sr
from gtts import gTTS
from openai import OpenAI

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # fine, plain environment variables still work

# ------------------------------------------------------------------ settings
NAME = "Marcus"
WAKE_WORDS = ("hi", "hello", "hey", "marcus", "marco")
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NEWS_COUNTRY = "in"
DEFAULT_CITY = "Bareilly"
AI_MODEL = "gpt-4o-mini"

SITES = {
    "google": "https://google.com",
    "youtube": "https://youtube.com",
    "facebook": "https://facebook.com",
    "linkedin": "https://linkedin.com",
    "instagram": "https://instagram.com",
    "github": "https://github.com",
    "gmail": "https://mail.google.com",
}

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
history = [
    {
        "role": "system",
        "content": (
            f"You are {NAME}, a friendly voice assistant. "
            "Keep answers short (1-3 sentences) because they are spoken aloud. "
            "Do not use markdown or lists."
        ),
    }
]


# ------------------------------------------------------------------ helpers
def has_word(text: str, *words: str) -> bool:
    """True if any of `words` appears as a whole word (so 'update' != 'date')."""
    return any(re.search(rf"\b{re.escape(w)}\b", text) for w in words)


def split_wake_word(heard: str):
    """
    Returns None if no wake word was heard.
    Otherwise returns whatever was said after the wake word ("" if nothing),
    so "hey marcus what time is it" works in one go.
    """
    words = re.findall(r"[a-z']+", heard.lower())
    for i, w in enumerate(words):
        if w in WAKE_WORDS:
            rest = words[i + 1:]
            while rest and rest[0] in WAKE_WORDS:
                rest.pop(0)
            return " ".join(rest)
    return None


# ------------------------------------------------------------------ speech out
def speak(text: str) -> None:
    print(f"{NAME}: {text}")
    filename = f"tts_{uuid.uuid4().hex}.mp3"
    try:
        gTTS(text=text, lang="en").save(filename)
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.load(filename)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.music.unload()
    except Exception as e:
        print("Speech output error:", e)
    finally:
        if os.path.exists(filename):
            try:
                os.remove(filename)
            except OSError:
                pass


# ------------------------------------------------------------------ AI chat
def ask_ai(prompt: str) -> str:
    if client is None:
        return "My AI brain is offline. Please set the OpenAI API key."
    history.append({"role": "user", "content": prompt})
    try:
        resp = client.chat.completions.create(model=AI_MODEL, messages=history)
        answer = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        history.pop()
        print("OpenAI error:", e)
        return "Sorry, I couldn't reach my AI service."
    history.append({"role": "assistant", "content": answer})
    while len(history) > 21:                   # keep system msg + last 20
        del history[1:3]
    return answer


# ------------------------------------------------------------------ features
def tell_news() -> None:
    if not NEWSAPI_KEY:
        speak("Please set the news API key first.")
        return
    try:
        r = requests.get(
            "https://newsapi.org/v2/top-headlines",
            params={"country": NEWS_COUNTRY, "apiKey": NEWSAPI_KEY},
            timeout=10,
        )
        r.raise_for_status()
        articles = r.json().get("articles", [])[:5]
        if not articles:
            speak("I couldn't find any headlines right now.")
            return
        speak("Here are the top headlines.")
        for a in articles:
            speak(a["title"])
    except Exception as e:
        print("News error:", e)
        speak("Sorry, I couldn't fetch the news.")


def tell_weather(city: str) -> None:
    try:
        r = requests.get(
            f"https://wttr.in/{quote_plus(city)}",
            params={"format": "%C, %t, humidity %h"},
            timeout=10,
        )
        r.raise_for_status()
        speak(f"Weather in {city}: {r.text.strip()}")
    except Exception as e:
        print("Weather error:", e)
        speak("Sorry, I couldn't get the weather.")


def wiki_summary(topic: str) -> None:
    try:
        speak(wikipedia.summary(topic, sentences=2, auto_suggest=True))
    except Exception:
        speak(f"I couldn't find anything on {topic}.")


# ------------------------------------------------------------------ commands
def process_command(command: str) -> bool:
    """Handle a command. Returns False if Marcus should shut down."""
    c = command.lower().strip().rstrip(".?!")

    if not c:
        return True

    if has_word(c, "goodbye", "exit", "quit") or "shut down" in c or "stop listening" in c:
        speak("Goodbye! Call me anytime.")
        return False

    if has_word(c, "time") and not has_word(c, "play"):
        speak("It's " + datetime.datetime.now().strftime("%I:%M %p"))

    elif has_word(c, "date") or (has_word(c, "today") and has_word(c, "day")):
        speak("Today is " + datetime.datetime.now().strftime("%A, %d %B %Y"))

    elif c.startswith("open "):
        target = c[5:].strip()
        if target in SITES:
            speak(f"Opening {target}")
            webbrowser.open(SITES[target])
        else:
            speak(f"Searching for {target}")
            webbrowser.open(f"https://www.google.com/search?q={quote_plus(target)}")

    elif c.startswith("play "):
        song = c[5:].strip()
        if song:
            speak(f"Playing {song} on YouTube")
            try:
                pywhatkit.playonyt(song)
            except Exception as e:
                print("YouTube error:", e)
                speak("Sorry, I couldn't play that.")
        else:
            speak("Please tell me what to play.")

    elif c.startswith("search "):
        query = c[7:].strip()
        speak(f"Searching for {query}")
        webbrowser.open(f"https://www.google.com/search?q={quote_plus(query)}")

    elif has_word(c, "news"):
        tell_news()

    elif has_word(c, "weather"):
        m = re.search(r"weather (?:in|of|at|for) (.+)", c)
        tell_weather(m.group(1) if m else DEFAULT_CITY)

    elif c.startswith(("who is ", "what is ", "tell me about ")):
        topic = re.sub(r"^(who is|what is|tell me about)\s+", "", c)
        wiki_summary(topic)

    elif "your name" in c or "who are you" in c:
        speak(f"I am {NAME}, your voice assistant.")

    elif "clear memory" in c or has_word(c, "forget"):
        del history[1:]
        speak("Okay, I've cleared our conversation.")

    else:
        speak(ask_ai(command))

    return True


# ------------------------------------------------------------------ main loop
def main() -> None:
    r = sr.Recognizer()
    r.dynamic_energy_threshold = True
    r.pause_threshold = 0.8

    with sr.Microphone() as source:
        print("Calibrating for background noise...")
        r.adjust_for_ambient_noise(source, duration=1)

    speak(f"{NAME} is ready. Say my name to wake me up.")
    running = True

    while running:
        try:
            with sr.Microphone() as source:
                print("Listening for wake word...")
                audio = r.listen(source, timeout=5, phrase_time_limit=8)
            heard = r.recognize_google(audio).lower()
            print("Heard:", heard)

            rest = split_wake_word(heard)
            if rest is None:
                continue

            if rest:
                # Wake word and command in one sentence
                command = rest
            else:
                speak("Yes?")
                with sr.Microphone() as source:
                    print(f"{NAME} is active... speak your command")
                    audio = r.listen(source, timeout=6, phrase_time_limit=10)
                command = r.recognize_google(audio)

            print("You:", command)
            running = process_command(command)

        except sr.WaitTimeoutError:
            pass                                # silence is fine
        except sr.UnknownValueError:
            pass                                # couldn't understand audio
        except sr.RequestError as e:
            print("Google speech service error:", e)
        except KeyboardInterrupt:
            speak("Shutting down.")
            break
        except Exception as e:
            print("Error:", e)


if __name__ == "__main__":
    main()