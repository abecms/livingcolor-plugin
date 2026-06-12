export const LINK_PROJECTS_VARIABLE = "link-projects";

export function resolveWorkflowVariable(name: string): string {
  if (name === LINK_PROJECTS_VARIABLE) {
    return "resolved-link";
  }
  throw new Error(`No variable exists with name: ${name}`);
}
