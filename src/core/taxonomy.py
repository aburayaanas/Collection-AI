"""
Error Taxonomy and Advisory System
Provides user-friendly, actionable hints for technical errors.
"""


class ErrorAdvisor:
    """
    Maps technical error patterns to actionable hints for operators.
    Helps reduce MTTR (Mean Time To Resolution) by providing immediate guidance.
    """
    
    # Static registry of error patterns -> actionable hints
    ERROR_REGISTRY = {
        "ORA-12170": "Check VPN connection or Firewall ports.",
        "ORA-01017": "Invalid Username/Password. Check .env file.",
        "ORA-12541": "TNS:no listener. Database service is down. Contact DBA.",
        "ORA-12514": "TNS:listener does not currently know of service. Check DB_DSN in .env.",
        "Access is denied": "File permission error. Try running as Administrator.",
        "TNS:listener": "Database service is down. Contact DBA.",
        "Connection refused": "Database is not accepting connections. Verify host and port.",
        "timeout": "Network timeout. Check network connectivity or increase timeout settings.",
        "No module named": "Missing Python dependency. Run: pip install -r requirements.txt",
        "Permission denied": "Insufficient file/directory permissions. Check ownership or run as admin.",
        "ECONNREFUSED": "Connection refused by remote server. Verify service is running.",
        "getaddrinfo failed": "DNS resolution failed. Check hostname or network connection.",
    }
    
    @classmethod
    def analyze(cls, exception: Exception) -> str:
        """
        Analyzes an exception and returns a formatted diagnostic message.
        
        Args:
            exception: The exception object to analyze
            
        Returns:
            A formatted string containing the error type, message, and actionable hint (if available)
        """
        error_type = type(exception).__name__
        error_message = str(exception)
        
        # Search for matching patterns in the registry
        hint = None
        for pattern, advisory in cls.ERROR_REGISTRY.items():
            if pattern in error_message:
                hint = advisory
                break
        
        # Build the diagnostic message
        diagnostic = f"[{error_type}] {error_message}"
        
        if hint:
            diagnostic += f"\n HINT: {hint}"
        else:
            diagnostic += "\n No specific guidance available. Check logs for details."
        
        return diagnostic
    
    @classmethod
    def register_pattern(cls, pattern: str, hint: str) -> None:
        """
        Dynamically register a new error pattern and its hint.
        Useful for extending the taxonomy at runtime.
        
        Args:
            pattern: The error substring to match
            hint: The actionable hint to display
        """
        cls.ERROR_REGISTRY[pattern] = hint
