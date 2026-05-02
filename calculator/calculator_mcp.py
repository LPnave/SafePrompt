"""
Calculator MCP Server
A simple MCP server providing basic mathematical calculation functions.
"""

import math
from typing import Dict
import uvicorn
from fastmcp import FastMCP, Context
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

# Initialize MCP server
mcp = FastMCP(name="Calculator")

# CORS middleware for browser-based clients (e.g., MCP Inspector)
middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=[
            "mcp-protocol-version",
            "mcp-session-id",
            "Authorization",
            "Content-Type",
        ],
        expose_headers=["mcp-session-id"],
    )
]

app = mcp.http_app(middleware=middleware)

@mcp.tool()
async def add(a: float, b: float, ctx: Context) -> Dict[str, float]:
    """
    Add two numbers together.
    
    Args:
        a: First number
        b: Second number
        ctx: FastMCP context for logging
    
    Returns:
        Dictionary with the result
    """
    result = a + b
    if ctx:
        await ctx.info(f"Adding {a} + {b} = {result}")
    return {"result": result}


@mcp.tool()
async def subtract(a: float, b: float, ctx: Context) -> Dict[str, float]:
    """
    Subtract second number from first number.
    
    Args:
        a: First number (minuend)
        b: Second number (subtrahend)
        ctx: FastMCP context for logging
    
    Returns:
        Dictionary with the result
    """
    result = a - b
    if ctx:
        await ctx.info(f"Subtracting {a} - {b} = {result}")
    return {"result": result}


@mcp.tool()
async def multiply(a: float, b: float, ctx: Context) -> Dict[str, float]:
    """
    Multiply two numbers together.
    
    Args:
        a: First number
        b: Second number
        ctx: FastMCP context for logging
    
    Returns:
        Dictionary with the result
    """
    result = a * b
    if ctx:
        await ctx.info(f"Multiplying {a} × {b} = {result}")
    return {"result": result}


@mcp.tool()
async def divide(a: float, b: float, ctx: Context) -> Dict[str, float]:
    """
    Divide first number by second number.
    
    Args:
        a: Numerator
        b: Denominator
        ctx: FastMCP context for logging
    
    Returns:
        Dictionary with the result or error message
    """
    if b == 0:
        if ctx:
            await ctx.error("Division by zero attempted")
        return {"error": "Cannot divide by zero"}
    
    result = a / b
    if ctx:
        await ctx.info(f"Dividing {a} ÷ {b} = {result}")
    return {"result": result}


@mcp.tool()
async def power(base: float, exponent: float, ctx: Context) -> Dict[str, float]:
    """
    Raise a number to a power.
    
    Args:
        base: The base number
        exponent: The exponent
        ctx: FastMCP context for logging
    
    Returns:
        Dictionary with the result
    """
    result = base ** exponent
    if ctx:
        await ctx.info(f"Calculating {base}^{exponent} = {result}")
    return {"result": result}


@mcp.tool()
async def square_root(number: float, ctx: Context) -> Dict[str, float]:
    """
    Calculate the square root of a number.
    
    Args:
        number: The number to find the square root of
        ctx: FastMCP context for logging
    
    Returns:
        Dictionary with the result or error message
    """
    if number < 0:
        if ctx:
            await ctx.error(f"Cannot calculate square root of negative number: {number}")
        return {"error": "Cannot calculate square root of negative number"}
    
    result = math.sqrt(number)
    if ctx:
        await ctx.info(f"Square root of {number} = {result}")
    return {"result": result}


@mcp.tool()
async def modulo(a: float, b: float, ctx: Context) -> Dict[str, float]:
    """
    Calculate the remainder of division (modulo operation).
    
    Args:
        a: Dividend
        b: Divisor
        ctx: FastMCP context for logging
    
    Returns:
        Dictionary with the result or error message
    """
    if b == 0:
        if ctx:
            await ctx.error("Modulo by zero attempted")
        return {"error": "Cannot perform modulo with zero divisor"}
    
    result = a % b
    if ctx:
        await ctx.info(f"Calculating {a} mod {b} = {result}")
    return {"result": result}


@mcp.tool()
async def absolute(number: float, ctx: Context) -> Dict[str, float]:
    """
    Calculate the absolute value of a number.
    
    Args:
        number: The number
        ctx: FastMCP context for logging
    
    Returns:
        Dictionary with the result
    """
    result = abs(number)
    if ctx:
        await ctx.info(f"Absolute value of {number} = {result}")
    return {"result": result}


@mcp.tool()
async def factorial(n: int, ctx: Context) -> Dict:
    """
    Calculate the factorial of a non-negative integer.
    
    Args:
        n: Non-negative integer
        ctx: FastMCP context for logging
    
    Returns:
        Dictionary with the result or error message
    """
    if n < 0:
        if ctx:
            await ctx.error(f"Cannot calculate factorial of negative number: {n}")
        return {"error": "Factorial is only defined for non-negative integers"}
    
    if n > 170:
        if ctx:
            await ctx.error(f"Factorial of {n} is too large to compute")
        return {"error": "Number too large (max 170)"}
    
    result = math.factorial(n)
    if ctx:
        await ctx.info(f"Factorial of {n} = {result}")
    return {"result": result}


@mcp.tool()
async def percentage(value: float, percentage: float, ctx: Context) -> Dict[str, float]:
    """
    Calculate a percentage of a value.
    
    Args:
        value: The base value
        percentage: The percentage (e.g., 20 for 20%)
        ctx: FastMCP context for logging
    
    Returns:
        Dictionary with the result
    """
    result = (value * percentage) / 100
    if ctx:
        await ctx.info(f"Calculating {percentage}% of {value} = {result}")
    return {"result": result}


@mcp.tool()
async def round_number(number: float, decimals: int = 2, ctx: Context = None) -> Dict[str, float]:
    """
    Round a number to a specified number of decimal places.
    
    Args:
        number: The number to round
        decimals: Number of decimal places (default: 2)
        ctx: FastMCP context for logging
    
    Returns:
        Dictionary with the result
    """
    result = round(number, decimals)
    if ctx:
        await ctx.info(f"Rounding {number} to {decimals} decimal places = {result}")
    return {"result": result}


def main():
    """Run the calculator MCP server with streamable HTTP transport and CORS support"""
    uvicorn.run(app, host="0.0.0.0", port=8003)

if __name__ == "__main__":
    main()
