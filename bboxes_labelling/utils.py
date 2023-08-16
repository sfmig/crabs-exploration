import json


def read_json_file(file_path):
    try:
        with open(file_path) as file:
            return json.load(file)
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        return None
    except json.JSONDecodeError:
        print(f"Error decoding JSON data from file: {file_path}")
        return None
