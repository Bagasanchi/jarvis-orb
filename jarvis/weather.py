import requests
from urllib.parse import quote

def get_weather(location: str = "Ulaanbaatar") -> str:
    """Fetch current weather summary for a location from wttr.in."""
    try:
        url = f"https://wttr.in/{quote(location, safe='')}?format=j1"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            curr = data['current_condition'][0]
            temp_c = curr['temp_C']
            desc = curr['weatherDesc'][0]['value']
            humidity = curr['humidity']
            feels_like = curr['FeelsLikeC']
            return f"The current weather in {location} is {desc} at {temp_c} degrees Celsius, feeling like {feels_like} degrees, with {humidity} percent humidity."
    except Exception as e:
        print(f"[Weather Error] {e}")

    return f"I couldn't retrieve the weather for {location}, sir. Please try again later."
