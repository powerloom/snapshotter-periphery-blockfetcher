#!/usr/bin/env python3
import os
import json
import subprocess
from string import Template
from dotenv import load_dotenv

def fill_template():
    """Fill settings template with environment variables"""
    # Load environment variables from .env file
    load_dotenv()

    template_path = 'config/settings.template.json'
    if not os.path.exists(template_path):
        print(f"Template file not found: {template_path}")
        return

    with open(template_path, 'r') as f:
        template = Template(f.read())
    
    # Debug: Print environment variables
    print("Environment Variables:")
    for key, value in os.environ.items():
        print(f"{key}={value}")

    # Get env vars with defaults
    filled = template.safe_substitute(os.environ)
    
    # Debug: Print filled template
    print("Filled Template:")
    print(filled)

    # Write filled settings
    with open('config/settings.json', 'w') as f:
        f.write(filled)

if __name__ == "__main__":
    fill_template()
    # Execute main application
    subprocess.run(["python", "main.py"]) 