import os
import json
from typing import TypedDict


STATE_FILE = os.path.expanduser("~/.intervals_sync_state.json")


class State(TypedDict):
    last_sync: str | None


def load_state() -> State:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_sync": None}


def save_state(state: State) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
