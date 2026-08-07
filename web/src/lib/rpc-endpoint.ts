const PATH_KEY_PLACEHOLDER = "{path_key}";
const API_KEY_PLACEHOLDER = "{api_key}";

export function endpointUsesPathKey(value: string): boolean {
  return (
    value.includes(API_KEY_PLACEHOLDER) || value.includes(PATH_KEY_PLACEHOLDER)
  );
}

export function fillPathKeyTemplate(value: string, pathKey: string): string {
  return value
    .replaceAll(API_KEY_PLACEHOLDER, pathKey)
    .replaceAll(PATH_KEY_PLACEHOLDER, pathKey);
}
