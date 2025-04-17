import json
from pathlib import Path

def generate_template():
    """Generate template preloaders.json with default configuration."""
    template = {
        "preloaders": [
            {
                "task_type": "block_details",
                "module": "utils.preloaders.block_details",
                "class_name": "BlockDetailsDumper"
            }
        ]
    }

    config_dir = Path(__file__).parent.parent / 'config'
    config_dir.mkdir(exist_ok=True)
    template_path = config_dir / 'preloaders.json'

    with open(template_path, 'w') as f:
        json.dump(template, f, indent=2)
    print(f"Generated preloader template at {template_path}")

if __name__ == "__main__":
    generate_template()
