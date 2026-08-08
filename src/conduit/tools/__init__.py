"""Tool implementations for Conduit, kept independent of the MCP SDK.

Each module here is plain Python — classes and functions with no import of
`mcp` anywhere. `conduit.server` is the only module that binds them to MCP
tool/prompt/resource decorators. That split means every tool is unit-testable
with a normal pytest fixture, no MCP client or protocol machinery required.
"""
