/** CSV for a spreadsheet: semicolons, a byte order mark for Excel, and no formulas (issue #31). */

// A cell that starts like this could run as a formula; a quote in front keeps it text, as the
// server does for its own exports.
const FORMULA = /^[=+\-@\t\r]/;

export function csvCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  let text = String(value);
  if (typeof value === "string" && FORMULA.test(text)) text = `'${text}`;
  return /[;"\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

export function toCsv(rows: readonly (readonly unknown[])[]): string {
  return "\uFEFF" + rows.map((row) => row.map(csvCell).join(";")).join("\r\n") + "\r\n";
}

export function downloadCsv(fileName: string, content: string): void {
  const url = URL.createObjectURL(new Blob([content], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
