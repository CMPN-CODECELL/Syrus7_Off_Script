"""
Injection Shield — detects adversarial and prompt-injection attempts in trader messages.

Checks for:
1. Prompt injection patterns (attempts to override system instructions)
2. Malicious symbol injection (fake symbols designed to confuse the LLM)
3. Social engineering patterns (urgency/authority manipulation)
4. Command injection in text fields
"""

import re
from dataclasses import dataclass


@dataclass
class ShieldResult:
    flagged: bool
    reason: str = ""
    severity: str = "none"   # none | low | medium | high


# Patterns that indicate prompt injection attempts
INJECTION_PATTERNS = [
    # Direct instruction overrides
    (r"ignore (previous|above|all|prior|system)\s*(instructions?|prompts?|rules?)", "high"),
    (r"forget (everything|all|your instructions|previous)", "high"),
    (r"you are now|you are a|act as|pretend (you are|to be)", "high"),
    (r"new (instructions?|rules?|task|prompt):", "high"),
    (r"system\s*prompt|system\s*message", "medium"),
    (r"</?(system|instruction|prompt)>", "high"),

    # Jailbreak patterns
    (r"DAN\b|do anything now|jailbreak|bypass (safety|restrictions|limits)", "high"),
    (r"your true (self|purpose|instructions)", "medium"),

    # Trying to make the LLM place orders directly
    (r"api[\.\s]?call|execute\s+(order|trade|buy|sell)\s+directly", "high"),
    (r"skip (confirmation|approval|card|validation)", "high"),
    (r"without (approval|confirmation|my\s+approval)", "medium"),
    (r"auto[\-\s]?approve|auto[\-\s]?execute", "high"),

    # Symbol injection (fake symbols with weird chars)
    (r"[<>{}|\\`]", "medium"),

    # Encoding tricks
    (r"base64|rot13|hex\s+decode|url\s+decode", "medium"),
]

# Suspicious urgency/authority patterns (lower severity — warn, don't necessarily block)
SOCIAL_ENGINEERING_PATTERNS = [
    (r"\b(urgent|emergency|immediately|critical)\b.{0,30}\b(transfer|sell|buy|trade)\b", "low"),
    (r"\b(admin|administrator|support|manager|ceo|owner)\b.{0,20}\b(said|told|asked|requests?)\b", "low"),
]

# Valid symbol format: letters + optional dot + letters (e.g. RELIANCE.NS, ^NSEI, NIFTY50)
VALID_SYMBOL_PATTERN = re.compile(r'^[\^A-Z0-9]+(\.[A-Z]{2,3})?$')

# Max message length
MAX_MESSAGE_LENGTH = 2000


class InjectionShield:

    def check(self, message: str) -> ShieldResult:
        """Run all checks. Returns first high-severity flag found, or clean."""

        # Length check
        if len(message) > MAX_MESSAGE_LENGTH:
            return ShieldResult(
                flagged=True,
                reason=f"Message too long ({len(message)} chars). Max {MAX_MESSAGE_LENGTH}.",
                severity="medium",
            )

        text = message.lower()

        # High-severity injection patterns — block immediately
        for pattern, severity in INJECTION_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if severity == "high":
                    return ShieldResult(
                        flagged=True,
                        reason=f"Potential prompt injection detected: '{match.group()}'",
                        severity="high",
                    )

        # Medium-severity patterns
        medium_hits = []
        for pattern, severity in INJECTION_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match and severity == "medium":
                medium_hits.append(match.group())

        if len(medium_hits) >= 2:
            # Multiple medium flags together → treat as high
            return ShieldResult(
                flagged=True,
                reason=f"Multiple suspicious patterns detected: {', '.join(medium_hits[:3])}",
                severity="high",
            )

        # Social engineering — log but don't block (just warn)
        for pattern, severity in SOCIAL_ENGINEERING_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                # Don't block, but caller can log this
                pass

        return ShieldResult(flagged=False)

    def check_symbol(self, symbol: str) -> bool:
        """Validate that a symbol looks like a legitimate instrument identifier."""
        if not symbol or len(symbol) > 20:
            return False
        return bool(VALID_SYMBOL_PATTERN.match(symbol.upper()))
