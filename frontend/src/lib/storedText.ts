import { serverText } from "./serverText";

/**
 * A message the server stored next to its code, such as a message about an import (ADR-0025).
 *
 * Since OAK keeps the values of a message with it, the message is shown in the chosen language.
 * A message stored before that has no data. Its code does not always say which sentence it was,
 * so then the stored Dutch text is shown as it is.
 */
export function storedText(
  group: string,
  code: string | null | undefined,
  message: string | null | undefined,
  data: Record<string, unknown> | null | undefined,
): string {
  if (!message) return "";
  return serverText(group, code && data ? { code, text: message, data } : message);
}
