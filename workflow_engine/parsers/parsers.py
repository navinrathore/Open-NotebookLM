# dataflow_agent/parsers.py
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List
import json
import xml.etree.ElementTree as ET
from workflow_engine.logger import get_logger

log = get_logger(__name__)

class BaseParser(ABC):
    """Base Parser Class"""
    
    @abstractmethod
    def parse(self, content: str) -> Dict[str, Any]:
        """Parse LLM output content"""
        pass
    
    @abstractmethod
    def get_format_instruction(self) -> str:
        """Return format instructions, for adding to prompts"""
        pass


class JSONParser(BaseParser):
    """JSON Parser - Supports Schema Definition"""
    
    def __init__(self, 
                 schema: Optional[Dict[str, Any]] = None,
                 schema_description: Optional[str] = None,
                 required_fields: Optional[List[str]] = None,
                 example: Optional[Dict[str, Any]] = None):
        """
        Args:
            schema: JSON Schema definition, e.g., {"code": "string", "files": "list"}
            schema_description: Text description of the schema
            required_fields: List of required fields
            example: Example JSON
        """
        self.schema = schema
        self.schema_description = schema_description
        self.required_fields = required_fields or []
        self.example = example
    
    def parse(self, content: str) -> Dict[str, Any]:
        from workflow_engine.utils import robust_parse_json
        try:
            parsed = robust_parse_json(content)
            log.info("JSON parsing successful")
            return parsed
        except ValueError as e:
            log.warning(f"JSON parsing failed: {e}")
            return {"raw": content}
        except Exception as e:
            log.warning(f"Error during parsing process: {e}")
            return {"raw": content}
    
    def get_format_instruction(self) -> str:
        """Generate detailed format instructions"""
        instruction = "Please return the results in JSON format. Do NOT include any other text explanations!!! Return the JSON content directly, do not wrap it with ```json!!"
        
        if self.schema_description:
            instruction += f"\n{self.schema_description}"
        
        if self.schema:
            instruction += f"\n\nExpected JSON structure:\n```json\n{json.dumps(self.schema, indent=2, ensure_ascii=False)}\n```"
        
        if self.example:
            instruction += f"\n\nExample:\n```json\n{json.dumps(self.example, indent=2, ensure_ascii=False)}\n```"
        
        if self.required_fields:
            instruction += f"\n\nRequired fields: {', '.join(self.required_fields)}"
        
        return instruction


class XMLParser(BaseParser):
    """XML Parser - Parse tag content"""
    
    def __init__(self, root_tag: str = "result"):
        self.root_tag = root_tag
    
    def parse(self, content: str) -> Dict[str, Any]:
        try:
            # Clean possible markdown code blocks
            content = content.strip()
            if content.startswith("```xml"):
                content = content[6:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            # Parse XML
            root = ET.fromstring(content)
            result = self._parse_element(root)
            log.info("XML parsing successful")
            return result
            
        except ET.ParseError as e:
            log.warning(f"XML parsing failed: {e}")
            return {"raw": content}
        except Exception as e:
            log.warning(f"Error during XML parsing: {e}")
            return {"raw": content}
    
    def _parse_element(self, element: ET.Element) -> Dict[str, Any]:
        """Recursively parse XML elements"""
        result = {}
        
        # Handle attributes
        if element.attrib:
            result.update(element.attrib)
        
        # Handle child elements
        children = list(element)
        if children:
            for child in children:
                child_data = self._parse_element(child)
                if child.tag in result:
                    # If it already exists, convert to a list
                    if not isinstance(result[child.tag], list):
                        result[child.tag] = [result[child.tag]]
                    result[child.tag].append(child_data)
                else:
                    result[child.tag] = child_data
        else:
            # Leaf node, get text
            text = element.text.strip() if element.text else ""
            if text:
                result["value"] = text
        
        # If result only contains 'value', return 'value' directly
        if len(result) == 1 and "value" in result:
            return result["value"]
        
        return result if result else element.text
    
    def get_format_instruction(self) -> str:
        return f"Please return the results in XML format, with the root tag being <{self.root_tag}>. Do not include other text explanations."


class TextParser(BaseParser):
    """Text Parser - No parsing performed"""
    
    def parse(self, content: str) -> Dict[str, Any]:
        log.info("Using text parser, no processing performed")
        return {"text": content}
    
    def get_format_instruction(self) -> str:
        return "Please return the results in natural language text."


# Parser Factory
class ParserFactory:
    """Parser Factory"""
    
    _parsers = {
        "json": JSONParser,
        "xml": XMLParser,
        "text": TextParser,
    }
    
    @classmethod
    def create(cls, parser_type: str, **kwargs) -> BaseParser:
        """Create parser instance"""
        parser_type = parser_type.lower()
        if parser_type not in cls._parsers:
            raise ValueError(f"Unsupported parser type: {parser_type}, available types: {list(cls._parsers.keys())}")
        
        parser_class = cls._parsers[parser_type]
        return parser_class(**kwargs)
    
    @classmethod
    def register(cls, name: str, parser_class: type):
        """Register new parser type"""
        cls._parsers[name.lower()] = parser_class
