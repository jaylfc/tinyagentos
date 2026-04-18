export function slugifyClient(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 63);
}

export const SLUG_REGEX = /^[a-z0-9][a-z0-9-]{0,62}$/;

export function isValidSlug(s: string): boolean {
  return SLUG_REGEX.test(s);
}
