import os
import json

STATE_FILE = os.path.expanduser("~/.intervals_sync_state.json")


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"synced_ids": [], "paths": {}, "last_sync": None}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
