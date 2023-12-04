import json

BLACKLIST_FILE = "blacklist.json"
CONFIG_FILE = "config.json"


def read_json_file(file_path: str):
    """Read and return JSON data from a file."""
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return {"ids": []} if "blacklist" in file_path else {"statuses": []}


def write_json_file(file_path: str, data):
    """Write JSON data to a file."""
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)


def load_blacklist():
    """Load blacklist from the blacklist file."""
    return read_json_file(BLACKLIST_FILE)


def load_config():
    """Load configuration from the config file."""
    return read_json_file(CONFIG_FILE)


def add_user_to_blacklist(user_id: int):
    """Add User to Blacklist"""
    file_data = read_json_file(BLACKLIST_FILE)
    file_data["ids"].append(user_id)
    write_json_file(BLACKLIST_FILE, file_data)


def remove_user_from_blacklist(user_id: int):
    """Remove User from Blacklist"""
    file_data = read_json_file(BLACKLIST_FILE)
    if user_id in file_data["ids"]:
        file_data["ids"].remove(user_id)
        write_json_file(BLACKLIST_FILE, file_data)


def add_status_to_config(status: str):
    """Add Status to Status list"""
    file_data = read_json_file(CONFIG_FILE)
    file_data["statuses"].append(status)
    write_json_file(CONFIG_FILE, file_data)


def remove_status_from_config(status: str):
    """Remove Status from Status list"""
    file_data = read_json_file(CONFIG_FILE)
    if status in file_data["statuses"]:
        file_data["statuses"].remove(status)
        write_json_file(CONFIG_FILE, file_data)
