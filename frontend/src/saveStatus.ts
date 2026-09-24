export interface ReprocessSaveStatusPayload {
  outputs: Array<{ beam: string; output_path: string }>;
}

export function reprocessSaveStatusText(saved: ReprocessSaveStatusPayload): string {
  if (saved.outputs.length === 1) {
    return `Saved ${fileName(saved.outputs[0].output_path)}`;
  }
  return `Saved ${saved.outputs.length.toLocaleString()} GeoPackages`;
}

function fileName(path: string): string {
  return path.split(/[\\/]/).pop() || path;
}
