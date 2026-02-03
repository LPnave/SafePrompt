"""
API Routes for the sanitization service
"""

import time
import httpx
import json
from typing import List
from fastapi import APIRouter, HTTPException, status, Request as FastAPIRequest
from fastapi.responses import StreamingResponse

from app.api.models import (
    SanitizeRequest, SanitizeResponse,
    BatchSanitizeRequest, BatchSanitizeResponse,
    SecurityLevelUpdate, SecurityLevelResponse,
    HealthResponse, StatsResponse,
    ChatRequest, ChatResponse, ChatMessage
)
from app.core.config import SecurityLevel, settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter()

# Global validator instance (will be set by main.py)
validator = None
start_time = time.time()
request_count = 0
total_processing_time = 0.0


def set_validator(val):
    """Set the global validator instance"""
    global validator
    validator = val


@router.post("/api/sanitize", response_model=SanitizeResponse)
async def sanitize_prompt(request: SanitizeRequest):
    """
    Sanitize a single prompt for security threats
    
    Args:
        request: SanitizeRequest with prompt and options
    
    Returns:
        SanitizeResponse with sanitization results
    """
    global request_count, total_processing_time
    
    logger.info(f"Received sanitize request: prompt_length={len(request.prompt)}, security_level={request.security_level}")
    
    if validator is None:
        logger.error("Validator is None - not initialized!")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Security validator not initialized"
        )
    
    try:
        # Update security level if provided
        if request.security_level:
            try:
                validator.security_level = SecurityLevel(request.security_level.lower())
                validator._configure_security_thresholds()  # Reconfigure thresholds for new level
                logger.debug(f"Security level set to: {request.security_level}")
            except ValueError:
                logger.error(f"Invalid security level: {request.security_level}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid security level: {request.security_level}"
                )
        
        # Validate the prompt
        logger.debug("Calling validator.validate_prompt...")
        result = validator.validate_prompt(request.prompt)
        logger.debug(f"Validation result: is_safe={result.is_safe}, confidence={result.confidence}")
        
        # Update stats
        request_count += 1
        total_processing_time += result.processing_time_ms
        
        # Build response
        sanitization_details = None
        if request.return_details:
            sanitization_details = {
                "classifications": result.classifications,
                "sanitization_applied": result.sanitization_applied
            }
        
        return SanitizeResponse(
            is_safe=result.is_safe,
            sanitized_prompt=result.modified_prompt,
            original_prompt=request.prompt,
            warnings=result.warnings,
            blocked_patterns=result.blocked_patterns,
            confidence=result.confidence,
            modifications_made=request.prompt != result.modified_prompt,
            sanitization_details=sanitization_details,
            processing_time_ms=result.processing_time_ms
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sanitizing prompt: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing prompt: {str(e)}"
        )


@router.post("/api/sanitize/batch", response_model=BatchSanitizeResponse)
async def sanitize_batch(request: BatchSanitizeRequest):
    """
    Sanitize multiple prompts in batch
    
    Args:
        request: BatchSanitizeRequest with list of prompts
    
    Returns:
        BatchSanitizeResponse with all results
    """
    if validator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Security validator not initialized"
        )
    
    try:
        start = time.time()
        results = []
        
        # Update security level if provided
        if request.security_level:
            try:
                validator.security_level = SecurityLevel(request.security_level.lower())
                validator._configure_security_thresholds()  # Reconfigure thresholds for new level
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid security level: {request.security_level}"
                )
        
        # Process each prompt
        for prompt in request.prompts:
            result = validator.validate_prompt(prompt)
            
            sanitization_details = None
            if request.return_details:
                sanitization_details = {
                    "classifications": result.classifications,
                    "sanitization_applied": result.sanitization_applied
                }
            
            results.append(SanitizeResponse(
                is_safe=result.is_safe,
                sanitized_prompt=result.modified_prompt,
                original_prompt=prompt,
                warnings=result.warnings,
                blocked_patterns=result.blocked_patterns,
                confidence=result.confidence,
                modifications_made=prompt != result.modified_prompt,
                sanitization_details=sanitization_details,
                processing_time_ms=result.processing_time_ms
            ))
        
        total_time = (time.time() - start) * 1000
        
        return BatchSanitizeResponse(
            results=results,
            total_processed=len(request.prompts),
            total_time_ms=total_time
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in batch sanitization: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing batch: {str(e)}"
        )


@router.post("/api/chat", response_model=ChatResponse)
async def chat(raw_request: FastAPIRequest):
    """
    Chat endpoint with sanitization and local GPT-OSS integration
    
    Flow:
    1. Sanitize the last user message
    2. Forward to local GPT-OSS model
    3. Return AI response with sanitization info
    
    Args:
        raw_request: Raw FastAPI Request
    
    Returns:
        ChatResponse with AI message and sanitization info
    """
    if validator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Security validator not initialized"
        )
    
    try:
        # Parse request body
        body = await raw_request.json()
        logger.info(f"Received chat request with body: {json.dumps(body, indent=2)}")
        
        # Transform messages: convert 'parts' array to 'content' string
        if "messages" in body:
            for msg in body["messages"]:
                if "parts" in msg and "content" not in msg:
                    # Extract text from parts array
                    parts = msg.pop("parts")
                    text_parts = []
                    for part in parts:
                        if isinstance(part, dict) and "text" in part:
                            text_parts.append(part["text"])
                        elif isinstance(part, str):
                            text_parts.append(part)
                    msg["content"] = " ".join(text_parts)
                    logger.debug(f"Converted parts to content: {msg['content'][:100]}...")
        
        # Parse into ChatRequest
        try:
            request = ChatRequest(**body)
        except Exception as e:
            logger.error(f"Failed to parse ChatRequest: {e}")
            logger.error(f"Body was: {body}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid request format: {str(e)}"
            )
        
        # Log incoming request for debugging
        logger.info(f"Chat request parsed successfully with {len(request.messages)} messages")
        for i, msg in enumerate(request.messages):
            logger.debug(f"Message {i}: role={msg.role}, content_length={len(str(msg.content))}")
        
        # Get the last user message
        last_message = None
        for msg in reversed(request.messages):
            if msg.role == "user":
                last_message = msg
                break
        
        if not last_message:
            logger.error("No user message found in request")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No user message found in request"
            )
        
        # Update security level if provided
        if request.security_level:
            try:
                validator.security_level = SecurityLevel(request.security_level.lower())
                validator._configure_security_thresholds()  # Reconfigure thresholds for new level
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid security level: {request.security_level}"
                )
        
        # Sanitize the last user message
        # Handle content that might be string or array
        original_content = last_message.content
        if isinstance(original_content, list):
            # If content is an array, join text parts
            original_content = " ".join([
                part.get("text", str(part)) if isinstance(part, dict) else str(part)
                for part in original_content
            ])
        else:
            original_content = str(original_content)
        
        logger.info(f"Sanitizing user message: {original_content[:100]}...")
        
        validation_result = validator.validate_prompt(original_content)
        
        # Check if prompt should be blocked (only if block_mode is enabled)
        # At LOW level (block_mode=False), threats are detected but not blocked
        if validator.block_mode and not validation_result.is_safe and validation_result.blocked_patterns:
            logger.warning(f"Prompt blocked: {validation_result.blocked_patterns}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Prompt blocked due to security concerns: {', '.join(validation_result.warnings)}"
            )
        elif not validator.block_mode and validation_result.blocked_patterns:
            logger.info(f"Threats detected but allowed (LOW level): {validation_result.blocked_patterns}")
        
        # Use sanitized prompt
        sanitized_content = validation_result.modified_prompt
        sanitization_applied = original_content != sanitized_content
        
        if sanitization_applied:
            logger.info("Prompt was sanitized, using modified version")
        
        # Prepare messages for GPT-OSS (use sanitized content for last message)
        gpt_messages = []
        for msg in request.messages:
            if msg == last_message:
                # Use sanitized version
                gpt_messages.append({
                    "role": msg.role,
                    "content": sanitized_content
                })
            else:
                # Convert content to string if it's not already
                msg_content = msg.content
                if isinstance(msg_content, list):
                    msg_content = " ".join([
                        part.get("text", str(part)) if isinstance(part, dict) else str(part)
                        for part in msg_content
                    ])
                else:
                    msg_content = str(msg_content)
                
                gpt_messages.append({
                    "role": msg.role,
                    "content": msg_content
                })
        
        # Call Google Gemini API
        if not settings.GEMINI_API_KEY:
            logger.error("GEMINI_API_KEY not configured")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Gemini API key not configured. Please set GEMINI_API_KEY in .env file"
            )
        
        logger.info(f"Calling Google Gemini ({settings.GEMINI_MODEL})")
        
        # Convert messages to Gemini format
        gemini_contents = []
        for msg in gpt_messages:
            gemini_contents.append({
                "role": "user" if msg["role"] == "user" else "model",
                "parts": [{"text": msg["content"]}]
            })
        
        # Log what's being sent to Gemini
        logger.info("=" * 60)
        logger.info("SENDING TO GEMINI:")
        for i, msg in enumerate(gemini_contents):
            logger.info(f"Message {i+1} [{msg['role']}]: {msg['parts'][0]['text'][:200]}...")
        logger.info("=" * 60)
        
        # Gemini API endpoint
        gemini_url = f"{settings.GEMINI_API_URL}/{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
        logger.info(f"Calling Gemini URL: {gemini_url[:100]}...")
        
        # Increase timeout for Gemini 2.5 Flash (can be slower)
        async with httpx.AsyncClient(timeout=90.0) as client:
            try:
                response = await client.post(
                    gemini_url,
                    json={
                        "contents": gemini_contents,
                        "generationConfig": {
                            "temperature": 0.7,
                            "maxOutputTokens": 5000,
                        }
                    }
                )
                
                if response.status_code != 200:
                    logger.error(f"Gemini API error: {response.status_code} - {response.text}")
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"Error from Gemini API: {response.text}"
                    )
                
                gemini_response = response.json()
                logger.info("Gemini response received")
            except httpx.TimeoutException as e:
                logger.error(f"Gemini API timeout after 90s: {str(e)}")
                logger.error(f"URL was: {gemini_url[:100]}...")
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail=f"Gemini API timeout (90s). Try: 1) Check internet connection 2) Verify model name '{settings.GEMINI_MODEL}' is correct 3) Check API key is valid"
                )
            except httpx.ConnectError as e:
                logger.error(f"Cannot connect to Gemini API: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Cannot connect to Gemini API. Check your internet connection."
                )
        
        # Extract AI message from Gemini response
        try:
            ai_message_content = gemini_response["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as e:
            logger.error(f"Failed to parse Gemini response: {e}")
            logger.error(f"Response was: {gemini_response}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Invalid response format from Gemini API"
            )
        
        logger.info(f"Streaming response back to client, length: {len(ai_message_content)}")
        
        # Create data stream protocol response
        async def generate_data_stream():
            """Generate data stream protocol format for assistant-ui"""
            
            # First, send sanitization info if the prompt was sanitized
            if sanitization_applied:
                sanitization_data = {
                    "type": "sanitization",
                    "original": original_content,
                    "sanitized": sanitized_content,
                    "warnings": validation_result.warnings
                }
                # Send as metadata annotation: 8:{"type":"sanitization",...}\n
                yield f'8:{json.dumps([sanitization_data])}\n'
                logger.info("Sent sanitization metadata to frontend")
            
            # Stream text in chunks (data stream protocol format)
            chunk_size = 5  # Small chunks for smooth streaming
            for i in range(0, len(ai_message_content), chunk_size):
                chunk = ai_message_content[i:i + chunk_size]
                # Format: 0:"text chunk"\n
                yield f'0:{json.dumps(chunk)}\n'
            
            # Send finish message
            # Format: d:{"finishReason":"stop"}\n
            finish_data = {
                "finishReason": "stop",
                "usage": {
                    "promptTokens": 0,
                    "completionTokens": len(ai_message_content)
                }
            }
            yield f'd:{json.dumps(finish_data)}\n'
            
            logger.info("Data stream completed")
        
        return StreamingResponse(
            generate_data_stream(),
            media_type="text/plain; charset=utf-8",
            headers={
                "X-Sanitization-Applied": str(sanitization_applied).lower(),
                "X-Warnings": json.dumps(validation_result.warnings),
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing chat: {str(e)}"
        )


@router.get("/api/security/level", response_model=SecurityLevelResponse)
async def get_security_level():
    """
    Get the current security level
    
    Returns:
        SecurityLevelResponse with current level
    """
    if validator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Security validator not initialized"
        )
    
    return SecurityLevelResponse(
        level=validator.security_level.value,
        success=True,
        message=f"Current security level is {validator.security_level.value}"
    )


@router.put("/api/security/level", response_model=SecurityLevelResponse)
async def update_security_level(request: SecurityLevelUpdate):
    """
    Update the security level
    
    Args:
        request: SecurityLevelUpdate with new level
    
    Returns:
        SecurityLevelResponse with updated level
    """
    if validator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Security validator not initialized"
        )
    
    try:
        new_level = SecurityLevel(request.level.lower())
        validator.security_level = new_level
        validator._configure_security_thresholds()  # Reconfigure thresholds for new level
        logger.info(f"Security level updated to: {new_level.value}")
        
        return SecurityLevelResponse(
            level=new_level.value,
            success=True,
            message=f"Security level updated to {new_level.value}"
        )
    
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid security level: {request.level}. Valid options: low, medium, high"
        )


@router.get("/api/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint
    
    Returns:
        HealthResponse with system status
    """
    uptime = time.time() - start_time
    
    return HealthResponse(
        status="healthy" if validator is not None else "unhealthy",
        model_loaded=validator is not None,
        uptime_seconds=uptime,
        version="1.0.0"
    )


@router.get("/api/stats", response_model=StatsResponse)
async def get_stats():
    """
    Get system statistics
    
    Returns:
        StatsResponse with performance metrics
    """
    if validator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Security validator not initialized"
        )
    
    import torch
    
    avg_latency = (total_processing_time / request_count) if request_count > 0 else 0
    
    return StatsResponse(
        security_level=validator.security_level.value,
        model_info={
            "model_name": "facebook/bart-large-mnli",
            "model_type": "zero-shot-classification",
            "device": "cuda" if torch.cuda.is_available() else "cpu",
            "spacy_model": "en_core_web_sm"
        },
        request_stats={
            "total_requests": request_count,
            "average_latency_ms": round(avg_latency, 2),
            "total_processing_time_ms": round(total_processing_time, 2),
            "uptime_seconds": round(time.time() - start_time, 2)
        },
        capabilities=[
            "Zero-shot classification",
            "Multi-label threat detection",
            "Contextual understanding",
            "Automatic sanitization",
            "Confidence scoring",
            "Detailed threat analysis",
            "Pattern matching (spaCy)",
            "Entropy-based detection"
        ]
    )
