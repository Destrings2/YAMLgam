"""
YAML Base and Overlay Generator

This module provides functionality to find the deep intersection of multiple YAML files,
creating a common base and individual overlays for each file, removing empty structures.

Date: 2024-07-13
"""

import yaml
from typing import Any, List, Dict, Union, Tuple
from functools import reduce
import logging
import argparse
from deepdiff import DeepDiff
import re

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def read_yaml(file_path: str) -> Union[Dict, List, None]:
    """Read a YAML file and return its contents."""
    try:
        with open(file_path, 'r') as file:
            return yaml.safe_load(file)
    except (yaml.YAMLError, IOError) as e:
        logger.error(f"Error reading YAML file {file_path}: {e}")
    return None

def save_yaml(data: Any, file_path: str) -> bool:
    """Save data to a YAML file."""
    try:
        with open(file_path, 'w') as file:
            yaml.dump(data, file, default_flow_style=False)
        logger.info(f"Data successfully saved to {file_path}")
        return True
    except (yaml.YAMLError, IOError) as e:
        logger.error(f"Error saving YAML file {file_path}: {e}")
    return False

def remove_empty_structures(data: Any) -> Any:
    """Recursively remove empty dictionaries and lists from the given data structure."""
    if isinstance(data, dict):
        return {k: remove_empty_structures(v) for k, v in data.items() 
                if remove_empty_structures(v) not in ({}, [], None)}
    elif isinstance(data, list):
        return [remove_empty_structures(item) for item in data 
                if remove_empty_structures(item) not in ({}, [], None)]
    else:
        return data

def deep_intersection(data_list: List[Any]) -> Any:
    """Recursively find the intersection of multiple nested data structures."""
    if not data_list:
        return None
    
    if all(isinstance(d, dict) for d in data_list):
        common_keys = reduce(set.intersection, (set(d.keys()) for d in data_list))
        result = {
            k: deep_intersection([d[k] for d in data_list if k in d])
            for k in common_keys
        }
        return remove_empty_structures(result)
    elif all(isinstance(d, list) for d in data_list):
        result = []
        for items in zip(*data_list):
            intersection = deep_intersection(list(items))
            if intersection not in ({}, [], None):
                result.append(intersection)
        return result if result else None
    elif all(d == data_list[0] for d in data_list):
        return data_list[0]
    else:
        return None

def parse_path(path: str) -> List[Union[str, int]]:
    """Parse a DeepDiff path string into a list of keys and indices."""
    components = re.findall(r'\[\'([^\']*)\'?\]|\[(\d+)\]', path)
    return [int(i) if i else s for s, i in components]

def set_nested(d: Dict, path: List[Union[str, int]], value: Any) -> None:
    """Set a value in a nested dictionary or list."""
    for i, key in enumerate(path[:-1]):
        if isinstance(key, str):
            d = d.setdefault(key, {} if isinstance(path[i+1], str) else [])
        else:  # key is an integer (list index)
            while len(d) <= key:
                d.append({} if isinstance(path[i+1], str) else [])
            d = d[key]
    last_key = path[-1]
    if isinstance(last_key, str):
        d[last_key] = value
    else:
        while len(d) <= last_key:
            d.append(None)
        d[last_key] = value

def get_nested(d: Dict, path: List[Union[str, int]]) -> Any:
    """Get a value from a nested dictionary or list."""
    for key in path:
        d = d[key]
    return d

def create_overlay(base: Dict, full: Dict) -> Dict:
    """Create an overlay by comparing the full structure to the base."""
    diff = DeepDiff(base, full, ignore_order=True)
    overlay = {}

    if 'dictionary_item_added' in diff:
        for item in diff['dictionary_item_added']:
            path = parse_path(item)
            value = get_nested(full, path)
            set_nested(overlay, path, value)

    if 'values_changed' in diff:
        for item, change in diff['values_changed'].items():
            path = parse_path(item)
            set_nested(overlay, path, change['new_value'])

    if 'iterable_item_added' in diff:
        for item, value in diff['iterable_item_added'].items():
            path = parse_path(item)
            parent_path, index = path[:-1], path[-1]
            parent = get_nested(overlay, parent_path) if parent_path else overlay
            if not isinstance(parent, list):
                parent = []
                set_nested(overlay, parent_path, parent)
            while len(parent) <= index:
                parent.append(None)
            parent[index] = value

    if 'type_changes' in diff:
        for item, change in diff['type_changes'].items():
            path = parse_path(item)
            set_nested(overlay, path, change['new_value'])

    return remove_empty_structures(overlay)

def generate_base_and_overlays(file_list: List[str]) -> Tuple[Dict, List[Dict]]:
    """Generate a common base and overlays for the given YAML files."""
    data_list = [read_yaml(file) for file in file_list]
    if None in data_list:
        logger.error("Failed to read one or more YAML files")
        return None, []
    
    base = deep_intersection(data_list)
    overlays = [create_overlay(base, data) for data in data_list]
    
    return base, overlays

def main(args: argparse.Namespace) -> None:
    """Main function to process YAML files and save the base and overlays."""
    logger.info(f"Processing {len(args.input_files)} input files")
    base, overlays = generate_base_and_overlays(args.input_files)
    
    if base is not None:
        base_file = args.output_prefix + "_base.yaml"
        if save_yaml(remove_empty_structures(base), base_file):
            logger.info(f"Base structure saved to {base_file}")
        else:
            logger.error(f"Failed to save base structure to {base_file}")
        
        for i, overlay in enumerate(overlays):
            overlay_file = f"{args.output_prefix}_overlay_{i+1}.yaml"
            if save_yaml(remove_empty_structures(overlay), overlay_file):
                logger.info(f"Overlay {i+1} saved to {overlay_file}")
            else:
                logger.error(f"Failed to save overlay {i+1} to {overlay_file}")
    else:
        logger.warning("No common base found")

def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate a common base and overlays for multiple YAML files.",
        epilog="Example: %(prog)s -o output input1.yaml input2.yaml input3.yaml"
    )
    parser.add_argument(
        '-o', '--output-prefix',
        required=True,
        help="Prefix for output files (base and overlays)"
    )
    parser.add_argument(
        'input_files',
        nargs='+',
        help="Input YAML files to process"
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help="Increase output verbosity"
    )
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    main(args)