"""Utility functions for file I/O, configuration loading, and hashing."""

import csv
import hashlib
import json
import os
from typing import Any, Dict, List, Optional


def load_config(config_path: str = "config/simulator_config.json") -> Dict[str, Any]:
    """Load and return configuration dictionary from JSON file."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found at: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    return config


def save_jsonl(records: List[Dict[str, Any]], filepath: str) -> None:
    """Save a list of dictionaries as a JSONL file with deterministic formatting."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8", newline="\n") as f:
        for record in records:
            line = json.dumps(record, ensure_ascii=False)
            f.write(line + "\n")


def read_jsonl(filepath: str) -> List[Dict[str, Any]]:
    """Read a JSONL file and return a list of dictionaries."""
    records = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def save_csv(records: List[Dict[str, Any]], filepath: str, fieldnames: List[str]) -> None:
    """Save records to a CSV file with deterministic Unix line terminators."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for record in records:
            # Format None values as empty strings for CSV compatibility
            row = {k: ("" if record.get(k) is None else record.get(k)) for k in fieldnames}
            writer.writerow(row)


def read_csv(filepath: str) -> List[Dict[str, Any]]:
    """Read a CSV file and return a list of dictionaries."""
    records = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(dict(row))
    return records


def compute_file_hash(filepath: str, algorithm: str = "sha256") -> str:
    """Compute cryptographic hash of a file's raw byte content."""
    h = hashlib.new(algorithm)
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def compute_dataset_hashes(file_paths: Dict[str, str]) -> Dict[str, str]:
    """Compute hashes for a dictionary of dataset filepaths {key: filepath}."""
    return {key: compute_file_hash(path) for key, path in file_paths.items() if os.path.exists(path)}

