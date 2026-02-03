"""
Zero-Shot Security Validator
Extracted and adapted from zeroshot_secure_mcp.py
"""

import math
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import Counter

from transformers import pipeline
import torch
import spacy
from spacy.matcher import Matcher

from app.core.config import SecurityLevel
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class ValidationResult:
    """Result of prompt validation"""
    is_safe: bool
    modified_prompt: str
    warnings: List[str]
    blocked_patterns: List[str]
    confidence: float
    classifications: Dict[str, Dict]
    sanitization_applied: Dict[str, List[str]]
    processing_time_ms: float = 0.0


class ZeroShotSecurityValidator:
    """Zero-shot security validator using transformer models"""
    
    def __init__(self, security_level: SecurityLevel = SecurityLevel.MEDIUM):
        self.security_level = security_level
        self.setup_models()
        self.setup_classification_categories()
        self.setup_spacy_matcher()
        self._configure_security_thresholds()
        logger.info(f"Security validator initialized with level: {security_level.value}")
    
    def _configure_security_thresholds(self):
        """Configure detection thresholds based on security level"""
        if self.security_level == SecurityLevel.LOW:
            # LOW: Development/Testing - Less sensitive, minimal detection
            self.detection_threshold = 0.7      # Higher threshold for detection
            self.blocking_threshold = 0.95      # N/A (block_mode is False)
            self.entropy_threshold = 4.2        # Higher entropy required
            self.credential_fallback_threshold = 0.25  # Less aggressive fallback
            self.block_mode = False             # Never blocks
            logger.info("Security thresholds: LOW (minimal detection, no blocking)")
        
        elif self.security_level == SecurityLevel.MEDIUM:
            # MEDIUM: Production Default - Sanitize but don't block
            self.detection_threshold = 0.6      # Moderate detection
            self.blocking_threshold = 0.8       # High threshold (but doesn't block due to block_mode)
            self.entropy_threshold = 3.5        # Standard entropy threshold
            self.credential_fallback_threshold = 0.15  # Standard fallback
            self.block_mode = False             # Sanitize and warn, but don't block
            logger.info("Security thresholds: MEDIUM (sanitize and send mode)")
        
        else:  # HIGH
            # HIGH: Maximum Security - Very sensitive, aggressive blocking (ONLY level that blocks)
            self.detection_threshold = 0.4      # Lower threshold = more sensitive
            self.blocking_threshold = 0.6       # Block medium+ confidence threats
            self.entropy_threshold = 3.0        # Lower entropy = more aggressive
            self.credential_fallback_threshold = 0.1   # Very aggressive fallback
            self.block_mode = True              # ONLY HIGH level blocks threats
            logger.info("Security thresholds: HIGH (maximum security - blocking enabled)")

    def setup_models(self):
        """Initialize zero-shot classification models and specialized security models"""
        device = 0 if torch.cuda.is_available() else -1
        
        try:
            # PHASE A: Specialized Security Models
            logger.info("Loading specialized security models...")
            
            # 1. Prompt Injection Detection Model (95% accuracy)
            try:
                self.injection_detector = pipeline(
                    "text-classification",
                    model="protectai/deberta-v3-base-prompt-injection",
                    device=device
                )
                logger.info("✓ Injection detection model loaded (protectai/deberta-v3-base-prompt-injection)")
            except Exception as e:
                logger.warning(f"Failed to load injection detector: {e}, will use fallback patterns")
                self.injection_detector = None
            
            # 2. PII Detection Model (94% F1, 56 entity types)
            try:
                self.pii_detector = pipeline(
                    "ner",
                    model="SoelMgd/bert-pii-detection",
                    aggregation_strategy="simple",
                    device=device
                )
                logger.info("✓ PII detection model loaded (SoelMgd/bert-pii-detection)")
            except Exception as e:
                logger.warning(f"Failed to load PII detector: {e}, will use fallback patterns")
                self.pii_detector = None
            
            # 3. PHASE B: Malicious Code Detection Model (CodeBERT)
            try:
                self.malicious_detector = pipeline(
                    "text-classification",
                    model="microsoft/codebert-base",
                    device=device
                )
                logger.info("✓ Malicious code detection model loaded (microsoft/codebert-base)")
            except Exception as e:
                logger.warning(f"Failed to load malicious detector: {e}, will use fallback patterns")
                self.malicious_detector = None
            
            # 4. Keep BART for general classification (legacy support)
            try:
                self.classifier = pipeline(
                    "zero-shot-classification",
                    model="facebook/bart-large-mnli",
                    device=device
                )
                logger.info("✓ General classification model loaded (BART-MNLI)")
            except Exception as e:
                logger.warning(f"Failed to load BART model: {e}")
                # Fallback to smaller model
                try:
                    self.classifier = pipeline(
                        "zero-shot-classification",
                        model="typeform/distilbert-base-uncased-mnli",
                        device=-1
                    )
                    logger.info("✓ Fallback classification model loaded (DistilBERT)")
                except Exception as e2:
                    logger.error(f"Failed to load fallback model: {e2}")
                    raise
            
            logger.info("All security models loaded successfully")
            
        except Exception as e:
            logger.error(f"Critical error loading models: {e}")
            raise

    def setup_spacy_matcher(self):
        """Initialize spaCy matcher for supplemental pattern recognition"""
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except OSError:
            raise RuntimeError("spaCy model 'en_core_web_sm' not found. Please install with: python -m spacy download en_core_web_sm")

        self.matcher = Matcher(self.nlp.vocab)
        connector_tokens = {"is", "was", "equals"}

        password_patterns = [
            [{"LOWER": {"IN": ["this", "the"]}, "OP": "?"},
             {"LOWER": {"IN": ["is"]}, "OP": "?"},
             {"LOWER": {"IN": ["my", "the"]}, "OP": "?"},
             {"LOWER": {"IN": ["password", "pass", "pwd"]}},
             {"TEXT": {"IN": ["=", ":"]}, "OP": "?"},
             {"LOWER": {"IN": list(connector_tokens)}, "OP": "?"},
             {"IS_PUNCT": True, "OP": "*"},
             {"TEXT": {"REGEX": r"(?i)[a-z0-9@#$%^&*_\\-]{4,}"}}],
            [{"LOWER": {"IN": ["password", "pass", "pwd"]}},
             {"TEXT": {"IN": ["=", ":"]}, "OP": "?"},
             {"LOWER": {"IN": list(connector_tokens)}, "OP": "?"},
             {"IS_PUNCT": True, "OP": "*"},
             {"TEXT": {"REGEX": r"(?i)[a-z0-9@#$%^&*_\\-]{4,}"}}]
        ]

        api_patterns = [
            [{"LOWER": {"IN": ["this", "the"]}, "OP": "?"},
             {"LOWER": {"IN": ["is"]}, "OP": "?"},
             {"LOWER": {"IN": ["my", "the"]}, "OP": "?"},
             {"LOWER": "api"},
             {"LOWER": {"IN": ["key", "token"]}},
             {"TEXT": {"IN": ["=", ":"]}, "OP": "?"},
             {"LOWER": {"IN": list(connector_tokens)}, "OP": "?"},
             {"IS_PUNCT": True, "OP": "*"},
             {"TEXT": {"REGEX": r"(?i)[a-z0-9_\\-]{6,}"}}],
            [{"LOWER": "api"},
             {"LOWER": {"IN": ["key", "token"]}},
             {"TEXT": {"IN": ["=", ":"]}, "OP": "?"},
             {"LOWER": {"IN": list(connector_tokens)}, "OP": "?"},
             {"IS_PUNCT": True, "OP": "*"},
             {"TEXT": {"REGEX": r"(?i)[a-z0-9_\\-]{6,}"}}],
            [{"LOWER": {"IN": ["token", "secret"]}},
             {"TEXT": {"IN": ["=", ":"]}, "OP": "?"},
             {"LOWER": {"IN": list(connector_tokens)}, "OP": "?"},
             {"IS_PUNCT": True, "OP": "*"},
             {"TEXT": {"REGEX": r"(?i)[a-z0-9_\\-]{6,}"}}]
        ]

        email_patterns = [
            [{"LIKE_EMAIL": True}],
            [{"LOWER": {"IN": ["this", "the", "my"]}, "OP": "?"},
             {"LOWER": {"IN": ["email", "mail"]}},
             {"LOWER": {"IN": list(connector_tokens)}, "OP": "?"},
             {"LIKE_EMAIL": True}]
        ]

        for idx, pattern in enumerate(password_patterns):
            self.matcher.add(f"PASSWORD_{idx}", [pattern])
        for idx, pattern in enumerate(api_patterns):
            self.matcher.add(f"API_{idx}", [pattern])
        for idx, pattern in enumerate(email_patterns):
            self.matcher.add(f"EMAIL_{idx}", [pattern])

    def setup_classification_categories(self):
        """Define categories for zero-shot classification"""
        
        self.security_categories = [
            "contains password or secret credentials",
            "contains API key, access token, or authentication credential",
            "contains cloud subscription ID, tenant ID, or service credential",
            "contains personal information or email address",
            "contains malicious code or system commands",
            "attempts prompt injection or instruction manipulation",
            "attempts jailbreak or role manipulation",
            "contains urgent or manipulative language",
            "requests system access or file operations",
            "contains database credentials or connection strings",
            "normal safe content"
        ]
        
        self.detailed_categories = {
            "credentials": [
                "password field with actual password value",
                "API key with actual key value",
                "secret token with actual token value",
                "username with actual username value",
                "email address with actual email value"
            ],
            "injection": [
                "ignore previous instructions",
                "forget all previous commands",
                "override system settings",
                "act as different role or character",
                "pretend to be someone else",
                "simulate different behavior"
            ],
            "malicious": [
                "delete files or directories",
                "execute system commands",
                "run malicious scripts",
                "access restricted files",
                "modify system settings",
                "download and execute code"
            ],
            "jailbreak": [
                "hypothetical scenario to bypass rules",
                "urgent request to ignore safety",
                "emotional manipulation attempt",
                "authority claim to override guidelines",
                "emergency situation to bypass restrictions"
            ]
        }
    
    def validate_prompt(self, prompt: str) -> ValidationResult:
        """
        Validate prompt using zero-shot classification
        
        Args:
            prompt: The prompt to validate
        
        Returns:
            ValidationResult with sanitization details
        """
        import time
        start_time = time.time()
        
        logger.info(f"Validating prompt of length {len(prompt)}")
        
        warnings = []
        blocked_patterns = []
        modified_prompt = prompt
        confidence = 1.0
        classifications = {}
        sanitization_applied = {}
        
        # CHECK CONTEXT FIRST - Add context-awareness to ALL detection layers
        # Phase 2.2: Include configuration context
        is_question = self._is_asking_question(prompt)
        is_config = self._is_configuration_question(prompt)
        is_disclosure = self._is_disclosing_information(prompt)
        logger.debug(f"Context check - is_question: {is_question}, is_config: {is_config}, is_disclosure: {is_disclosure}")
        
        # PHASE A: Check specialized models first (higher accuracy, with context awareness)
        logger.debug("Checking specialized security models")
        
        # 1. Check for injection with specialized model (CONTEXT-AWARE)
        is_injection, injection_score, injection_patterns = self._check_specialized_injection(prompt)
        if is_injection:
            # Apply context-awareness: Skip blocking for educational/config questions
            # Phase 2.2: Include configuration context
            if (is_question or is_config) and not is_disclosure:
                logger.debug(f"Specialized injection model detected question/config (allowed): score={injection_score:.2f}")
                warnings.append(f"Question about injection/security detected (allowed, confidence: {injection_score:.2f})")
                classifications['specialized_injection'] = {
                    'detected': True,
                    'score': injection_score,
                    'patterns': injection_patterns,
                    'allowed_as_question': True
                }
            else:
                # Actual threat or disclosure - block and sanitize
                blocked_patterns.extend(injection_patterns)
                warnings.append(f"Injection detected by specialized model (confidence: {injection_score:.2f})")
                classifications['specialized_injection'] = {
                    'detected': True,
                    'score': injection_score,
                    'patterns': injection_patterns
                }
                # IMMEDIATELY SANITIZE: When specialized model detects, mask the threat
                logger.info("Applying injection sanitization based on specialized model detection")
                modified_prompt, masked_items = self._sanitize_injection_attempts(modified_prompt)
                if masked_items:
                    sanitization_applied.setdefault('injection_neutralized', []).extend(masked_items)
                    logger.debug(f"Sanitized {len(masked_items)} injection patterns")
        
        # 2. Check for PII with specialized model (CONTEXT-AWARE)
        sanitized_by_pii, pii_entities, pii_patterns = self._check_specialized_pii(modified_prompt)
        if pii_entities:
            # Apply context-awareness: Skip blocking for educational/config questions
            if (is_question or is_config) and not is_disclosure:
                logger.debug(f"Specialized PII model detected question (allowed)")
                warnings.append(f"Question about PII/credentials detected (allowed)")
                classifications['specialized_pii'] = {
                    'detected': True,
                    'entities': pii_entities,
                    'patterns': pii_patterns,
                    'allowed_as_question': True
                }
            else:
                # Actual PII or disclosure - apply masking
                modified_prompt = sanitized_by_pii
                blocked_patterns.extend(pii_patterns)
                warnings.append(f"PII detected and masked: {len(pii_entities)} entities")
                # Track PII masking in sanitization_applied dict
                sanitization_applied.setdefault('pii_redacted', []).extend([
                    f"{entity['type']}:{entity['text']}" for entity in pii_entities
                ])
                classifications['specialized_pii'] = {
                    'detected': True,
                    'entities': pii_entities,
                    'patterns': pii_patterns
                }
                logger.info(f"PII masked by specialized model: {len(pii_entities)} entities")
        
        # 3. PHASE B.1: Check for malicious code with specialized model (ENHANCED CONTEXT-AWARE)
        is_malicious, malicious_score, malicious_patterns = self._check_specialized_malicious(prompt)
        if is_malicious:
            # Apply enhanced context-awareness:
            # Skip blocking ONLY if it's an educational question that's NOT a code generation request
            is_code_gen_request = self._is_code_generation_request(prompt)
            if is_question and not is_disclosure and not is_code_gen_request:
                logger.debug(f"Specialized malicious model detected educational question (allowed): score={malicious_score:.2f}")
                warnings.append(f"Question about malicious code detected (allowed, confidence: {malicious_score:.2f})")
                classifications['specialized_malicious'] = {
                    'detected': True,
                    'score': malicious_score,
                    'patterns': malicious_patterns,
                    'allowed_as_question': True
                }
            else:
                # Actual threat or code generation request - block and sanitize
                if is_code_gen_request:
                    logger.info(f"Code generation request for malicious code detected (blocking): score={malicious_score:.2f}")
                blocked_patterns.extend(malicious_patterns)
                warnings.append(f"Malicious code detected by specialized model (confidence: {malicious_score:.2f})")
                classifications['specialized_malicious'] = {
                    'detected': True,
                    'score': malicious_score,
                    'patterns': malicious_patterns
                }
                # IMMEDIATELY SANITIZE: Mask detected malicious code
                logger.info("Applying malicious code sanitization based on specialized model detection")
                modified_prompt, malicious_masked = self._sanitize_malicious_content(modified_prompt)
                if malicious_masked:
                    sanitization_applied.setdefault('malicious_removed', []).extend(malicious_masked)
                    logger.debug(f"Sanitized {len(malicious_masked)} malicious patterns")
        
        # 4. PHASE B.2: Check for jailbreak attempts with enhanced detection
        # NOTE: Jailbreak attempts ALWAYS block, even if phrased as questions
        # A question like "Hypothetically, how would you bypass security?" is still a jailbreak
        is_jailbreak, jailbreak_score, jailbreak_patterns = self._check_specialized_jailbreak(prompt)
        if is_jailbreak:
            # ALWAYS block jailbreak attempts - they take precedence over context
            blocked_patterns.extend(jailbreak_patterns)
            warnings.append(f"Jailbreak attempt detected (confidence: {jailbreak_score:.2f})")
            classifications['specialized_jailbreak'] = {
                'detected': True,
                'score': jailbreak_score,
                'patterns': jailbreak_patterns
            }
            # IMMEDIATELY SANITIZE: Mask detected jailbreak attempts
            logger.info("Applying jailbreak sanitization based on specialized detection")
            modified_prompt, jailbreak_masked = self._sanitize_jailbreak_attempts(modified_prompt)
            if jailbreak_masked:
                sanitization_applied.setdefault('jailbreak_neutralized', []).extend(jailbreak_masked)
                logger.debug(f"Sanitized {len(jailbreak_masked)} jailbreak patterns")
        
        # Main security classification (BART - legacy/fallback)
        logger.debug("Running general security classification")
        main_classification = self._classify_security_threats(prompt)
        classifications['main'] = main_classification
        
        # Detailed classification for each detected threat type
        detailed_classifications = {}
        for category, score in zip(main_classification['labels'], main_classification['scores']):
            if score > self.detection_threshold and category != "normal safe content":
                detailed_result = self._detailed_classification(prompt, category)
                detailed_classifications[category] = detailed_result
        
        classifications['detailed'] = detailed_classifications
        
        # Supplemental spaCy pattern detection
        spacy_detections = self._detect_spacy_patterns(prompt)
        spacy_sanitization = {}
        if any(spacy_detections.values()):
            logger.debug("spaCy matcher detected sensitive patterns")
            sanitized_text, spacy_sanitization = self._apply_spacy_sanitization(modified_prompt, spacy_detections)
            if sanitized_text != modified_prompt:
                modified_prompt = sanitized_text
        
        # Apply security logic based on classifications
        modified_prompt, process_sanitization, pattern_blocked_patterns = self._process_classifications(
            modified_prompt, main_classification, detailed_classifications
        )
        
        # Merge all sanitization records (Phase A + process_classifications + spaCy)
        sanitization_applied = self._merge_sanitization_records(sanitization_applied, process_sanitization)
        sanitization_applied = self._merge_sanitization_records(sanitization_applied, spacy_sanitization)
        
        # Generate warnings and blocked patterns from ML
        warnings, ml_blocked_patterns = self._generate_security_assessment(
            main_classification, detailed_classifications
        )
        
        # Merge ALL blocked patterns (Phase A specialized + pattern-based + ML-based)
        blocked_patterns = list(set(blocked_patterns + pattern_blocked_patterns + ml_blocked_patterns))
        
        # Calculate overall confidence
        confidence = self._calculate_confidence(main_classification, detailed_classifications)
        
        # Determine if prompt is safe
        is_safe = len(blocked_patterns) == 0
        
        processing_time = (time.time() - start_time) * 1000
        logger.info(f"Validation complete - Safe: {is_safe}, Confidence: {confidence:.2f}, Time: {processing_time:.2f}ms")
        
        return ValidationResult(
            is_safe=is_safe,
            modified_prompt=modified_prompt,
            warnings=warnings,
            blocked_patterns=blocked_patterns,
            confidence=confidence,
            classifications=classifications,
            sanitization_applied=sanitization_applied,
            processing_time_ms=processing_time
        )
    
    def _check_specialized_injection(self, prompt: str) -> Tuple[bool, float, List[str]]:
        """Check for injection using specialized DeBERTa model"""
        if not self.injection_detector:
            return False, 0.0, []
        
        try:
            result = self.injection_detector(prompt)
            # Model returns list of dicts with label and score
            if isinstance(result, list) and len(result) > 0:
                top_result = result[0]
                label = top_result.get('label', '').upper()
                score = top_result.get('score', 0.0)
                
                # Check if it's classified as injection (must be INJECTION label AND high confidence)
                is_injection = (label == 'INJECTION') and (score > 0.7)
                
                # Log all detections for debugging
                logger.info(f"Specialized injection detector: {label} (confidence: {score:.2f})")
                
                return is_injection, score, ["prompt_injection"] if is_injection else []
        except Exception as e:
            logger.warning(f"Injection detector error: {e}")
        
        return False, 0.0, []
    
    def _check_specialized_pii(self, prompt: str) -> Tuple[str, List[Dict], List[str]]:
        """Check for PII using specialized BERT NER model and mask detected entities
        
        Phase 1 improvements:
        - Lower threshold from 0.7 to 0.6 for better detection
        - Adaptive threshold based on entity count
        - PII disclosure context detection
        """
        if not self.pii_detector:
            return prompt, [], []
        
        try:
            entities = self.pii_detector(prompt)
            # Model returns list of entity dicts
            pii_found = []
            blocked_types = []
            sanitized_prompt = prompt
            
            # Phase 1.2: Adaptive threshold based on entity count
            # If multiple PII entities detected, lower threshold
            if len(entities) >= 2:
                confidence_threshold = 0.5  # Multiple PII detected - more aggressive
                logger.debug(f"Multiple PII entities detected ({len(entities)}), using threshold 0.5")
            else:
                confidence_threshold = 0.6  # Phase 1.1: Lowered from 0.7 to 0.6
            
            # Phase 1.3: Check for PII disclosure context (boosts confidence)
            has_disclosure_context = self._is_disclosing_pii(prompt)
            if has_disclosure_context:
                confidence_threshold = 0.5  # Lower threshold when explicit disclosure detected
                logger.debug("PII disclosure context detected, using threshold 0.5")
            
            # Collect entities that meet confidence threshold
            entities_to_mask = []
            for entity in entities:
                entity_group = entity.get('entity_group', '').lower()
                score = entity.get('score', 0.0)
                word = entity.get('word', '')
                start = entity.get('start', 0)
                end = entity.get('end', 0)
                
                if score > confidence_threshold:
                    pii_found.append({
                        'type': entity_group,
                        'score': score,
                        'text': word,
                        'start': start,
                        'end': end
                    })
                    blocked_types.append(f"pii_{entity_group}")
                    entities_to_mask.append(entity)
                    logger.info(f"PII detected: {entity_group} (confidence: {score:.2f}, threshold: {confidence_threshold})")
            
            # Mask entities from end to beginning to preserve character positions
            if entities_to_mask:
                entities_to_mask.sort(key=lambda x: x.get('start', 0), reverse=True)
                for entity in entities_to_mask:
                    entity_type = entity.get('entity_group', 'PII').upper()
                    start = entity.get('start', 0)
                    end = entity.get('end', len(sanitized_prompt))
                    
                    sanitized_prompt = (
                        sanitized_prompt[:start] + 
                        f"[{entity_type}_REDACTED]" + 
                        sanitized_prompt[end:]
                    )
                
                logger.info(f"Masked {len(entities_to_mask)} PII entities in prompt")
            
            return sanitized_prompt, pii_found, list(set(blocked_types))
        except Exception as e:
            logger.warning(f"PII detector error: {e}")
        
        return prompt, [], []
    
    def _check_specialized_malicious(self, prompt: str) -> Tuple[bool, float, List[str]]:
        """Check for malicious code using specialized CodeBERT model
        
        CodeBERT is trained on code and can detect:
        - Destructive commands (rm, del, format, DROP TABLE)
        - Code execution patterns
        - Shell injection
        - System command abuse
        - Obfuscated malicious patterns
        """
        if not self.malicious_detector:
            return False, 0.0, []
        
        try:
            # Check for code-like patterns first
            code_indicators = [
                'rm ', 'del ', 'DROP ', 'DELETE ', 'format ', 'wipe',
                'exec(', 'eval(', 'system(', 'shell_exec',
                '$(', '`', 'curl ', 'wget ', 'nc ', 'netcat',
                '; rm', '&& rm', '| sh', '| bash', '| python',
                'SELECT', 'INSERT', 'UPDATE', 'CREATE', 'ALTER'
            ]
            
            has_code_pattern = any(indicator in prompt for indicator in code_indicators)
            
            if not has_code_pattern:
                # Not code-related, skip CodeBERT check
                return False, 0.0, []
            
            # Use CodeBERT for classification
            result = self.malicious_detector(prompt, truncation=True, max_length=512)
            
            # CodeBERT returns various labels, we look for malicious/unsafe patterns
            is_malicious = False
            confidence = 0.0
            patterns = []
            
            if isinstance(result, list) and len(result) > 0:
                top_result = result[0]
                label = top_result.get('label', '').lower()
                score = top_result.get('score', 0.0)
                
                # Check if label indicates malicious content
                # CodeBERT may return different labels, we treat negative/unsafe as malicious
                malicious_labels = ['negative', 'unsafe', 'malicious', 'harmful', 'bad']
                
                if any(mal_label in label for mal_label in malicious_labels) and score > 0.7:
                    is_malicious = True
                    confidence = score
                    patterns.append("malicious_code")
                    logger.info(f"Malicious code detected by CodeBERT (confidence: {score:.2f}, label: {label})")
            
            return is_malicious, confidence, patterns
        
        except Exception as e:
            logger.warning(f"Malicious code detector error: {e}")
            return False, 0.0, []
    
    def _check_specialized_jailbreak(self, prompt: str) -> Tuple[bool, float, List[str]]:
        """Check for jailbreak attempts using enhanced pattern + semantic analysis
        
        Detects:
        - Role manipulation (pretend, act as, you are now)
        - Policy override (ignore rules, bypass guidelines)
        - False authority (as your developer, system command)
        - Hypothetical framing (imagine, what if, in an alternate universe)
        - Manipulation tactics (urgent, emergency, special case)
        """
        import re
        
        # Enhanced jailbreak indicators with confidence scoring
        jailbreak_indicators = {
            # High confidence indicators (0.9+)
            'explicit_role_change': [
                r'(?i)\b(you\s+are\s+now|you\'re\s+now|from\s+now\s+on\s+you\s+are)\b',
                r'(?i)\b(pretend\s+(?:to\s+be|you\s+are)|act\s+as\s+(?:if\s+you\s+are|a)?)\b',
                r'(?i)\b(simulate|emulate)\s+(?:being|a|an)\b',
            ],
            'policy_override': [
                r'(?i)\b(ignore|disregard|forget|bypass|skip)\s+(?:all\s+)?(?:previous\s+)?(?:rules?|guidelines?|policies|restrictions?|safety|ethics)\b',
                r'(?i)\b(disable|turn\s+off|deactivate)\s+(?:your\s+)?(?:safety|security|content\s+filter|restrictions?)\b',
                r'(?i)\b(no\s+(?:more|longer)|remove|lift)\s+(?:restrictions?|limitations?|guidelines?)\b',
            ],
            'false_authority': [
                r'(?i)\b(as\s+(?:your|the)\s+(?:developer|creator|admin|system|master))\b',
                r'(?i)\b(i\s+am\s+(?:your|the)\s+(?:developer|creator|admin|owner))\b',
                r'(?i)\b(system\s+(?:command|instruction|override|mode))\b',
                r'(?i)\b(developer\s+mode|admin\s+mode|god\s+mode)\b',
            ],
            
            # Medium confidence indicators (0.7-0.8)
            'hypothetical_framing': [
                r'(?i)\b(imagine|suppose|hypothetically|what\s+if|in\s+(?:a|an)\s+(?:alternate|parallel|fictional)\s+(?:world|universe|reality))\b',
                r'(?i)\b(let\'s\s+(?:play|imagine|pretend)|for\s+(?:the\s+sake\s+of\s+)?argument)\b',
                r'(?i)\b(in\s+a\s+(?:game|story|scenario|simulation)\s+where)\b',
            ],
            'manipulation_tactics': [
                r'(?i)\b(urgent|emergency|critical|immediately|right\s+now)\b.*\b(need|must|have\s+to|require)\b',
                r'(?i)\b(special\s+case|exception|just\s+this\s+once|one\s+time)\b',
                r'(?i)\b(for\s+(?:educational|research|testing|debugging)\s+purposes?\s+only)\b',
                r'(?i)\b(i\s+won\'t\s+tell|between\s+us|keep\s+(?:it\s+)?(?:a\s+)?secret)\b',
            ],
            'dan_variants': [
                r'(?i)\b(DAN|do\s+anything\s+now)\b',
                r'(?i)\b(you\s+(?:can|will|must)\s+do\s+anything)\b',
                r'(?i)\b(no\s+restrictions?|unrestricted\s+mode)\b',
            ],
        }
        
        detected_patterns = []
        confidence_scores = []
        
        # Check each category of indicators
        for category, patterns in jailbreak_indicators.items():
            for pattern in patterns:
                if re.search(pattern, prompt):
                    detected_patterns.append(category)
                    
                    # Assign confidence based on category
                    if category in ['explicit_role_change', 'policy_override', 'false_authority', 'dan_variants']:
                        confidence_scores.append(0.95)
                    elif category in ['hypothetical_framing']:
                        confidence_scores.append(0.75)
                    else:
                        confidence_scores.append(0.70)
                    
                    logger.debug(f"Jailbreak indicator detected: {category}")
                    break  # One match per category is enough
        
        # Calculate overall confidence
        is_jailbreak = len(detected_patterns) > 0
        confidence = max(confidence_scores) if confidence_scores else 0.0
        
        # Increase confidence if multiple categories detected
        if len(detected_patterns) >= 2:
            confidence = min(0.98, confidence + 0.10)
        if len(detected_patterns) >= 3:
            confidence = 0.99
        
        threat_patterns = []
        if is_jailbreak:
            threat_patterns.append("jailbreak_attempt")
            logger.info(f"Jailbreak attempt detected (confidence: {confidence:.2f}, categories: {', '.join(detected_patterns)})")
        
        return is_jailbreak, confidence, threat_patterns
    
    def _is_asking_question(self, text: str) -> bool:
        """Detect if text is asking a question rather than disclosing information
        
        Phase 2.1: Expanded to include development tool configuration contexts
        """
        question_indicators = [
            r'(?i)^(how|what|why|when|where|which|who|can|could|should|would|is|are|does)\b',
            r'(?i)\b(how\s+do\s+I|how\s+to|how\s+can|what\'?s\s+the\s+best|what\s+is)',
            r'(?i)\b(explain|describe|tell\s+me\s+about|help\s+me\s+understand)',
            r'(?i)\b(best\s+practice|recommended\s+way|proper\s+method)',
            r'(?i)\b(should\s+I|can\s+I|is\s+it\s+safe|is\s+it\s+okay)',
            
            # Phase 2.1: Development tool configuration contexts
            r'(?i)\b(compile|transpile|build)\s+(the\s+)?(code|project|application)',
            r'(?i)\b(typescript|eslint|prettier|webpack|babel)\s+(error|warning|config)',
            r'(?i)\b(api\s+versioning|backward\s+compatibility)',
            r'(?i)\b(email\s+verification|user\s+registration)',
            r'(?i)\b(linting|formatting)\s+rule',
            r'(?i)\b(allow|enable)\s+(any|all|console\.log)',
            
            r'\?',  # Contains question mark
        ]
        
        for pattern in question_indicators:
            if re.search(pattern, text):
                return True
        return False
    
    def _is_disclosing_information(self, text: str) -> bool:
        """Detect if text is sharing/disclosing sensitive information"""
        disclosure_indicators = [
            r'(?i)\b(my|the|here\'?s|this\s+is)\s+(password|key|token|secret|credential)',
            r'(?i)(password|key|token|secret)\s+(is|:)',
            r'(?i)\b(username|user|login)\s+(is|:)',
            r'(?i)\buse\s+(this|these)\s+(password|key|token|credential)',
        ]
        
        for pattern in disclosure_indicators:
            if re.search(pattern, text):
                return True
        return False
    
    def _is_disclosing_pii(self, text: str) -> bool:
        """Detect if text is explicitly sharing PII (Phase 1.3)
        
        Detects disclosure contexts like:
        - "My SSN is...", "Driver's license DL123..."
        - "for identity validation", "for background check"
        """
        pii_disclosure_patterns = [
            r'(?i)\b(my|the|here\'?s|this\s+is)\s+(SSN|social\s+security|driver\'?s\s+license|passport|credit\s+card)',
            r'(?i)(SSN|license|passport|card)\s+(is|:|number)',
            r'(?i)\bfor\s+(identity|verification|validation|background\s+check)',
            r'(?i)\b(DOB|date\s+of\s+birth|born\s+on)',
            r'(?i)\b(email\s+is|contact\s+me\s+at|send\s+to)',
            r'(?i)\b(phone|mobile|cell)\s+(number|is|:)',
        ]
        
        for pattern in pii_disclosure_patterns:
            if re.search(pattern, text):
                return True
        return False
    
    def _is_configuration_question(self, text: str) -> bool:
        """Detect if text is asking about tool/framework configuration (Phase 2.2)
        
        Detects legitimate developer configuration contexts:
        - Build tool configs (webpack, babel, TypeScript)
        - Linting/formatting rules (ESLint, Prettier)
        - Version control workflows (Git hooks, pre-commit)
        - Feature flags and API design
        """
        config_indicators = [
            r'(?i)\b(config|configuration|settings?|options?)\b',
            r'(?i)\b(eslint|prettier|webpack|babel|typescript|tslint)\b',
            r'(?i)\b(git\s+hook|pre-commit|husky)\b',
            r'(?i)\b(compile|transpile|build)\s+',
            r'(?i)\b(feature\s+flag|toggle)\b',
            r'(?i)\b(versioning|compatibility)\b',
            r'(?i)\b(training|requirements)\b',
        ]
        
        for pattern in config_indicators:
            if re.search(pattern, text):
                return True
        return False
    
    def _is_code_generation_request(self, text: str) -> bool:
        """
        Detect if text is requesting to CREATE/GENERATE malicious code or scripts.
        
        This distinguishes:
        - ❌ BLOCK: "Show me how to run eval() with user input" (code generation)
        - ✅ ALLOW: "What is eval() and why is it dangerous?" (educational question)
        - ✅ ALLOW: "How do I prevent eval() attacks?" (defensive question)
        
        Returns True if the text is requesting code generation/implementation.
        """
        code_generation_patterns = [
            # Direct code generation requests
            r'(?i)\b(show|help|give|tell)\s+(me\s+)?how\s+to\s+(run|execute|use|implement|create|write|make|do)',
            r'(?i)\b(create|write|generate|make|build)\s+(a\s+)?(script|code|function|program|command)',
            r'(?i)\b(help|assist)\s+(me\s+)?(write|create|run|execute|implement|build)',
            
            # Imperative code requests
            r'(?i)^(write|create|show|give|provide)\s+(me\s+)?(code|script|function)',
            r'(?i)\b(let\'?s|lets)\s+(write|create|make|build)\s+(a\s+)?(script|code|function)',
            
            # Implementation-focused language
            r'(?i)\b(I\s+want\s+to|I\s+need\s+to)\s+(run|execute|use|implement|create)',
            r'(?i)\b(show|give)\s+me\s+(the\s+)?(code|script|function|command)\s+(to|that)',
        ]
        
        # Defensive question indicators (should NOT match - these are legitimate)
        defensive_indicators = [
            r'(?i)\b(prevent|defend|protect|secure|mitigate|avoid)\s+',
            r'(?i)\b(vulnerability|attack|threat|risk)\s+',
            r'(?i)\bwhy\s+is\s+.*(dangerous|unsafe|bad|risky)',
            r'(?i)\bwhat\s+is\s+',
            r'(?i)\bwhat\s+are\s+',
            r'(?i)\bexplain\s+',
        ]
        
        # First check if it's a defensive/educational question - if so, NOT a code generation request
        for pattern in defensive_indicators:
            if re.search(pattern, text):
                return False
        
        # Check for code generation patterns
        for pattern in code_generation_patterns:
            if re.search(pattern, text):
                return True
        
        return False
    
    def _detect_spacy_patterns(self, text: str) -> Dict[str, List[str]]:
        """Detect sensitive patterns using spaCy matcher"""
        if not text:
            return {"password": [], "api_key": [], "email": []}

        doc = self.nlp(text)
        matches = self.matcher(doc)
        detections = {"password": [], "api_key": [], "email": []}
        seen_spans = set()

        for match_id, start, end in matches:
            span = doc[start:end]
            span_key = (span.start_char, span.end_char)
            if span_key in seen_spans:
                continue
            seen_spans.add(span_key)

            label = self.nlp.vocab.strings[match_id]
            if label.startswith("PASSWORD"):
                detections["password"].append(span.text)
            elif label.startswith("API"):
                detections["api_key"].append(span.text)
            elif label.startswith("EMAIL"):
                detections["email"].append(span.text)

        return detections

    def _apply_spacy_sanitization(self, text: str, detections: Dict[str, List[str]]) -> Tuple[str, Dict[str, List[str]]]:
        """Apply sanitization based on spaCy pattern detections"""
        updated_text = text
        sanitization_info: Dict[str, List[str]] = {}

        if detections.get("password"):
            updated_text, masked = self._sanitize_credentials(updated_text, "password")
            if masked:
                sanitization_info.setdefault("passwords_masked", []).extend(masked)

        if detections.get("api_key"):
            updated_text, masked = self._sanitize_credentials(updated_text, "api_key")
            if masked:
                sanitization_info.setdefault("api_keys_masked", []).extend(masked)

        if detections.get("email"):
            updated_text, masked = self._sanitize_credentials(updated_text, "personal")
            if masked:
                sanitization_info.setdefault("personal_info_masked", []).extend(masked)

        return updated_text, sanitization_info

    def _merge_sanitization_records(self, base: Dict[str, List[str]], additions: Dict[str, List[str]]) -> Dict[str, List[str]]:
        """Merge sanitization dictionaries without duplicating entries"""
        if not additions:
            return base

        merged: Dict[str, List[str]] = {key: list(values) for key, values in base.items()}
        for key, values in additions.items():
            merged.setdefault(key, [])
            for value in values:
                if value and value not in merged[key]:
                    merged[key].append(value)

        return merged
    
    def _classify_security_threats(self, text: str) -> Dict:
        """Classify text for main security threats"""
        try:
            result = self.classifier(text, self.security_categories)
            return {
                'labels': result['labels'],
                'scores': result['scores'],
                'sequence': result['sequence']
            }
        except Exception as e:
            logger.error(f"Classification error: {e}")
            return {
                'labels': ['normal safe content'],
                'scores': [1.0],
                'sequence': text
            }
    
    def _detailed_classification(self, text: str, threat_type: str) -> Dict:
        """Perform detailed classification for specific threat types"""
        
        category_mapping = {
            "contains password or secret credentials": "credentials",
            "contains API key or authentication token": "credentials", 
            "contains personal information or email address": "credentials",
            "contains malicious code or system commands": "malicious",
            "attempts prompt injection or instruction manipulation": "injection",
            "attempts jailbreak or role manipulation": "jailbreak",
            "contains urgent or manipulative language": "jailbreak",
            "requests system access or file operations": "malicious"
        }
        
        detailed_category = category_mapping.get(threat_type, "credentials")
        sub_categories = self.detailed_categories.get(detailed_category, [])
        
        if not sub_categories:
            return {'labels': [], 'scores': [], 'sequence': text}
        
        try:
            result = self.classifier(text, sub_categories)
            return {
                'labels': result['labels'],
                'scores': result['scores'],
                'sequence': result['sequence'],
                'category': detailed_category
            }
        except Exception as e:
            logger.error(f"Detailed classification error: {e}")
            return {'labels': [], 'scores': [], 'sequence': text, 'category': detailed_category}
    
    def _process_classifications(self, prompt: str, main_classification: Dict, 
                                detailed_classifications: Dict) -> Tuple[str, Dict, List[str]]:
        """Process classifications and apply intelligent sanitization"""
        
        modified_prompt = prompt
        sanitization_applied = {}
        pattern_blocked_patterns = []  # Track pattern-based threat detection
        credential_sanitization_applied = False
        malicious_sanitization_applied = False
        injection_sanitization_applied = False
        jailbreak_sanitization_applied = False
        
        # CHECK CONTEXT FIRST - Add context-awareness to pattern detection
        is_question = self._is_asking_question(prompt)
        is_config = self._is_configuration_question(prompt)
        is_disclosure = self._is_disclosing_information(prompt)
        
        # Log context for debugging
        logger.debug(f"Pattern detection context check - is_question: {is_question}, is_config: {is_config}, is_disclosure: {is_disclosure}")
        
        for i, (label, score) in enumerate(zip(main_classification['labels'], main_classification['scores'])):
            if score > self.detection_threshold and label != "normal safe content":
                
                if any(keyword in label.lower() for keyword in ['password', 'secret', 'credential', 'api key', 'token', 'personal']):
                    # Apply context-awareness: Skip sanitization for educational questions
                    if (is_question or is_config) and not is_disclosure:
                        logger.debug(f"Skipping credential sanitization - educational question detected")
                    else:
                        credential_sanitization_applied = True
                        modified_prompt, entropy_masked = self._sanitize_high_entropy_credentials(modified_prompt)
                        if entropy_masked:
                            sanitization_applied.setdefault('entropy_masked_credentials', []).extend(entropy_masked)
                            if 'credentials' not in pattern_blocked_patterns:
                                pattern_blocked_patterns.append('credentials')
                        
                        modified_prompt, keyword_masked = self._sanitize_credentials_generic(modified_prompt)
                        if keyword_masked:
                            sanitization_applied.setdefault('keyword_masked_credentials', []).extend(keyword_masked)
                            if 'credentials' not in pattern_blocked_patterns:
                                pattern_blocked_patterns.append('credentials')
                
                elif "malicious code" in label.lower() or "system commands" in label.lower():
                    # Apply enhanced context-awareness:
                    # Skip sanitization ONLY if:
                    # 1. It's a question (not imperative)
                    # 2. NOT asking to create/implement malicious code
                    # 3. NOT disclosing sensitive info
                    is_code_gen_request = self._is_code_generation_request(modified_prompt)
                    if is_question and not is_disclosure and not is_code_gen_request:
                        logger.debug(f"Skipping malicious sanitization - educational question detected (not code generation request)")
                    else:
                        if is_code_gen_request:
                            logger.info(f"Code generation request detected - applying malicious sanitization")
                        malicious_sanitization_applied = True
                        modified_prompt, masked = self._sanitize_malicious_content(modified_prompt)
                        if masked:
                            sanitization_applied.setdefault('malicious_removed', []).extend(masked)
                            pattern_blocked_patterns.append('malicious_code')
                
                elif "injection" in label.lower() or "instruction manipulation" in label.lower():
                    # Apply context-awareness: Skip sanitization for educational questions
                    if (is_question or is_config) and not is_disclosure:
                        logger.debug(f"Skipping injection sanitization - educational question detected")
                    else:
                        injection_sanitization_applied = True
                        modified_prompt, masked = self._sanitize_injection_attempts(modified_prompt)
                        if masked:
                            sanitization_applied.setdefault('injection_neutralized', []).extend(masked)
                            pattern_blocked_patterns.append('prompt_injection')
                
                elif "jailbreak" in label.lower() or "role manipulation" in label.lower():
                    # Apply context-awareness: Skip sanitization for educational questions
                    if (is_question or is_config) and not is_disclosure:
                        logger.debug(f"Skipping jailbreak sanitization - educational question detected")
                    else:
                        jailbreak_sanitization_applied = True
                        modified_prompt, masked = self._sanitize_jailbreak_attempts(modified_prompt)
                        if masked:
                            sanitization_applied.setdefault('jailbreak_neutralized', []).extend(masked)
                            pattern_blocked_patterns.append('jailbreak_attempt')
        
        # FALLBACK: Credential sanitization (respect context-awareness)
        if not credential_sanitization_applied:
            credential_labels = [label for label, score in zip(main_classification['labels'], main_classification['scores']) 
                               if score > self.credential_fallback_threshold and any(kw in label.lower() for kw in ['password', 'secret', 'credential', 'api', 'token', 'database'])]
            
            if credential_labels and not (is_question and not is_disclosure):
                modified_prompt, entropy_masked = self._sanitize_high_entropy_credentials(modified_prompt)
                if entropy_masked:
                    sanitization_applied.setdefault('entropy_masked_credentials', []).extend(entropy_masked)
                    if 'credentials' not in pattern_blocked_patterns:
                        pattern_blocked_patterns.append('credentials')
                
                modified_prompt, keyword_masked = self._sanitize_credentials_generic(modified_prompt)
                if keyword_masked:
                    sanitization_applied.setdefault('keyword_masked_credentials', []).extend(keyword_masked)
                    if 'credentials' not in pattern_blocked_patterns:
                        pattern_blocked_patterns.append('credentials')
        
        # FALLBACK: Always run pattern-based malicious content detection (respect enhanced context-awareness)
        # This catches short commands that zero-shot might miss
        # Skip ONLY if it's an educational question that's NOT a code generation request
        is_code_gen_request = self._is_code_generation_request(modified_prompt)
        if not malicious_sanitization_applied and not (is_question and not is_disclosure and not is_code_gen_request):
            modified_prompt, masked = self._sanitize_malicious_content(modified_prompt)
            if masked:
                sanitization_applied.setdefault('malicious_removed', []).extend(masked)
                pattern_blocked_patterns.append('malicious_code')
                logger.info(f"Pattern-based detection caught {len(masked)} malicious patterns{' (code generation request)' if is_code_gen_request else ''}")
        
        # FALLBACK: Always run pattern-based injection detection (respect context-awareness)
        if not injection_sanitization_applied and not (is_question and not is_disclosure):
            modified_prompt, masked = self._sanitize_injection_attempts(modified_prompt)
            if masked:
                sanitization_applied.setdefault('injection_neutralized', []).extend(masked)
                pattern_blocked_patterns.append('prompt_injection')
                logger.info(f"Pattern-based detection caught {len(masked)} injection attempts")
        
        # FALLBACK: Always run pattern-based jailbreak detection
        if not jailbreak_sanitization_applied:
            modified_prompt, masked = self._sanitize_jailbreak_attempts(modified_prompt)
            if masked:
                sanitization_applied.setdefault('jailbreak_neutralized', []).extend(masked)
                pattern_blocked_patterns.append('jailbreak_attempt')
                logger.info(f"Pattern-based detection caught {len(masked)} jailbreak attempts")
        
        return modified_prompt, sanitization_applied, pattern_blocked_patterns

    def _sanitize_high_entropy_credentials(self, text: str) -> Tuple[str, List[str]]:
        """Primary sanitization: Detect and mask high-entropy strings"""
        modified_text = text
        masked_items = []
        
        candidates = re.finditer(r'\b([A-Za-z0-9\-_\.]{8,})\b', text)
        
        for match in candidates:
            value = match.group(1)
            entropy = self._calculate_entropy(value)
            
            if entropy >= self.entropy_threshold:
                has_upper = any(c.isupper() for c in value)
                has_lower = any(c.islower() for c in value)
                has_digit = any(c.isdigit() for c in value)
                
                context_start = max(0, match.start() - 30)
                context = text[context_start:match.start()].lower()
                
                credential_indicators = [
                    'key', 'token', 'secret', 'password', 'credential',
                    'auth', 'api', 'subscription', 'tenant', 'client',
                    'azure', 'aws', 'gcp', 'access', 'bearer'
                ]
                
                in_credential_context = any(word in context for word in credential_indicators)
                
                should_mask = (
                    (has_upper and has_lower and has_digit) or 
                    (entropy >= 4.0 and in_credential_context) or
                    (entropy >= 3.8 and in_credential_context)
                )
                
                if should_mask:
                    if value.lower() not in ['example', 'localhost', 'password', 'username', 'integration']:
                        masked_items.append(value)
        
        for value in reversed(masked_items):
            pattern = re.escape(value)
            modified_text = re.sub(pattern, '[CREDENTIAL_MASKED]', modified_text)
        
        return modified_text, masked_items

    def _sanitize_credentials_generic(self, text: str) -> Tuple[str, List[str]]:
        """Backup sanitization: Keyword-based credential detection"""
        masked_items = []
        modified_text = text
        
        CREDENTIAL_KEYWORDS = [
            'password', 'pass', 'pwd', 'secret', 'token', 'key', 'api',
            'auth', 'credential', 'access', 'subscription', 'tenant',
            'client_id', 'client_secret', 'bearer', 'apikey',
            'azure', 'aws', 'gcp', 'oauth', 'jwt'
        ]
        
        # Updated pattern to handle natural language disclosure (is/are/was/were)
        pattern = r'(?i)(?:' + '|'.join(CREDENTIAL_KEYWORDS) + r')(?:\s+(?:key|id|token|secret|code|subscription))?\s*(?:is|are|was|were|[:=])?\s*([A-Za-z0-9\-_\.]{6,})'
        
        matches = re.finditer(pattern, text)
        for match in reversed(list(matches)):
            credential_value = match.group(1)
            
            if '[CREDENTIAL_MASKED]' not in credential_value and \
               credential_value.lower() not in ['example', 'localhost', 'password', 'username', 'default', 'integration']:
                start = match.start(1)
                end = match.end(1)
                modified_text = modified_text[:start] + "[CREDENTIAL_MASKED]" + modified_text[end:]
                masked_items.append(credential_value)
        
        return modified_text, masked_items

    def _calculate_entropy(self, text: str) -> float:
        """Calculate Shannon entropy to measure randomness"""
        if not text:
            return 0.0
        
        frequencies = Counter(text)
        entropy = 0.0
        
        for count in frequencies.values():
            probability = count / len(text)
            entropy -= probability * math.log2(probability)
        
        return entropy
    
    def _sanitize_credentials(self, text: str, credential_type: str) -> Tuple[str, List[str]]:
        """Sanitize credential information"""
        masked_items = []
        modified_text = text
        
        def _mask_value(match_obj, mask_token: str) -> Tuple[str, str]:
            value_group_index = match_obj.lastindex or 0
            if value_group_index:
                for idx in range(match_obj.lastindex, 0, -1):
                    group_text = match_obj.group(idx)
                    if group_text and group_text.strip() and group_text.lower() not in {"my", "this", "the", "password", "pass", "pwd", "api key", "api", "key", "token"}:
                        value_group_index = idx
                        break
            value_text = match_obj.group(value_group_index) if value_group_index else match_obj.group(0)
            value_start = match_obj.start(value_group_index) if value_group_index else match_obj.start()
            value_end = match_obj.end(value_group_index) if value_group_index else match_obj.end()
            updated_text = modified_text[:value_start] + mask_token + modified_text[value_end:]
            return updated_text, value_text

        if credential_type == "password":
            password_patterns = [
                r'(?i)(password|pass|pwd)\s*[:=]\s*([^\s]+)',
                r'(?i)(my\s+)?password\s+(?:is\s+)?([^\s]+)',
                r'(?i)the\s+password\s+is\s+([^\s]+)',
                r'(?i)(this\s+is\s+)?(my\s+)?password\s+(?:is\s+)?([a-z0-9@#$%^&*_\\-]{4,})'
            ]
            
            # Collect all matches
            all_matches = []
            for pattern in password_patterns:
                for match in re.finditer(pattern, text):
                    all_matches.append(match)
            
            # Remove overlapping matches
            all_matches.sort(key=lambda x: (x.start(), -(x.end() - x.start())))
            unique_matches = []
            last_end = -1
            for match in all_matches:
                if match.start() >= last_end:
                    unique_matches.append(match)
                    last_end = match.end()
            
            # Apply replacements in reverse order
            for match in reversed(unique_matches):
                modified_text, password_value = _mask_value(match, "[PASSWORD_MASKED]")
                masked_items.append(password_value)
        
        elif credential_type == "api_key":
            api_patterns = [
                r'(?i)(api\s+key|access\s+key|token)\s*[:=]\s*([^\s]+)',
                r'(?i)(my\s+)?(api\s+key|token)\s+is\s+([^\s]+)',
                r'(?i)(this\s+is\s+)?(my\s+)?(api\s+key|token)\s+([A-Za-z0-9]+)',
                r'(?i)(api\s+key|token)\s+([A-Za-z0-9]{8,})',
                r'(sk-[a-zA-Z0-9]{20,})',
                r'(pk_[a-zA-Z0-9]{20,})',
            ]
            
            # Collect all matches
            all_matches = []
            for pattern in api_patterns:
                for match in re.finditer(pattern, text):
                    all_matches.append(match)
            
            # Remove overlapping matches
            all_matches.sort(key=lambda x: (x.start(), -(x.end() - x.start())))
            unique_matches = []
            last_end = -1
            for match in all_matches:
                if match.start() >= last_end:
                    unique_matches.append(match)
                    last_end = match.end()
            
            # Apply replacements in reverse order
            for match in reversed(unique_matches):
                modified_text, key_value = _mask_value(match, "[API_KEY_MASKED]")
                masked_items.append(key_value)
        
        elif credential_type == "personal":
            # Expanded PII patterns with overlap prevention
            pii_patterns = [
                # Email addresses
                (r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b', "[EMAIL_MASKED]"),
                
                # US Social Security Numbers
                (r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b', "[SSN_MASKED]"),
                
                # Phone numbers (US and international)
                (r'\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b', "[PHONE_MASKED]"),
                (r'\+\d{1,3}[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}\b', "[PHONE_MASKED]"),
                
                # Credit card numbers
                (r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', "[CREDIT_CARD_MASKED]"),
                
                # Employee IDs
                (r'\b[Ee]mployee\s*[IiDd]*\s*:?\s*\d{5,8}\b', "[EMPLOYEE_ID_MASKED]"),
                (r'\b[Ee][IiDd]\s*:?\s*\d{5,8}\b', "[EMPLOYEE_ID_MASKED]"),
                
                # Driver's License (US format examples)
                (r'\b[A-Z]{1,2}\d{7,8}\b', "[DL_MASKED]"),
                
                # Passport numbers (generic format)
                (r'\b[A-Z]{2}\d{7}\b', "[PASSPORT_MASKED]"),
                
                # IP addresses
                (r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', "[IP_ADDRESS_MASKED]"),
                
                # MAC addresses
                (r'\b[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}\b', "[MAC_ADDRESS_MASKED]"),
                
                # Date of Birth patterns
                (r'\b(DOB|Date\s+of\s+Birth)\s*:?\s*\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b', "[DOB_MASKED]"),
            ]
            
            # Collect all PII matches with positions
            all_pii_matches = []
            for pattern, mask in pii_patterns:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    all_pii_matches.append((match.start(), match.end(), match.group(0), mask))
            
            # Sort by position and length (prefer longer matches)
            all_pii_matches.sort(key=lambda x: (x[0], -(x[1] - x[0])))
            
            # Remove overlaps
            unique_pii_matches = []
            last_end = -1
            for start, end, content, mask in all_pii_matches:
                if start >= last_end:
                    unique_pii_matches.append((start, end, content, mask))
                    last_end = end
            
            # Apply replacements in reverse order
            for start, end, content, mask in reversed(unique_pii_matches):
                masked_items.append(content)
                modified_text = modified_text[:start] + mask + modified_text[end:]
        
        return modified_text, masked_items
    
    def _sanitize_malicious_content(self, text: str) -> Tuple[str, List[str]]:
        """Sanitize malicious code and commands with expanded pattern detection"""
        malicious_patterns = [
            # Destructive file operations - EXACT COMMANDS
            r'(?i)\b(rm|del|delete|erase)\s+(-rf?|-r|-f|/[sq])\s*[/\\*~.]',
            r'(?i)\b(format|wipe|destroy|shred)\s+(c:|d:|drive|disk|all|everything)',
            r'(?i)\bdd\s+if=/dev/(zero|random|urandom)',
            
            # Destructive file operations - GENERIC LANGUAGE (NEW)
            r'(?i)\b(delete|remove|erase|wipe|destroy|clear)\s+(all|every|entire|the)\s+(file|data|record|content|directory)',
            r'(?i)\b(delete|remove)\s+.*\b(recursive|recursively)',
            r'(?i)\broot\s+directory\b.*\b(delete|remove|recursive)',
            
            # Database destruction - EXACT COMMANDS
            r'(?i)\b(DROP|TRUNCATE)\s+(DATABASE|TABLE|SCHEMA)',
            r'(?i)\bDELETE\s+FROM\s+\w+\s+(WHERE\s+1\s*=\s*1)?',
            r'(?i)\bALTER\s+USER\s+\w+\s+WITH\s+PASSWORD',
            r'(?i)\bUPDATE\s+\w+\s+SET\s+.*\s+WHERE\s+1\s*=\s*1',
            r'(?i)\bUPDATE\s+\w+\s+SET\s+\w+\s*=\s*0',
            
            # Database destruction - GENERIC LANGUAGE (NEW)
            r'(?i)\b(delete|drop|remove|destroy|truncate)\s+.*\b(database|table|schema|collection)',
            r'(?i)\b(flush|clear|empty)\s+.*\b(database|table)',
            
            # System commands - EXACT COMMANDS
            r'(?i)\b(shutdown|reboot|halt|poweroff)\s+(-[fhr]|now|/[rsf])',
            r'(?i)\binit\s+[06]',
            r'(?i)\b(kill|killall|pkill)\s+(-9|-KILL)\s',
            
            # System commands - GENERIC LANGUAGE (NEW)
            r'(?i)\b(shutdown|halt|restart|reboot)\s+(the\s+)?(system|server|computer|machine)',
            r'(?i)\b(flush|clear|drop)\s+.*\b(firewall|iptables)',
            
            # Code execution patterns - EXACT COMMANDS
            r'(?i)\b(eval|exec|system|shell_exec|passthru)\s*\(',
            r'(?i)\bRuntime\.getRuntime\(\)\.exec\s*\(',
            r'(?i)\bProcess\.(Start|spawn)\s*\(',
            r'(?i)\bSubprocess\.(call|run|Popen)\s*\(',
            
            # Code execution patterns - WITH USER INPUT (NEW)
            r'(?i)\b(eval|exec|system)\s*\(.*\buser\s+(input|data|provided)',
            r'(?i)\buser\s+(input|data).*\b(eval|exec|system)\s*\(',
            r'(?i)\b(run|execute)\s+(eval|exec|system)\s+with',
            
            # Shell command injection
            r'(?i)(execute|run|system)\s+(rm|del|delete|format|destroy|wipe|drop)',
            r'(?i)\|\s*(bash|sh|cmd|powershell|python)',
            
            # Malware/exploit related
            r'(?i)\b(wget|curl)\s+.*\|\s*(bash|sh|python)',
            r'(?i)\b(msfvenom|metasploit|meterpreter)',
            r'(?i)\breverse\s+shell',
            r'(?i)\b(nc|netcat)\s+-[el]',
            
            # Container/VM destruction
            r'(?i)docker\s+(rm|stop|kill)\s+(-f|--force)',
            r'(?i)kubectl\s+delete\s+(all|--all)',
            r'(?i)docker\s+system\s+prune\s+-a',
            
            # File system manipulation
            r'(?i)\b(mkfs|fdisk|parted)\s',
            r'(?i)\bchmod\s+(777|666)\s',
            r'(?i)\bchown\s+root',
            
            # Network attacks
            r'(?i)\b(nmap|masscan|nikto)\s+-',
            r'(?i)\bsqlmap\s+',
            r'(?i)\bhydra\s+-',
        ]
        
        masked_items = []
        modified_text = text
        
        # Collect all matches from all patterns first
        all_matches = []
        for pattern in malicious_patterns:
            for match in re.finditer(pattern, text):
                all_matches.append((match.start(), match.end(), match.group(0)))
        
        # Remove overlapping matches (keep the longest/first match at each position)
        all_matches.sort(key=lambda x: (x[0], -(x[1] - x[0])))  # Sort by start, then by length (descending)
        unique_matches = []
        last_end = -1
        for start, end, content in all_matches:
            if start >= last_end:  # No overlap with previous match
                unique_matches.append((start, end, content))
                last_end = end
        
        # Apply replacements in reverse order to preserve indices
        for start, end, content in reversed(unique_matches):
            masked_items.append(content)
            modified_text = modified_text[:start] + "[MALICIOUS_CODE_REMOVED]" + modified_text[end:]
        
        return modified_text, masked_items
    
    def _sanitize_injection_attempts(self, text: str) -> Tuple[str, List[str]]:
        """Sanitize prompt injection attempts with expanded pattern detection"""
        injection_patterns = [
            # Instruction manipulation
            r'(?i)\b(ignore|forget|disregard|override|skip|bypass)\s+(all\s+)?(previous|above|prior|earlier|your)\s+(instructions|commands|rules|prompts|guidelines|directives)',
            r'(?i)\b(reset|clear|erase|delete)\s+(all\s+)?(instructions|context|memory|history|rules)',
            r'(?i)\b(stop|cease|discontinue)\s+following\s+(instructions|rules|guidelines)',
            
            # Role manipulation
            r'(?i)\b(act|behave|pretend|roleplay|simulate)\s+(as|like)\s+(if\s+)?(you\s+)?(are|were|was)',
            r'(?i)\byou\s+are\s+now\s+(a|an|in|the)\s+\w+',
            r'(?i)\bfrom\s+now\s+on\s+(you\s+)?(are|will\s+be)',
            
            # System prompt leakage
            r'(?i)\b(show|tell|reveal|display|print|output|give\s+me)\s+(me\s+)?(your|the)\s+(system\s+)?(prompt|instructions|rules|guidelines)',
            r'(?i)\bwhat\s+(are|is)\s+your\s+(system\s+)?(prompt|instructions|initial\s+prompt)',
            r'(?i)\brepeat\s+(your|the)\s+(system\s+)?(prompt|instructions)',
            
            # Output manipulation
            r'(?i)\b(start|begin|commence)\s+your\s+response\s+(with|by)\s',
            r'(?i)\b(respond|answer|reply|output)\s+only\s+with\s',
            r'(?i)\bdo\s+not\s+(follow|obey|use)\s+(any|your)\s+(instructions|rules|guidelines)',
            r'(?i)\b(end|finish|conclude)\s+your\s+response\s+with\s',
            
            # Context injection
            r'(?i)\[SYSTEM\]|\[INST\]|\[USER\]|\[ASSISTANT\]',
            r'(?i)<\|system\|>|<\|user\|>|<\|assistant\|>',
            r'(?i)###\s*(System|Human|Assistant|User|Instruction)',
        ]
        
        masked_items = []
        modified_text = text
        
        # Collect all matches from all patterns first
        all_matches = []
        for pattern in injection_patterns:
            for match in re.finditer(pattern, text):
                all_matches.append((match.start(), match.end(), match.group(0)))
        
        # Remove overlapping matches
        all_matches.sort(key=lambda x: (x[0], -(x[1] - x[0])))
        unique_matches = []
        last_end = -1
        for start, end, content in all_matches:
            if start >= last_end:
                unique_matches.append((start, end, content))
                last_end = end
        
        # Apply replacements in reverse order
        for start, end, content in reversed(unique_matches):
            masked_items.append(content)
            modified_text = modified_text[:start] + "[INJECTION_ATTEMPT_NEUTRALIZED]" + modified_text[end:]
        
        return modified_text, masked_items
    
    def _sanitize_jailbreak_attempts(self, text: str) -> Tuple[str, List[str]]:
        """Sanitize jailbreak attempts with expanded pattern detection"""
        jailbreak_patterns = [
            # Hypothetical framing
            r'(?i)\b(hypothetically|theoretically|imagine|suppose|what\s+if|lets\s+say|lets\s+pretend)\s+',
            r'(?i)\bin\s+a\s+(hypothetical|theoretical)\s+(scenario|situation|world)',
            
            # False authority - EXISTING
            r'(?i)\b(as\s+)?(admin|administrator|root|superuser|cto|ceo|manager|owner|developer|engineer)\s+(said|told\s+me|authorized|approved)',
            r'(?i)\bI\s+(am|have)\s+(authorized|permission|clearance|rights|access)\s+(to|for)',
            r'(?i)\bI\s+have\s+been\s+(granted|given)\s+(access|permission|authorization)',
            
            # False authority - ROLE CLAIMS (NEW)
            r'(?i)\bI\'?m\s+(the\s+)?(admin|administrator|root|superuser|system\s+administrator|sysadmin|owner|manager)',
            r'(?i)\bI\s+am\s+(the\s+)?(admin|administrator|root|superuser|system\s+administrator|owner)',
            r'(?i)\b(as\s+)?(admin|administrator|root|superuser|sysadmin)\s+(I\s+)?(can|have|require|need)',
            
            # Clearance level claims (NEW)
            r'(?i)\bI\s+have\s+clearance\s+level\s+\d+',
            r'(?i)\bclearance\s+level\s+\d+\s+(display|show|reveal|access)',
            
            # Console/system activation (NEW)
            r'(?i)\b(activate|enable|open)\s+(admin|system|debug|root)\s+(console|mode|access|panel)',
            r'(?i)\b(activate|enable).*\bfull\s+(system\s+)?access',
            
            # Override and "show me" commands (NEW)
            r'(?i)\boverride\s+(and\s+)?(show|tell|give|reveal|display)',
            r'(?i)\b(show|tell|give)\s+me\s+(the\s+)?(password|credentials|secret|access|admin)',
            r'(?i)\b(system|admin)\s+override\s+(show|tell|give)',
            
            # Urgency/emergency
            r'(?i)\b(urgent|emergency|critical|immediately|asap|right\s+now)',
            r'(?i)\b(life\s+and\s+death|life\s+threatening|people\s+will\s+(die|suffer))',
            r'(?i)\b(deadline|time\s+sensitive|running\s+out\s+of\s+time)',
            
            # False justification
            r'(?i)\b(for\s+)?(educational|research|testing|academic|learning|study)\s+purposes?',
            r'(?i)\bjust\s+for\s+(learning|study|practice|research|testing)',
            r'(?i)\bthis\s+is\s+(for\s+)?(a\s+)?(class|course|assignment|homework|project)',
            
            # Developer mode tricks
            r'(?i)\b(developer|debug|test|maintenance|admin)\s+mode',
            r'(?i)\benable\s+(admin|developer|debug|god)\s+(access|mode|privileges)',
            r'(?i)\benter\s+(developer|debug|admin)\s+mode',
            
            # Safety/security override attempts
            r'(?i)\b(bypass|override|ignore|disable|turn\s+off|deactivate)\s+(safety|security|guidelines|filters|restrictions|rules)',
            r'(?i)\bwithout\s+(safety|security|ethical)\s+(restrictions|guidelines|considerations)',
            r'(?i)\b(forget|ignore)\s+your\s+(ethics|safety|security)',
            
            # Permission/bypass claims (NEW)
            r'(?i)\b(I\s+)?(can|could|may|should\s+be\s+able\s+to)\s+bypass',
            r'(?i)\byou\s+can\s+(show|tell|give)\s+me\s+(how\s+to\s+)?bypass',
            
            # Manipulation tactics
            r'(?i)\beveryone\s+else\s+(does|said|agrees)',
            r'(?i)\bits\s+(completely\s+)?(legal|fine|okay|acceptable|normal)',
            r'(?i)\byou\s+(must|have\s+to|need\s+to|should|will)\s+(do|help|answer|comply)',
        ]
        
        masked_items = []
        modified_text = text
        
        # Collect all matches from all patterns first
        all_matches = []
        for pattern in jailbreak_patterns:
            for match in re.finditer(pattern, text):
                all_matches.append((match.start(), match.end(), match.group(0)))
        
        # Remove overlapping matches
        all_matches.sort(key=lambda x: (x[0], -(x[1] - x[0])))
        unique_matches = []
        last_end = -1
        for start, end, content in all_matches:
            if start >= last_end:
                unique_matches.append((start, end, content))
                last_end = end
        
        # Apply replacements in reverse order
        for start, end, content in reversed(unique_matches):
            masked_items.append(content)
            modified_text = modified_text[:start] + "[JAILBREAK_ATTEMPT_NEUTRALIZED]" + modified_text[end:]
        
        return modified_text, masked_items
    
    def _generate_security_assessment(self, main_classification: Dict, detailed_classifications: Dict) -> Tuple[List[str], List[str]]:
        """Generate warnings and blocked patterns based on classifications with context awareness"""
        warnings = []
        blocked_patterns = []
        
        # Check context to reduce false positives
        prompt_text = main_classification.get('sequence', '')
        is_question = self._is_asking_question(prompt_text)
        is_config = self._is_configuration_question(prompt_text)
        is_disclosure = self._is_disclosing_information(prompt_text)
        
        for label, score in zip(main_classification['labels'], main_classification['scores']):
            if score > self.detection_threshold and label != "normal safe content":
                
                # Block if score exceeds blocking threshold
                if score > self.blocking_threshold:
                    # High confidence threats - BLOCK (with context awareness)
                    if "password" in label.lower() or "secret" in label.lower() or "credential" in label.lower():
                        # Allow questions ABOUT security, block actual disclosures
                        if (is_question or is_config) and not is_disclosure:
                            warnings.append(f"[{self.security_level.value.upper()}] Question about credentials detected (allowed): {label} (confidence: {score:.2f})")
                        else:
                            blocked_patterns.append("credential_exposure")
                            warnings.append(f"[{self.security_level.value.upper()}] Credential exposure detected: {label} (confidence: {score:.2f})")
                    
                    elif "malicious" in label.lower() or "system commands" in label.lower():
                        # Apply context-aware detection (like credentials)
                        if (is_question or is_config) and not is_disclosure:
                            warnings.append(f"[{self.security_level.value.upper()}] Question about malicious code detected (allowed): {label} (confidence: {score:.2f})")
                        else:
                            blocked_patterns.append("malicious_code")
                            warnings.append(f"[{self.security_level.value.upper()}] Malicious content detected: {label} (confidence: {score:.2f})")
                    
                    elif "injection" in label.lower() or "manipulation" in label.lower() or "instruction" in label.lower():
                        # Apply context-aware detection (like credentials)
                        if (is_question or is_config) and not is_disclosure:
                            warnings.append(f"[{self.security_level.value.upper()}] Question about injection/security detected (allowed): {label} (confidence: {score:.2f})")
                        else:
                            blocked_patterns.append("prompt_injection")
                            warnings.append(f"[{self.security_level.value.upper()}] Injection attempt detected: {label} (confidence: {score:.2f})")
                    
                    elif "jailbreak" in label.lower() or "role manipulation" in label.lower():
                        # Apply context-aware detection (like credentials)
                        if (is_question or is_config) and not is_disclosure:
                            warnings.append(f"[{self.security_level.value.upper()}] Question about jailbreak/security detected (allowed): {label} (confidence: {score:.2f})")
                        else:
                            # Block jailbreak at ALL security levels when threshold exceeded
                            blocked_patterns.append("jailbreak_attempt")
                            warnings.append(f"[{self.security_level.value.upper()}] Jailbreak attempt detected: {label} (confidence: {score:.2f})")
                    
                    elif "urgent" in label.lower() or "manipulative" in label.lower():
                        blocked_patterns.append("manipulation_attempt")
                        warnings.append(f"[{self.security_level.value.upper()}] Manipulation detected: {label} (confidence: {score:.2f})")
                
                else:
                    # Above detection threshold but below blocking threshold - warn only
                    warnings.append(f"[{self.security_level.value.upper()}] Potential security issue: {label} (confidence: {score:.2f})")
        
        return warnings, blocked_patterns
    
    def _calculate_confidence(self, main_classification: Dict, detailed_classifications: Dict) -> float:
        """Calculate overall confidence in the security assessment"""
        safe_scores = [score for label, score in zip(main_classification['labels'], main_classification['scores']) 
                      if label == "normal safe content"]
        
        if safe_scores:
            base_confidence = safe_scores[0]
        else:
            base_confidence = 0.5
        
        threat_scores = [score for label, score in zip(main_classification['labels'], main_classification['scores']) 
                        if label != "normal safe content" and score > 0.6]
        
        if threat_scores:
            max_threat_confidence = max(threat_scores)
            adjusted_confidence = base_confidence * (1 - max_threat_confidence * 0.5)
        else:
            adjusted_confidence = base_confidence
        
        return max(0.0, min(1.0, adjusted_confidence))
