"""
BCF Handler Module
Handles all BCF (BIM Collaboration Format) operations including:
- Topic extraction and parsing
- Compliance issue management
- IFC GUID matching
- BCF analysis and prioritization
"""

from pathlib import Path
from collections import defaultdict
import os
import re
import ast
import json
import uuid
import zipfile
import shutil
import string
import xml.dom.minidom as minidom
import pandas as pd
import ifcopenshell
from typing import List, Optional

from common.paths import get_path

class Topic:
    """
    Represents a single BCF topic with metadata and IFC references.
    """
    
    def __init__(self, topic_id: str, directory: Optional[Path] = None, description: Optional[str] = None):
        self.directory = directory
        self.path = Path(directory) / topic_id if directory else None
        self.id = topic_id
        self.title = None
        self.description = description
        self.author = None
        self.snapshot = None
        self.ifc_guids = []
        
        if self.description is None and self.path:
            self._extract_topic_data()
    
    def _extract_topic_data(self):
        """Extract topic metadata from BCF markup and viewpoint files."""
        if not self.path:
            return
        
        try:
            # Parse markup.bcf for metadata
            markup = minidom.parse(str(self.path / 'markup.bcf'))
            self.title = markup.getElementsByTagName('Title')[0].childNodes[0].nodeValue
            self.title = string.capwords(self.title, sep=None) # type: ignore
            
            desc_nodes = markup.getElementsByTagName('Description')[0].childNodes
            self.description = desc_nodes[0].nodeValue if desc_nodes else ''
            
            self.author = markup.getElementsByTagName('CreationAuthor')[0].childNodes[0].nodeValue
            self.snapshot = self.path / markup.getElementsByTagName('Snapshot')[0].childNodes[0].nodeValue # type: ignore
            
            # Parse viewpoint.bcfv for IFC GUIDs
            viewpoint_xml = minidom.parse(str(self.path / 'viewpoint.bcfv'))
            components = viewpoint_xml.getElementsByTagName('Component')
            
            self.ifc_guids = [comp.getAttribute('IfcGuid') for comp in components]
            
        except Exception as e:
            print(f"Error extracting topic data for {self.id}: {e}")
    
    def __repr__(self) -> str:
        return (f"Topic ID: {self.id}\n"
                f"Title: {self.title}\n"
                f"Description: {self.description}\n"
                f"Author: {self.author}\n\n")


class ComplianceIssue:
    """
    Represents a compliance issue extracted from BCF topics.
    Stores structured information about building code violations.
    """
    
    def __init__(self, id: str, description: str, ifc_guids: List[str]):
        self.id = id
        self.description = description
        self.ifc_guids = ifc_guids
        
        # Structured compliance information
        self.info_issue = {
            "regulation_clause": "",
            "core_component_type": "",
            "core_component_type_number": "",
            "core_component_GUID": "",
            "checking_variable_name": "",
            "checking_variable_unit": "",
            "required_variable_value": "",
            "actual_variable_value": "",
            "bcf_id": "",
            "other_component_GUID": []  # IFC GUIDs from viewpoint file
        }
    
    def disassemble_prompt_response_to_issue_parts(self, details_string: str):
        """
        Parse LLM response string and populate info_issue dictionary.
        Handles markdown code blocks and converts string to dict.
        """
        # Remove markdown code blocks
        details_cleaned = re.sub(r"```(?:python)?\n|\n```", "", details_string).strip()
        
        try:
            details_dict = ast.literal_eval(details_cleaned)
            
            # Update info_issue with parsed values
            for key in self.info_issue.keys():
                if key in details_dict:
                    self.info_issue[key] = details_dict[key]
                    
        except (SyntaxError, ValueError) as e:
            print(f"Error parsing prompt response for issue {self.id}: {e}")


class IfcInfoProvider:
    """
    Provides IFC model information and GUID matching capabilities.
    Uses lazy loading for efficient memory management.
    """
    
    def __init__(self, ifc_file_path: str):
        self.ifc_file_path = ifc_file_path
        self.ifc_model = None  # Lazy loading
    
    def _load_ifc_model(self):
        """Load IFC model only when needed."""
        if self.ifc_model is None:
            self.ifc_model = ifcopenshell.open(self.ifc_file_path)
    
    def match_objects(self, ifc_guids: List[str], attribute_target: str) -> str:
        """
        Match IFC elements by GUID and find the one matching the target attribute.
        
        Args:
            ifc_guids: List of IFC GUIDs to search
            attribute_target: Target element name or long name to match
        
        Returns:
            GUID of matched element, or empty string if no match
        """
        self._load_ifc_model()
        
        collection_elements = {}
        for guid in ifc_guids:
            try:
                element = self.ifc_model.by_guid(guid) # type: ignore
                if element:
                    collection_elements[guid] = element
            except Exception as e:
                print(f"Warning: Could not find element with GUID {guid}: {e}")
        
        # Match by name or long name
        matched_guid = ''
        if collection_elements:
            target_lower = str(attribute_target).lower()
            for guid, element in collection_elements.items():
                element_name = getattr(element, "Name", "").lower()
                element_name_long = getattr(element, "LongName", "").lower()
                
                if target_lower == element_name or target_lower == element_name_long:
                    matched_guid = guid
                    break
        
        return matched_guid


class BcfExtractor:
    """
    Extracts and manages BCF topics from a BCF ZIP file.
    """
    
    def __init__(self, zip_file_path: str):
        self.path = zip_file_path
        if not self.path:
            raise ValueError("BCF zip file path cannot be None")
        
        # Setup extraction
        self.extract_path = self._create_extraction_path()
        self._extract_bcfzip()
        
        # Extract topics
        self.topics: List[Topic] = []
        self._create_topics()
        self._sort_topics_alphabetically()
    
    @staticmethod
    def to_model_name(filename: str) -> str:
        """Normalize a file/model identifier to its base name without extension."""
        return os.path.splitext(os.path.basename(str(filename)))[0]

    @staticmethod
    def is_already_extracted(project_name: str) -> bool:
        """
        Check if BCF content has been extracted for a given project.
        Considered extracted if data/processed/acc_result/<project>/temp exists
        and contains any topic-like folders (excluding 'bcf.version').
        """
        acc_res_root = str(get_path('data', 'processed', 'acc_result'))
        temp_dir = os.path.join(acc_res_root, project_name, 'temp')
        if not os.path.isdir(temp_dir):
            return False
        try:
            entries = [
                e for e in os.listdir(temp_dir)
                if os.path.isdir(os.path.join(temp_dir, e)) and e != 'bcf.version'
            ]
            return len(entries) > 0
        except Exception:
            return False
    
    def _create_extraction_path(self) -> Path:
        """Create temporary extraction directory, removing old contents if exists."""
        extraction_path = Path(self.path).parent.parent / "temp"
        
        if extraction_path.exists():
            shutil.rmtree(extraction_path)
        
        extraction_path.mkdir(parents=True, exist_ok=True)
        return extraction_path
    
    def _extract_bcfzip(self):
        """Extract BCF ZIP contents to extraction path."""
        with zipfile.ZipFile(self.path, 'r') as zip_file:
            zip_file.extractall(self.extract_path)
    
    def _create_topics(self):
        """Create Topic objects for each extracted directory."""
        for topic_id in os.listdir(self.extract_path):
            if topic_id == 'bcf.version':
                continue
            self.topics.append(Topic(topic_id, self.extract_path))
    
    def _sort_topics_alphabetically(self):
        """Sort topics by title alphabetically."""
        self.topics.sort(key=lambda x: x.title) # type: ignore
    
    def drop_topics_by_description_key(self, keyword: str):
        """Remove topics whose description contains the specified keyword."""
        self.topics = [topic for topic in self.topics if keyword not in topic.description] # type: ignore
    
    def copy_snapshots(self, output_dir: Optional[Path] = None):
        """
        Copy all topic snapshots to a collection directory.
        
        Args:
            output_dir: Optional output directory. Defaults to temp-snapshots.
        """
        if output_dir is None:
            output_dir = Path(self.path).parent.parent / "temp-snapshots"
        
        if output_dir.exists():
            shutil.rmtree(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for topic in self.topics:
            if topic.snapshot and topic.snapshot.exists():
                shutil.copy(topic.snapshot, output_dir / f"{topic.id}.png")


class BcfAnalyzer:
    """
    Analyzes BCF topics and provides prioritization and classification.
    Supports log file integration for additional compliance checks.
    """
    
    def __init__(self, bcf_extractor: BcfExtractor):
        self.path = bcf_extractor.path
        self.topics = bcf_extractor.topics
        self.ifcguid_mapping = defaultdict(list)
        self.description_mapping = defaultdict(list)
        self.prioritized_topics = []
        self.log_dir = None  # Can be set externally for log processing
        
        self._classify_topics()
        self._summarize_topics()
    
    def _extract_description_identifier(self, description: str) -> str:
        """Extract identifier from description (text before first period)."""
        return description.split(".")[0].strip() if description else "Unknown"
    
    def _classify_topics(self):
        """Classify topics by IFC GUID and description identifier."""
        for topic in self.topics:
            # Map by IFC GUID
            for guid in topic.ifc_guids:
                self.ifcguid_mapping[guid].append(topic)
            
            # Map by description identifier
            desc_id = self._extract_description_identifier(topic.description) # type: ignore
            if desc_id:
                self.description_mapping[desc_id].append(topic)
    
    def _summarize_topics(self):
        """Create summary DataFrames for topics by GUID and description."""
        self.topic_summary = {
            "ifcguid": pd.DataFrame([
                {
                    "ifc guid": guid,
                    "number of issues": len(topics),
                    "related topics": ", ".join(t.title for t in topics)
                }
                for guid, topics in self.ifcguid_mapping.items()
            ]),
            "description": pd.DataFrame([
                {
                    "description identifier": desc,
                    "number of issues": len(topics),
                    "related topics": ", ".join(t.title for t in topics)
                }
                for desc, topics in self.description_mapping.items()
            ])
        }
    
    def get_topics_by_ifcguid(self, guid: str) -> List[Topic]:
        """Retrieve topics associated with a specific IFC GUID."""
        return self.ifcguid_mapping.get(guid, [])
    
    def get_topics_by_description(self, description: str) -> List[Topic]:
        """Retrieve topics associated with a specific description identifier."""
        return self.description_mapping.get(
            self._extract_description_identifier(description), []
        )

# -----------------------------
# Internal helper functions
# -----------------------------
def _to_model_name(filename: str) -> str:
    return os.path.splitext(os.path.basename(filename))[0]

def _determine_target_names(acc_res_root: str, model_names: Optional[List[str]]) -> List[str]:
    if model_names:
        return [_to_model_name(fn) for fn in model_names]
    if not os.path.isdir(acc_res_root):
        print("No acc_result folder found.")
        return []
    return [
        d for d in os.listdir(acc_res_root)
        if os.path.isdir(os.path.join(acc_res_root, d))
    ]

def _find_bcfzip_for_project(acc_res_root: str, name: str) -> str:
    bcf_folder = os.path.join(acc_res_root, name, 'bcfzip')
    if not os.path.isdir(bcf_folder):
        print(f"- Skipping '{name}': no .bcfzip found under {bcf_folder}")
        return ""
    for f in os.listdir(bcf_folder):
        if f.lower().endswith('.bcfzip'):
            return os.path.join(bcf_folder, f)
    print(f"- Skipping '{name}': no .bcfzip found under {bcf_folder}")
    return ""

def _resolve_ifc_path(ifc_root: str, name: str) -> str:
    ifc_path = os.path.join(ifc_root, f"{name}.ifc")
    if os.path.isfile(ifc_path):
        return ifc_path
    alt = os.path.join(ifc_root, name, f"{name}.ifc")
    if os.path.isfile(alt):
        return alt
    print(f"  Warning: IFC not found for '{name}' at {ifc_path}")
    return ""

def _print_bcf_summary(name: str, bcfzip_path: str, acc_res_root: str, bcf_analyzer: BcfAnalyzer):
    num_topics = len(getattr(bcf_analyzer, 'prioritized_topics', []) or bcf_analyzer.topics) # type: ignore
    desc_df = bcf_analyzer.topic_summary.get('description') if hasattr(bcf_analyzer, 'topic_summary') else None # type: ignore
    num_groups = 0 if desc_df is None else getattr(desc_df, 'shape', [0, 0])[0] # type: ignore
    rel_bcf = os.path.relpath(bcfzip_path, acc_res_root)
    print(f"✓ {name}: {num_topics} topics, {num_groups} description groups | {rel_bcf}")

def _export_project_issues(acc_res_root: str, name: str, bcf_analyzer: BcfAnalyzer):
    """
    Save issues extracted from topics into data/processed/acc_result/<name>/issues/topics.json
    Each entry contains title, description, and list of IFC GUIDs.
    """
    issues_dir = os.path.join(acc_res_root, name, "issues")
    os.makedirs(issues_dir, exist_ok=True)
    topics_out = []
    for topic in bcf_analyzer.topics:
        topics_out.append({
            "topic_id": getattr(topic, "id", ""),
            "title": getattr(topic, "title", ""),
            "description": getattr(topic, "description", ""),
            "ifc_guids": list(getattr(topic, "ifc_guids", [])),
        })
    out_path = os.path.join(issues_dir, "topics.json")
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(topics_out, f, ensure_ascii=False, indent=2)
        print(f"  Issues saved to: {os.path.relpath(out_path, acc_res_root)}")
    except Exception as e:
        print(f"  Warning: Failed to save issues for '{name}': {e}")


# Utility functions for BCF processing
def extract_checking_issues(bcfzip_path: str,) -> BcfAnalyzer:
    """
    Main function to extract and analyze BCF issues.
    
    Args:
        bcfzip_path: Path to BCF ZIP file
        ibc_rule_keys_bcf: Rule keys to prioritize from BCF topics
        ibc_rule_keys_log: Rule keys to extract from log files
        log_dir: Directory containing Solibri log files
    
    Returns:
        BcfAnalyzer instance with prioritized topics
    """

    # BcfExtractor: unzips the .bcfzip, loads topic folders, parses markup/viewpoint to build Topic list
    bcf_extractor = BcfExtractor(bcfzip_path)
    # BcfAnalyzer: classifies topics, builds summary tables, and provides query/prioritization utilities
    bcf_analyzer = BcfAnalyzer(bcf_extractor)

    return bcf_analyzer

def analyze_bcf_projects(model_names: Optional[List[str]] = None) -> List[str]:
    """
    Discover and analyze BCF results across projects.

    If model_names is provided, only those names are analyzed (normalized to base names).
    Otherwise, analyzes all projects discovered under data/processed/acc_result.

    Returns:
        List of successfully analyzed project names.
    """
    acc_res_root = str(get_path('data', 'processed', 'acc_result'))
    ifc_root = str(get_path('data', 'processed', 'ifc'))

    target_names = _determine_target_names(acc_res_root, model_names)
    if not target_names:
        print("No projects to analyze.")
        return []

    successful_projects = []

    for name in target_names:
        bcfzip_path = _find_bcfzip_for_project(acc_res_root, name)
        if not bcfzip_path:
            continue

        ifc_path = _resolve_ifc_path(ifc_root, name)

        try:
            bcf_analyzer = extract_checking_issues(bcfzip_path=bcfzip_path) # type: ignore

            if ifc_path and os.path.isfile(ifc_path):
                _ifc_provider = IfcInfoProvider(ifc_file_path=ifc_path) # type: ignore

            # Export issues (title, description, ifc_guids) as JSON under acc_result/<name>/issues
            _export_project_issues(acc_res_root, name, bcf_analyzer) # type: ignore

            _print_bcf_summary(name, bcfzip_path, acc_res_root, bcf_analyzer) # type: ignore
            successful_projects.append(name)

        except Exception as e:
            print(f"× Failed to analyze '{name}': {e}")

    print(f"\n✓ Successfully analyzed {len(successful_projects)} BCF project(s)")
    return successful_projects