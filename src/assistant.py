import datetime
import json
import os
import subprocess

import requests

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


TOOL_IMPLEMENTATIONS = {
    "open_app": open_app,
    "get_time": get_time,
    "close_app": close_app,
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
