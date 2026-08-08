Welcome to the Conduit workspace
Anything placed under this workspace/ directory is reachable through Conduit's file tools. read_file, write_file, list_directory, and search_files all resolve paths relative to this folder, and refuse to touch anything outside it — try asking for ../../etc/passwd and it will be rejected before the filesystem is ever touched.
A few things worth trying once Conduit is connected to an agent:
"List everything in the workspace"
"Search the workspace for 'conduit'"
"Run the summarize_workspace_file command on notes/welcome.md"
"Look up the anthropics/mcp repo on GitHub and run repo_health_check on it"