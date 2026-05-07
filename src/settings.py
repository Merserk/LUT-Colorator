"""
Global Settings for LUT Studio Generator
"""

import os
import configparser

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.ini")

QUALITY_OPTIONS = [
    "Standard (33 Grid - Fast)", 
    "Ultra (65 Grid - Recommended Quality)",
    "Extreme (129 Grid - Best Quality)"
]

LOGIC_ENGINE_OPTIONS = [
    "Stochastic Parametric (Standard)", 
    "ARRI LogC4 (Pro)"
]

# Defaults (Fallback)
DEFAULT_QUALITY = "Ultra (65 Grid - Recommended Quality)"
DEFAULT_LOGIC_ENGINE = "ARRI LogC4 (Pro)" # Updated default as requested

def load_config():
    """Loads settings from config.ini, returns (quality, logic_engine)."""
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)
        if "Settings" in config:
            qual = config["Settings"].get("quality", DEFAULT_QUALITY)
            logic = config["Settings"].get("logic_engine", DEFAULT_LOGIC_ENGINE)
            return qual, logic
    
    # If not exists, create it with defaults
    save_config(DEFAULT_QUALITY, DEFAULT_LOGIC_ENGINE)
    return DEFAULT_QUALITY, DEFAULT_LOGIC_ENGINE

def save_config(quality, logic_engine):
    """Saves settings to config.ini."""
    config = configparser.ConfigParser()
    config["Settings"] = {
        "quality": quality,
        "logic_engine": logic_engine
    }
    with open(CONFIG_FILE, "w") as f:
        config.write(f)

# Load on module import to set initial constants
CURRENT_QUALITY, CURRENT_LOGIC_ENGINE = load_config()

# Re-assign DEFAULT constants to loaded values so app.py uses them on startup
DEFAULT_QUALITY = CURRENT_QUALITY
DEFAULT_LOGIC_ENGINE = CURRENT_LOGIC_ENGINE

def get_grid_size(quality_name):
    """Returns grid size (int) based on quality name string."""
    if "Extreme" in quality_name:
        return 129
    elif "Ultra" in quality_name:
        return 65
    else:
        # Standard or fallback
        return 33
