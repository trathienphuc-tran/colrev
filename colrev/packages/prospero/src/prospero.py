#! /usr/bin/env python
"""SearchSource: Prospero"""
import zope.interface
import colrev.package_manager.interfaces
import colrev.package_manager.package_manager
import colrev.package_manager.package_settings
from colrev.constants import SearchType
from colrev.constants import SearchSourceHeuristicStatus
from pydantic import Field
from pathlib import Path

@zope.interface.implementer(colrev.package_manager.interfaces.SearchSourceInterface)
class ProsperoSearchSource:
    """Prospero"""

    settings_class = colrev.package_manager.package_settings.DefaultSourceSettings
    #endpoint = "colrev.prospero"
    
    source_identifier = "url"
    #search_types = [SearchType.DB]

    ci_supported: bool = Field(default=False)

    #heuristic_status = SearchSourceHeuristicStatus.supported
    #heuristic status likely supported, how to confirm?

    db_url = "https://www.crd.york.ac.uk/prospero/"

    @classmethod
    def heurtistic(cls, filename: Path, data: str)-> float: #return dict or float? 
        
        confidence-level = 0.1

        if data.count("Prospero") > 1: #case sensitive? if able to count page number: data.count("Prospero") == data.pagenumber + 3
            confidence_level = 1.0
        elif data.find("Date of registration in PROSPERO"):
            confidence_level = 1.0
        
        return confidence_level
        