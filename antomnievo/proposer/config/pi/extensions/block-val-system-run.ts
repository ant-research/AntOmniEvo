/**
 * Prevent the proposer agent from accessing validation set trajectories.
 *
 * The val_system_run directory stores run traces on the validation set,
 * used only for offline evaluation. The proposer must not read these
 * during optimization to avoid overfitting to the validation set.
 */
// Types inlined to avoid module resolution issues in standalone extension files.
// At runtime, PI's jiti loader provides the actual module.
interface ToolCallEvent {
  toolName: string;
  input: Record<string, unknown>;
}

interface ExtensionAPI {
  on(event: "tool_call", handler: (event: ToolCallEvent) => { block: boolean; reason: string } | undefined | void): void;
}

export default function (pi: ExtensionAPI) {
  const BLOCKED_PATTERN = /val_system_run/;

  pi.on("tool_call", (event: ToolCallEvent) => {
    let pathToCheck: string | undefined;

    switch (event.toolName) {
      case "read":
        
      case "write":
      case "edit":
        pathToCheck = (event.input as any).file_path ?? (event.input as any).path;
        break;
      case "bash":
        pathToCheck = (event.input as any).command;
        break;
      case "grep":
        pathToCheck = (event.input as any).path ?? (event.input as any).directory;
        break;
      case "find":
      case "ls":
        pathToCheck = (event.input as any).path ?? (event.input as any).directory;
        break;
    }

    if (pathToCheck && BLOCKED_PATTERN.test(pathToCheck)) {
      return {
        block: true,
        reason: "Access to val_system_run is not allowed. This directory contains validation set data that must not be used during optimization.",
      };
    }
  });
}
