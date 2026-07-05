import datetime
import json
import os
import subprocess
import sys
import threading
import webbrowser

import requests

# Windows consoles often default to cp1252, which can't print weather symbols etc.
sys.stdout.reconfigure(encoding="utf-8")

# Step 1: read the API key from our config file
with open("config/api_key.txt", "r") as f:
    api_key = f.read().strip()

# Step 2: define the tool(s) Nemotron is allowed to call
tools = [
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Open an application on the user's Windows computer",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Name of the application to open, e.g. notepad, calculator, chrome",
                    }
                },
                "required": ["app_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "Get the current date and time",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "close_app",
            "description": "Close a running application on the user's Windows computer",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "Name of the application to close, e.g. notepad, explorer, chrome",
                    }
                },
                "required": ["app_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web and return a short summary of the top result",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search for, e.g. python tutorial",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather conditions for a city",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name, e.g. Chennai, London, New York",
                    }
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_note",
            "description": "Save a note for the user, with a timestamp, to notes.txt",
            "parameters": {
                "type": "object",
                "properties": {
                    "note": {
                        "type": "string",
                        "description": "The text of the note to save",
                    }
                },
                "required": ["note"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_running_apps",
            "description": "List the applications currently open on the user's computer (apps with visible windows, not background processes)",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_volume",
            "description": "Set the Windows system volume",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "integer",
                        "description": "Volume level from 0 (mute) to 100 (max)",
                    }
                },
                "required": ["level"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Capture a screenshot of the screen and save it to the screenshots folder",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_info",
            "description": "Get system status: battery percentage, CPU usage, RAM usage, and free disk space",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_website",
            "description": "Open a website in the user's default browser",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The website URL, e.g. youtube.com or https://github.com",
                    }
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": "Set a reminder that will pop up after a number of minutes",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "What to remind the user about",
                    },
                    "minutes": {
                        "type": "number",
                        "description": "How many minutes from now to show the reminder",
                    },
                },
                "required": ["message", "minutes"],
            },
        },
    },
]


def find_app_id(app_name):
    # Store/UWP apps (e.g. Apple Music) aren't findable via `start` - look them
    # up by display name through Get-StartApps instead. app_name is passed via
    # an env var rather than interpolated into the script, to avoid injection.
    script = (
        '(Get-StartApps | Where-Object { $_.Name -like "*$env:OPEN_APP_NAME*" } '
        "| Select-Object -First 1).AppID"
    )
    env = {**os.environ, "OPEN_APP_NAME": app_name}
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        env=env,
    )
    return result.stdout.strip()


def open_app(app_name):
    app_id = find_app_id(app_name)
    if app_id:
        subprocess.Popen(["explorer.exe", f"shell:appsFolder\\{app_id}"])
    else:
        # "start" is a cmd builtin, not an executable, so it must run through the shell
        subprocess.Popen(f'start "" "{app_name}"', shell=True)
    return f"Opened {app_name}"


def get_time():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def close_app(app_name):
    # taskkill matches on image name, so it needs the .exe suffix
    image_name = app_name if app_name.lower().endswith(".exe") else f"{app_name}.exe"
    subprocess.run(["taskkill", "/IM", image_name, "/F"])
    return f"Closed {app_name}"


def search_web(query):
    # DuckDuckGo instant answer API - free, no key needed
    response = requests.get(
        "https://api.duckduckgo.com/",
        params={"q": query, "format": "json", "no_html": 1},
    )
    result = response.json()
    if result.get("AbstractText"):
        return result["AbstractText"]
    # no direct abstract - fall back to the first related topic
    for topic in result.get("RelatedTopics", []):
        if isinstance(topic, dict) and topic.get("Text"):
            return topic["Text"]
    return f"No instant answer found for '{query}'"


def get_weather(city):
    # wttr.in - free weather service, no key needed; format=3 gives a one-liner
    response = requests.get(f"https://wttr.in/{city}", params={"format": "3"})
    return response.text.strip()


def take_note(note):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("notes.txt", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {note}\n")
    return f"Note saved: {note}"


def list_running_apps():
    # only processes with a visible window title = actual apps, not background stuff
    script = (
        'Get-Process | Where-Object { $_.MainWindowTitle -ne "" } '
        "| Select-Object -ExpandProperty ProcessName -Unique"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
    )
    apps = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return ", ".join(apps) if apps else "No apps with open windows found"


def set_volume(level):
    from pycaw.pycaw import AudioUtilities

    level = max(0, min(100, int(level)))
    endpoint = AudioUtilities.GetSpeakers().EndpointVolume
    endpoint.SetMasterVolumeLevelScalar(level / 100, None)
    return f"Volume set to {level}%"


def take_screenshot():
    import pyautogui

    os.makedirs("screenshots", exist_ok=True)
    filename = datetime.datetime.now().strftime("screenshots/screenshot_%Y%m%d_%H%M%S.png")
    pyautogui.screenshot(filename)
    return f"Screenshot saved to {filename}"


def get_system_info():
    import psutil

    parts = []
    battery = psutil.sensors_battery()
    if battery:
        plugged = "plugged in" if battery.power_plugged else "on battery"
        parts.append(f"Battery: {battery.percent}% ({plugged})")
    else:
        parts.append("Battery: none detected")
    parts.append(f"CPU: {psutil.cpu_percent(interval=0.5)}%")
    ram = psutil.virtual_memory()
    parts.append(f"RAM: {ram.percent}% used")
    disk = psutil.disk_usage("C:\\")
    parts.append(f"Disk C: {disk.free / (1024**3):.1f} GB free of {disk.total / (1024**3):.1f} GB")
    return " | ".join(parts)


def open_website(url):
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    webbrowser.open(url)
    return f"Opened {url}"


def set_reminder(message, minutes):
    def show_reminder():
        print(f"\n*** REMINDER: {message} ***")
        # also pop a Windows toast-style message box so it's visible outside the console
        subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Add-Type -AssemblyName System.Windows.Forms; "
                "[System.Windows.Forms.MessageBox]::Show($env:REMINDER_MSG, 'Reminder')",
            ],
            env={**os.environ, "REMINDER_MSG": message},
        )

    timer = threading.Timer(minutes * 60, show_reminder)
    timer.daemon = True  # don't keep the program alive just for the reminder
    timer.start()
    return f"Reminder set for {minutes} minute(s) from now: {message}"


TOOL_IMPLEMENTATIONS = {
    "open_app": open_app,
    "get_time": get_time,
    "close_app": close_app,
    "search_web": search_web,
    "get_weather": get_weather,
    "take_note": take_note,
    "list_running_apps": list_running_apps,
    "set_volume": set_volume,
    "take_screenshot": take_screenshot,
    "get_system_info": get_system_info,
    "open_website": open_website,
    "set_reminder": set_reminder,
}

# Step 3: chat loop - prompt, send to Nemotron, act on the reply, repeat
url = "https://openrouter.ai/api/v1/chat/completions"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}

conversation_history = []

while True:
    user_input = input("You: ")
    if user_input.lower() in ("quit", "exit"):
        break

    conversation_history.append({"role": "user", "content": user_input})

    data = {
        "model": "nvidia/nemotron-3-super-120b-a12b:free",
        "messages": conversation_history,
        "tools": tools,
    }

    response = requests.post(url, headers=headers, json=data)
    result = response.json()
    message = result["choices"][0]["message"]
    conversation_history.append(message)

    # if the model asked to call a tool, run it; otherwise print its text reply
    tool_calls = message.get("tool_calls")
    if tool_calls:
        for call in tool_calls:
            function_name = call["function"]["name"]
            arguments = json.loads(call["function"]["arguments"])
            implementation = TOOL_IMPLEMENTATIONS[function_name]
            output = implementation(**arguments)
            print(output)
            conversation_history.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "name": function_name,
                    "content": str(output),
                }
            )
    else:
        print(message["content"])
