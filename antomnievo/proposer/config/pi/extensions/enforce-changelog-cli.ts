/**
 * Prevent the proposer/mutation agent from writing to changelog.jsonl directly.
 *
 * The agent MUST use the `append-changelog` CLI tool to record changes,
 * which ensures proper JSONL formatting (one JSON object per line with
 * required fields like diff, files_modified, timestamp). Direct writes
 * to changelog.jsonl have produced malformed entries (e.g. multiple JSON
 * objects concatenated on the same line), breaking downstream parsing.
 */
// Types inlined to avoid module resolution issues in standalone extension files.
interface ToolCallEvent {
  toolName: string;
  input: Record<string, unknown>;
}

interface ToolResultEvent {
  toolName: string;
  input: Record<string, unknown>;
  content: Array<{ type: string; text?: string }>;
}

interface ExtensionAPI {
  on(event: "tool_call", handler: (event: ToolCallEvent) => { block: boolean; reason: string } | undefined | void): void;
  on(event: "tool_result", handler: (event: ToolResultEvent) => { content?: Array<{ type: string; text?: string }>; isError?: boolean } | undefined | void): void;
}

export default function (pi: ExtensionAPI) {
  const CHANGELOG_PATTERN = /changelog\.jsonl/;

  pi.on("tool_call", (event: ToolCallEvent) => {
    if (event.toolName === "write" || event.toolName === "edit") {
      const filePath = (event.input as any).file_path ?? (event.input as any).path ?? "";
      if (CHANGELOG_PATTERN.test(filePath)) {
        return {
          block: true,
          reason:
            "Direct writes to changelog.jsonl are not allowed. " +
            "Use the `append-changelog` CLI tool instead:\n\n" +
            "  append-changelog <parent_spec_dir> <new_spec_dir> <new_data_dir>/changelog.jsonl --type <type> --subject '<subject>' --body - << 'CHANGELOG_EOF'\n" +
            "  <your body text here>\n" +
            "  CHANGELOG_EOF\n\n" +
            "This ensures proper JSONL formatting with required fields (diff, files_modified, timestamp).",
        };
      }
    }

    if (event.toolName === "bash") {
      const command = (event.input as any).command ?? "";
      // Block shell commands that write to changelog.jsonl via redirection or tee
      const redirectPattern = /changelog\.jsonl\s*(>>?>|<<<|\|)/;
      const teePattern = /\btee\b.*changelog\.jsonl/;
      if (CHANGELOG_PATTERN.test(command) && (redirectPattern.test(command) || teePattern.test(command))) {
        return {
          block: true,
          reason:
            "Redirecting output to changelog.jsonl is not allowed. " +
            "Use the `append-changelog` CLI tool instead:\n\n" +
            "  append-changelog <parent_spec_dir> <new_spec_dir> <new_data_dir>/changelog.jsonl --type <type> --subject '<subject>' --body - << 'CHANGELOG_EOF'\n" +
            "  <your body text here>\n" +
            "  CHANGELOG_EOF",
        };
      }
    }
  });

  // Also watch for bash commands that cat/echo/write to changelog.jsonl after the fact
  pi.on("tool_result", (event: ToolResultEvent) => {
    if (event.toolName === "bash" && CHANGELOG_PATTERN.test(JSON.stringify(event.input))) {
      // Log a warning but don't block — the tool_call handler should catch direct writes
    }
  });
}