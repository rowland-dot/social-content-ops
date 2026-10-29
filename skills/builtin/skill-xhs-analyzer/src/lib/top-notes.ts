/**
 * How the analyzer ranks posts: likes plus favourites together is a post's total impression score
 * (The owner, 2026-10-28). Lives in its own file (not cli.ts, which runs the program as soon as it is
 * imported) so a test can import it.
 */

export function likesPlusFavourites(note: { likes: number; collects: number }): number {
  return note.likes + note.collects;
}

/** The top post by likes + favourites; "totalEngagement" (likes + comments + favourites + shares) is the separate, named measure. */
export function topReportNote<
  T extends { likes: number; collects: number; totalEngagement: number }
>(
  notes: T[],
  measure: "likesPlusFavourites" | "totalEngagement" = "likesPlusFavourites"
): T | null {
  if (notes.length === 0) return null;
  const score = (note: T) =>
    measure === "totalEngagement" ? note.totalEngagement : likesPlusFavourites(note);
  return notes.reduce((best, note) => score(note) > score(best) ? note : best, notes[0]);
}
