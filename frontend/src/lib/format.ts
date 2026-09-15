/** Small presentation helpers shared across components. */

/** Turn a snake-cased category into a readable label: `Restrictive covenant`. */
export function humaniseCategory(category: string): string {
  const spaced = category.replace(/_/g, ' ');
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}
