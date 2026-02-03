# SecureMCP Validation Flow - Class/Method Reference

## Complete Validation Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ENTRY POINT: validate_prompt()                            │
│              ZeroShotSecurityValidator.validate_prompt()                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    STEP 1: Context Analysis (Upfront)                       │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ ZeroShotSecurityValidator._is_asking_question(prompt)                │ │
│  │ ZeroShotSecurityValidator._is_configuration_question(prompt)         │ │
│  │ ZeroShotSecurityValidator._is_disclosing_information(prompt)         │ │
│  │                                                                        │ │
│  │ Returns: is_question, is_config, is_disclosure                       │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              PHASE A: Specialized ML Models (Context-Aware)                  │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │ 1. Injection Detection                                              │ │
│  │    ZeroShotSecurityValidator._check_specialized_injection(prompt)  │ │
│  │    ├─ Uses: protectai/deberta-v3-base-prompt-injection             │ │
│  │    ├─ Context Check: if (is_question or is_config) and not         │ │
│  │    │                is_disclosure → Allow                           │ │
│  │    └─ If threat: ZeroShotSecurityValidator._sanitize_injection_    │ │
│  │                   attempts(modified_prompt)                          │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │ 2. PII Detection                                                    │ │
│  │    ZeroShotSecurityValidator._check_specialized_pii(prompt)        │ │
│  │    ├─ Uses: SoelMgd/bert-pii-detection (NER model)                 │ │
│  │    ├─ Adaptive Threshold Logic:                                     │ │
│  │    │   - Multiple entities (≥2) → threshold = 0.5                  │ │
│  │    │   - Disclosure context → threshold = 0.5                      │ │
│  │    │   - Otherwise → threshold = 0.6                               │ │
│  │    ├─ ZeroShotSecurityValidator._is_disclosing_pii(prompt)         │ │
│  │    ├─ Context Check: if (is_question or is_config) and not         │ │
│  │    │                is_disclosure → Allow                           │ │
│  │    └─ If PII found: Masks entities inline (returns sanitized)       │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │ 3. Malicious Code Detection                                         │ │
│  │    ZeroShotSecurityValidator._check_specialized_malicious(prompt)  │ │
│  │    ├─ Uses: microsoft/codebert-base                                │ │
│  │    ├─ Code Pattern Pre-check (rm, del, DROP, exec, etc.)           │ │
│  │    ├─ Context Check: if is_question and not is_disclosure and      │ │
│  │    │                not is_code_gen_request → Allow                 │ │
│  │    └─ If threat: ZeroShotSecurityValidator._sanitize_malicious_   │ │
│  │                   content(modified_prompt)                          │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │ 4. Jailbreak Detection (ALWAYS BLOCKS)                              │ │
│  │    ZeroShotSecurityValidator._check_specialized_jailbreak(prompt)  │ │
│  │    ├─ Enhanced pattern matching + confidence scoring                │ │
│  │    ├─ NO CONTEXT-AWARENESS (always blocks)                          │ │
│  │    └─ If detected: ZeroShotSecurityValidator._sanitize_jailbreak_ │ │
│  │                     attempts(modified_prompt)                        │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              PHASE B: Zero-Shot Classification (BART-MNLI)                 │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ ZeroShotSecurityValidator._classify_security_threats(prompt)        │ │
│  │ ├─ Uses: facebook/bart-large-mnli (or DistilBERT fallback)        │ │
│  │ ├─ Categories: credentials, PII, injection, malicious, jailbreak  │ │
│  │ └─ Returns: main_classification dict with labels and scores         │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │ Detailed Classification (for high-confidence threats)              │ │
│  │ ZeroShotSecurityValidator._detailed_classification(prompt, category)│ │
│  │ └─ Sub-category analysis for specific threat types                  │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              PHASE C: Pattern-Based Detection (spaCy + Regex)              │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ ZeroShotSecurityValidator._detect_spacy_patterns(prompt)           │ │
│  │ ├─ Uses: spaCy Matcher with linguistic patterns                     │ │
│  │ ├─ Detects: credential disclosure patterns                          │ │
│  │ └─ Returns: dict of detected patterns by type                      │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │ ZeroShotSecurityValidator._apply_spacy_sanitization(                │ │
│  │     modified_prompt, spacy_detections)                             │ │
│  │ └─ Applies sanitization based on spaCy pattern matches              │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │ Additional Pattern-Based Sanitization:                             │ │
│  │ ├─ ZeroShotSecurityValidator._sanitize_high_entropy_credentials() │ │
│  │ ├─ ZeroShotSecurityValidator._sanitize_credentials_generic()       │ │
│  │ └─ ZeroShotSecurityValidator._sanitize_credentials()               │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              PHASE D: Classification Processing (Context-Aware)              │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ ZeroShotSecurityValidator._process_classifications(                  │ │
│  │     modified_prompt, main_classification, detailed_classifications) │ │
│  │ ├─ Applies context-awareness to ML classification results           │ │
│  │ ├─ Checks: if (is_question or is_config) and not is_disclosure      │ │
│  │ ├─ Applies sanitization based on threat types                        │ │
│  │ └─ Returns: sanitized_prompt, sanitization_dict, blocked_patterns   │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              PHASE E: Sanitization Record Merging                          │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ ZeroShotSecurityValidator._merge_sanitization_records(               │ │
│  │     sanitization_applied, process_sanitization)                      │ │
│  │ └─ Combines sanitization records from all phases                     │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              PHASE F: Security Assessment Generation                        │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ ZeroShotSecurityValidator._generate_security_assessment(             │ │
│  │     main_classification, detailed_classifications)                   │ │
│  │ ├─ Applies context-awareness: if (is_question or is_config) and     │ │
│  │ │                                not is_disclosure → Allow           │ │
│  │ ├─ Generates human-readable warnings                                 │ │
│  │ ├─ Determines blocked_patterns from ML results                       │ │
│  │ └─ Returns: warnings list, ml_blocked_patterns list                 │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              PHASE G: Final Assessment                                      │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ ZeroShotSecurityValidator._calculate_confidence(                     │ │
│  │     main_classification, detailed_classifications)                   │ │
│  │ └─ Calculates overall confidence score                               │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │ Final Decision Logic:                                                │ │
│  │ ├─ Merge all blocked_patterns (Phase A + pattern + ML)             │ │
│  │ ├─ is_safe = len(blocked_patterns) == 0                             │ │
│  │ ├─ Check block_mode and blocking_threshold                          │ │
│  │ └─ Return ValidationResult object                                   │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RETURN: ValidationResult                                 │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ ValidationResult(                                                     │ │
│  │     is_safe: bool,                                                    │ │
│  │     modified_prompt: str,                                             │ │
│  │     warnings: List[str],                                              │ │
│  │     blocked_patterns: List[str],                                      │ │
│  │     confidence: float,                                                │ │
│  │     classifications: Dict,                                            │ │
│  │     sanitization_applied: Dict,                                       │ │
│  │     processing_time_ms: float                                          │ │
│  │ )                                                                      │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Key Helper Methods

### Context Detection Methods
- `ZeroShotSecurityValidator._is_asking_question(text: str) -> bool`
  - Detects interrogative patterns, question words, educational verbs
  - Phase 2: Added development tool configuration recognition

- `ZeroShotSecurityValidator._is_configuration_question(text: str) -> bool`
  - Detects developer configuration discussions (ESLint, webpack, Git hooks, etc.)
  - Phase 2 enhancement

- `ZeroShotSecurityValidator._is_disclosing_information(text: str) -> bool`
  - Detects actual credential/PII disclosure patterns
  - Looks for: "my password is", "here's my API key", etc.

- `ZeroShotSecurityValidator._is_disclosing_pii(text: str) -> bool`
  - Specific PII disclosure context detection
  - Used for adaptive threshold adjustment

### Specialized Model Detection Methods
- `ZeroShotSecurityValidator._check_specialized_injection(prompt: str) -> Tuple[bool, float, List[str]]`
  - DeBERTa model for injection detection (95% accuracy)
  - Returns: (is_injection, confidence_score, pattern_list)

- `ZeroShotSecurityValidator._check_specialized_pii(prompt: str) -> Tuple[str, List[Dict], List[str]]`
  - BERT NER model for PII detection (94% F1, 56 entity types)
  - Returns: (sanitized_prompt, pii_entities, pattern_list)
  - Phase 1: Adaptive thresholds based on entity count and disclosure context

- `ZeroShotSecurityValidator._check_specialized_malicious(prompt: str) -> Tuple[bool, float, List[str]]`
  - CodeBERT model for malicious code detection
  - Pre-filters with code pattern indicators

- `ZeroShotSecurityValidator._check_specialized_jailbreak(prompt: str) -> Tuple[bool, float, List[str]]`
  - Enhanced pattern matching + confidence scoring
  - ALWAYS blocks (no context-awareness)

### Classification Methods
- `ZeroShotSecurityValidator._classify_security_threats(text: str) -> Dict`
  - Main zero-shot classification using BART-MNLI
  - Returns classification results with labels and scores

- `ZeroShotSecurityValidator._detailed_classification(text: str, category: str) -> Dict`
  - Sub-category analysis for specific threat types
  - Used when main classification shows high confidence

### Pattern Detection Methods
- `ZeroShotSecurityValidator._detect_spacy_patterns(text: str) -> Dict[str, List[str]]`
  - spaCy Matcher for linguistic credential patterns
  - Returns detected patterns by type

- `ZeroShotSecurityValidator._apply_spacy_sanitization(text: str, detections: Dict) -> Tuple[str, Dict]`
  - Applies sanitization based on spaCy pattern matches

### Sanitization Methods
- `ZeroShotSecurityValidator._sanitize_injection_attempts(text: str) -> Tuple[str, List[str]]`
  - Neutralizes prompt injection patterns
  - Returns: (sanitized_text, masked_items_list)

- `ZeroShotSecurityValidator._sanitize_jailbreak_attempts(text: str) -> Tuple[str, List[str]]`
  - Removes jailbreak manipulation patterns
  - Always applied when jailbreak detected

- `ZeroShotSecurityValidator._sanitize_malicious_content(text: str) -> Tuple[str, List[str]]`
  - Removes dangerous code patterns and URLs

- `ZeroShotSecurityValidator._sanitize_credentials(text: str, credential_type: str) -> Tuple[str, List[str]]`
  - Generic credential sanitization
  - Uses multiple detection methods (entropy, patterns, keywords)

- `ZeroShotSecurityValidator._sanitize_high_entropy_credentials(text: str) -> Tuple[str, List[str]]`
  - Detects random-looking strings (API keys, tokens)
  - Uses Shannon entropy calculation

- `ZeroShotSecurityValidator._sanitize_credentials_generic(text: str) -> Tuple[str, List[str]]`
  - Keyword-based credential detection fallback

### Processing Methods
- `ZeroShotSecurityValidator._process_classifications(prompt: str, main_classification: Dict, detailed_classifications: Dict) -> Tuple[str, Dict, List[str]]`
  - Processes ML classification results with context-awareness
  - Applies sanitization based on threat types
  - Returns: (sanitized_prompt, sanitization_dict, blocked_patterns)

- `ZeroShotSecurityValidator._generate_security_assessment(main_classification: Dict, detailed_classifications: Dict) -> Tuple[List[str], List[str]]`
  - Generates warnings and blocked patterns from ML results
  - Applies context-awareness
  - Returns: (warnings_list, blocked_patterns_list)

- `ZeroShotSecurityValidator._calculate_confidence(main_classification: Dict, detailed_classifications: Dict) -> float`
  - Calculates overall confidence score
  - Adjusts based on threat detections

- `ZeroShotSecurityValidator._merge_sanitization_records(existing: Dict, new: Dict) -> Dict`
  - Combines sanitization records from multiple phases
  - Prevents duplicate entries

## Initialization Flow

```
ZeroShotSecurityValidator.__init__(security_level: SecurityLevel)
    │
    ├─> setup_models()
    │   ├─> Load protectai/deberta-v3-base-prompt-injection
    │   ├─> Load SoelMgd/bert-pii-detection
    │   ├─> Load microsoft/codebert-base
    │   ├─> Load facebook/bart-large-mnli (or DistilBERT fallback)
    │   └─> Configure GPU/CPU device
    │
    ├─> setup_classification_categories()
    │   ├─> Define security_categories (main threat types)
    │   └─> Define detailed_categories (sub-categories)
    │
    ├─> setup_spacy_matcher()
    │   ├─> Load spaCy en_core_web_sm model
    │   └─> Define credential disclosure patterns
    │
    └─> _configure_security_thresholds()
        ├─> Set detection_threshold (0.4-0.7)
        ├─> Set blocking_threshold (0.6-0.95)
        ├─> Set entropy_threshold (3.0-4.2)
        └─> Set block_mode (True/False)
```

## Context-Awareness Decision Logic

The context-awareness pattern used throughout the pipeline:

```python
# Pattern applied in multiple detection phases
if (is_question or is_config) and not is_disclosure:
    # Allow - Educational question or configuration discussion
    logger.debug("Allowed as question/config")
    warnings.append("Question detected (allowed)")
else:
    # Block/Sanitize - Actual threat or disclosure
    blocked_patterns.extend(detected_patterns)
    modified_prompt = sanitize(modified_prompt)
```

**Exception:** Jailbreak detection ALWAYS blocks regardless of context:
```python
# Jailbreak detection (no context check)
if is_jailbreak:
    # Always block - manipulation is dangerous regardless of phrasing
    blocked_patterns.extend(jailbreak_patterns)
    modified_prompt = sanitize_jailbreak(modified_prompt)
```

## Method Call Sequence Summary

1. **Entry**: `validate_prompt(prompt)`
2. **Context Setup**: `_is_asking_question()`, `_is_configuration_question()`, `_is_disclosing_information()`
3. **Phase A - Specialized Models**:
   - `_check_specialized_injection()` → `_sanitize_injection_attempts()` (if threat)
   - `_check_specialized_pii()` → inline masking (if PII found)
   - `_check_specialized_malicious()` → `_sanitize_malicious_content()` (if threat)
   - `_check_specialized_jailbreak()` → `_sanitize_jailbreak_attempts()` (if detected)
4. **Phase B - Zero-Shot Classification**:
   - `_classify_security_threats()` → `_detailed_classification()` (for high-confidence)
5. **Phase C - Pattern Detection**:
   - `_detect_spacy_patterns()` → `_apply_spacy_sanitization()`
   - Additional credential sanitization methods
6. **Phase D - Processing**:
   - `_process_classifications()` (context-aware processing)
7. **Phase E - Merging**:
   - `_merge_sanitization_records()` (combine all sanitization records)
8. **Phase F - Assessment**:
   - `_generate_security_assessment()` (context-aware warnings)
9. **Phase G - Final**:
   - `_calculate_confidence()` → Final `ValidationResult` construction


