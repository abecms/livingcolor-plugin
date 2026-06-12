export async function renderProject(documentId: string, ameNode: string): Promise<string> {
  return `render-${documentId}-${ameNode}`;
}

export async function diagnoseMediaOffline(renderId: string): Promise<string[]> {
  return [`Media offline detected for render ${renderId}`];
}
