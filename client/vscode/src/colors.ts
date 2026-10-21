// A palette tuned to read on both light and dark themes.

export const TOKEN_COLORS: Record<string, string | { foreground?: string; bold?: boolean; italic?: boolean }> = {
  // parts of speech
  noun: "#4E9BDE",
  properNoun: { foreground: "#2F7FD0", bold: true },
  verb: "#E0533D",
  auxiliary: "#C98A80",
  adjective: "#3BA55C",
  adverb: "#8BB33A",
  pronoun: "#3AAFB9",
  determiner: "#998F87",
  adposition: "#A07BD1",
  conjunction: "#D17BB4",
  numeral: "#E08E2B",
  particle: "#998F87",
  interjection: { foreground: "#D9A520", italic: true },
  // sentence roles
  subject: "#2F80ED",
  predicate: "#E0533D",
  object: "#27AE60",
  complement: "#F2994A",
  adjunct: "#9B51E0",
  "*.head": { bold: true },
  // entities
  entityPerson: "#EB5757",
  entityPlace: "#27AE60",
  entityOrg: "#2D9CDB",
  entityTime: "#F2994A",
  entityQuantity: "#BB6BD9",
  entityOther: "#828282",
};

export const ROLE_UNDERLINE: Record<string, string> = {
  subject: "#2F80ED",
  predicate: "#E0533D",
  object: "#27AE60",
  complement: "#F2994A",
};

export const ENTITY_BORDER = "rgba(130, 130, 130, 0.6)";
export const CLAUSE_TINT = "rgba(155, 81, 224, 0.07)"; // stacks for nested clauses
