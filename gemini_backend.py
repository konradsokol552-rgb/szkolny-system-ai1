"""
Moduł kompatybilności wstecznej dla gemini_backend.py.
Deleguje zapytania do nowego serwisu services.ai_service.
"""
from services.ai_service import zapytaj_ai

__all__ = ["zapytaj_ai"]
