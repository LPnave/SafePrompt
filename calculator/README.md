# Calculator MCP Server

A simple Model Context Protocol (MCP) server providing basic mathematical calculation functions.

## Features

This calculator MCP provides the following operations:

- **add**: Add two numbers
- **subtract**: Subtract two numbers
- **multiply**: Multiply two numbers
- **divide**: Divide two numbers (with zero-division handling)
- **power**: Raise a number to a power
- **square_root**: Calculate square root (with negative number handling)
- **modulo**: Calculate remainder of division
- **absolute**: Get absolute value
- **factorial**: Calculate factorial of non-negative integers
- **percentage**: Calculate percentage of a value
- **round_number**: Round a number to specified decimal places

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Running the Server

```bash
python calculator_mcp.py
```

### Available Tools

#### Basic Operations

- `add(a: float, b: float)` - Returns the sum of two numbers
- `subtract(a: float, b: float)` - Returns the difference (a - b)
- `multiply(a: float, b: float)` - Returns the product
- `divide(a: float, b: float)` - Returns the quotient (handles division by zero)

#### Advanced Operations

- `power(base: float, exponent: float)` - Returns base^exponent
- `square_root(number: float)` - Returns the square root (handles negative numbers)
- `modulo(a: float, b: float)` - Returns a mod b (handles zero divisor)
- `absolute(number: float)` - Returns the absolute value
- `factorial(n: int)` - Returns n! (handles negative and large numbers)

#### Utility Functions

- `percentage(value: float, percentage: float)` - Returns percentage of value
- `round_number(number: float, decimals: int)` - Rounds to specified decimal places

## Examples

### Using with an AI Assistant

Once connected to an MCP-compatible client, you can use natural language:

- "Add 45 and 67"
- "What's 12.5 times 8?"
- "Calculate the square root of 144"
- "What's 20% of 500?"
- "Round 3.14159 to 2 decimal places"

## Error Handling

The calculator includes proper error handling for:

- Division by zero
- Square root of negative numbers
- Modulo with zero divisor
- Factorial of negative numbers
- Factorial of very large numbers (> 170)

All errors return a dictionary with an `"error"` key containing a descriptive message.

## Integration with Cursor/Claude

To use this MCP server with Cursor or Claude:

1. Add to your MCP settings configuration:
```json
{
  "mcpServers": {
    "calculator": {
      "command": "python",
      "args": ["path/to/calculator/calculator_mcp.py"]
    }
  }
}
```

2. Restart your IDE/client to load the MCP server

3. The calculator tools will be available to the AI assistant

## Development

The server is built using FastMCP, which provides:
- Automatic tool registration
- Context-aware logging
- Type hints and validation
- Easy async/await support

## License

This calculator MCP is part of the SecureMCP project.
